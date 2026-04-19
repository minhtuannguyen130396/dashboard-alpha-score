"""Prop trading (tự doanh) flow primitive.

Inherits the intent of ``signal_scoring_v4._score_prop_trading_v4`` but fixes
the normalization bug where thinly-traded prop flows produce inflated scores:
we normalize against the stock's own average traded value, not against the
average absolute prop flow.
"""
from typing import List

from src.analysis.smart_money.config import SmartMoneyConfig
from src.analysis.smart_money.normalize import clamp, safe_ratio, tanh_scale
from src.analysis.smart_money.primitives.base import _deal_value
from src.analysis.smart_money.types import FlowPrimitive


class PropFlowPrimitive:
    name = "prop"
    bucket = "setup"

    def min_records(self) -> int:
        return 10

    def compute(self, records: List, cfg: SmartMoneyConfig) -> FlowPrimitive:
        short_n = min(cfg.short_window, len(records))
        long_n = min(cfg.long_window, len(records))
        if short_n <= 0 or long_n <= 0:
            return FlowPrimitive(
                name=self.name, bucket="setup",
                value=0.0, confidence=0.0,
                components={}, reasons=["insufficient data"],
            )

        def _net(r) -> float:
            v = getattr(r, "propTradingNetValue", None)
            return float(v) if v is not None else 0.0

        long_window = records[-long_n:]
        short_window = records[-short_n:]
        prop_net_long = [_net(r) for r in long_window]

        short_sum = sum(_net(r) for r in short_window)
        long_sum = sum(prop_net_long)
        today = _net(records[-1])

        # Normalize against the stock's own average traded value
        traded_values = [_deal_value(r) for r in long_window]
        traded_values = [v for v in traded_values if v > 0]
        avg_traded = (sum(traded_values) / len(traded_values)) if traded_values else 0.0

        if avg_traded <= 0:
            # No reliable baseline — confidence 0
            return FlowPrimitive(
                name=self.name, bucket="setup",
                value=0.0, confidence=0.0,
                components={
                    "short_sum": short_sum,
                    "long_sum": long_sum,
                    "today": today,
                },
                reasons=["no traded-value baseline"],
            )

        short_ratio = safe_ratio(short_sum, avg_traded * short_n)
        long_ratio = safe_ratio(long_sum, avg_traded * long_n)
        today_ratio = safe_ratio(today, avg_traded)

        # tanh keeps extreme single-day prints from dominating
        value = clamp(
            0.5 * tanh_scale(short_ratio, 20.0)
            + 0.3 * tanh_scale(long_ratio, 20.0)
            + 0.2 * tanh_scale(today_ratio, 20.0)
        )

        # Confidence = fraction of long-window bars that carried prop data
        has_data = sum(1 for v in prop_net_long if v != 0.0)
        confidence = has_data / long_n if long_n > 0 else 0.0

        reasons: List[str] = []
        if confidence == 0.0:
            reasons.append("no prop data")
        else:
            if short_sum > 0:
                reasons.append(f"prop net buy {short_sum/1e9:.1f}B/{short_n}d")
            elif short_sum < 0:
                reasons.append(f"prop net sell {short_sum/1e9:.1f}B/{short_n}d")
            if abs(today_ratio) >= 0.01:
                reasons.append(f"today {today_ratio*100:+.2f}% of avg traded")

        return FlowPrimitive(
            name=self.name,
            bucket="setup",
            value=value,
            confidence=confidence,
            components={
                "short_sum": short_sum,
                "long_sum": long_sum,
                "today": today,
                "short_ratio": short_ratio,
                "long_ratio": long_ratio,
                "today_ratio": today_ratio,
                "avg_traded": avg_traded,
            },
            reasons=reasons,
        )
