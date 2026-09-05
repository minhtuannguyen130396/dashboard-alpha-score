"""Reversal formations — the shapes made by a *sequence* of swing pivots.

Triangles and channels come out of two trendlines, and ``patterns.py`` already
reads those. Double tops and head-and-shoulders are a different family: what
defines them is the order and the relative heights of three to five pivots, and
a neckline drawn through the troughs between them. Nothing about slope.

The pivots are already computed — ``pivots.find_pivots`` hands back exactly the
alternating high/low sequence these rules need, and until now only
``trendlines.py`` consumed it.

This family is the easiest in all of technical analysis to hallucinate: look
back far enough and every chart has a head and shoulders somewhere. Three
constraints do the work of keeping it honest:

* a prior move to reverse — a top formation inside a downtrend is meaningless
* proportion, measured in ATR rather than percent, so the same rule holds for
  a 12k penny stock and a 130k blue chip
* a *close* through the neckline to confirm, never an intraday wick

Volume is recorded but never used to reject: the classic signature (the second
top trading lighter than the first) is evidence, and the caller decides what it
is worth.
"""
from dataclasses import asdict, dataclass, field
from typing import List, Optional, Sequence, Tuple

import pandas as pd

from src.analysis.technical_indicators import IndicatorGroup3
from src.data.stock_data_loader import StockRecord
from src.ta.pivots import HIGH, LOW, Pivot, find_pivots
from src.ta.retest import Retest, find_retest

DOUBLE_TOP = "double_top"
DOUBLE_BOTTOM = "double_bottom"
TRIPLE_TOP = "triple_top"
TRIPLE_BOTTOM = "triple_bottom"
HEAD_SHOULDERS = "head_shoulders"
INVERSE_HEAD_SHOULDERS = "inverse_head_shoulders"

FORMATION_NAMES = {
    DOUBLE_TOP: "Hai đỉnh",
    DOUBLE_BOTTOM: "Hai đáy",
    TRIPLE_TOP: "Ba đỉnh",
    TRIPLE_BOTTOM: "Ba đáy",
    HEAD_SHOULDERS: "Vai đầu vai",
    INVERSE_HEAD_SHOULDERS: "Vai đầu vai ngược",
}

BEARISH = "bearish"
BULLISH = "bullish"

FORMATION_BIAS = {
    DOUBLE_TOP: BEARISH,
    DOUBLE_BOTTOM: BULLISH,
    TRIPLE_TOP: BEARISH,
    TRIPLE_BOTTOM: BULLISH,
    HEAD_SHOULDERS: BEARISH,
    INVERSE_HEAD_SHOULDERS: BULLISH,
}

#: Names for the defining pivots, in order, per formation.
PIVOT_ROLES = {
    DOUBLE_TOP: ["đỉnh 1", "đáy giữa", "đỉnh 2"],
    DOUBLE_BOTTOM: ["đáy 1", "đỉnh giữa", "đáy 2"],
    TRIPLE_TOP: ["đỉnh 1", "đáy 1", "đỉnh 2", "đáy 2", "đỉnh 3"],
    TRIPLE_BOTTOM: ["đáy 1", "đỉnh 1", "đáy 2", "đỉnh 2", "đáy 3"],
    HEAD_SHOULDERS: ["vai trái", "đáy trái", "đầu", "đáy phải", "vai phải"],
    INVERSE_HEAD_SHOULDERS: ["vai trái", "đỉnh trái", "đầu", "đỉnh phải", "vai phải"],
}

FORMING = "forming"
CONFIRMED = "confirmed"
FAILED = "failed"

STATE_LABELS = {
    FORMING: "đang hình thành, chưa phá neckline",
    CONFIRMED: "đã phá neckline",
    FAILED: "mô hình hỏng",
}

#: A break older than this stops being news.
_STALE_BREAK_BARS = 25

#: How far past the last pivot a sloping neckline still describes something.
#: Without this a mild tilt extrapolates into nonsense — a 0.2/bar slope run
#: out 120 bars puts the neckline of a 78-point stock at 48.
_MAX_PROJECTION = 30


