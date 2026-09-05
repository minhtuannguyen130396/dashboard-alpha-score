"""Bar-level price action — the shape of one candle, or of two or three in a row.

A candle pattern means nothing on its own. On a Vietnamese daily chart a doji
turns up every other week and a hammer every month; taken as standalone signals
they are close to noise. What they are good for is *timing a decision inside a
structure somebody else already found* — at the right shoulder of a head and
shoulders, on the bar that breaks a neckline, on the retest afterwards.

So this module stays deliberately context-free. It reports shapes, and how
cleanly each one formed, and says nothing about trend, location, or what to do
about it. Deciding whether a shape landed somewhere that matters belongs to the
caller.

One local wrinkle gets its own guard. A stock locked at the ceiling closes on
its high with no upper wick — the exact silhouette of a decisive marubozu, and
the opposite meaning: buyers queued up and never got filled, so the bar records
an absence of trading rather than a battle won. Those sessions are recognised
from ``priceBasic`` and kept out of the shape classifiers entirely.
"""
from dataclasses import asdict, dataclass
from typing import Callable, List, Optional, Sequence, Tuple

from src.analysis.technical_indicators import IndicatorGroup3
from src.data.stock_data_loader import StockRecord

# ── Pattern ids ────────────────────────────────────────────────────────────
DOJI = "doji"
SPINNING_TOP = "spinning_top"
INSIDE_BAR = "inside_bar"
HAMMER = "hammer"
SHOOTING_STAR = "shooting_star"
BULLISH_ENGULFING = "bullish_engulfing"
BEARISH_ENGULFING = "bearish_engulfing"
PIERCING = "piercing"
DARK_CLOUD = "dark_cloud"
MORNING_STAR = "morning_star"
EVENING_STAR = "evening_star"
THREE_WHITE_SOLDIERS = "three_white_soldiers"
THREE_BLACK_CROWS = "three_black_crows"
GAP_UP = "gap_up"
GAP_DOWN = "gap_down"
#: Not shapes — the two sessions where the shape cannot be read at all.
LIMIT_UP = "limit_up"
LIMIT_DOWN = "limit_down"

PATTERN_NAMES = {
    DOJI: "Doji",
    SPINNING_TOP: "Con xoay",
    INSIDE_BAR: "Nến trong",
    HAMMER: "Búa",
    SHOOTING_STAR: "Sao băng",
    BULLISH_ENGULFING: "Nhấn chìm tăng",
    BEARISH_ENGULFING: "Nhấn chìm giảm",
    PIERCING: "Xuyên thấu",
    DARK_CLOUD: "Mây đen che phủ",
    MORNING_STAR: "Sao mai",
    EVENING_STAR: "Sao hôm",
    THREE_WHITE_SOLDIERS: "Ba chàng lính trắng",
    THREE_BLACK_CROWS: "Ba con quạ đen",
    GAP_UP: "Nhảy giá lên",
    GAP_DOWN: "Nhảy giá xuống",
    LIMIT_UP: "Phiên trần",
    LIMIT_DOWN: "Phiên sàn",
}

BULLISH = "bullish"
BEARISH = "bearish"
NEUTRAL = "neutral"

PATTERN_BIAS = {
    DOJI: NEUTRAL,
    SPINNING_TOP: NEUTRAL,
    INSIDE_BAR: NEUTRAL,
    HAMMER: BULLISH,
    SHOOTING_STAR: BEARISH,
    BULLISH_ENGULFING: BULLISH,
    BEARISH_ENGULFING: BEARISH,
    PIERCING: BULLISH,
    DARK_CLOUD: BEARISH,
    MORNING_STAR: BULLISH,
    EVENING_STAR: BEARISH,
    THREE_WHITE_SOLDIERS: BULLISH,
    THREE_BLACK_CROWS: BEARISH,
    GAP_UP: BULLISH,
    GAP_DOWN: BEARISH,
    LIMIT_UP: BULLISH,
    LIMIT_DOWN: BEARISH,
}

