"""Fit the lines a chartist would draw through swing highs and swing lows.

Every pair of same-side pivots defines a candidate line. A candidate survives
only if price never cut through it between its two anchors; survivors are then
scored on whether the line is still *live* — recent, close to current price,
touched repeatedly while it held. A line that was broken two months ago is
history, not a level, and is dropped outright.
"""
from dataclasses import asdict, dataclass, field
from typing import List, Optional, Sequence

from src.analysis.technical_indicators import IndicatorGroup3
from src.data.stock_data_loader import StockRecord
from src.ta.pivots import HIGH, LOW, Pivot, find_pivots
from src.ta.retest import Retest, find_retest

RESISTANCE = "resistance"
SUPPORT = "support"

#: A line is only useful near the current price; beyond this it is noise.
_MAX_DISTANCE_PCT = 15.0
#: A break older than this many bars means the line stopped mattering.
_STALE_BREAK_BARS = 25
#: Anchors closer together than this describe a wiggle, not a trend.
_MIN_SPAN_BARS = 10


@dataclass
class TrendLine:
    kind: str                       # RESISTANCE | SUPPORT
    p1_index: int
    p1_date: str
    p1_price: float
    p2_index: int
    p2_date: str
    p2_price: float
    slope: float                    # price change per bar
    intercept: float                # value at bar index 0
    touches: int                    # bars that tested the line while it held
    span: int
    score: float
    value_now: float                # projected value at the last bar
    distance_pct: float             # close vs the line, in percent
    slope_pct_per_bar: float        # slope normalised by the anchor price
    broken: bool = False
    break_index: Optional[int] = None
    break_date: Optional[str] = None
    bars_since_break: Optional[int] = None
    retest: Optional[Retest] = None
    label: str = ""
    touch_dates: List[str] = field(default_factory=list)
    id: str = ""                    # "#2" — handle for asking about this line

    @property
    def name(self) -> str:
        side = "Nối đỉnh" if self.kind == RESISTANCE else "Nối đáy"
        return f"{side} {self.id}".strip()

    def value_at(self, index: int) -> float:
        return self.intercept + self.slope * index

    def to_dict(self) -> dict:
        return asdict(self)


def _atr_at(atr: Sequence[Optional[float]], index: int, fallback: float) -> float:
    for i in range(min(index, len(atr) - 1), -1, -1):
        if atr[i] is not None:
            return float(atr[i])
    return fallback


def _candidate(
    records: List[StockRecord],
    p1: Pivot,
    p2: Pivot,
    kind: str,
    atr_s: Sequence[Optional[float]],
    typical: float,
    tol_atr: float,
    break_atr: float,
) -> Optional[TrendLine]:
    span = p2.index - p1.index
    if span < _MIN_SPAN_BARS:
        return None
    slope = (p2.price - p1.price) / span
    intercept = p1.price - slope * p1.index
    n = len(records)

    def line(i: int) -> float:
        return intercept + slope * i

    # 1) Between the anchors the line must hold — no bar may cut through it.
    for i in range(p1.index, p2.index + 1):
        tol = tol_atr * _atr_at(atr_s, i, typical)
        if kind == RESISTANCE:
            if records[i].priceHigh > line(i) + tol:
                return None
        elif records[i].priceLow < line(i) - tol:
            return None

    # 2) Walk forward to the first genuine break; the line is only meaningful
    #    up to that point, so touches are counted over the same stretch.
    broken = False
    break_index: Optional[int] = None
    for i in range(p2.index + 1, n):
        atr_i = _atr_at(atr_s, i, typical)
        close = records[i].priceClose
        level = line(i)
        cut = (close > level + break_atr * atr_i) if kind == RESISTANCE else (
            close < level - break_atr * atr_i)
        if cut:
            broken, break_index = True, i
            break

    live_end = break_index if broken else n - 1
    bars_since_break = (n - 1 - break_index) if break_index is not None else None
    if broken and bars_since_break > _STALE_BREAK_BARS:
        return None                     # long dead, not a level anyone watches

    touches = 0
    touch_dates: List[str] = []
    touching = False
    for i in range(p1.index, live_end + 1):
        tol = tol_atr * _atr_at(atr_s, i, typical)
        probe = records[i].priceHigh if kind == RESISTANCE else records[i].priceLow
        near = abs(probe - line(i)) <= tol
        if near and not touching:
            touches += 1
            touch_dates.append(records[i].date.strftime("%Y-%m-%d"))
        touching = near
    if touches < 2:
        return None

    close = records[-1].priceClose
    value_now = line(n - 1)
    if value_now <= 0:
        return None
    distance_pct = (close / value_now - 1) * 100
    if abs(distance_pct) > _MAX_DISTANCE_PCT:
        return None                     # too far from price to trade against

    # Scoring: proximity and recency matter more than raw touch count.
    touch_score = min(touches, 5) / 5.0
    recency = 1.0 - (n - 1 - live_end) / max(n - 1, 1)
    span_score = min(span / 60.0, 1.0)
    proximity = 1.0 - min(abs(distance_pct) / _MAX_DISTANCE_PCT, 1.0)
    score = 3.0 * touch_score + 3.0 * recency + 2.0 * span_score + 5.0 * proximity
    if broken:
        # A fresh break is the signal itself; an older one just weakens the line.
        score -= 1.0 if bars_since_break <= 5 else 2.5

    anchor = p1.price or 1.0
    out = TrendLine(
        kind=kind,
        p1_index=p1.index, p1_date=p1.date, p1_price=round(p1.price, 2),
        p2_index=p2.index, p2_date=p2.date, p2_price=round(p2.price, 2),
        slope=round(slope, 6), intercept=round(intercept, 6),
        touches=touches, span=span, score=round(score, 3),
        value_now=round(value_now, 2),
        distance_pct=round(distance_pct, 2),
        slope_pct_per_bar=round(slope / anchor * 100, 4),
        broken=broken,
        break_index=break_index,
        break_date=records[break_index].date.strftime("%Y-%m-%d") if break_index else None,
        bars_since_break=bars_since_break,
        touch_dates=touch_dates,
    )
    if broken and break_index is not None:
        # A broken resistance that price came back to and could not reclaim has
        # switched sides — that is the level worth quoting, not the break bar.
        out.retest = find_retest(
            records, break_index, out.value_at,
            "up" if kind == RESISTANCE else "down",
            _atr_at(atr_s, break_index, typical),
        )
    return out


