"""Effort against result — reading volume as evidence rather than as a filter.

Everywhere else volume is a threshold: a breakout counts if volume clears 1.5×
the 20-day average, and does not if it doesn't. That is volume as a gate. It
answers "was there enough?" and never "enough for what?".

The other reading pairs the volume of a session against what the session
actually achieved. Volume is effort; the spread of the bar and where it closed
are the result. When the two agree there is nothing to say. When they disagree
— enormous volume that moved price nowhere, a rally on volume that dried up —
the disagreement is the signal, because it says one side was being met by
somebody the tape does not name.

Five readings, each of which needs both halves to fire:

* **climax** — wide bar, huge volume, closing against its own direction
* **churn** — huge volume, narrow bar: effort spent, nothing gained
* **no demand** / **no supply** — a move on volume that never showed up
* **dry-up** — volume contracting to a multi-week low while range narrows

None of these is directional on its own. A churn bar at the top of a run and
the same bar at the bottom of a slide mean opposite things, and this module
does not know which it is looking at — that is the caller's job, the same
division of labour ``candles.py`` already follows.
"""
from dataclasses import asdict, dataclass
from typing import List, Optional, Sequence

import pandas as pd

from src.data.stock_data_loader import StockRecord
from src.ta import candles
from src.ta.candles import CandleShape

BUYING_CLIMAX = "buying_climax"
SELLING_CLIMAX = "selling_climax"
CHURN = "churn"
NO_DEMAND = "no_demand"
NO_SUPPLY = "no_supply"
DRY_UP = "dry_up"

VSA_NAMES = {
    BUYING_CLIMAX: "Cao trào mua",
    SELLING_CLIMAX: "Cao trào bán",
    CHURN: "Volume lớn nhưng giá không đi",
    NO_DEMAND: "Tăng không có cầu",
    NO_SUPPLY: "Giảm không có cung",
    DRY_UP: "Volume cạn kiệt",
}

#: What each reading says. Never a direction — the location decides that.
VSA_MEANINGS = {
    BUYING_CLIMAX: ("phiên tăng biên độ rộng, volume rất lớn, nhưng đóng cửa ở nửa dưới "
                    "— có bên bán ra đỡ hết lực mua"),
    SELLING_CLIMAX: ("phiên giảm biên độ rộng, volume rất lớn, nhưng đóng cửa ở nửa trên "
                     "— có bên mua vào hấp thụ hết lực bán"),
    CHURN: ("volume lớn mà biên độ hẹp — nỗ lực bỏ ra nhiều nhưng giá không đi được, "
            "hai bên đang đổi tay ở vùng này"),
    NO_DEMAND: ("phiên tăng nhưng biên độ hẹp và volume cạn — không có ai đuổi giá, "
                "nhịp tăng này thiếu người mua thật"),
    NO_SUPPLY: ("phiên giảm nhưng biên độ hẹp và volume cạn — không có ai bán tháo, "
                "nhịp giảm này thiếu người bán thật"),
    DRY_UP: ("volume co lại thấp nhất nhiều tuần kèm biên độ hẹp dần — thị trường hết "
             "quan tâm, thường đi trước một nhịp chuyển động"),
}

#: Volume multiples of the 20-day EMA.
HIGH_VOLUME = 2.0
LOW_VOLUME = 0.7
#: Spread multiples of ATR14.
WIDE_SPREAD = 1.3
NARROW_SPREAD = 0.7
#: Bars a dry-up is measured over.
DRY_UP_BARS = 20


@dataclass
class VsaSignal:
    kind: str
    name: str
    index: int
    date: str
    volume_x: float            # session volume over the 20-day EMA
    spread_atr: Optional[float]
    close_pos: Optional[float]
    strength: float
    label: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def volume_multiples(records: Sequence[StockRecord]) -> List[float]:
    """Each session's volume as a multiple of its own 20-day EMA."""
    volumes = [r.priceImpactVolume for r in records]
    ema = pd.Series(volumes).ewm(span=20, adjust=False).mean().tolist()
    return [(v / e if e else 0.0) for v, e in zip(volumes, ema)]


def _strength(base: float, volume_x: float, spread_atr: Optional[float]) -> float:
    score = base
    if volume_x >= 3.0:
        score += 0.20
    elif volume_x >= 2.5:
        score += 0.10
    if spread_atr is not None and spread_atr >= 1.8:
        score += 0.10
    return round(max(0.0, min(1.0, score)), 2)