# ── Session limit states ───────────────────────────────────────────────────
NORMAL = "normal"
CEILING = "ceiling"                  # closed at the ceiling
FLOOR = "floor"                      # closed at the floor
TOUCHED_CEILING = "touched_ceiling"  # reached it intraday, gave it back
TOUCHED_FLOOR = "touched_floor"

LIMIT_LABELS = {
    NORMAL: "phiên thường",
    CEILING: "đóng cửa giá trần",
    FLOOR: "đóng cửa giá sàn",
    TOUCHED_CEILING: "chạm trần rồi tụt lại",
    TOUCHED_FLOOR: "chạm sàn rồi bật lại",
}

UP = "up"
DOWN = "down"
FLAT = "flat"

#: HOSE bands at ±7%, HNX at ±10%, UPCoM at ±15% — and the exchange is not in
#: the data. So the test stays loose and leans on the close instead.
BAND_PCT = 0.06

#: A gap smaller than this is just the open drifting off yesterday's close.
GAP_ATR = 0.35


@dataclass
class CandleShape:
    """Everything about one bar that a pattern rule might ask about."""
    index: int
    date: str
    open: float
    high: float
    low: float
    close: float
    body: float
    bar_range: float
    upper_wick: float
    lower_wick: float
    body_pct: Optional[float]      # body as a share of the whole range
    close_pos: Optional[float]     # 0 = closed on the low, 1 = closed on the high
    direction: str                 # up | down | flat
    spread_atr: Optional[float]    # range measured in ATR14 — wide bar or narrow
    change_pct: Optional[float]    # close against the reference price
    gap_atr: Optional[float]       # open against yesterday's close, in ATR
    gap_filled: Optional[bool]     # did this bar trade back through the gap
    limit: str                     # normal | ceiling | floor | touched_*

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class CandleSignal:
    kind: str
    name: str
    bias: str                      # bullish | bearish | neutral
    index: int                     # bar the pattern completes on
    date: str
    bars: int                      # how many bars the shape spans
    strength: float                # 0..1 — how cleanly it formed
    spread_atr: Optional[float]
    close_pos: Optional[float]
    label: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def _atr_at(atr: Sequence[Optional[float]], index: int, fallback: float) -> float:
    for i in range(min(index, len(atr) - 1), -1, -1):
        if atr[i] is not None:
            return float(atr[i])
    return fallback


def limit_state(record: StockRecord, band_pct: float = BAND_PCT) -> str:
    """Ceiling / floor session, inferred from the reference price.

    A normal 6.5% day almost never closes exactly on its high; a ceiling day
    always does. That pairing — a big move *and* the close pinned to the
    extreme — separates the two without needing to know which exchange the
    symbol trades on.
    """
    basic = record.priceBasic
    if not basic:
        return NORMAL
    if (record.priceClose / basic - 1.0) >= band_pct and record.priceClose >= record.priceHigh:
        return CEILING
    if (record.priceClose / basic - 1.0) <= -band_pct and record.priceClose <= record.priceLow:
        return FLOOR
    if (record.priceHigh / basic - 1.0) >= band_pct:
        return TOUCHED_CEILING
    if (record.priceLow / basic - 1.0) <= -band_pct:
        return TOUCHED_FLOOR
    return NORMAL


def shapes(
    records: Sequence[StockRecord],
    atr: Optional[Sequence[Optional[float]]] = None,
    band_pct: float = BAND_PCT,
) -> List[CandleShape]:
    """Measure every bar once. Pattern rules read from this, never from records."""
    n = len(records)
    if n == 0:
        return []
    atr_s = list(atr) if atr is not None else IndicatorGroup3.atr(list(records), 14)
    typical = sum(r.priceHigh - r.priceLow for r in records) / n or 1e-9

    out: List[CandleShape] = []
    for i, r in enumerate(records):
        o, h, l, c = r.priceOpen, r.priceHigh, r.priceLow, r.priceClose
        rng = h - l
        body = abs(c - o)
        atr_i = _atr_at(atr_s, i, typical)
        gap = gap_filled = None
        if i > 0 and atr_i:
            prev_close = records[i - 1].priceClose
            gap = round((o - prev_close) / atr_i, 2)
            # A gap that the same session trades back through left no hole.
            gap_filled = (l <= prev_close) if gap > 0 else (h >= prev_close)
        out.append(CandleShape(
            index=i,
            date=r.date.strftime("%Y-%m-%d"),
            open=o, high=h, low=l, close=c,
            body=body,
            bar_range=rng,
            upper_wick=h - max(o, c),
            lower_wick=min(o, c) - l,
            body_pct=(body / rng) if rng > 0 else None,
            close_pos=((c - l) / rng) if rng > 0 else None,
            direction=UP if c > o else (DOWN if c < o else FLAT),
            spread_atr=round(rng / atr_i, 2) if atr_i else None,
            change_pct=round((c / r.priceBasic - 1.0) * 100, 2) if r.priceBasic else None,
            gap_atr=gap,
            gap_filled=gap_filled,
            limit=limit_state(r, band_pct),
        ))
    return out