@dataclass
class Formation:
    kind: str
    name: str
    bias: str                        # bearish | bullish
    state: str                       # forming | confirmed | failed
    pivots: List[Pivot]
    start_index: int
    start_date: str
    end_index: int                   # last defining pivot
    end_date: str
    bars: int
    peak: float                      # the head, or the higher/lower of the tops
    neckline_now: float              # neckline value at the last bar
    neckline_slope: float            # price per bar; 0 for a flat neckline
    height: float                    # peak to neckline, measured at the peak
    target: Optional[float]
    invalidation: float
    fit_atr: float                   # how far apart the matching pivots sat, in ATR
    shoulder_volume_ratio: Optional[float]   # right vs left (or top 2 vs top 1)
    break_index: Optional[int] = None
    break_date: Optional[str] = None
    break_close: Optional[float] = None
    break_volume_x: Optional[float] = None
    bars_since_break: Optional[int] = None
    resolved_index: Optional[int] = None     # bar the formation stopped forming
    resolved_date: Optional[str] = None
    retest: Optional[Retest] = None
    target_hit: bool = False
    score: float = 0.0
    id: str = ""
    label: str = ""

    def neckline_at(self, index: int) -> float:
        base = self.pivots[1]
        # Past the horizon the line holds flat rather than running away — the
        # same thing a person drawing it on paper would do.
        capped = min(index, self.end_index + _MAX_PROJECTION)
        return base.price + self.neckline_slope * (capped - base.index)

    def to_dict(self) -> dict:
        data = asdict(self)
        data["pivots"] = [p.to_dict() for p in self.pivots]
        data["roles"] = PIVOT_ROLES.get(self.kind, [])
        return data


def _atr_at(atr: Sequence[Optional[float]], index: int, fallback: float) -> float:
    for i in range(min(index, len(atr) - 1), -1, -1):
        if atr[i] is not None:
            return float(atr[i])
    return fallback


def _pivot_volume(records: Sequence[StockRecord], index: int, window: int = 2) -> float:
    """Average traded volume around a pivot.

    A pivot is one bar, and one bar's volume is noisy — what the classic rule
    is really describing is how heavily the market traded *at* that turn.
    """
    lo = max(0, index - window)
    hi = min(len(records) - 1, index + window)
    span = records[lo:hi + 1]
    return sum(r.priceImpactVolume for r in span) / len(span) if span else 0.0


def _prior_move(records: Sequence[StockRecord], first: Pivot, bars: int,
                bearish: bool) -> float:
    """How far price travelled into the formation — the thing it would reverse."""
    lo = max(0, first.index - bars)
    window = records[lo:first.index + 1]
    if not window:
        return 0.0
    if bearish:
        return first.price - min(r.priceLow for r in window)
    return max(r.priceHigh for r in window) - first.price


def _neckline_slope(a: Pivot, b: Pivot) -> float:
    return (b.price - a.price) / (b.index - a.index) if b.index != a.index else 0.0


def _resolve(
    records: Sequence[StockRecord],
    formation: Formation,
    atr_s: Sequence[Optional[float]],
    typical: float,
    vol_ema: Sequence[float],
    confirm_atr: float,
) -> None:
    """Walk forward from the last pivot and settle the formation's state.

    Order matters here. Price running back past the extreme kills the shape
    before any neckline break can rescue it, which is why invalidation is
    checked on every bar rather than only at the end.
    """
    n = len(records)
    bearish = formation.bias == BEARISH

    for i in range(formation.end_index + 1, n):
        close = records[i].priceClose
        # The shape is gone once price retakes the level that defined it.
        if (bearish and close > formation.invalidation) or \
           (not bearish and close < formation.invalidation):
            formation.state = FAILED
            formation.resolved_index = i
            formation.resolved_date = records[i].date.strftime("%Y-%m-%d")
            return

        level = formation.neckline_at(i)
        margin = confirm_atr * _atr_at(atr_s, i, typical)
        broke = (close < level - margin) if bearish else (close > level + margin)
        if not broke:
            continue

        base = vol_ema[i] or 1e-9
        formation.state = CONFIRMED
        formation.resolved_index = i
        formation.resolved_date = records[i].date.strftime("%Y-%m-%d")
        formation.break_index = i
        formation.break_date = records[i].date.strftime("%Y-%m-%d")
        formation.break_close = round(close, 2)
        formation.break_volume_x = round(records[i].priceImpactVolume / base, 2)
        formation.bars_since_break = n - 1 - i
        formation.target = round(level - formation.height if bearish
                                 else level + formation.height, 2)
        formation.retest = find_retest(
            records, i, formation.neckline_at,
            "down" if bearish else "up",
            _atr_at(atr_s, i, typical),
        )
        after = records[i:]
        formation.target_hit = any(
            (r.priceLow <= formation.target) if bearish else
            (r.priceHigh >= formation.target) for r in after
        )
        # A break that was handed straight back is not a break.
        last_close = records[-1].priceClose
        last_level = formation.neckline_at(n - 1)
        if (bearish and last_close > last_level) or \
           (not bearish and last_close < last_level):
            formation.state = FAILED
        return


