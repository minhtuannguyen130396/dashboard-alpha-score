"""Toxic flow detector — hard blocker, NOT a scoring component.

Detects "retail FOMO + smart money exit" cases where price has rallied
but cumulative prop + foreign flow is strongly net negative. The detector
sets ``signal.is_toxic = True``; bucket composites are *not* modified, so
turning the blocker off in scoring leaves the underlying values intact.
"""
from typing import List

from src.analysis.smart_money.config import SmartMoneyConfig
from src.analysis.smart_money.normalize import safe_ratio
from src.analysis.smart_money.primitives.base import _deal_value


class ToxicFlowDetector:
    name = "toxic_flow"

    def detect(self, records: List, cfg: SmartMoneyConfig) -> bool:
        if len(records) < 6:
            return False
        window = records[-cfg.long_window:] if len(records) >= cfg.long_window else records

        close_now = float(records[-1].priceClose)
        close_then = float(records[-6].priceClose)
        if close_then <= 0:
            return False

        price_change_5d = (close_now - close_then) / close_then

        recent5 = records[-5:]

        def _flow(r) -> float:
            prop = float(getattr(r, "propTradingNetValue", 0.0) or 0.0)
            buy = float(getattr(r, "buyForeignValue", 0.0) or 0.0)
            sell = float(getattr(r, "sellForeignValue", 0.0) or 0.0)
            return prop + (buy - sell)

        smart_money_5d = sum(_flow(r) for r in recent5)

        traded = [_deal_value(r) for r in window if _deal_value(r) > 0]
        avg_traded = sum(traded) / len(traded) if traded else 0.0
        if avg_traded <= 0:
            return False
        sm_normalized = safe_ratio(smart_money_5d, avg_traded * 5)

        # Bullish toxic = price rally + smart money distribution
        return (
            price_change_5d > cfg.toxic_price_change_threshold
            and sm_normalized < cfg.toxic_flow_opposite_threshold
        )