def _strength(base: float, shape: CandleShape,
              close_toward: Optional[str] = None) -> float:
    """Base confidence, adjusted by how much the bar actually moved.

    The same silhouette drawn on a listless bar and on a wide decisive one is
    worth very different amounts, and the shape rules cannot tell them apart —
    they are all ratios measured inside the bar.
    """
    score = base
    if shape.spread_atr is not None:
        if shape.spread_atr >= 1.5:
            score += 0.20
        elif shape.spread_atr >= 1.0:
            score += 0.10
        elif shape.spread_atr < 0.5:
            score -= 0.15
    if close_toward is not None and shape.close_pos is not None:
        pos = shape.close_pos if close_toward == "high" else 1.0 - shape.close_pos
        if pos >= 0.80:
            score += 0.15
        elif pos <= 0.40:
            score -= 0.10
    return round(max(0.0, min(1.0, score)), 2)


# ── Shape rules ────────────────────────────────────────────────────────────
# Each returns a strength in 0..1, or None when the bar does not qualify.

def _doji(sh: List[CandleShape], i: int) -> Optional[float]:
    s = sh[i]
    if s.body_pct is None:
        return None
    if s.spread_atr is not None and s.spread_atr < 0.3:
        return None                      # a dead bar, not a standoff
    if s.body_pct > 0.10:
        return None
    return _strength(0.45, s)


def _spinning_top(sh: List[CandleShape], i: int) -> Optional[float]:
    s = sh[i]
    if s.body_pct is None or not 0.10 < s.body_pct <= 0.30:
        return None
    if s.spread_atr is not None and s.spread_atr < 0.4:
        return None
    if s.upper_wick < s.body or s.lower_wick < s.body:
        return None
    return _strength(0.40, s)


def _inside_bar(sh: List[CandleShape], i: int) -> Optional[float]:
    if i < 1:
        return None
    s, p = sh[i], sh[i - 1]
    if p.bar_range <= 0 or s.high > p.high or s.low < p.low:
        return None
    # Narrowness is the whole point here, so this one skips the spread penalty.
    squeeze = max(0.0, 1.0 - s.bar_range / p.bar_range)
    return round(min(1.0, 0.35 + 0.35 * squeeze), 2)


def _hammer(sh: List[CandleShape], i: int) -> Optional[float]:
    s = sh[i]
    if s.body_pct is None or s.body_pct > 0.35:
        return None
    if s.spread_atr is not None and s.spread_atr < 0.5:
        return None
    if s.lower_wick < 2 * s.body or s.lower_wick < 0.55 * s.bar_range:
        return None
    if s.upper_wick > s.body and s.upper_wick > 0.15 * s.bar_range:
        return None
    return _strength(0.50, s, close_toward="high")


def _shooting_star(sh: List[CandleShape], i: int) -> Optional[float]:
    s = sh[i]
    if s.body_pct is None or s.body_pct > 0.35:
        return None
    if s.spread_atr is not None and s.spread_atr < 0.5:
        return None
    if s.upper_wick < 2 * s.body or s.upper_wick < 0.55 * s.bar_range:
        return None
    if s.lower_wick > s.body and s.lower_wick > 0.15 * s.bar_range:
        return None
    return _strength(0.50, s, close_toward="low")