def _dedupe(lines: List[TrendLine], price: float, tol_pct: float = 2.0) -> List[TrendLine]:
    """Drop lines sitting on top of a better one already kept."""
    kept: List[TrendLine] = []
    for line in lines:
        if any(
            abs(line.value_now - other.value_now) / max(price, 1e-9) * 100 < tol_pct
            and abs(line.slope_pct_per_bar - other.slope_pct_per_bar) < 0.08
            for other in kept
        ):
            continue
        kept.append(line)
    return kept


def find_trendlines(
    records: List[StockRecord],
    pivots: Optional[Sequence[Pivot]] = None,
    kinds: Sequence[str] = (RESISTANCE, SUPPORT),
    top_n: int = 2,
    tol_atr: float = 0.25,
    break_atr: float = 0.3,
    atr: Optional[Sequence[Optional[float]]] = None,
) -> List[TrendLine]:
    """Best ``top_n`` live lines per side, highest score first."""
    n = len(records)
    if n < 20:
        return []
    atr_s = list(atr) if atr is not None else IndicatorGroup3.atr(records, 14)
    typical = sum(r.priceHigh - r.priceLow for r in records) / n or 1e-9
    pv = list(pivots) if pivots is not None else find_pivots(records, atr=atr_s)
    close = records[-1].priceClose

    out: List[TrendLine] = []
    for kind in kinds:
        side = [p for p in pv if p.kind == (HIGH if kind == RESISTANCE else LOW)]
        found = [
            line
            for a in range(len(side) - 1)
            for b in range(a + 1, len(side))
            if (line := _candidate(records, side[a], side[b], kind,
                                   atr_s, typical, tol_atr, break_atr)) is not None
        ]
        found.sort(key=lambda l: -l.score)
        out.extend(_dedupe(found, close)[:top_n])

    for line in out:
        line.label = describe_trendline(line)
    return out


def describe_trendline(line: TrendLine) -> str:
    side = "Kháng cự" if line.kind == RESISTANCE else "Hỗ trợ"
    tilt = ("dốc lên" if line.slope_pct_per_bar > 0.02
            else "dốc xuống" if line.slope_pct_per_bar < -0.02 else "nằm ngang")
    text = (f"{side} chéo {tilt} nối {line.p1_date} ({line.p1_price}) → "
            f"{line.p2_date} ({line.p2_price}), chạm {line.touches} lần, "
            f"hiện ở {line.value_now}")
    if line.broken:
        action = "vượt lên" if line.kind == RESISTANCE else "thủng xuống"
        meaning = ("tín hiệu mua" if line.kind == RESISTANCE else "tín hiệu bán")
        text += (f" — đã bị {action} ngày {line.break_date} "
                 f"({line.bars_since_break} phiên trước, {meaning})")
    else:
        text += f", giá cách {line.distance_pct:+.1f}%"
    return text
