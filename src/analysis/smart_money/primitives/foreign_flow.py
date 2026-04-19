"""Foreign (khối ngoại) flow primitive.

Uses buyForeignValue - sellForeignValue as the raw flow so mid-cap and
large-cap names are directly comparable. Confidence reflects the share of
bars in which foreigners actually traded.
"""
from typing import List

from src.analysis.smart_money.config import SmartMoneyConfig
from src.analysis.smart_money.normalize import clamp, safe_ratio, tanh_scale
from src.analysis.smart_money.primitives.base import _deal_value
from src.analysis.smart_money.types import FlowPrimitive


class ForeignFlowPrimitive:
    name = "foreign"
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
            buy = getattr(r, "buyForeignValue", 0.0) or 0.0
            sell = getattr(r, "sellForeignValue", 0.0) or 0.0
            return float(buy) - float(sell)

        def _gross(r) -> float:
            buy = getattr(r, "buyForeignValue", 0.0) or 0.0
            sell = getattr(r, "sellForeignValue", 0.0) or 0.0
            return float(buy) + float(sell)

        long_window = records[-long_n:]
        short_window = records[-short_n:]
        net_long = [_net(r) for r in long_window]

        short_sum = sum(_net(r) for r in short_window)
        long_sum = sum(net_long)
        today = _net(records[-1])

        traded_values = [_deal_value(r) for r in long_window]
        traded_values = [v for v in traded_values if v > 0]
        avg_traded = (sum(traded_values) / len(traded_values)) if traded_values else 0.0

        if avg_traded <= 0:
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

        value = clamp(
            0.5 * tanh_scale(short_ratio, 20.0)
            + 0.3 * tanh_scale(long_ratio, 20.0)
            + 0.2 * tanh_scale(today_ratio, 20.0)
        )

        # Confidence: fraction of bars with foreigners actually trading
        active = sum(1 for r in long_window if _gross(r) > 0)
        confidence = active / long_n if long_n > 0 else 0.0

        # TODO(phase-2): shrink confidence when stock is at full foreign room
        foreign_room_confidence_factor = 1.0
        confidence *= foreign_room_confidence_factor

        reasons: List[str] = []
        if confidence == 0.0:
            reasons.append("no foreign trading")
        else:
            if short_sum > 0:
                reasons.append(f"NN net buy {short_sum/1e9:.1f}B/{short_n}d")
            elif short_sum < 0:
                reasons.append(f"NN net sell {short_sum/1e9:.1f}B/{short_n}d")

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
