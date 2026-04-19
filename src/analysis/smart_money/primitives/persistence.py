"""Persistence detector — multiplier (NOT a bucket primitive).

Returns a ``PersistenceSignal`` (own dataclass), never a ``FlowPrimitive``,
so the composite cannot accidentally aggregate it into a bucket.

Used by composite to scale ``setup_confidence``: stable flow → keep
confidence, noisy flow → halve it. See phase_2 §2.3 for the rationale.
"""
from dataclasses import dataclass, field
from typing import Dict, List

from src.analysis.smart_money.config import SmartMoneyConfig


@dataclass
class PersistenceSignal:
    value: float                              # [-1..+1]
    confidence: float                         # [0..1]
    components: Dict[str, float] = field(default_factory=dict)


class PersistenceDetector:
    name = "persistence"

    def min_records(self) -> int:
        return 10

    def compute(self, records: List, cfg: SmartMoneyConfig) -> PersistenceSignal:
        n = min(cfg.long_window, len(records))
        if n < self.min_records():
            return PersistenceSignal(value=0.0, confidence=0.0)

        window = records[-n:]

        def _flow(r) -> float:
            prop = float(getattr(r, "propTradingNetValue", 0.0) or 0.0)
            buy = float(getattr(r, "buyForeignValue", 0.0) or 0.0)
            sell = float(getattr(r, "sellForeignValue", 0.0) or 0.0)
            return prop + (buy - sell)

        flows = [_flow(r) for r in window]
        positive_days = sum(1 for x in flows if x > 0)
        negative_days = sum(1 for x in flows if x < 0)
        active_days = positive_days + negative_days

        if active_days == 0:
            return PersistenceSignal(
                value=0.0, confidence=0.0,
                components={"active_days": 0},
            )

        net_days = positive_days - negative_days
        value = net_days / n
        confidence = active_days / n

        return PersistenceSignal(
            value=value,
            confidence=confidence,
            components={
                "positive_days": float(positive_days),
                "negative_days": float(negative_days),
                "active_days": float(active_days),
            },
        )
