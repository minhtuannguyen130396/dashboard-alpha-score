"""Horizontal levels — the prices the market keeps coming back to.

``trendlines.py`` draws sloping lines through pairs of pivots. That misses the
most common thing a chart actually has: a flat price that has been rejected
four times over six months by pivots that never lined up on any one line. Those
prices are found by clustering, not by fitting.

Two independent sources feed the same list:

* **swing clusters** — pivots that sit at the same price within an ATR tolerance
* **volume by price** — where the shares actually changed hands, which is where
  positions are trapped and where reactions come from

The volume profile is built by spreading each session's volume evenly across
the bars it traded through, rather than dumping it all on the close. A wide bar
distributes its volume over the whole range it covered, which is the honest
reading — nobody knows where inside the day the trades happened, and pretending
they all happened at one price invents structure that is not there.

Unfilled gaps are levels too, and they arrive already computed on
``CandleShape``, so they join the list rather than getting their own module.
"""
from dataclasses import asdict, dataclass, field
from typing import List, Optional, Sequence, Tuple

from src.analysis.technical_indicators import IndicatorGroup3
from src.data.stock_data_loader import StockRecord
from src.ta import candles
from src.ta.pivots import HIGH, Pivot, find_pivots

RESISTANCE = "resistance"
SUPPORT = "support"
AT_PRICE = "at_price"

KIND_LABELS = {
    RESISTANCE: "kháng cự",
    SUPPORT: "hỗ trợ",
    AT_PRICE: "giá đang nằm trong vùng",
}

SWING = "swing"
VOLUME = "volume"
GAP = "gap"

SOURCE_LABELS = {
    SWING: "đỉnh/đáy cũ",
    VOLUME: "vùng volume lớn",
    GAP: "khoảng trống giá chưa lấp",
}

#: How far apart two pivots may sit and still be the same level.
CLUSTER_ATR = 0.6
#: A bar counts as testing a level if it came this close.
TOUCH_ATR = 0.4
#: Bins used for the volume-by-price histogram.
PROFILE_BINS = 60
#: Share of total volume that defines the value area.
VALUE_AREA = 0.70


@dataclass
class Level:
    price: float                     # the zone's centre
    low: float
    high: float
    kind: str                        # resistance | support | at_price
    source: str                      # swing | volume | gap
    touches: int
    last_touch_index: int
    last_touch_date: str
    volume_share: float              # share of all traded volume inside the zone
    distance_pct: float              # close against the level
    score: float
    id: str = ""
    label: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class VolumeProfile:
    low: float
    high: float
    step: float
    volumes: List[float] = field(default_factory=list)
    poc: float = 0.0                 # the single busiest price
    value_low: float = 0.0
    value_high: float = 0.0

    def bin_of(self, price: float) -> int:
        if self.step <= 0:
            return 0
        return max(0, min(len(self.volumes) - 1, int((price - self.low) / self.step)))

    def share_between(self, low: float, high: float) -> float:
        total = sum(self.volumes) or 1e-9
        lo, hi = self.bin_of(low), self.bin_of(high)
        return sum(self.volumes[lo:hi + 1]) / total

    def to_dict(self) -> dict:
        return asdict(self)


def build_profile(records: Sequence[StockRecord],
                  bins: int = PROFILE_BINS) -> Optional[VolumeProfile]:
    """Volume by price, each session spread across the range it traded."""
    if not records:
        return None
    low = min(r.priceLow for r in records)
    high = max(r.priceHigh for r in records)
    if high <= low:
        return None
    step = (high - low) / bins
    buckets = [0.0] * bins

    for r in records:
        lo = max(0, min(bins - 1, int((r.priceLow - low) / step)))
        hi = max(0, min(bins - 1, int((r.priceHigh - low) / step)))
        span = hi - lo + 1
        share = r.priceImpactVolume / span
        for b in range(lo, hi + 1):
            buckets[b] += share

    poc_bin = max(range(bins), key=lambda b: buckets[b])
    total = sum(buckets) or 1e-9
    # Grow outward from the busiest price until 70% of the volume is inside.
    lo = hi = poc_bin
    covered = buckets[poc_bin]
    while covered / total < VALUE_AREA and (lo > 0 or hi < bins - 1):
        below = buckets[lo - 1] if lo > 0 else -1.0
        above = buckets[hi + 1] if hi < bins - 1 else -1.0
        if above >= below:
            hi += 1
            covered += buckets[hi]
        else:
            lo -= 1
            covered += buckets[lo]

    return VolumeProfile(
        low=round(low, 2), high=round(high, 2), step=step, volumes=buckets,
        poc=round(low + (poc_bin + 0.5) * step, 2),
        value_low=round(low + lo * step, 2),
        value_high=round(low + (hi + 1) * step, 2),
    )


def _atr_at(atr: Sequence[Optional[float]], index: int, fallback: float) -> float:
    for i in range(min(index, len(atr) - 1), -1, -1):
        if atr[i] is not None:
            return float(atr[i])
    return fallback


def _cluster(pivots: Sequence[Pivot], tol: float) -> List[List[Pivot]]:
    """Group pivots sitting at the same price, cheapest possible linkage."""
    if not pivots:
        return []
    ordered = sorted(pivots, key=lambda p: p.price)
    groups: List[List[Pivot]] = [[ordered[0]]]
    for pivot in ordered[1:]:
        centre = sum(p.price for p in groups[-1]) / len(groups[-1])
        if abs(pivot.price - centre) <= tol:
            groups[-1].append(pivot)
        else:
            groups.append([pivot])
    return groups


