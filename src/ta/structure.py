"""One pass over a symbol producing everything the chart needs drawn on it.

Pivots feed trendlines, trendlines feed the pattern, the box is found
independently, and the whole thing is turned into a short brief that explains
which level does what. This is the object the renderer and the MCP tools share.
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from src.analysis.technical_indicators import IndicatorGroup1, IndicatorGroup3
from src.data.stock_data_loader import StockRecord
from src.ta import asof as asof_mod
from src.ta.boxes import INSIDE, Box, find_box
from src.ta.confluence import Evidence, assess_all
from src.ta.formations import Formation, find_formations
from src.ta.levels import Level, VolumeProfile, find_levels
from src.ta.loader import load_recent
from src.ta.swings import MarketStructure, build_market_structure
from src.ta.patterns import Pattern, classify
from src.ta.pivots import Pivot, find_pivots
from src.ta.trendlines import TrendLine, find_trendlines


@dataclass
class Structure:
    symbol: str
    as_of: str
    bars: int
    close: float
    atr14: Optional[float]
    pivots: List[Pivot] = field(default_factory=list)
    trendlines: List[TrendLine] = field(default_factory=list)
    box: Optional[Box] = None
    pattern: Optional[Pattern] = None
    market: Optional[MarketStructure] = None
    levels: List[Level] = field(default_factory=list)
    profile: Optional[VolumeProfile] = None
    formations: List[Formation] = field(default_factory=list)
    evidence: List[Evidence] = field(default_factory=list)
    ema20: List[Optional[float]] = field(default_factory=list)
    ema50: List[Optional[float]] = field(default_factory=list)
    records: List[StockRecord] = field(default_factory=list, repr=False)
    brief: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    #: Mốc hồi tưởng đã yêu cầu (rỗng = dữ liệu mới nhất). Xem ``ta.asof``.
    as_of_requested: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """JSON-safe view — drops the raw records the renderer needs."""
        data = {
            "symbol": self.symbol,
            "as_of": self.as_of,
            "as_of_requested": self.as_of_requested,
            "bars": self.bars,
            "close": self.close,
            "atr14": self.atr14,
            "pivots": [p.to_dict() for p in self.pivots],
            "trendlines": [t.to_dict() for t in self.trendlines],
            "box": self.box.to_dict() if self.box else None,
            "pattern": self.pattern.to_dict() if self.pattern else None,
            "market": self.market.to_dict() if self.market else None,
            "levels": [l.to_dict() for l in self.levels],
            "profile": self.profile.to_dict() if self.profile else None,
            "formations": [e.to_dict() for e in self.evidence],
            "brief": self.brief,
            "warnings": self.warnings,
        }
        return data

    def line(self, kind: str) -> Optional[TrendLine]:
        return next((t for t in self.trendlines if t.kind == kind), None)


def _assign_ids(box: Optional[Box], lines: List[TrendLine],
                formations: Optional[List[Formation]] = None) -> None:
    """Number every drawn object once, box first, in the order they are listed.

    One counter across both kinds, so an id names exactly one thing on the chart
    and the user can point at it ("tại sao nối #3?").
    """
    counter = 1
    if box is not None:
        box.id = f"#{counter}"
        counter += 1
    for line in lines:
        line.id = f"#{counter}"
        counter += 1
    for formation in formations or []:
        formation.id = f"#{counter}"
        counter += 1


def _brief(records: List[StockRecord], box: Optional[Box],
           lines: List[TrendLine], pattern: Optional[Pattern],
           evidence: Optional[List[Evidence]] = None,
           market: Optional[MarketStructure] = None,
           levels: Optional[List[Level]] = None) -> List[str]:
    """The 'lý giải' — what each drawn level means for a decision."""
    out: List[str] = []
    close = records[-1].priceClose

    # Market structure comes first: it frames everything drawn below it.
    if market is not None and market.swings:
        out.append(market.label)

    if box is not None:
        out.append(f"{box.id} {box.label}")
        if box.state == INSIDE and box.position_pct is not None:
            if box.position_pct >= 75:
                out.append(
                    f"Giá đang áp sát cạnh trên hộp — đây là vùng cần theo dõi sát, "
                    f"vượt {box.top} kèm volume là điểm mua đẹp nhất của cấu trúc này."
                )
            elif box.position_pct <= 25:
                out.append(
                    f"Giá đang nằm sát cạnh dưới hộp ({box.bottom}) — hoặc bật lên từ đây, "
                    f"hoặc thủng xuống; chờ phiên xác nhận thay vì đoán trước."
                )

    for line in lines:
        out.append(f"{line.id} {line.label}")

    if pattern is not None and pattern.kind != "none":
        out.append(pattern.label)

    # Reversal formations get the last word among the drawn objects: they
    # carry a level, a target and a condition, which the shapes above do not.
    for ev in evidence or []:
        out.append(f"{ev.mark} {ev.formation.id} {ev.formation.name} — {ev.conclusion}")

    for level in (levels or [])[:3]:
        out.append(level.label)

    # Where the nearest actionable level sits relative to price.
    marks = []
    if box is not None:
        marks += [(f"cạnh trên hộp {box.id}", box.top),
                  (f"cạnh dưới hộp {box.id}", box.bottom)]
    for line in lines:
        # Name the line by how it was drawn, not by a role — a broken
        # resistance now sitting under price acts as support.
        marks.append((line.name.lower(), line.value_now))
    for level in (levels or []):
        marks.append((f"vùng {level.id}", level.price))
    above = sorted(((v, n) for n, v in marks if v > close))
    below = sorted(((v, n) for n, v in marks if v < close), reverse=True)
    if above or below:
        parts = []
        if above:
            v, n = above[0]
            parts.append(f"kháng cự gần nhất {v} ({n}, +{(v / close - 1) * 100:.1f}%)")
        if below:
            v, n = below[0]
            parts.append(f"hỗ trợ gần nhất {v} ({n}, {(v / close - 1) * 100:.1f}%)")
        out.append(f"Giá {close:.2f} — " + ", ".join(parts) + ".")

    return out


def build_structure(
    symbol: str,
    lookback_days: int = 260,
    as_of: Optional[datetime] = None,
    fractal: int = 3,
    records: Optional[List[StockRecord]] = None,
) -> Structure:
    recs = records if records is not None else load_recent(symbol, lookback_days, as_of)
    if not recs:
        return Structure(symbol=symbol, as_of="-", bars=0, close=0.0, atr14=None,
                         as_of_requested=asof_mod.label(as_of),
                         warnings=[f"Không có dữ liệu cho {symbol}"])

    atr_s = IndicatorGroup3.atr(recs, 14)
    atr14 = next((round(float(v), 2) for v in reversed(atr_s) if v is not None), None)

    warnings: List[str] = []
    if len(recs) < 40:
        warnings.append(f"Chỉ có {len(recs)} phiên — cấu trúc dựng ra kém tin cậy")

    pivots = find_pivots(recs, fractal=fractal, atr=atr_s)
    lines = find_trendlines(recs, pivots, atr=atr_s)
    box = find_box(recs, atr=atr_s)
    pattern = classify(recs, lines, atr=atr_s) if lines else None
    market = build_market_structure(recs, pivots, atr=atr_s)
    levels, profile = find_levels(recs, pivots, atr=atr_s)
    formations = find_formations(recs, pivots, atr=atr_s)
    evidence = assess_all(recs, formations, atr=atr_s)
    _assign_ids(box, lines, formations)
    if not pivots:
        warnings.append("Không tìm được swing pivot nào — chuỗi giá quá ngắn hoặc quá phẳng")

    structure = Structure(
        symbol=recs[-1].symbol,
        as_of=recs[-1].date.strftime("%Y-%m-%d"),
        as_of_requested=asof_mod.label(as_of),
        bars=len(recs),
        close=round(recs[-1].priceClose, 2),
        atr14=atr14,
        pivots=pivots,
        trendlines=lines,
        box=box,
        pattern=pattern,
        market=market,
        levels=levels,
        profile=profile,
        formations=formations,
        evidence=evidence,
        ema20=IndicatorGroup1.ema(recs, 20),
        ema50=IndicatorGroup1.ema(recs, 50),
        records=recs,
        warnings=warnings,
    )
    structure.brief = _brief(recs, box, lines, pattern, evidence, market, levels)
    return structure
