"""Protocol that every flow primitive must satisfy."""
from typing import List, Protocol

from src.analysis.smart_money.config import SmartMoneyConfig
from src.analysis.smart_money.types import Bucket, FlowPrimitive


class Primitive(Protocol):
    name: str
    bucket: Bucket

    def compute(
        self, records: List, cfg: SmartMoneyConfig
    ) -> FlowPrimitive: ...

    def min_records(self) -> int: ...


def _deal_value(r) -> float:
    """Traded value excluding putthrough (price-impact value).

    The smart money docs talk about ``priceImpactValue``; StockRecord doesn't
    expose that directly, but ``totalValue - putthroughValue`` is the exact
    analogue of ``priceImpactVolume = dealVolume`` already used elsewhere.
    """
    total = float(getattr(r, "totalValue", 0.0) or 0.0)
    pt = float(getattr(r, "putthroughValue", 0.0) or 0.0)
    dv = total - pt
    if dv > 0:
        return dv
    # Fallback: priceAverage * dealVolume when totalValue is missing
    pa = float(getattr(r, "priceAverage", 0.0) or 0.0)
    dvol = float(getattr(r, "dealVolume", 0.0) or 0.0)
    return max(0.0, pa * dvol)
