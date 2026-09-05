"""Market structure — the trend as the price series itself reports it.

Everywhere else in this engine the trend comes from moving averages: price
above EMA20 above EMA50 is "tăng". That is a smoothed opinion about the trend,
not the trend. The price series states its own case in plainer terms — each
swing high either clears the last one or fails to, each swing low either holds
above the last one or gives way — and the sequence of those four verdicts is
what a trader means by "cấu trúc".

Two events matter inside that sequence, and they are not the same thing:

* **BOS** (phá vỡ cấu trúc) — the trend does again what it was already doing:
  a close above the last swing high while already rising. Continuation.
* **CHoCH** (đổi tính chất) — the first crack: in an uptrend, a close *below*
  the most recent higher low. Nothing has reversed yet, but the pattern that
  defined the uptrend has been broken once.

Levels are consumed when they break, so one swing high fires one BOS and not a
signal on every bar that stays above it. And a pivot only becomes usable
``confirm_lag`` bars after it forms, because that is when a fractal pivot is
actually knowable — reading it any earlier is look-ahead bias dressed up as a
backtest.
"""
from dataclasses import asdict, dataclass, field
from typing import List, Optional, Sequence

from src.analysis.technical_indicators import IndicatorGroup3
from src.data.stock_data_loader import StockRecord
from src.ta.pivots import HIGH, LOW, Pivot, find_pivots

HH = "higher_high"
LH = "lower_high"
HL = "higher_low"
LL = "lower_low"
#: Two swings at the same level are neither higher nor lower. Without this
#: a flat range reads as LH + LL — a downtrend — which is exactly backwards.
EQH = "equal_high"
EQL = "equal_low"

SWING_NAMES = {
    HH: "đỉnh cao hơn",
    LH: "đỉnh thấp hơn",
    HL: "đáy cao hơn",
    LL: "đáy thấp hơn",
    EQH: "đỉnh ngang",
    EQL: "đáy ngang",
}

SWING_SHORT = {HH: "HH", LH: "LH", HL: "HL", LL: "LL", EQH: "EQH", EQL: "EQL"}

#: How close two swings must be, in ATR, before they count as level.
EQUAL_ATR = 0.25

UPTREND = "uptrend"
DOWNTREND = "downtrend"
RANGE = "range"

TREND_NAMES = {
    UPTREND: "Xu hướng tăng theo cấu trúc",
    DOWNTREND: "Xu hướng giảm theo cấu trúc",
    RANGE: "Chưa có cấu trúc rõ ràng",
}

BOS = "bos"
CHOCH = "choch"

EVENT_NAMES = {
    BOS: "phá vỡ cấu trúc",
    CHOCH: "đổi tính chất",
}


@dataclass
class SwingLabel:
    index: int
    date: str
    price: float
    kind: str              # HIGH | LOW
    label: str             # HH | LH | HL | LL
    short: str             # the two-letter form used on charts
    versus: float          # the previous same-side pivot it was measured against

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class StructureEvent:
    kind: str              # bos | choch
    direction: str         # up | down
    index: int
    date: str
    level: float           # the swing level that gave way
    close: float
    label: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class MarketStructure:
    trend: str
    swings: List[SwingLabel] = field(default_factory=list)
    events: List[StructureEvent] = field(default_factory=list)
    last_high: Optional[float] = None      # the live swing high overhead
    last_low: Optional[float] = None       # the live swing low underneath
    bars_since_event: Optional[int] = None
    label: str = ""

    @property
    def last_event(self) -> Optional[StructureEvent]:
        return self.events[-1] if self.events else None

    def to_dict(self) -> dict:
        return {
            "trend": self.trend,
            "trend_name": TREND_NAMES.get(self.trend, self.trend),
            "swings": [s.to_dict() for s in self.swings],
            "events": [e.to_dict() for e in self.events],
            "last_high": self.last_high,
            "last_low": self.last_low,
            "bars_since_event": self.bars_since_event,
            "label": self.label,
        }


def _atr_at(atr: Sequence[Optional[float]], index: int) -> float:
    for i in range(min(index, len(atr) - 1), -1, -1):
        if atr[i] is not None:
            return float(atr[i])
    return 0.0


def label_swings(
    pivots: Sequence[Pivot],
    atr: Optional[Sequence[Optional[float]]] = None,
    tol_atr: float = EQUAL_ATR,
) -> List[SwingLabel]:
    """Name each pivot against the previous pivot on the same side.

    ``atr`` supplies the "close enough to be level" tolerance. Without it
    only exact ties read as equal, which is fine for constructed series and
    too strict for real prices.
    """
    out: List[SwingLabel] = []
    prev_high: Optional[Pivot] = None
    prev_low: Optional[Pivot] = None
    for p in pivots:
        tol = tol_atr * _atr_at(atr, p.index) if atr is not None else 0.0
        if p.kind == HIGH:
            if prev_high is None:
                prev_high = p
                continue
            gap = p.price - prev_high.price
            label = EQH if abs(gap) <= tol else (HH if gap > 0 else LH)
            versus = prev_high.price
            prev_high = p
        else:
            if prev_low is None:
                prev_low = p
                continue
            gap = p.price - prev_low.price
            label = EQL if abs(gap) <= tol else (HL if gap > 0 else LL)
            versus = prev_low.price
            prev_low = p
        out.append(SwingLabel(
            index=p.index, date=p.date, price=p.price, kind=p.kind,
            label=label, short=SWING_SHORT[label], versus=round(versus, 2),
        ))
    return out