def _engulfing(sh: List[CandleShape], i: int, bullish: bool) -> Optional[float]:
    if i < 1:
        return None
    s, p = sh[i], sh[i - 1]
    # Engulfing a doji is not a reversal, it is just a bigger doji day.
    if p.body_pct is None or p.body_pct < 0.15 or s.body <= 0:
        return None
    if bullish:
        if p.direction != DOWN or s.direction != UP:
            return None
        if s.open > p.close or s.close < p.open:
            return None
    else:
        if p.direction != UP or s.direction != DOWN:
            return None
        if s.open < p.close or s.close > p.open:
            return None
    ratio = s.body / p.body if p.body > 0 else 2.0
    if ratio < 1.0:
        return None
    base = 0.50 + min(0.15, 0.05 * (ratio - 1.0))
    return _strength(base, s, close_toward="high" if bullish else "low")


def _piercing(sh: List[CandleShape], i: int, bullish: bool) -> Optional[float]:
    """Close back through the midpoint of the previous body, without engulfing it."""
    if i < 1:
        return None
    s, p = sh[i], sh[i - 1]
    if p.body_pct is None or p.body_pct < 0.30 or p.body <= 0:
        return None
    mid = (p.open + p.close) / 2
    if bullish:
        if p.direction != DOWN or s.direction != UP:
            return None
        if s.open >= p.close or not mid < s.close < p.open:
            return None
        depth = (s.close - p.close) / p.body
    else:
        if p.direction != UP or s.direction != DOWN:
            return None
        if s.open <= p.close or not p.open < s.close < mid:
            return None
        depth = (p.close - s.close) / p.body
    base = 0.45 + min(0.15, 0.30 * (depth - 0.5))
    return _strength(base, s, close_toward="high" if bullish else "low")


def _star(sh: List[CandleShape], i: int, bullish: bool) -> Optional[float]:
    """Big bar, small pause, big bar back the other way.

    The textbook wants the middle bar to gap clear on both sides. VN daily bars
    gap far less often than that rule assumes, so the test here is that the
    pause *reached past* the first bar's close, not that it left a hole.
    """
    if i < 2:
        return None
    a, b, c = sh[i - 2], sh[i - 1], sh[i]
    if a.body_pct is None or a.body_pct < 0.40:
        return None
    if c.body_pct is None or c.body_pct < 0.40:
        return None
    if b.body > 0.40 * a.body:
        return None                      # the middle bar has to be indecisive
    a_mid = (a.open + a.close) / 2
    if bullish:
        if a.direction != DOWN or c.direction != UP:
            return None
        if min(b.open, b.close) > a.close or c.close <= a_mid:
            return None
        recovered = (c.close - a.close) / a.body
    else:
        if a.direction != UP or c.direction != DOWN:
            return None
        if max(b.open, b.close) < a.close or c.close >= a_mid:
            return None
        recovered = (a.close - c.close) / a.body
    base = 0.55 + min(0.15, 0.20 * (recovered - 0.5))
    return _strength(base, c, close_toward="high" if bullish else "low")


def _three_in_a_row(sh: List[CandleShape], i: int, bullish: bool) -> Optional[float]:
    if i < 2:
        return None
    bars = [sh[i - 2], sh[i - 1], sh[i]]
    want = UP if bullish else DOWN
    for s in bars:
        if s.direction != want or s.body_pct is None or s.body_pct < 0.55:
            return None
    for prev, cur in zip(bars, bars[1:]):
        if bullish:
            if cur.close <= prev.close or not prev.open <= cur.open <= prev.close:
                return None
        else:
            if cur.close >= prev.close or not prev.close <= cur.open <= prev.open:
                return None
    # A long wick against the run is the other side pushing back.
    wick = max((s.upper_wick if bullish else s.lower_wick) for s in bars)
    tidy = 1.0 - min(1.0, wick / max(bars[-1].bar_range, 1e-9))
    return _strength(0.50 + 0.15 * tidy, bars[-1],
                     close_toward="high" if bullish else "low")


