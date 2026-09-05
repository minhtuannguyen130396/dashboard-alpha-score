"""Swing pivot detection - the foundation for trendlines, boxes and patterns.

Raw fractals are noisy: on a VN daily chart a 3-bar fractal fires every few
sessions. So candidates are filtered twice - they must alternate high/low, and
each leg must be worth at least a fraction of ATR. What comes out is a ZigZag:
the handful of turning points a person would actually draw a line through.
"""
from dataclasses import asdict, dataclass
from typing import List, Optional, Sequence

from src.analysis.technical_indicators import IndicatorGroup3
from src.data.stock_data_loader import StockRecord

HIGH = "high"
LOW = "low"


@dataclass
class Pivot:
    index: int
    date: str
    price: float
    kind: str            # HIGH | LOW

    def to_dict(self) -> dict:
        return asdict(self)


def _atr_at(atr: Sequence[Optional[float]], index: int, fallback: float) -> float:
    """ATR at a bar, falling back to the nearest earlier value."""
    for i in range(min(index, len(atr) - 1), -1, -1):
        if atr[i] is not None:
            return float(atr[i])
    return fallback


def find_pivots(
    records: List[StockRecord],
    fractal: int = 3,
    min_swing_atr: float = 0.8,
    atr: Optional[Sequence[Optional[float]]] = None,
) -> List[Pivot]:
    """Alternating swing highs and lows, oldest first.

    ``fractal`` is the number of bars that must sit lower (higher) on each
    side. ``min_swing_atr`` drops any leg smaller than that many ATRs.
    """
    n = len(records)
    if n < 2 * fractal + 1:
        return []

    atr_s = list(atr) if atr is not None else IndicatorGroup3.atr(records, 14)
    typical_range = sum(r.priceHigh - r.priceLow for r in records) / n or 1e-9

    highs = [r.priceHigh for r in records]
    lows = [r.priceLow for r in records]

    candidates: List[Pivot] = []
    for i in range(fractal, n - fractal):
        window = slice(i - fractal, i + fractal + 1)
        if highs[i] == max(highs[window]):
            candidates.append(Pivot(i, records[i].date.strftime("%Y-%m-%d"), highs[i], HIGH))
        if lows[i] == min(lows[window]):
            candidates.append(Pivot(i, records[i].date.strftime("%Y-%m-%d"), lows[i], LOW))
    candidates.sort(key=lambda p: p.index)

    # Enforce alternation, keeping the most extreme pivot of each run, and drop
    # legs too small to matter.
    confirmed: List[Pivot] = []
    for pivot in candidates:
        if not confirmed:
            confirmed.append(pivot)
            continue
        last = confirmed[-1]
        if pivot.kind == last.kind:
            better = (pivot.price > last.price) if pivot.kind == HIGH else (pivot.price < last.price)
            if better:
                confirmed[-1] = pivot
            continue
        threshold = min_swing_atr * _atr_at(atr_s, pivot.index, typical_range)
        if abs(pivot.price - last.price) < threshold:
            # Too shallow to be a real turn — let the previous pivot absorb it.
            continue
        confirmed.append(pivot)

    return confirmed


def split_pivots(pivots: Sequence[Pivot]):
    """``(highs, lows)`` as separate lists."""
    return ([p for p in pivots if p.kind == HIGH],
            [p for p in pivots if p.kind == LOW])


def last_pivot(pivots: Sequence[Pivot], kind: str) -> Optional[Pivot]:
    for pivot in reversed(pivots):
        if pivot.kind == kind:
            return pivot
    return None
