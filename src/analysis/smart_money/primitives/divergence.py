"""Daily price ↔ smart money flow divergence primitive (bucket=trigger).

Bullish divergence: price prints a lower low while cumulative
``prop + foreign`` flow prints a higher low — institutions are quietly
accumulating into retail capitulation.

Bearish divergence: price prints a higher high while cumulative flow prints
a lower high — institutions are distributing into a retail rally.
"""
from typing import List

from src.analysis.smart_money.config import SmartMoneyConfig
from src.analysis.smart_money.normalize import clamp, safe_ratio
from src.analysis.smart_money.primitives.base import _deal_value
from src.analysis.smart_money.types import FlowPrimitive


def _argmin(seq: List[float]) -> int:
    best = 0
    for i, v in enumerate(seq):
        if v < seq[best]:
            best = i
    return best


def _argmax(seq: List[float]) -> int:
    best = 0
    for i, v in enumerate(seq):
        if v > seq[best]:
            best = i
    return best


class DivergencePrimitive:
    name = "divergence"
    bucket = "trigger"

    MIN_PIVOT_GAP = 8     # bars between the two pivots — avoids false positives

    def min_records(self) -> int:
        return self.MIN_PIVOT_GAP * 2 + 2

    def compute(self, records: List, cfg: SmartMoneyConfig) -> FlowPrimitive:
        n = min(cfg.long_window, len(records))
        if n < self.min_records():
            return FlowPrimitive(
                name=self.name, bucket="trigger",
                value=0.0, confidence=0.0,
                components={}, reasons=["insufficient bars"],
            )

        window = records[-n:]
        closes = [float(r.priceClose) for r in window]

        def _flow(r) -> float:
            prop = float(getattr(r, "propTradingNetValue", 0.0) or 0.0)
            buy = float(getattr(r, "buyForeignValue", 0.0) or 0.0)
            sell = float(getattr(r, "sellForeignValue", 0.0) or 0.0)
            return prop + (buy - sell)

        flows = [_flow(r) for r in window]
        # Cumulative smart money flow series
        cum = []
        running = 0.0
        for f in flows:
            running += f
            cum.append(running)

        traded_values = [_deal_value(r) for r in window if _deal_value(r) > 0]
        avg_traded = sum(traded_values) / len(traded_values) if traded_values else 0.0
        if avg_traded <= 0:
            return FlowPrimitive(
                name=self.name, bucket="trigger",
                value=0.0, confidence=0.0,
                components={}, reasons=["no traded baseline"],
            )

        # Two halves: prior pivot in [0..n-MIN_PIVOT_GAP], recent pivot in last MIN_PIVOT_GAP
        split = n - self.MIN_PIVOT_GAP
        prior_closes = closes[:split]
        recent_closes = closes[split:]
        prior_cum = cum[:split]
        recent_cum = cum[split:]

        # Bullish divergence
        bull_value = 0.0
        bull_reason = ""
        i_prior_low = _argmin(prior_closes)
        i_recent_low_off = _argmin(recent_closes)
        price_prior_low = prior_closes[i_prior_low]
        price_recent_low = recent_closes[i_recent_low_off]
        cum_prior_low = prior_cum[i_prior_low]
        cum_recent_low = recent_cum[i_recent_low_off]
        if price_recent_low < price_prior_low:
            price_delta = safe_ratio(price_recent_low - price_prior_low, price_prior_low)
            flow_delta_norm = safe_ratio(cum_recent_low - cum_prior_low, avg_traded)
            # Bullish when flow_delta - price_delta is positive (flow holds while price drops)
            bull_value = clamp(flow_delta_norm - price_delta, -1.0, 1.0)
            if bull_value > 0:
                bull_reason = "bullish div: price LL, flow HL"

        # Bearish divergence
        bear_value = 0.0
        bear_reason = ""
        i_prior_high = _argmax(prior_closes)
        i_recent_high_off = _argmax(recent_closes)
        price_prior_high = prior_closes[i_prior_high]
        price_recent_high = recent_closes[i_recent_high_off]
        cum_prior_high = prior_cum[i_prior_high]
        cum_recent_high = recent_cum[i_recent_high_off]
        if price_recent_high > price_prior_high:
            price_delta = safe_ratio(price_recent_high - price_prior_high, price_prior_high)
            flow_delta_norm = safe_ratio(cum_recent_high - cum_prior_high, avg_traded)
            # Bearish when flow trails price (flow_delta < price_delta) → negative value
            bear_value = clamp(flow_delta_norm - price_delta, -1.0, 1.0)
            if bear_value < 0:
                bear_reason = "bearish div: price HH, flow LH"

        # Pick the dominant divergence by magnitude
        if abs(bull_value) >= abs(bear_value):
            value = bull_value
            reason = bull_reason
        else:
            value = bear_value
            reason = bear_reason

        # Confidence: requires (a) clear pivots, (b) enough range, (c) flow data present
        price_range = max(closes) - min(closes)
        range_conf = clamp(safe_ratio(price_range, max(closes) * 0.02), 0.0, 1.0)
        flow_active = sum(1 for f in flows if f != 0.0) / len(flows)
        confidence = min(1.0, range_conf * flow_active)

        return FlowPrimitive(
            name=self.name,
            bucket="trigger",
            value=value,
            confidence=confidence,
            components={
                "bull_value": bull_value,
                "bear_value": bear_value,
                "price_range": price_range,
                "avg_traded": avg_traded,
            },
            reasons=[reason] if reason else [],
        )