def _gap(sh: List[CandleShape], i: int, up: bool) -> Optional[float]:
    """An open clear of yesterday's close, still unfilled at the bell.

    A gap that the session itself closes is not a gap — price simply opened
    away and came back. What matters is the hole that survives the day, because
    that is the range where nobody traded and where price tends to react later.
    """
    s = sh[i]
    if s.gap_atr is None or s.gap_filled:
        return None
    if (s.gap_atr < GAP_ATR) if up else (s.gap_atr > -GAP_ATR):
        return None
    size = min(1.0, abs(s.gap_atr) / 1.5)
    return _strength(0.40 + 0.25 * size, s, close_toward="high" if up else "low")


#: (id, bars consumed, rule). Order only breaks ties — output is sorted by strength.
_DETECTORS: List[Tuple[str, int, Callable[[List[CandleShape], int], Optional[float]]]] = [
    (BEARISH_ENGULFING, 2, lambda sh, i: _engulfing(sh, i, False)),
    (BULLISH_ENGULFING, 2, lambda sh, i: _engulfing(sh, i, True)),
    (EVENING_STAR, 3, lambda sh, i: _star(sh, i, False)),
    (MORNING_STAR, 3, lambda sh, i: _star(sh, i, True)),
    (THREE_BLACK_CROWS, 3, lambda sh, i: _three_in_a_row(sh, i, False)),
    (THREE_WHITE_SOLDIERS, 3, lambda sh, i: _three_in_a_row(sh, i, True)),
    (DARK_CLOUD, 2, lambda sh, i: _piercing(sh, i, False)),
    (PIERCING, 2, lambda sh, i: _piercing(sh, i, True)),
    (SHOOTING_STAR, 1, _shooting_star),
    (HAMMER, 1, _hammer),
    (SPINNING_TOP, 1, _spinning_top),
    (DOJI, 1, _doji),
    (INSIDE_BAR, 2, _inside_bar),
    (GAP_UP, 2, lambda sh, i: _gap(sh, i, True)),
    (GAP_DOWN, 2, lambda sh, i: _gap(sh, i, False)),
]

#: A bar that closed at its limit is unreadable as a shape. One that merely
#: touched the limit still is — and "chạm trần rồi tụt" is worth seeing.
_UNREADABLE = (CEILING, FLOOR)


def _signal(kind: str, shape: CandleShape, bars: int, strength: float) -> CandleSignal:
    sig = CandleSignal(
        kind=kind,
        name=PATTERN_NAMES[kind],
        bias=PATTERN_BIAS[kind],
        index=shape.index,
        date=shape.date,
        bars=bars,
        strength=strength,
        spread_atr=shape.spread_atr,
        close_pos=round(shape.close_pos, 2) if shape.close_pos is not None else None,
    )
    sig.label = describe(sig, shape)
    return sig


def detect(
    records: Sequence[StockRecord],
    index: int = -1,
    atr: Optional[Sequence[Optional[float]]] = None,
    measured: Optional[List[CandleShape]] = None,
) -> List[CandleSignal]:
    """Every shape completing on one bar, strongest first.

    More than one can fire — a dragonfly doji is also a hammer — and both are
    reported rather than one being picked arbitrarily.
    """
    sh = measured if measured is not None else shapes(records, atr)
    n = len(sh)
    if n == 0:
        return []
    i = index if index >= 0 else n + index
    if not 0 <= i < n:
        return []

    if sh[i].limit in _UNREADABLE:
        kind = LIMIT_UP if sh[i].limit == CEILING else LIMIT_DOWN
        return [_signal(kind, sh[i], 1, 1.0)]
    if sh[i].bar_range <= 0:
        # A bar that never moved has no silhouette to read. Left unguarded it
        # scores as the tightest inside bar on the chart, which is backwards:
        # that is an absence of trading, not a coiled spring.
        return []

    out: List[CandleSignal] = []
    for kind, span, rule in _DETECTORS:
        start = i - span + 1
        if start < 0:
            continue
        if any(sh[j].limit in _UNREADABLE for j in range(start, i + 1)):
            continue
        strength = rule(sh, i)
        if strength is None:
            continue
        out.append(_signal(kind, sh[i], span, strength))
    out.sort(key=lambda s: -s.strength)
    return out