def _read(sh: CandleShape, volume_x: float, vols: Sequence[float],
          shapes_: Sequence[CandleShape]) -> List[str]:
    """Which readings this one bar supports. Order does not matter."""
    out: List[str] = []
    spread = sh.spread_atr
    pos = sh.close_pos
    if spread is None or pos is None:
        return out

    heavy = volume_x >= HIGH_VOLUME
    thin = volume_x <= LOW_VOLUME
    wide = spread >= WIDE_SPREAD
    narrow = spread <= NARROW_SPREAD

    if heavy and wide:
        # Closing against the bar's own direction is the whole point: the move
        # happened and was then given back, on the heaviest trade in weeks.
        if sh.direction == candles.UP and pos <= 0.45:
            out.append(BUYING_CLIMAX)
        elif sh.direction == candles.DOWN and pos >= 0.55:
            out.append(SELLING_CLIMAX)
    if heavy and narrow:
        out.append(CHURN)
    if thin and narrow:
        if sh.direction == candles.UP:
            out.append(NO_DEMAND)
        elif sh.direction == candles.DOWN:
            out.append(NO_SUPPLY)

    i = sh.index
    if i >= DRY_UP_BARS and thin:
        window = vols[i - DRY_UP_BARS + 1:i + 1]
        spreads = [s.spread_atr for s in shapes_[i - DRY_UP_BARS + 1:i + 1]
                   if s.spread_atr is not None]
        if window and volume_x <= min(window) + 1e-9 and spreads and \
                spread <= sorted(spreads)[max(0, len(spreads) // 4)]:
            out.append(DRY_UP)
    return out


def detect(
    records: Sequence[StockRecord],
    index: int = -1,
    atr: Optional[Sequence[Optional[float]]] = None,
    measured: Optional[List[CandleShape]] = None,
    volumes: Optional[Sequence[float]] = None,
) -> List[VsaSignal]:
    """Every effort-vs-result reading that fits one bar, strongest first."""
    sh = measured if measured is not None else candles.shapes(records, atr)
    n = len(sh)
    if n == 0:
        return []
    i = index if index >= 0 else n + index
    if not 0 <= i < n:
        return []
    if sh[i].limit in (candles.CEILING, candles.FLOOR):
        return []                    # a locked session reports queue size, not trade

    vols = list(volumes) if volumes is not None else volume_multiples(records)
    # Round for display only. Comparing a rounded multiple against the raw
    # window minimum makes the bar fail to be its own minimum.
    raw = vols[i]
    volume_x = round(raw, 2)

    out: List[VsaSignal] = []
    for kind in _read(sh[i], raw, vols, sh):
        signal = VsaSignal(
            kind=kind, name=VSA_NAMES[kind], index=i, date=sh[i].date,
            volume_x=volume_x, spread_atr=sh[i].spread_atr,
            close_pos=round(sh[i].close_pos, 2) if sh[i].close_pos is not None else None,
            strength=_strength(0.55 if kind in (BUYING_CLIMAX, SELLING_CLIMAX) else 0.45,
                               volume_x, sh[i].spread_atr),
        )
        signal.label = describe(signal)
        out.append(signal)
    out.sort(key=lambda s: -s.strength)
    return out


def scan(
    records: Sequence[StockRecord],
    start: int = 0,
    end: Optional[int] = None,
    atr: Optional[Sequence[Optional[float]]] = None,
    measured: Optional[List[CandleShape]] = None,
) -> List[VsaSignal]:
    """Readings over an inclusive slice of the series, oldest bar first."""
    sh = measured if measured is not None else candles.shapes(records, atr)
    if not sh:
        return []
    vols = volume_multiples(records)
    last = len(sh) - 1
    lo = max(0, start if start >= 0 else len(sh) + start)
    hi = last if end is None else min(last, end if end >= 0 else len(sh) + end)

    out: List[VsaSignal] = []
    for i in range(lo, hi + 1):
        out += detect(records, i, measured=sh, volumes=vols)
    return out


def describe(signal: VsaSignal) -> str:
    spread = (f"biên độ {signal.spread_atr:g}× ATR"
              if signal.spread_atr is not None else "")
    close = (f"đóng ở {signal.close_pos * 100:.0f}% biên độ nến"
             if signal.close_pos is not None else "")
    facts = " · ".join(p for p in (f"volume {signal.volume_x:g}×", spread, close) if p)
    return f"**{signal.name}** · {facts} — {VSA_MEANINGS[signal.kind]}."