def _trend_from(swings: Sequence[SwingLabel]) -> str:
    """The verdict of the two most recent swings, one per side."""
    last_high = next((s for s in reversed(swings) if s.kind == HIGH), None)
    last_low = next((s for s in reversed(swings) if s.kind == LOW), None)
    if last_high is None or last_low is None:
        return RANGE
    if last_high.label == HH and last_low.label == HL:
        return UPTREND
    if last_high.label == LH and last_low.label == LL:
        return DOWNTREND
    return RANGE


def build_market_structure(
    records: Sequence[StockRecord],
    pivots: Optional[Sequence[Pivot]] = None,
    atr: Optional[Sequence[Optional[float]]] = None,
    confirm_lag: int = 3,
) -> MarketStructure:
    """Swing labels, BOS/CHoCH events and the resulting trend for one symbol."""
    n = len(records)
    if n == 0:
        return MarketStructure(trend=RANGE, label=TREND_NAMES[RANGE])
    atr_s = list(atr) if atr is not None else IndicatorGroup3.atr(list(records), 14)
    pv = list(pivots) if pivots is not None else find_pivots(list(records), atr=atr_s)
    swings = label_swings(pv, atr_s)

    highs = [p for p in pv if p.kind == HIGH]
    lows = [p for p in pv if p.kind == LOW]
    events: List[StructureEvent] = []
    trend = RANGE
    ref_high: Optional[Pivot] = None
    ref_low: Optional[Pivot] = None
    hi_i = lo_i = 0

    for i in range(n):
        # A fractal pivot is only knowable once the bars on its right exist.
        while hi_i < len(highs) and highs[hi_i].index + confirm_lag <= i:
            ref_high = highs[hi_i]
            hi_i += 1
        while lo_i < len(lows) and lows[lo_i].index + confirm_lag <= i:
            ref_low = lows[lo_i]
            lo_i += 1

        close = records[i].priceClose
        if ref_high is not None and close > ref_high.price:
            kind = CHOCH if trend == DOWNTREND else BOS
            events.append(StructureEvent(
                kind=kind, direction="up", index=i,
                date=records[i].date.strftime("%Y-%m-%d"),
                level=round(ref_high.price, 2), close=round(close, 2),
            ))
            trend = UPTREND
            ref_high = None              # consumed; wait for the next swing high
        elif ref_low is not None and close < ref_low.price:
            kind = CHOCH if trend == UPTREND else BOS
            events.append(StructureEvent(
                kind=kind, direction="down", index=i,
                date=records[i].date.strftime("%Y-%m-%d"),
                level=round(ref_low.price, 2), close=round(close, 2),
            ))
            trend = DOWNTREND
            ref_low = None

    for event in events:
        event.label = describe_event(event)

    # The label sequence is the primary verdict; the event walk only overrides
    # it when the swings themselves are inconclusive.
    by_labels = _trend_from(swings)
    structure = MarketStructure(
        trend=by_labels if by_labels != RANGE else trend,
        swings=swings,
        events=events,
        last_high=round(ref_high.price, 2) if ref_high is not None else None,
        last_low=round(ref_low.price, 2) if ref_low is not None else None,
        bars_since_event=(n - 1 - events[-1].index) if events else None,
    )
    structure.label = describe_structure(structure)
    return structure


def describe_event(e: StructureEvent) -> str:
    way = "tăng" if e.direction == "up" else "giảm"
    if e.kind == BOS:
        return (f"BOS {way} ngày {e.date} — đóng cửa {e.close} "
                f"{'vượt' if e.direction == 'up' else 'thủng'} {e.level}, "
                f"xu hướng đi tiếp")
    other = "giảm" if e.direction == "down" else "tăng"
    return (f"CHoCH {way} ngày {e.date} — đóng cửa {e.close} "
            f"{'vượt' if e.direction == 'up' else 'thủng'} {e.level}, "
            f"lần đầu cấu trúc {other} bị bẻ")


def describe_structure(ms: MarketStructure) -> str:
    recent = [s.short for s in ms.swings[-4:]]
    seq = " → ".join(recent) if recent else "chưa đủ swing"
    head = f"{TREND_NAMES.get(ms.trend, ms.trend)} ({seq})"

    parts = [head]
    event = ms.last_event
    if event is not None:
        parts.append(f"{event.label} ({ms.bars_since_event} phiên trước)")
    bounds = []
    if ms.last_high is not None:
        bounds.append(f"đỉnh swing gần nhất {ms.last_high}")
    if ms.last_low is not None:
        bounds.append(f"đáy swing gần nhất {ms.last_low}")
    if bounds:
        parts.append("Mốc cấu trúc: " + ", ".join(bounds))
    return ". ".join(parts) + "."