def scan(
    records: Sequence[StockRecord],
    start: int = 0,
    end: Optional[int] = None,
    atr: Optional[Sequence[Optional[float]]] = None,
    min_strength: float = 0.0,
    measured: Optional[List[CandleShape]] = None,
) -> List[CandleSignal]:
    """Every shape over a slice of the series, oldest bar first.

    ``start`` and ``end`` are inclusive bar indices — the caller passes the
    window a structure says is interesting, not the whole chart. A caller
    scanning several windows should measure once and pass ``measured`` in.
    """
    sh = measured if measured is not None else shapes(records, atr)
    if not sh:
        return []
    last = len(sh) - 1
    lo = max(0, start if start >= 0 else len(sh) + start)
    hi = last if end is None else min(last, end if end >= 0 else len(sh) + end)

    out: List[CandleSignal] = []
    for i in range(lo, hi + 1):
        out += [s for s in detect(records, i, measured=sh)
                if s.strength >= min_strength]
    return out


_MEANINGS = {
    DOJI: "mở và đóng gần bằng nhau — hai bên cân sức, đà hiện tại đang chững",
    SPINNING_TOP: "thân nhỏ, râu cả hai phía — giằng co, chưa bên nào giành được phiên",
    INSIDE_BAR: "biên độ nằm gọn trong phiên trước — thị trường nén lại, chờ phá ra một phía",
    HAMMER: "bị bán xuống sâu trong phiên rồi kéo về đóng ở trên — có lực đỡ tại đáy nến",
    SHOOTING_STAR: "được kéo lên cao rồi bị đánh tụt về đóng ở dưới — có lực bán tại đỉnh nến",
    BULLISH_ENGULFING: "thân nến tăng trùm hết thân nến giảm hôm trước — bên mua giành lại quyền chủ động",
    BEARISH_ENGULFING: "thân nến giảm trùm hết thân nến tăng hôm trước — bên bán giành lại quyền chủ động",
    PIERCING: "mở thấp hơn rồi đóng vượt quá nửa thân nến giảm hôm trước — lực mua phản công",
    DARK_CLOUD: "mở cao hơn rồi đóng thủng quá nửa thân nến tăng hôm trước — lực bán phản công",
    MORNING_STAR: "nến giảm mạnh, một phiên do dự, rồi nến tăng lấy lại quá nửa — đáy tạm hình thành",
    EVENING_STAR: "nến tăng mạnh, một phiên do dự, rồi nến giảm trả lại quá nửa — đỉnh tạm hình thành",
    THREE_WHITE_SOLDIERS: "ba phiên tăng thân dài liên tiếp, mỗi phiên đóng cao hơn — cầu vào đều tay",
    THREE_BLACK_CROWS: "ba phiên giảm thân dài liên tiếp, mỗi phiên đóng thấp hơn — cung ra đều tay",
    GAP_UP: "mở cửa nhảy hẳn trên đóng cửa hôm trước và không lấp lại trong phiên — để lại vùng trống phía dưới, thường được test lại",
    GAP_DOWN: "mở cửa nhảy hẳn dưới đóng cửa hôm trước và không lấp lại trong phiên — để lại vùng trống phía trên, thường được test lại",
    LIMIT_UP: "đóng cửa giá trần — dư mua chất đống, không đọc được hình nến",
    LIMIT_DOWN: "đóng cửa giá sàn — dư bán chất đống, không đọc được hình nến",
}


def describe(signal: CandleSignal, shape: Optional[CandleShape] = None) -> str:
    """One sentence: what formed, how wide the bar was, what the shape says."""
    meaning = _MEANINGS.get(signal.kind, "")
    parts = [f"**{signal.name}**"]
    if signal.kind not in (LIMIT_UP, LIMIT_DOWN):
        if signal.spread_atr is not None:
            parts.append(f"biên độ {signal.spread_atr:g}× ATR")
        if signal.close_pos is not None:
            parts.append(f"đóng ở {signal.close_pos * 100:.0f}% biên độ nến")
    if shape is not None and shape.limit in (TOUCHED_CEILING, TOUCHED_FLOOR):
        parts.append(LIMIT_LABELS[shape.limit])
    head = " · ".join(parts)
    return f"{head} — {meaning}." if meaning else f"{head}."