def _candidate(
    records: Sequence[StockRecord],
    group: List[Pivot],
    kind: str,
    atr_s: Sequence[Optional[float]],
    typical: float,
    vol_ema: Sequence[float],
    tol_atr: float,
    min_depth_atr: float,
    trend_atr: float,
    confirm_atr: float,
    min_bars: int,
    max_age: int,
    max_tilt: float,
) -> Optional[Formation]:
    n = len(records)
    bearish = FORMATION_BIAS[kind] == BEARISH
    first, last = group[0], group[-1]
    span = last.index - first.index + 1
    if span < min_bars:
        return None
    if n - 1 - last.index > max_age:
        return None                  # finished too long ago to be news

    atr_ref = _atr_at(atr_s, last.index, typical)
    tol = tol_atr * atr_ref
    depth = min_depth_atr * atr_ref

    extremes = [p for p in group if p.kind == (HIGH if bearish else LOW)]
    troughs = [p for p in group if p.kind == (LOW if bearish else HIGH)]
    if len(troughs) < 1:
        return None

    if kind in (HEAD_SHOULDERS, INVERSE_HEAD_SHOULDERS):
        left, head, right = extremes
        # The head has to stand clear of both shoulders, not merely tie them.
        if bearish:
            if head.price < left.price + tol or head.price < right.price + tol:
                return None
        else:
            if head.price > left.price - tol or head.price > right.price - tol:
                return None
        if abs(left.price - right.price) > tol:
            return None
        shoulder = min(left.price, right.price) if bearish else max(left.price, right.price)
        for t in troughs:
            if bearish and t.price >= shoulder:
                return None
            if not bearish and t.price <= shoulder:
                return None
        fit = abs(left.price - right.price) / atr_ref
        peak_pivot = head
        # Losing the right shoulder already breaks the structure — waiting for
        # price to retake the head would call the failure far too late.
        invalidation = right.price
    else:
        prices = [p.price for p in extremes]
        if max(prices) - min(prices) > tol:
            return None
        peak_pivot = max(extremes, key=lambda p: p.price) if bearish else \
            min(extremes, key=lambda p: p.price)
        # The trough between them has to be a real retreat, not a pause.
        for t in troughs:
            gap = (min(prices) - t.price) if bearish else (t.price - max(prices))
            if gap < depth:
                return None
        fit = (max(prices) - min(prices)) / atr_ref
        invalidation = peak_pivot.price
    peak = peak_pivot.price

    if _prior_move(records, first, span, bearish) < trend_atr * atr_ref:
        return None                  # nothing to reverse

    slope = _neckline_slope(troughs[0], troughs[-1]) if len(troughs) > 1 else 0.0
    formation = Formation(
        kind=kind,
        name=FORMATION_NAMES[kind],
        bias=BEARISH if bearish else BULLISH,
        state=FORMING,
        pivots=list(group),
        start_index=first.index,
        start_date=first.date,
        end_index=last.index,
        end_date=last.date,
        bars=span,
        peak=round(peak, 2),
        neckline_now=0.0,
        neckline_slope=slope,
        height=0.0,
        target=None,
        invalidation=round(invalidation, 2),
        fit_atr=round(fit, 2),
        shoulder_volume_ratio=None,
    )
    # ``neckline_at`` reads pivots[1], which is the first trough in every layout.
    formation.height = round(abs(peak - formation.neckline_at(peak_pivot.index)), 2)
    if formation.height < depth:
        return None                  # too shallow to be worth a name
    # A steeply tilted neckline means the troughs are collapsing, which is a
    # downtrend rather than the flat base these formations are built on. The
    # tilt is judged against the formation's own height so the test holds at
    # any price level.
    travel = abs(formation.neckline_at(last.index) - formation.neckline_at(first.index))
    if travel > max_tilt * formation.height:
        return None
    formation.neckline_now = round(formation.neckline_at(n - 1), 2)

    left_vol = _pivot_volume(records, extremes[0].index)
    right_vol = _pivot_volume(records, extremes[-1].index)
    formation.shoulder_volume_ratio = round(right_vol / left_vol, 2) if left_vol else None

    _resolve(records, formation, atr_s, typical, vol_ema, confirm_atr)
    if formation.bars_since_break is not None and \
            formation.bars_since_break > _STALE_BREAK_BARS:
        return None

    formation.score = _score(formation, n)
    formation.label = describe_formation(formation)
    return formation


def _score(f: Formation, bars: int) -> float:
    """Recency first, then how cleanly the matching pivots lined up."""
    recency = max(0.0, 1.0 - (bars - 1 - f.end_index) / 60.0)
    tightness = max(0.0, 1.0 - f.fit_atr)
    size = min(1.0, f.bars / 60.0)
    score = 4.0 * recency + 3.0 * tightness + 1.5 * size
    if f.state == CONFIRMED:
        score += 2.0
    elif f.state == FAILED:
        score -= 3.0
    return round(score, 3)