def _count_touches(records: Sequence[StockRecord], low: float, high: float,
                   tol: float) -> Tuple[int, int]:
    """``(touches, last index)`` — consecutive bars in the zone count once."""
    touches = 0
    last = -1
    inside = False
    for i, r in enumerate(records):
        near = r.priceHigh >= low - tol and r.priceLow <= high + tol
        if near:
            last = i
            if not inside:
                touches += 1
        inside = near
    return touches, last


def find_levels(
    records: Sequence[StockRecord],
    pivots: Optional[Sequence[Pivot]] = None,
    atr: Optional[Sequence[Optional[float]]] = None,
    cluster_atr: float = CLUSTER_ATR,
    touch_atr: float = TOUCH_ATR,
    min_touches: int = 2,
    max_distance_pct: float = 20.0,
    limit: int = 5,
) -> Tuple[List[Level], Optional[VolumeProfile]]:
    """Horizontal levels near the current price, best first, plus the profile."""
    n = len(records)
    if n < 20:
        return [], None
    atr_s = list(atr) if atr is not None else IndicatorGroup3.atr(list(records), 14)
    typical = sum(r.priceHigh - r.priceLow for r in records) / n or 1e-9
    atr_now = _atr_at(atr_s, n - 1, typical)
    pv = list(pivots) if pivots is not None else find_pivots(list(records), atr=atr_s)
    profile = build_profile(records)
    close = records[-1].priceClose

    found: List[Level] = []
    seen: List[float] = []

    def _add(price: float, low: float, high: float, source: str,
             touches: int, last: int, bonus: float = 0.0) -> None:
        if any(abs(price - other) <= cluster_atr * atr_now for other in seen):
            return
        distance = (close / price - 1) * 100 if price else 0.0
        if abs(distance) > max_distance_pct:
            return
        share = profile.share_between(low, high) if profile else 0.0
        if close > high:
            kind = SUPPORT
        elif close < low:
            kind = RESISTANCE
        else:
            kind = AT_PRICE
        recency = 1.0 - (n - 1 - last) / max(n - 1, 1)
        proximity = 1.0 - min(abs(distance) / max_distance_pct, 1.0)
        score = (2.0 * min(touches, 6) / 6.0 + 2.0 * recency + 3.0 * proximity
                 + 4.0 * share + bonus)
        level = Level(
            price=round(price, 2), low=round(low, 2), high=round(high, 2),
            kind=kind, source=source, touches=touches,
            last_touch_index=last,
            last_touch_date=records[last].date.strftime("%Y-%m-%d") if last >= 0 else "-",
            volume_share=round(share * 100, 1),
            distance_pct=round(distance, 2),
            score=round(score, 3),
        )
        level.label = describe_level(level)
        found.append(level)
        seen.append(price)

    tol = touch_atr * atr_now
    for group in _cluster(pv, cluster_atr * atr_now):
        if len(group) < min_touches:
            continue
        prices = [p.price for p in group]
        low, high = min(prices), max(prices)
        touches, last = _count_touches(records, low, high, tol)
        if touches < min_touches:
            continue
        _add(sum(prices) / len(prices), low, high, SWING, touches, last)

    if profile is not None:
        touches, last = _count_touches(records, profile.poc, profile.poc, tol)
        _add(profile.poc, profile.poc - tol, profile.poc + tol, VOLUME,
             touches, last, bonus=1.0)

    # Unfilled gaps: the range nobody traded through is the range price reacts to.
    shapes = candles.shapes(records, atr_s)
    for i in range(n - 1, max(0, n - 120), -1):
        sh = shapes[i]
        if sh.gap_atr is None or sh.gap_filled or abs(sh.gap_atr) < candles.GAP_ATR:
            continue
        prev_close = records[i - 1].priceClose
        low, high = sorted((prev_close, sh.open))
        # A gap is filled once price returns to the far edge of the hole —
        # the previous close. Demanding that one bar span the whole gap lets
        # a zone stay "unfilled" after price has nibbled through it from
        # both sides over a fortnight.
        later = records[i + 1:]
        if sh.gap_atr > 0:
            if any(r.priceLow <= prev_close for r in later):
                continue
        elif any(r.priceHigh >= prev_close for r in later):
            continue
        touches, last = _count_touches(records, low, high, tol)
        _add((low + high) / 2, low, high, GAP, max(touches, 1), max(last, i))

    found.sort(key=lambda level: -level.score)
    kept = found[:limit]
    # A list that is all resistance tells the reader nothing about where the
    # floor is. If both sides exist, make sure both are represented.
    for side in (RESISTANCE, SUPPORT):
        if any(l.kind == side for l in kept):
            continue
        best = next((l for l in found if l.kind == side), None)
        if best is not None and kept:
            kept[-1] = best
            kept.sort(key=lambda level: -level.score)
    for i, level in enumerate(kept, 1):
        level.id = f"L{i}"
        level.label = describe_level(level)
    return kept, profile


def describe_level(level: Level) -> str:
    role = KIND_LABELS.get(level.kind, level.kind)
    source = SOURCE_LABELS.get(level.source, level.source)
    band = (f"{level.low}–{level.high}" if level.high > level.low
            else f"{level.price}")
    head = f"{level.id} ".lstrip() if level.id else ""
    return (f"{head}Vùng {band} — {role} ({source}), chạm {level.touches} lần, "
            f"gần nhất {level.last_touch_date}, "
            f"{level.volume_share:g}% volume giao dịch nằm trong vùng, "
            f"giá cách {level.distance_pct:+.1f}%.")
