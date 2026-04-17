"""Flow concentration / "load-up day" primitive (bucket=trigger).

A single bar that grabs an outsized share of the long-window flow with the
*right* price + volume context is a strong proxy for institutional entry
(positive) or exit (negative).
"""
from typing import List

from src.analysis.smart_money.config import SmartMoneyConfig
from src.analysis.smart_money.normalize import clamp, safe_ratio
from src.analysis.smart_money.primitives.base import _deal_value
from src.analysis.smart_money.types import FlowPrimitive


class ConcentrationPrimitive:
    name = "concentration"
    bucket = "trigger"

    def min_records(self) -> int:
        return 10

    def compute(self, records: List, cfg: SmartMoneyConfig) -> FlowPrimitive:
        n = min(cfg.long_window, len(records))
        if n < self.min_records():
            return FlowPrimitive(
                name=self.name, bucket="trigger",
                value=0.0, confidence=0.0,
                components={}, reasons=["insufficient bars"],
            )

        window = records[-n:]

        def _flow(r) -> float:
            prop = float(getattr(r, "propTradingNetValue", 0.0) or 0.0)
            buy = float(getattr(r, "buyForeignValue", 0.0) or 0.0)
            sell = float(getattr(r, "sellForeignValue", 0.0) or 0.0)
            return prop + (buy - sell)

        flows = [_flow(r) for r in window]
        today_flow = flows[-1]
        total_abs = sum(abs(f) for f in flows)
        if total_abs <= 0:
            return FlowPrimitive(
                name=self.name, bucket="trigger",
                value=0.0, confidence=0.0,
                components={"today_flow": today_flow},
                reasons=["no flow"],
            )

        concentration_ratio = abs(today_flow) / total_abs

        # Volume context — RVOL today vs window mean
        deal_values = [_deal_value(r) for r in window]
        window_mean_dv = (
            sum(deal_values[:-1]) / max(1, len(deal_values) - 1) if len(deal_values) > 1 else 0.0
        )
        today_dv = deal_values[-1]
        rvol = safe_ratio(today_dv, window_mean_dv, fallback=0.0)

        today = window[-1]
        is_green = today.priceClose > today.priceOpen
        is_red = today.priceClose < today.priceOpen

        is_load_up = (
            concentration_ratio >= 0.25 and today_flow > 0 and is_green and rvol >= 1.3
        )
        is_load_down = (
            concentration_ratio >= 0.25 and today_flow < 0 and is_red and rvol >= 1.3
        )

        sign = 0.0
        if is_load_up:
            sign = 1.0
        elif is_load_down:
            sign = -1.0
        else:
            # Soft signal proportional to concentration when context is partial
            if today_flow > 0 and is_green:
                sign = 0.5
            elif today_flow < 0 and is_red:
                sign = -0.5

        value = clamp(sign * concentration_ratio * 2.0, -1.0, 1.0)
        confidence = min(1.0, concentration_ratio * 2.0)

        reasons: List[str] = []
        if is_load_up:
            reasons.append(f"load-up day {concentration_ratio*100:.0f}% conc, RVOL {rvol:.2f}")
        elif is_load_down:
            reasons.append(f"load-down day {concentration_ratio*100:.0f}% conc, RVOL {rvol:.2f}")

        return FlowPrimitive(
            name=self.name,
            bucket="trigger",
            value=value,
            confidence=confidence,
            components={
                "concentration_ratio": concentration_ratio,
                "today_flow": today_flow,
                "rvol": rvol,
                "is_load_up": float(is_load_up),
                "is_load_down": float(is_load_down),
            },
            reasons=reasons,
        )