#: (id, pivot count, kind of the first pivot)
_LAYOUTS: List[Tuple[str, int, str]] = [
    (HEAD_SHOULDERS, 5, HIGH),
    (INVERSE_HEAD_SHOULDERS, 5, LOW),
    (TRIPLE_TOP, 5, HIGH),
    (TRIPLE_BOTTOM, 5, LOW),
    (DOUBLE_TOP, 3, HIGH),
    (DOUBLE_BOTTOM, 3, LOW),
]


def find_formations(
    records: Sequence[StockRecord],
    pivots: Optional[Sequence[Pivot]] = None,
    atr: Optional[Sequence[Optional[float]]] = None,
    tol_atr: float = 1.0,
    min_depth_atr: float = 1.5,
    trend_atr: float = 2.0,
    confirm_atr: float = 0.25,
    min_bars: int = 15,
    max_age: int = 90,
    max_tilt: float = 0.5,
    limit: int = 3,
) -> List[Formation]:
    """Reversal formations visible in the pivot sequence, best first.

    A five-pivot window that qualifies as a head and shoulders also contains a
    double top, so the layouts are tried longest-first and a window that
    matches is not offered to the shorter rules.
    """
    n = len(records)
    if n < min_bars:
        return []
    atr_s = list(atr) if atr is not None else IndicatorGroup3.atr(list(records), 14)
    typical = sum(r.priceHigh - r.priceLow for r in records) / n or 1e-9
    pv = list(pivots) if pivots is not None else find_pivots(list(records), atr=atr_s)
    if len(pv) < 3:
        return []

    volumes = [r.priceImpactVolume for r in records]
    vol_ema = pd.Series(volumes).ewm(span=20, adjust=False).mean().tolist()

    found: List[Formation] = []
    claimed: List[Tuple[int, int]] = []
    for kind, size, head_kind in _LAYOUTS:
        for start in range(len(pv) - size, -1, -1):
            group = pv[start:start + size]
            if group[0].kind != head_kind:
                continue
            window = (group[0].index, group[-1].index)
            if any(window[0] <= c[1] and c[0] <= window[1] for c in claimed):
                continue
            formation = _candidate(
                records, group, kind, atr_s, typical, vol_ema,
                tol_atr, min_depth_atr, trend_atr, confirm_atr, min_bars, max_age,
                max_tilt,
            )
            if formation is None:
                continue
            found.append(formation)
            claimed.append(window)

    found.sort(key=lambda f: -f.score)
    return found[:limit]


def describe_formation(f: Formation) -> str:
    roles = PIVOT_ROLES.get(f.kind, [])
    marks = " · ".join(
        f"{role.capitalize()} {p.price:.2f}" for role, p in zip(roles, f.pivots)
        if "đáy giữa" not in role and "đỉnh giữa" not in role
    )
    tilt = ""
    if abs(f.neckline_slope) > 1e-9:
        tilt = " (nghiêng lên)" if f.neckline_slope > 0 else " (nghiêng xuống)"
    head = (f"**{f.name}** ({f.start_date} → {f.end_date}, {f.bars} phiên) — "
            f"{STATE_LABELS[f.state]}")
    body = f"{marks} · Neckline {f.neckline_now}{tilt}"

    if f.state == FORMING:
        side = "dưới" if f.bias == BEARISH else "trên"
        return (f"{head}. {body}. Đóng cửa {side} {f.neckline_now} là xác nhận; "
                f"mô hình huỷ nếu đóng cửa {'trên' if f.bias == BEARISH else 'dưới'} "
                f"{f.invalidation}.")
    if f.state == CONFIRMED:
        vol = (f"volume {f.break_volume_x:g}× trung bình 20 phiên"
               if f.break_volume_x is not None else "")
        reached = " — đã chạm mục tiêu" if f.target_hit else ""
        return (f"{head} ngày {f.break_date} ({f.bars_since_break} phiên trước), {vol}. "
                f"{body}. Mục tiêu đo được {f.target}{reached}, "
                f"phủ định nếu đóng cửa "
                f"{'trên' if f.bias == BEARISH else 'dưới'} {f.invalidation}.")
    if f.break_index is not None:
        side = "trên" if f.bias == BEARISH else "dưới"
        return (f"{head}. {body}. Đã thủng neckline ngày {f.break_date} rồi đóng cửa "
                f"lại {side} — phá vỡ giả, không còn hiệu lực.")
    return (f"{head}. {body}. Giá quay lại quá {f.invalidation} trước khi kịp phá "
            f"neckline — cấu trúc bị xoá.")
