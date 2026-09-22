"""Rank a whole basket on the readings the per-symbol report already produces.

``build_report`` answers "what does this symbol look like". This module answers
"out of the basket, which ones look like that *most*". Nothing new is measured
here: the trend reading comes from ``snapshot`` + ``swings``, the pattern
reading from ``formations`` / ``confluence`` / ``boxes``, and every sentence is
the one those modules already wrote. What is added is an **ordering** — two
numbers per symbol, plus the components that produced them, so a rank can
always be taken apart into the readings behind it.

Two axes, deliberately kept apart:

* **Cường độ xu hướng** — signed, -100..+100. Magnitude is how hard the trend
  is running, sign is which way. Four components (ADX, xếp tầng EMA, chuỗi
  swing, quãng đường 20 phiên đo bằng ATR), each capped, so no single reading
  can carry a rank on its own.
* **Độ tin cậy mẫu hình** — 0..100 plus a state (`đã xác nhận` / `chưa xác
  nhận` / ...). This is not "how big the move will be"; it is how much of the
  evidence a pattern needs has actually arrived.

Blending the two into one "điểm cổ phiếu" would hide the case that matters
most — a bullish reversal *confirmed* against a still-falling trend — so they
stay two columns and two sorts.

One pass writes two artefacts: a self-contained HTML board (sortable in the
browser) and a JSON file. The JSON is the point: re-sorting the basket by a
different criterion later reads that file instead of recomputing everything.
"""
import html as html_escape
import json
import re
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from src.ta.boxes import (
    BREAKDOWN_CONFIRMED, BREAKDOWN_WEAK, BREAKOUT_UP_CONFIRMED, BREAKOUT_UP_WEAK,
    FALSE_BREAKDOWN, FALSE_BREAKOUT_UP, INSIDE, Box,
)
from src.ta.boxes import STATE_LABELS as BOX_STATE_LABELS
from src.ta.confluence import CONFLICT as TIER_CONFLICT
from src.ta.confluence import FULL as TIER_FULL
from src.ta.confluence import PARTIAL as TIER_PARTIAL
from src.ta.confluence import Evidence
from src.ta.formations import BEARISH, BULLISH
from src.ta.formations import CONFIRMED as F_CONFIRMED
from src.ta.formations import FAILED as F_FAILED
from src.ta.formations import FORMING as F_FORMING
from src.ta import loader
from src.ta.loader import PROJECT_ROOT, resolve_universe
from src.ta.patterns import NONE as PATTERN_NONE
from src.ta.patterns import Pattern
from src.ta import asof as asof_mod
from src.ta.report import REPORT_CSS, _asof_html
from src.ta import futures as futures_mod
from src.ta.futures import FuturesSnapshot, SymbolExposure
from src.ta.snapshot import Snapshot, build_snapshot
from src.ta.structure import Structure, build_structure
from src.ta.swings import BOS, DOWNTREND, HH, HL, LH, LL, UPTREND, MarketStructure

REPORT_DIR = PROJECT_ROOT / "reports"
#: Stable path so "sắp xếp lại theo tiêu chí khác" never has to hunt for a file.
LATEST_JSON = REPORT_DIR / "xep_hang_moi_nhat.json"

UP, DOWN, FLAT = "up", "down", "flat"
SIDE_VN = {UP: "tăng", DOWN: "giảm", FLAT: "đi ngang"}
SIDE_MARK = {UP: "▲", DOWN: "▼", FLAT: "•"}
BIAS_VN = {BULLISH: "tăng", BEARISH: "giảm", "neutral": "trung tính"}
BIAS_MARK = {BULLISH: "▲", BEARISH: "▼", "neutral": "•"}

#: How far the composite must travel before a side is called at all. Below
#: this the four components are pulling against each other and "đi ngang" is
#: the honest label.
TREND_SIDE_MIN = 15.0

# --- pattern confidence states, strongest first ----------------------------
CONFIRMED = "confirmed"
PARTIAL = "partial"
PENDING = "pending"
CONFLICT = "conflict"
FAILED = "failed"
NO_PATTERN = "none"

CONFIDENCE_VN = {
    CONFIRMED: "đã xác nhận",
    PARTIAL: "xác nhận một phần",
    PENDING: "chưa xác nhận",
    CONFLICT: "có yếu tố mâu thuẫn",
    FAILED: "mẫu hình hỏng",
    NO_PATTERN: "không có mẫu hình",
}
CONFIDENCE_RANK = {CONFIRMED: 5, PARTIAL: 4, PENDING: 3, CONFLICT: 2, FAILED: 1, NO_PATTERN: 0}
CONFIDENCE_MARK = {
    CONFIRMED: "✅", PARTIAL: "🟡", PENDING: "⏳",
    CONFLICT: "⚠️", FAILED: "❌", NO_PATTERN: "·",
}

FORMATION_SRC, BOX_SRC, PATTERN_SRC, NO_SRC = "formation", "box", "chart_pattern", "none"
SOURCE_VN = {
    FORMATION_SRC: "mô hình đảo chiều",
    BOX_SRC: "hộp tích luỹ",
    PATTERN_SRC: "hình mẫu giá",
    NO_SRC: "—",
}


# ---------------------------------------------------------------------------
# scoring primitives
# ---------------------------------------------------------------------------
def _ramp(value: float, curve: Sequence[Tuple[float, float]]) -> float:
    """Piecewise-linear map, held flat past both ends of ``curve``."""
    if value <= curve[0][0]:
        return curve[0][1]
    for (x0, y0), (x1, y1) in zip(curve, curve[1:]):
        if value <= x1:
            span = x1 - x0
            return y0 if span == 0 else y0 + (y1 - y0) * (value - x0) / span
    return curve[-1][1]


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _sign(value: Optional[float]) -> float:
    if not value:
        return 0.0
    return 1.0 if value > 0 else -1.0


#: ADX below 20 says "no trend" whatever the number is, so the curve stays
#: nearly flat until then and only pays out across 20 → 35.
_ADX_CURVE = ((0.0, 0.0), (15.0, 3.0), (20.0, 9.0), (25.0, 16.0), (35.0, 25.0), (50.0, 30.0))
#: Distance travelled in 20 sessions, measured in ATR — a 10% move means very
#: different things on a 1%-ATR stock and a 4%-ATR one.
_MOVE_CURVE = ((0.0, 0.0), (1.0, 6.0), (3.0, 14.0), (6.0, 20.0))


# ---------------------------------------------------------------------------
# trend axis
# ---------------------------------------------------------------------------
@dataclass
class TrendRank:
    """The trend as a signed intensity, plus the four readings that set it."""
    side: str                       # up | down | flat
    score: float                    # -100..+100
    ema_side: str
    ema_label: str
    structure_side: str
    structure_label: str
    conflict: bool                  # EMA and swing structure disagree
    adx: Optional[float]
    adx_direction: str
    adx_regime: str
    components: Dict[str, float] = field(default_factory=dict)
    reasons: List[str] = field(default_factory=list)

    @property
    def note(self) -> str:
        return " · ".join(self.reasons)


def _ema_side(snap: Snapshot) -> str:
    close = snap.price.get("close")
    e20, e50 = snap.trend.get("ema20"), snap.trend.get("ema50")
    if close is None or e20 is None or e50 is None:
        return FLAT
    if close > e20 > e50:
        return UP
    if close < e20 < e50:
        return DOWN
    return FLAT


def _ema_points(snap: Snapshot) -> Tuple[float, str]:
    """Four stacking checks worth ±25 together — the order of the averages."""
    close = snap.price.get("close")
    e20, e50, e100 = (snap.trend.get("ema20"), snap.trend.get("ema50"),
                      snap.trend.get("ema100"))
    checks = (
        (close, e20, 6.0),
        (e20, e50, 8.0),
        (close, e50, 5.0),
        (e50, e100, 6.0),
    )
    pts = 0.0
    passed = total = 0
    for above, below, weight in checks:
        if above is None or below is None:
            continue
        total += 1
        if above > below:
            pts += weight
            passed += 1
        else:
            pts -= weight
    if total == 0:
        return 0.0, "chưa đủ dữ liệu EMA"
    return pts, f"xếp tầng EMA {passed}/{total}"


def _structure_points(market: Optional[MarketStructure]) -> Tuple[float, str]:
    """Trend label + the last four swing verdicts + the most recent break."""
    if market is None or not market.swings:
        return 0.0, "chưa có swing nào"
    pts = {UPTREND: 14.0, DOWNTREND: -14.0}.get(market.trend, 0.0)
    tally = 0.0
    for swing in market.swings[-4:]:
        if swing.label in (HH, HL):
            tally += 2.0
        elif swing.label in (LH, LL):
            tally -= 2.0
    pts += _clamp(tally, -8.0, 8.0)

    event = market.last_event
    tail = ""
    if event is not None:
        # A BOS only restates the trend label already counted above; a CHoCH is
        # the first crack in it and deserves the bigger vote.
        weight = 2.0 if event.kind == BOS else 4.0
        if market.bars_since_event is not None and market.bars_since_event > 20:
            weight /= 2.0                     # a break that old stopped being news
        pts += weight * (1.0 if event.direction == "up" else -1.0)
        tail = f", {event.kind.upper()} {event.direction}"
    labels = "/".join(s.short for s in market.swings[-3:])
    return _clamp(pts, -25.0, 25.0), f"cấu trúc {labels or '—'}{tail}"


def _momentum_points(snap: Snapshot) -> Tuple[float, str]:
    """How far price actually travelled in 20 sessions, in ATR units."""
    change = snap.price.get("change_20d")
    atr_pct = snap.momentum.get("atr_pct")
    if change is None:
        return 0.0, "chưa đủ 20 phiên"
    if not atr_pct:
        return _clamp(change, -20.0, 20.0), f"20 phiên {change:+.1f}%"
    move_atr = change / atr_pct
    pts = _sign(move_atr) * _ramp(abs(move_atr), _MOVE_CURVE)
    return pts, f"20 phiên {move_atr:+.1f} ATR"


def build_trend_rank(snap: Snapshot, structure: Optional[Structure] = None) -> TrendRank:
    adx_value = snap.adx.get("adx")
    direction = snap.adx.get("direction", "flat")
    adx_pts = _ramp(adx_value or 0.0, _ADX_CURVE) * (
        1.0 if direction == "up" else -1.0 if direction == "down" else 0.0)
    ema_pts, ema_note = _ema_points(snap)
    market = structure.market if structure is not None else None
    struct_pts, struct_note = _structure_points(market)
    momo_pts, momo_note = _momentum_points(snap)

    score = _clamp(adx_pts + ema_pts + struct_pts + momo_pts, -100.0, 100.0)
    side = UP if score >= TREND_SIDE_MIN else DOWN if score <= -TREND_SIDE_MIN else FLAT

    ema_s = _ema_side(snap)
    struct_s = {UPTREND: UP, DOWNTREND: DOWN}.get(market.trend if market else "", FLAT)
    arrow = {"up": "↑", "down": "↓"}.get(direction, "→")

    return TrendRank(
        side=side,
        score=round(score, 1),
        ema_side=ema_s,
        ema_label=snap.trend.get("label", ""),
        structure_side=struct_s,
        structure_label=(market.label if market else "") or "",
        # Two readings of the same trend; where they part is the information,
        # so it gets a flag of its own rather than being averaged away.
        conflict=(ema_s != FLAT and struct_s != FLAT and ema_s != struct_s),
        adx=adx_value,
        adx_direction=direction,
        adx_regime=snap.adx.get("regime", ""),
        components={
            "adx": round(adx_pts, 1),
            "ema": round(ema_pts, 1),
            "structure": round(struct_pts, 1),
            "momentum": round(momo_pts, 1),
        },
        reasons=[
            (f"ADX {adx_value:.0f} {arrow} ({adx_pts:+.0f})" if adx_value is not None
             else "ADX chưa tính được (+0)"),
            f"{ema_note} ({ema_pts:+.0f})",
            f"{struct_note} ({struct_pts:+.0f})",
            f"{momo_note} ({momo_pts:+.0f})",
        ],
    )


# ---------------------------------------------------------------------------
# pattern axis
# ---------------------------------------------------------------------------
@dataclass
class PatternRank:
    """The strongest pattern claim on the chart and how much of it is proven."""
    source: str                     # formation | box | chart_pattern | none
    name: str
    bias: str                       # bullish | bearish | neutral
    state: str                      # confirmed | partial | pending | conflict | failed | none
    confidence: float               # 0..100
    trigger: Optional[float] = None
    target: Optional[float] = None
    invalidation: Optional[float] = None
    bars_since_break: Optional[int] = None
    target_hit: bool = False
    note: str = ""
    missing: List[str] = field(default_factory=list)

    @property
    def signed(self) -> float:
        """Confidence carrying the direction, for a single up-to-down ordering."""
        if self.bias == BULLISH:
            return self.confidence
        if self.bias == BEARISH:
            return -self.confidence
        return 0.0

    @property
    def rank(self) -> int:
        return CONFIDENCE_RANK.get(self.state, 0)


_FORMATION_BASE = {
    (F_CONFIRMED, TIER_FULL): 84.0,
    (F_CONFIRMED, TIER_PARTIAL): 66.0,
    (F_CONFIRMED, TIER_CONFLICT): 44.0,
    (F_FORMING, TIER_FULL): 45.0,        # confluence cannot emit this today
    (F_FORMING, TIER_PARTIAL): 38.0,
    (F_FORMING, TIER_CONFLICT): 28.0,
    (F_FAILED, TIER_FULL): 12.0,
    (F_FAILED, TIER_PARTIAL): 12.0,
    (F_FAILED, TIER_CONFLICT): 12.0,
}

_FORMATION_STATE = {
    (F_CONFIRMED, TIER_FULL): CONFIRMED,
    (F_CONFIRMED, TIER_PARTIAL): PARTIAL,
    (F_CONFIRMED, TIER_CONFLICT): CONFLICT,
    (F_FORMING, TIER_FULL): PENDING,
    (F_FORMING, TIER_PARTIAL): PENDING,
    (F_FORMING, TIER_CONFLICT): CONFLICT,
    (F_FAILED, TIER_FULL): FAILED,
    (F_FAILED, TIER_PARTIAL): FAILED,
    (F_FAILED, TIER_CONFLICT): FAILED,
}

_BOX_BASE = {
    BREAKOUT_UP_CONFIRMED: 72.0, BREAKDOWN_CONFIRMED: 72.0,
    BREAKOUT_UP_WEAK: 50.0, BREAKDOWN_WEAK: 50.0,
    FALSE_BREAKOUT_UP: 15.0, FALSE_BREAKDOWN: 15.0,
}

#: A box break is named by the direction it was attempted in — a false upside
#: break stays a "mẫu hình tăng", with `hỏng` as its confidence.
_BOX_STATE = {
    BREAKOUT_UP_CONFIRMED: (CONFIRMED, BULLISH),
    BREAKDOWN_CONFIRMED: (CONFIRMED, BEARISH),
    BREAKOUT_UP_WEAK: (PARTIAL, BULLISH),
    BREAKDOWN_WEAK: (PARTIAL, BEARISH),
    FALSE_BREAKOUT_UP: (FAILED, BULLISH),
    FALSE_BREAKDOWN: (FAILED, BEARISH),
}


def _pick_evidence(evidence: Sequence[Evidence]) -> Optional[Evidence]:
    """A confirmed formation outranks a forming one; then the cleaner tier wins."""
    if not evidence:
        return None
    state_order = {F_CONFIRMED: 0, F_FORMING: 1, F_FAILED: 2}
    tier_order = {TIER_FULL: 0, TIER_PARTIAL: 1, TIER_CONFLICT: 2}
    return sorted(
        evidence,
        key=lambda e: (state_order.get(e.formation.state, 3),
                       tier_order.get(e.tier, 3),
                       -e.formation.end_index),
    )[0]


def _decay(conf: float, retest, bars_since: Optional[int],
           volume_x: Optional[float], target_hit: bool) -> float:
    """Adjust a base score by what happened *after* the break."""
    if retest is not None:
        conf += 6.0 if retest.held else -10.0
    if bars_since is not None:
        if bars_since <= 5:
            conf += 4.0
        elif bars_since > 15:
            conf -= 6.0                       # the break stopped being news
    if volume_x and volume_x >= 2.0:
        conf += 4.0
    if target_hit:
        conf -= 8.0                           # the move the pattern promised is spent
    return _clamp(conf, 0.0, 100.0)


def _formation_claim(structure: Structure) -> Optional[PatternRank]:
    evidence = _pick_evidence(getattr(structure, "evidence", []))
    if evidence is None:
        return None
    f = evidence.formation
    key = (f.state, evidence.tier)
    conf = _decay(_FORMATION_BASE.get(key, 30.0), f.retest, f.bars_since_break,
                  f.break_volume_x, f.target_hit)
    return PatternRank(
        source=FORMATION_SRC, name=f.name, bias=f.bias,
        state=_FORMATION_STATE.get(key, PENDING), confidence=round(conf, 1),
        trigger=f.neckline_now, target=f.target, invalidation=f.invalidation,
        bars_since_break=f.bars_since_break, target_hit=f.target_hit,
        note=evidence.conclusion, missing=list(evidence.missing),
    )


def _box_claim(structure: Structure) -> Optional[PatternRank]:
    box: Optional[Box] = structure.box
    if box is None:
        return None
    if box.state != INSIDE:
        state, bias = _BOX_STATE.get(box.state, (PENDING, "neutral"))
        conf = _decay(_BOX_BASE.get(box.state, 30.0), box.retest, box.bars_since_breakout,
                      box.breakout_volume_x, box.target_hit)
        return PatternRank(
            source=BOX_SRC, name=BOX_STATE_LABELS.get(box.state, box.state), bias=bias,
            state=state, confidence=round(conf, 1),
            trigger=box.top if bias == BULLISH else box.bottom,
            target=box.target, invalidation=box.invalidation,
            bars_since_break=box.bars_since_breakout, target_hit=box.target_hit,
            note=box.label,
        )
    # Still inside: not a direction, but price pinned against an edge is a
    # setup one session away from becoming one.
    pos = box.position_pct
    edge = pos is not None and (pos >= 75.0 or pos <= 25.0)
    return PatternRank(
        source=BOX_SRC, name=f"hộp {box.bottom}–{box.top}", bias="neutral",
        state=PENDING, confidence=32.0 if edge else 20.0,
        trigger=box.top, target=box.target, invalidation=box.bottom,
        note=box.label, missing=["chưa phá cạnh hộp"],
    )


def _chart_claim(structure: Structure) -> Optional[PatternRank]:
    pattern: Optional[Pattern] = structure.pattern
    if pattern is None or pattern.kind == PATTERN_NONE:
        return None
    return PatternRank(
        source=PATTERN_SRC, name=pattern.name, bias=pattern.bias, state=PENDING,
        confidence=25.0 + (5.0 if pattern.converging else 0.0),
        trigger=pattern.upper_now, invalidation=pattern.lower_now, note=pattern.label,
        missing=["hình mẫu mới là hình học, chưa có phiên phá vỡ"],
    )


def build_pattern_rank(structure: Optional[Structure]) -> PatternRank:
    """The strongest *live* claim on the chart, whichever module found it.

    Priority is by evidence state, not by source: a dead double-bottom tells
    you less than an accumulation box price is still trading inside, so the
    box wins. Only when nothing is live does a broken formation surface — and
    then it surfaces as `mẫu hình hỏng`, which is itself worth knowing.
    """
    if structure is None:
        return PatternRank(NO_SRC, "—", "neutral", NO_PATTERN, 0.0)
    claims = [c for c in (_formation_claim(structure), _box_claim(structure),
                          _chart_claim(structure)) if c is not None]
    if not claims:
        return PatternRank(NO_SRC, "—", "neutral", NO_PATTERN, 0.0)
    return max(claims, key=lambda c: (c.rank, c.confidence))


# ---------------------------------------------------------------------------
# one row
# ---------------------------------------------------------------------------
@dataclass
class SymbolRank:
    symbol: str
    as_of: str
    bars: int
    close: Optional[float]
    change_pct: Optional[float]
    change_5d: Optional[float]
    change_20d: Optional[float]
    rsi: Optional[float]
    rsi_state: str
    rvol: Optional[float]
    atr_pct: Optional[float]
    vs_ema20: Optional[float]
    vs_ema50: Optional[float]
    box_position: Optional[float]
    box_top: Optional[float]
    box_bottom: Optional[float]
    trend: TrendRank
    pattern: PatternRank
    brief: List[str] = field(default_factory=list)
    #: Sự kiện của hộp, tách khỏi ``pattern`` vì hai câu hỏi khác nhau: mẫu
    #: hình hỏi "bằng chứng đã đủ chưa", mấy trường này hỏi "cú phá xảy ra
    #: lúc nào và volume có đỡ không". Mang sẵn ở đây để tầng trên
    #: (``prospect.py``) khỏi phải dựng lại ``Structure`` cho cả 79 mã.
    box_state: str = ""
    box_breakout_volume_x: Optional[float] = None
    box_bars_since_breakout: Optional[int] = None
    box_retest_held: Optional[bool] = None
    #: Giá trị khớp lệnh trung bình 20 phiên, **tỷ đồng/phiên**. Giá trong
    #: ``data/`` tính bằng nghìn đồng nên nhân 1e3 rồi chia 1e9.
    avg_value_bn: Optional[float] = None
    #: Trục thứ ba, **đứng riêng**: mã này chịu dòng tiền phái sinh tới đâu.
    #:
    #: Cố ý không cộng vào ``trend`` hay ``pattern``, cùng lý do hai cột kia
    #: không cộng vào nhau. Một mã trend +80 nằm ngoài rổ VN30 và một mã trend
    #: +80 beta 1,6 sát ngày đáo hạn là hai tình huống khác hẳn; gộp điểm lại
    #: là xoá mất đúng chỗ khác nhau đó. Và khác hai cột kia ở một điểm nữa:
    #: đây gần như là **đặc tính dài hạn** của mã, không phải trạng thái phiên —
    #: nó gần như không đổi giữa hai lần dựng bảng.
    futures: Optional[SymbolExposure] = None

    @property
    def target_pct(self) -> Optional[float]:
        """Distance from here to the pattern's measured target, in percent."""
        if not self.close or self.pattern.target is None:
            return None
        return round((self.pattern.target / self.close - 1.0) * 100.0, 2)

    @property
    def risk_reward(self) -> Optional[float]:
        """Measured move against the distance to invalidation."""
        p = self.pattern
        if not self.close or p.target is None or p.invalidation is None:
            return None
        risk = abs(self.close - p.invalidation)
        if risk < 1e-9:
            return None
        return round(abs(p.target - self.close) / risk, 2)

    @property
    def headline(self) -> str:
        """One line: what this symbol is doing, in the words of the module that saw it."""
        if self.pattern.state in (CONFIRMED, PARTIAL) and self.pattern.note:
            return self.pattern.note
        if self.trend.side != FLAT and self.trend.structure_label:
            return self.trend.structure_label
        return self.pattern.note or self.trend.ema_label

    @property
    def futures_score(self) -> Optional[float]:
        return self.futures.score if self.futures else None

    @property
    def beta_vn30(self) -> Optional[float]:
        return self.futures.beta if self.futures else None

    def to_dict(self) -> dict:
        data = asdict(self)
        data["trend"]["note"] = self.trend.note
        data["pattern"]["signed"] = self.pattern.signed
        data["target_pct"] = self.target_pct
        data["risk_reward"] = self.risk_reward
        data["headline"] = self.headline
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SymbolRank":
        """Rebuild from ``to_dict`` output, dropping the derived keys it added."""
        trend = {k: v for k, v in data["trend"].items() if k != "note"}
        pattern = {k: v for k, v in data["pattern"].items() if k != "signed"}
        derived = ("trend", "pattern", "futures", "target_pct", "risk_reward",
                   "headline", "futures_score", "beta_vn30")
        fields = {k: v for k, v in data.items() if k not in derived}
        exposure = data.get("futures")
        return cls(trend=TrendRank(**trend), pattern=PatternRank(**pattern),
                   futures=SymbolExposure(**exposure) if exposure else None,
                   **fields)


@dataclass
class Ranking:
    as_of: str
    generated: str
    universe: str
    #: Mốc hồi tưởng đã yêu cầu (rỗng = bảng dựng trên dữ liệu mới nhất).
    #: Đi theo cả file JSON, nên ``rank_list`` đọc lại vẫn biết bảng này là
    #: ảnh chụp của ngày nào chứ không tưởng nhầm là hôm nay.
    as_of_requested: str = ""
    rows: List[SymbolRank] = field(default_factory=list)
    skipped: List[str] = field(default_factory=list)
    html_path: Optional[str] = None
    json_path: Optional[str] = None
    #: Bối cảnh phái sinh của phiên — một bản cho cả bảng. Đi theo file JSON để
    #: ``rank_list`` đọc lại vẫn nói được "hôm đó còn 2 phiên tới đáo hạn", thay
    #: vì phải tính lại từ dữ liệu hôm nay và nói sai về một bảng của quá khứ.
    futures: Optional[FuturesSnapshot] = None

    def to_dict(self) -> dict:
        return {
            "as_of": self.as_of,
            "as_of_requested": self.as_of_requested,
            "generated": self.generated,
            "universe": self.universe,
            "rows": [r.to_dict() for r in self.rows],
            "skipped": self.skipped,
            "html_path": self.html_path,
            "json_path": self.json_path,
            "futures": self.futures.to_dict() if self.futures else None,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Ranking":
        return cls(
            as_of=data.get("as_of", "-"),
            as_of_requested=data.get("as_of_requested", ""),
            generated=data.get("generated", "-"),
            universe=data.get("universe", ""),
            rows=[SymbolRank.from_dict(r) for r in data.get("rows", [])],
            skipped=list(data.get("skipped", [])),
            html_path=data.get("html_path"),
            json_path=data.get("json_path"),
            futures=(FuturesSnapshot(**data["futures"])
                     if data.get("futures") else None),
        )


# ---------------------------------------------------------------------------
# building the whole basket
# ---------------------------------------------------------------------------
def _build_row(symbol: str, lookback_days: int, profile: str,
               as_of: Optional[datetime]) -> Optional[SymbolRank]:
    # EMA100 and ADX need a long warm-up; the structure only needs the window
    # actually being drawn, so the two calls get different lookbacks.
    snap = build_snapshot(symbol, as_of=as_of, lookback_days=max(lookback_days, 400),
                          profile=profile)
    if not snap.bars:
        return None
    structure = build_structure(symbol, lookback_days=lookback_days, as_of=as_of)
    box = structure.box
    close = snap.price.get("close")
    avg_vol = snap.volume.get("avg20")
    avg_value_bn = (round(close * avg_vol * 1e3 / 1e9, 1)
                    if close and avg_vol else None)
    return SymbolRank(
        symbol=symbol,
        as_of=snap.as_of,
        bars=snap.bars,
        close=snap.price.get("close"),
        change_pct=snap.price.get("change_pct"),
        change_5d=snap.price.get("change_5d"),
        change_20d=snap.price.get("change_20d"),
        rsi=snap.momentum.get("rsi14"),
        rsi_state=snap.rsi_zone.get("state", ""),
        rvol=snap.volume.get("rvol"),
        atr_pct=snap.momentum.get("atr_pct"),
        vs_ema20=snap.trend.get("vs_ema20_pct"),
        vs_ema50=snap.trend.get("vs_ema50_pct"),
        box_position=box.position_pct if box else None,
        box_top=box.top if box else None,
        box_bottom=box.bottom if box else None,
        trend=build_trend_rank(snap, structure),
        pattern=build_pattern_rank(structure),
        brief=list(structure.brief),
        box_state=box.state if box else "",
        box_breakout_volume_x=box.breakout_volume_x if box else None,
        box_bars_since_breakout=box.bars_since_breakout if box else None,
        box_retest_held=(box.retest.held if box and box.retest else None),
        avg_value_bn=avg_value_bn,
        futures=futures_mod.symbol_exposure(symbol, as_of),
    )


def build(
    universe: str = "all",
    lookback_days: int = 260,
    profile: str = "standard",
    as_of: Optional[datetime] = None,
    max_workers: int = 8,
    write_files: bool = True,
    with_html: bool = True,
    out_dir: Optional[str] = None,
) -> Ranking:
    """Score every symbol in ``universe`` and write the board + the JSON."""
    symbols = resolve_universe(universe)
    ranking = Ranking(
        as_of="-",
        generated=datetime.now().strftime("%Y-%m-%d %H:%M"),
        universe=universe,
        as_of_requested=asof_mod.label(as_of),
    )
    if not symbols:
        ranking.skipped.append(f"Không tìm thấy dữ liệu cho {universe!r}")
        return ranking

    # Bối cảnh phái sinh dựng một lần, và `vn30_liquidity_share` được gọi ở đây
    # để **hâm cache trước khi mở pool**: 8 luồng cùng chạm vào một `lru_cache`
    # trống thì cả 8 cùng đi nạp 30 mã, vì lru_cache dùng lại *kết quả* chứ
    # không khoá lượt tính.
    ranking.futures = futures_mod.build_futures_snapshot(as_of)
    futures_mod.vn30_liquidity_share(as_of)

    def _work(sym: str):
        try:
            return sym, _build_row(sym, lookback_days, profile, as_of)
        except Exception as exc:        # one bad symbol must not kill the batch
            return sym, exc

    with ThreadPoolExecutor(max_workers=max(1, max_workers)) as pool:
        for sym, outcome in pool.map(_work, symbols):
            if isinstance(outcome, Exception):
                ranking.skipped.append(f"{sym}: {type(outcome).__name__}: {outcome}")
            elif outcome is None:
                ranking.skipped.append(f"{sym}: không có dữ liệu giá")
            else:
                ranking.rows.append(outcome)

    ranking.rows.sort(key=lambda r: -r.trend.score)
    if ranking.rows:
        ranking.as_of = max(r.as_of for r in ranking.rows)
    if write_files and ranking.rows:
        if with_html:
            ranking.html_path = write_html(ranking, out_dir=out_dir)
        ranking.json_path = save_json(ranking, out_dir=out_dir)
    return ranking


# ---------------------------------------------------------------------------
# criteria — the vocabulary the user sorts by
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Criterion:
    key: str
    label: str
    unit: str
    value: Callable[[SymbolRank], Optional[float]]
    explain: str
    #: When ordering needs more than the displayed number (confidence sorts by
    #: state band first, then by score inside the band).
    sort: Optional[Callable[[SymbolRank], Optional[float]]] = None
    digits: int = 1

    def sort_value(self, row: SymbolRank) -> Optional[float]:
        return (self.sort or self.value)(row)


def _conf_sort(row: SymbolRank) -> float:
    """State band first, score inside it — `đã xác nhận 70` beats `chưa 95`."""
    return row.pattern.rank * 1000.0 + row.pattern.confidence


CRITERIA: Dict[str, Criterion] = {
    c.key: c for c in (
        Criterion("trend", "Cường độ xu hướng", "điểm", lambda r: r.trend.score,
                  "Tổng có dấu của 4 thành phần: ADX×hướng (±30), xếp tầng EMA (±25), "
                  "chuỗi swing + BOS/CHoCH (±25), quãng đường 20 phiên đo bằng ATR (±20). "
                  "Dương = tăng, âm = giảm."),
        Criterion("trend_abs", "Cường độ xu hướng (bỏ dấu)", "điểm",
                  lambda r: abs(r.trend.score),
                  "Cùng thang điểm trên nhưng bỏ dấu — mã chạy mạnh nhất bất kể hướng nào."),
        Criterion("pattern", "Mẫu hình (có dấu theo hướng)", "điểm",
                  lambda r: r.pattern.signed,
                  "Độ tin cậy mang dấu: dương cho mẫu hình tăng, âm cho mẫu hình giảm."),
        Criterion("confidence", "Độ tin cậy mẫu hình", "điểm",
                  lambda r: r.pattern.confidence,
                  "0–100 theo lượng bằng chứng đã có: đã phá mốc chưa, nến tại vùng quyết "
                  "định có không, volume có xác nhận không, retest có giữ không. "
                  "Xếp theo nhóm trạng thái trước (đã xác nhận > xác nhận một phần > chưa "
                  "xác nhận > mâu thuẫn > hỏng), rồi mới tới điểm.",
                  sort=_conf_sort),
        Criterion("adx", "ADX14", "", lambda r: r.trend.adx,
                  "Độ mạnh xu hướng, không phân biệt hướng. Dưới 20 coi như chưa có xu hướng."),
        Criterion("rsi", "RSI14", "", lambda r: r.rsi,
                  "Động lượng 0–100; > 70 quá mua, < 30 quá bán (profile standard)."),
        Criterion("change_pct", "Thay đổi phiên gần nhất", "%", lambda r: r.change_pct,
                  "Phần trăm so với phiên liền trước.", digits=2),
        Criterion("change_5d", "Thay đổi 5 phiên", "%", lambda r: r.change_5d,
                  "Phần trăm so với 5 phiên trước.", digits=2),
        Criterion("change_20d", "Thay đổi 20 phiên", "%", lambda r: r.change_20d,
                  "Phần trăm so với 20 phiên trước.", digits=2),
        Criterion("rvol", "RVOL", "×", lambda r: r.rvol,
                  "Volume phiên gần nhất chia trung bình 20 phiên (dùng dealVolume).",
                  digits=2),
        Criterion("atr_pct", "Biến động ATR14", "%", lambda r: r.atr_pct,
                  "ATR14 tính theo phần trăm giá — biên độ một phiên bình thường."),
        Criterion("vs_ema20", "Khoảng cách EMA20", "%", lambda r: r.vs_ema20,
                  "Giá đang trên (+) hay dưới (−) EMA20 bao nhiêu phần trăm.", digits=2),
        Criterion("vs_ema50", "Khoảng cách EMA50", "%", lambda r: r.vs_ema50,
                  "Giá đang trên (+) hay dưới (−) EMA50 bao nhiêu phần trăm.", digits=2),
        Criterion("box_position", "Vị trí trong hộp", "%", lambda r: r.box_position,
                  "0% = sát cạnh dưới hộp tích luỹ, 100% = sát cạnh trên.", digits=0),
        Criterion("close", "Giá đóng cửa", "", lambda r: r.close, "Giá đóng cửa phiên gần nhất.",
                  digits=2),
        Criterion("liquidity", "Thanh khoản", "tỷ/phiên", lambda r: r.avg_value_bn,
                  "Giá trị khớp lệnh trung bình 20 phiên, tính bằng tỷ đồng "
                  "(giá đóng cửa × volume trung bình, dùng dealVolume). Một mẫu hình "
                  "đẹp trên mã không ai giao dịch được là mẫu hình không dùng được.",
                  digits=0),
        Criterion("target_pct", "Khoảng tới mục tiêu", "%", lambda r: r.target_pct,
                  "Từ giá hiện tại tới mục tiêu đo được của mẫu hình, tính bằng phần trăm.",
                  digits=2),
        Criterion("risk_reward", "Mục tiêu / khoảng huỷ", "×", lambda r: r.risk_reward,
                  "Quãng đường tới mục tiêu chia quãng đường tới mức huỷ mẫu hình.",
                  digits=2),
        Criterion("futures", "Phơi nhiễm phái sinh", "điểm", lambda r: r.futures_score,
                  "0–100, chỉ để sắp thứ tự: nằm trong rổ VN30 (40) + beta so với VN30 (30) "
                  "+ tỷ trọng thanh khoản trong rổ (20) + biên độ phiên đáo hạn so với "
                  "phiên thường (10). Mã trong rổ chịu ảnh hưởng CƠ HỌC — lệnh chênh lệch "
                  "giá rơi thẳng vào 30 mã đó; mã ngoài rổ chỉ chịu qua tâm lý chung.",
                  digits=0),
        Criterion("beta", "Beta so với VN30", "×", lambda r: r.beta_vn30,
                  "Mã đi bao nhiêu khi rổ cơ sở VN30 đi 1%, ước lượng trên 120 phiên. "
                  "Mốc là VN30 chứ không phải VNINDEX, vì hợp đồng tương lai thanh toán "
                  "theo VN30.", digits=2),
    )
}


def _norm(text: str) -> str:
    """Fold Vietnamese to bare ASCII words so 'Độ tin cậy' == 'do_tin_cay'."""
    text = (text or "").strip().lower().replace("đ", "d")
    text = "".join(ch for ch in unicodedata.normalize("NFD", text)
                   if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+", "_", text).strip("_")


_CRITERION_ALIASES = {
    "cuong_do": "trend", "cuong_do_xu_huong": "trend", "xu_huong": "trend",
    "suc_manh": "trend", "trend_score": "trend", "strength": "trend",
    "cuong_do_tuyet_doi": "trend_abs", "manh_nhat": "trend_abs",
    "mau_hinh": "pattern", "hinh_mau": "pattern", "pattern_score": "pattern",
    "do_tin_cay": "confidence", "tin_cay": "confidence", "xac_nhan": "confidence",
    "adx14": "adx", "rsi14": "rsi",
    "thay_doi": "change_pct", "phien": "change_pct", "1_phien": "change_pct",
    "5_phien": "change_5d", "20_phien": "change_20d",
    "thanh_khoan": "rvol", "volume": "rvol", "khoi_luong": "rvol",
    "bien_dong": "atr_pct", "atr": "atr_pct",
    "ema20": "vs_ema20", "ema50": "vs_ema50",
    "vi_tri_hop": "box_position", "hop": "box_position",
    "gia": "close",
    "muc_tieu": "target_pct", "target": "target_pct",
    "rr": "risk_reward", "risk_reward_ratio": "risk_reward", "loi_nhuan_rui_ro": "risk_reward",
    "phai_sinh": "futures", "phoi_nhiem": "futures", "phoi_nhiem_phai_sinh": "futures",
    "futures_exposure": "futures", "anh_huong_phai_sinh": "futures",
    "derivative": "futures", "derivatives": "futures",
    "beta_vn30": "beta", "he_so_beta": "beta",
}

_SIDE_ALIASES = {
    "tang": UP, "up": UP, "bull": UP, "bullish": UP, "len": UP, "uptrend": UP,
    "giam": DOWN, "down": DOWN, "bear": DOWN, "bearish": DOWN, "xuong": DOWN,
    "downtrend": DOWN,
    "di_ngang": FLAT, "ngang": FLAT, "flat": FLAT, "sideway": FLAT, "range": FLAT,
}

_BIAS_ALIASES = {
    "tang": BULLISH, "up": BULLISH, "bull": BULLISH, "bullish": BULLISH,
    "giam": BEARISH, "down": BEARISH, "bear": BEARISH, "bearish": BEARISH,
    "trung_tinh": "neutral", "neutral": "neutral",
}

_CONFIDENCE_ALIASES = {
    "da_xac_nhan": CONFIRMED, "confirmed": CONFIRMED, "xac_nhan": CONFIRMED,
    "xac_nhan_mot_phan": PARTIAL, "mot_phan": PARTIAL, "partial": PARTIAL,
    "chua_xac_nhan": PENDING, "pending": PENDING, "dang_hinh_thanh": PENDING,
    "mau_thuan": CONFLICT, "conflict": CONFLICT,
    "hong": FAILED, "failed": FAILED, "mau_hinh_hong": FAILED,
    "khong_co": NO_PATTERN, "none": NO_PATTERN,
}


def resolve_criterion(name: str) -> Criterion:
    key = _norm(name) or "trend"
    key = _CRITERION_ALIASES.get(key, key)
    if key not in CRITERIA:
        raise ValueError(
            f"Tiêu chí không hợp lệ: {name!r}. Chọn: " + ", ".join(CRITERIA)
        )
    return CRITERIA[key]


def _resolve(value: str, table: Dict[str, str], what: str) -> Optional[str]:
    if not (value or "").strip():
        return None
    key = _norm(value)
    if key in table:
        return table[key]
    raise ValueError(f"{what} không hợp lệ: {value!r}. Chọn: "
                     + ", ".join(sorted(set(table.values()))))


def sort_rows(
    rows: Sequence[SymbolRank],
    criterion: str = "trend",
    descending: bool = True,
    side: str = "",
    bias: str = "",
    min_confidence: str = "",
    limit: int = 0,
) -> Tuple[List[SymbolRank], Criterion]:
    """Filter then order. Symbols with no value for the criterion always go last."""
    crit = resolve_criterion(criterion)
    want_side = _resolve(side, _SIDE_ALIASES, "Hướng xu hướng")
    want_bias = _resolve(bias, _BIAS_ALIASES, "Hướng mẫu hình")
    floor = _resolve(min_confidence, _CONFIDENCE_ALIASES, "Mức tin cậy")

    out = list(rows)
    if want_side:
        out = [r for r in out if r.trend.side == want_side]
    if want_bias:
        out = [r for r in out if r.pattern.bias == want_bias]
    if floor:
        need = CONFIDENCE_RANK[floor]
        out = [r for r in out if r.pattern.rank >= need]

    def _key(row: SymbolRank):
        value = crit.sort_value(row)
        if value is None:
            return (1, 0.0, row.symbol)
        return (0, -value if descending else value, row.symbol)

    out.sort(key=_key)
    return (out[:limit] if limit and limit > 0 else out), crit


# ---------------------------------------------------------------------------
# persistence — the JSON is what a later re-sort reads
# ---------------------------------------------------------------------------
def _out_root(out_dir: Optional[str], ranking: Optional[Ranking] = None) -> Path:
    cutoff = asof_mod.parse(ranking.as_of_requested) if ranking else None
    return asof_mod.out_root(REPORT_DIR, cutoff, out_dir)


def _stem(ranking: Ranking) -> str:
    tag = _norm(ranking.universe) or "tuy_chon"
    return f"xep_hang_{tag[:24]}_{asof_mod.file_tag(asof_mod.parse(ranking.as_of_requested))}"


def is_stock_board(ranking: Ranking) -> bool:
    """Bảng này có phải bảng của **rổ cổ phiếu** không.

    Con trỏ ``xep_hang_moi_nhat.json`` mang đúng một nghĩa: *bảng của rổ cổ
    phiếu, phiên mới nhất*. Hai chỗ đọc nó đều dựa vào nghĩa đó — ``rank_list``
    xoay lại bảng người dùng đang mở, và ``market.Breadth`` đếm bao nhiêu phần
    trăm **mã** đang trên EMA20.

    Từ khi ``resolve_universe`` nhận nhóm ``sectors``, ``build_ranking`` chạy
    được trên 31 chỉ số ngành — và nếu nó cũng làm mới con trỏ thì độ rộng thị
    trường trong mọi hồ sơ 1 mã lặng lẽ chuyển sang đếm *chỉ số ngành* thay vì
    *cổ phiếu*. Không có gì báo, vì cả hai đều là một danh sách symbol có
    ``vs_ema20``. Đúng loại lỗi mà quy ước "bảng hồi tưởng không đụng con trỏ"
    đã chặn một lần, chỉ khác đường vào.
    """
    marks = loader.non_tradable_symbols()
    return bool(ranking.rows) and not any(
        r.symbol.strip().upper() in marks for r in ranking.rows)


def save_json(ranking: Ranking, out_dir: Optional[str] = None) -> str:
    """Write the dated copy and refresh the stable `mới nhất` pointer.

    Con trỏ chỉ được làm mới bởi **bảng của rổ cổ phiếu, không có mốc hồi
    tưởng**. Hai loại bảng bị loại, vì hai lý do khác nhau nhưng cùng một hậu
    quả — con trỏ nói một đằng, nội dung một nẻo:

    * **Bảng hồi tưởng.** Nhịp dùng hàng ngày (`/rank` rồi xoay bảng vài lần)
      đọc đúng con trỏ đó, và một lần thử "giả sử hôm nay là 01/01/2025" không
      được phép biến bảng của phiên thật thành bảng của một năm trước mà không
      ai nhận ra. Bản hồi tưởng nằm ở ``reports/asof_<ngày>/`` và
      ``board_path(as_of)`` tìm lại được nó.
    * **Bảng không phải cổ phiếu** — chỉ số ngành, benchmark, phái sinh. Xem
      ``is_stock_board``.

    Bảng bị loại vẫn ghi bản có ngày tháng bình thường; chỉ con trỏ là không
    đụng tới.
    """
    path = _out_root(out_dir, ranking) / f"{_stem(ranking)}.json"
    payload = ranking.to_dict()
    payload["json_path"] = str(path)
    text = json.dumps(payload, ensure_ascii=False, indent=1)
    path.write_text(text, encoding="utf-8")
    if not ranking.as_of_requested and is_stock_board(ranking):
        LATEST_JSON.parent.mkdir(parents=True, exist_ok=True)
        LATEST_JSON.write_text(text, encoding="utf-8")
    return str(path)


def board_path(as_of: Optional[datetime] = None) -> Path:
    """File JSON của bảng ứng với ``as_of`` — con trỏ `mới nhất` khi không có mốc."""
    if as_of is None:
        return LATEST_JSON
    root = REPORT_DIR / f"asof_{asof_mod.label(as_of)}"
    boards = sorted(root.glob("xep_hang_*.json"), key=lambda f: f.stat().st_mtime)
    if not boards:
        raise FileNotFoundError(
            f"Chưa có bảng xếp hạng nào cho mốc {asof_mod.label(as_of)} — "
            f"chạy `build_ranking` với as_of={asof_mod.label(as_of)} trước."
        )
    return boards[-1]


def load_ranking(path: Optional[str] = None,
                 as_of: Optional[datetime] = None) -> Ranking:
    """Read back a saved board. Defaults to the most recent one built."""
    target = Path(path) if path else board_path(as_of)
    if not target.is_file():
        raise FileNotFoundError(
            f"Chưa có bảng xếp hạng nào ở {target} — chạy `build_ranking` trước."
        )
    return Ranking.from_dict(json.loads(target.read_text(encoding="utf-8")))


# ---------------------------------------------------------------------------
# html board
# ---------------------------------------------------------------------------
RANK_CSS = """
.legend { font-size: 13px; color: #8b949e; }
.legend b { color: #c9d1d9; }
th.sortable { cursor: pointer; user-select: none; white-space: nowrap; }
th.sortable:hover { color: #58a6ff; }
th.sortable::after { content: ' ⇅'; opacity: .35; }
th.sortable.asc::after { content: ' ↑'; opacity: 1; color: #58a6ff; }
th.sortable.desc::after { content: ' ↓'; opacity: 1; color: #58a6ff; }
.tools { display: flex; gap: 10px; align-items: center; margin: 12px 0; flex-wrap: wrap; }
.tools input { background: #0d1117; border: 1px solid #30363d; color: #c9d1d9;
               border-radius: 6px; padding: 6px 10px; font: inherit; min-width: 220px; }
.tools button { background: #21262d; border: 1px solid #30363d; color: #c9d1d9;
                border-radius: 6px; padding: 6px 12px; font: inherit; cursor: pointer; }
.tools button.on { background: #1f6feb; border-color: #1f6feb; color: #fff; }
.up { color: #3fb950; font-weight: 600; }
.down { color: #f85149; font-weight: 600; }
.flat { color: #8b949e; }
.bar { display: inline-block; height: 8px; border-radius: 4px; vertical-align: middle;
       margin-left: 6px; }
.bar.up { background: #3fb950; } .bar.down { background: #f85149; }
.why { color: #8b949e; font-size: 12.5px; }
.pill { display: inline-block; padding: 1px 8px; border-radius: 999px; font-size: 12px;
        border: 1px solid #30363d; }
.pill.confirmed { border-color: #3fb950; color: #3fb950; }
.pill.partial { border-color: #e3b341; color: #e3b341; }
.pill.pending { border-color: #58a6ff; color: #58a6ff; }
.pill.conflict { border-color: #a371f7; color: #a371f7; }
.pill.failed { border-color: #f85149; color: #f85149; }
.pill.none { border-color: #30363d; color: #6e7681; }
.detail h3 { margin-top: 22px; }
.detail .card { margin: 8px 0 20px; }
"""

_SORT_JS = """
(function () {
  function cellValue(row, i) {
    var cell = row.cells[i];
    if (!cell) return null;
    var raw = cell.getAttribute('data-v');
    if (raw === null || raw === '') return null;
    var num = parseFloat(raw);
    return isNaN(num) ? raw.toLowerCase() : num;
  }
  document.querySelectorAll('table[data-sortable]').forEach(function (table) {
    var head = table.tHead.rows[0];
    Array.prototype.forEach.call(head.cells, function (th, i) {
      th.classList.add('sortable');
      th.addEventListener('click', function () {
        var desc = !th.classList.contains('desc');
        Array.prototype.forEach.call(head.cells, function (o) {
          o.classList.remove('asc', 'desc');
        });
        th.classList.add(desc ? 'desc' : 'asc');
        var body = table.tBodies[0];
        var rows = Array.prototype.slice.call(body.rows);
        rows.sort(function (a, b) {
          var x = cellValue(a, i), y = cellValue(b, i);
          if (x === null && y === null) return 0;
          if (x === null) return 1;          // missing values always last
          if (y === null) return -1;
          if (x < y) return desc ? 1 : -1;
          if (x > y) return desc ? -1 : 1;
          return 0;
        });
        rows.forEach(function (r) { body.appendChild(r); });
      });
    });
  });
  var box = document.getElementById('filter');
  var table = document.getElementById('all-table');
  var mode = 'all';
  function apply() {
    var q = (box.value || '').trim().toUpperCase();
    Array.prototype.forEach.call(table.tBodies[0].rows, function (row) {
      var okText = !q || row.cells[0].textContent.toUpperCase().indexOf(q) >= 0;
      var okSide = mode === 'all' || row.getAttribute('data-side') === mode;
      row.style.display = (okText && okSide) ? '' : 'none';
    });
  }
  box.addEventListener('input', apply);
  document.querySelectorAll('[data-mode]').forEach(function (btn) {
    btn.addEventListener('click', function () {
      mode = btn.getAttribute('data-mode');
      document.querySelectorAll('[data-mode]').forEach(function (o) {
        o.classList.remove('on');
      });
      btn.classList.add('on');
      apply();
    });
  });
})();
"""


def _esc(value: Any) -> str:
    return html_escape.escape(str(value if value is not None else "—"))


def _esc_md(value: Any) -> str:
    """Structure notes carry markdown; **bold** is the only markup used."""
    return re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", _esc(value))


def _side_cell(score: float, side: str) -> str:
    width = max(2, round(abs(score) * 0.6))
    return (f'<span class="{side}">{SIDE_MARK[side]} {score:+.1f}</span>'
            f'<span class="bar {side}" style="width:{width}px"></span>')


def _conf_cell(pattern: PatternRank) -> str:
    return (f'<span class="pill {pattern.state}">{_esc(CONFIDENCE_VN[pattern.state])}</span> '
            f"{pattern.confidence:.0f}")


def _num(value: Optional[float], digits: int = 2) -> str:
    return "—" if value is None else f"{value:,.{digits}f}"


def _rank_table(rows: Sequence[SymbolRank], kind: str) -> List[str]:
    """A pre-sorted top list: trend rows carry the components, pattern rows the levels."""
    if not rows:
        return ['<div class="sub">Không có mã nào.</div>']
    out = ['<div class="scroll">', "<table>"]
    if kind == "trend":
        out.append("<tr><th>#</th><th>Mã</th><th class='num'>Giá</th><th class='num'>+/-</th>"
                   "<th class='num'>Cường độ</th><th class='num'>ADX</th>"
                   "<th>Đọc từ EMA / cấu trúc</th><th>Điểm đến từ đâu</th></tr>")
        for i, r in enumerate(rows, 1):
            warn = " ⚠️" if r.trend.conflict else ""
            out.append(
                f"<tr><td>{i}</td><td><b>{_esc(r.symbol)}</b></td>"
                f"<td class='num'>{_num(r.close)}</td>"
                f"<td class='num'>{_signed_html(r.change_pct)}</td>"
                f"<td class='num'>{_side_cell(r.trend.score, r.trend.side)}</td>"
                f"<td class='num'>{_num(r.trend.adx, 1)}</td>"
                f"<td>{_esc(r.trend.ema_label)}{warn}</td>"
                f'<td class="why">{_esc(r.trend.note)}</td></tr>'
            )
    elif kind == "futures":
        out.append("<tr><th>#</th><th>Mã</th><th>Kênh lan truyền</th>"
                   "<th class='num'>β VN30</th><th class='num'>R²</th>"
                   "<th class='num'>% thanh khoản rổ</th>"
                   "<th class='num'>Biên độ phiên đáo hạn</th>"
                   "<th class='num'>RS 20p</th><th class='num'>Điểm</th></tr>")
        for i, r in enumerate(rows, 1):
            e = r.futures
            if e is None:
                continue
            share = "—" if e.liquidity_share_pct is None else f"{e.liquidity_share_pct:.2f}"
            out.append(
                f"<tr><td>{i}</td><td><b>{_esc(r.symbol)}</b></td>"
                f"<td>{_esc(e.channel)}</td>"
                f"<td class='num'>{_num(e.beta, 2)}</td>"
                f"<td class='num'>{_num(e.r2, 2)}</td>"
                f"<td class='num'>{_esc(share)}</td>"
                f"<td class='num'>{_num(e.expiry_move_ratio, 2)}×</td>"
                f"<td class='num'>{_signed_html(e.rs_20)}</td>"
                f"<td class='num'><b>{e.score:.0f}</b></td></tr>"
            )
        out += ["</table>", "</div>"]
        return out
    else:
        out.append("<tr><th>#</th><th>Mã</th><th>Mẫu hình</th><th>Độ tin cậy</th>"
                   "<th class='num'>Mốc</th><th class='num'>Mục tiêu</th>"
                   "<th class='num'>Huỷ nếu</th><th>Trạng thái</th></tr>")
        for i, r in enumerate(rows, 1):
            p = r.pattern
            out.append(
                f"<tr><td>{i}</td><td><b>{_esc(r.symbol)}</b></td>"
                f"<td>{BIAS_MARK.get(p.bias, '•')} {_esc(p.name)}</td>"
                f"<td>{_conf_cell(p)}</td>"
                f"<td class='num'>{_num(p.trigger)}</td>"
                f"<td class='num'>{_num(p.target)}</td>"
                f"<td class='num'>{_num(p.invalidation)}</td>"
                f'<td class="why">{_esc(p.note)}</td></tr>'
            )
    out += ["</table>", "</div>"]
    return out


def _signed_html(value: Optional[float]) -> str:
    if value is None:
        return "—"
    return f'<span class="{"pos" if value >= 0 else "neg"}">{value:+.2f}%</span>'


def _futures_context_html(fsnap, ref_date: str = "") -> str:
    """Bối cảnh phái sinh của phiên, dựng từ **cùng** câu chữ bản terminal in.

    Không viết lại câu ở đây — ``format_futures_brief`` là nguồn duy nhất, nên
    sửa một chữ ở đó là cả bảng HTML lẫn terminal đổi theo.
    """
    from src.ta.format import format_futures_brief

    items = [ln[2:] for ln in format_futures_brief(fsnap, None, ref_date=ref_date)
             if ln.startswith("- ")]
    if not items:
        return ""
    body = "".join(f"<li>{_esc_md(i)}</li>" for i in items)
    return ('<div class="card"><b>Bối cảnh phái sinh</b>'
            f"<ul>{body}</ul></div>")


def write_html(ranking: Ranking, out_dir: Optional[str] = None,
               top: int = 20) -> Optional[str]:
    """The board: four ranked lists, one sortable master table, then every symbol."""
    if not ranking.rows:
        return None

    by_trend_up, _ = sort_rows(ranking.rows, "trend", True, side=UP, limit=top)
    by_trend_down, _ = sort_rows(ranking.rows, "trend", False, side=DOWN, limit=top)
    by_bull, _ = sort_rows(ranking.rows, "confidence", True, bias=BULLISH, limit=top)
    by_bear, _ = sort_rows(ranking.rows, "confidence", True, bias=BEARISH, limit=top)

    parts: List[str] = [
        "<!DOCTYPE html>", '<html lang="vi">', "<head>", '<meta charset="UTF-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        f"<title>Xếp hạng kỹ thuật {_esc(ranking.as_of)}</title>",
        f"<style>{REPORT_CSS}{RANK_CSS}</style>", "</head>", "<body>", '<div class="wrap">',
        f"<h1>Bảng xếp hạng kỹ thuật — {_esc(ranking.as_of)}</h1>",
        f'<div class="sub">{len(ranking.rows)} mã · nhóm <b>{_esc(ranking.universe)}</b> · '
        f"dựng lúc {_esc(ranking.generated)}</div>",
        _asof_html(ranking.as_of_requested, ranking.as_of),
        '<div class="card legend">'
        "<b>Cường độ xu hướng</b> (−100…+100) = ADX×hướng (±30) + xếp tầng EMA (±25) + "
        "chuỗi swing &amp; BOS/CHoCH (±25) + quãng đường 20 phiên đo bằng ATR (±20). "
        f"Dưới |{TREND_SIDE_MIN:.0f}| điểm coi như đi ngang.<br>"
        "<b>Độ tin cậy mẫu hình</b> (0…100) = lượng bằng chứng đã có, không phải kích thước "
        "kỳ vọng: đã phá mốc chưa · nến tại vùng quyết định · volume xác nhận · retest giữ hay "
        "mất.<br>"
        "<b>Phơi nhiễm phái sinh</b> (0…100) = trong rổ VN30 (40) + beta so với VN30 (30) + "
        "tỷ trọng thanh khoản trong rổ (20) + biên độ phiên đáo hạn (10). Đây là đặc tính "
        "dài hạn của mã, không phải trạng thái phiên.<br>"
        "Ba cột này cố ý <b>không cộng vào nhau</b>. Mẫu hình đảo chiều đáng chú ý nhất luôn "
        "là mẫu hình đi ngược xu hướng đang chạy; và một mã cường độ +80 nằm ngoài rổ VN30 "
        "khác hẳn một mã cường độ +80 beta 1,6 sát ngày đáo hạn — gộp lại là xoá đúng chỗ "
        "khác nhau đó.<br>"
        "⚠️ = EMA và cấu trúc swing đang đọc ngược nhau. Bấm vào tiêu đề cột để sắp xếp lại."
        "</div>",
        _futures_context_html(ranking.futures, ranking.as_of),
        f"<h2>▲ Xu hướng tăng — {len(by_trend_up)} mã mạnh nhất</h2>",
    ]
    parts += _rank_table(by_trend_up, "trend")
    parts.append(f"<h2>▼ Xu hướng giảm — {len(by_trend_down)} mã yếu nhất</h2>")
    parts += _rank_table(by_trend_down, "trend")
    parts.append("<h2>▲ Mẫu hình tăng — theo độ tin cậy</h2>")
    parts += _rank_table(by_bull, "pattern")
    parts.append("<h2>▼ Mẫu hình giảm — theo độ tin cậy</h2>")
    parts += _rank_table(by_bear, "pattern")
    by_futures, _ = sort_rows(ranking.rows, "futures", True, limit=top)
    if any(r.futures and r.futures.beta is not None for r in by_futures):
        parts.append("<h2>⚙️ Chịu dòng tiền phái sinh nhiều nhất</h2>")
        parts += _rank_table(by_futures, "futures")

    parts += [
        f"<h2>Toàn bộ {len(ranking.rows)} mã</h2>",
        '<div class="tools">',
        '<input id="filter" type="search" placeholder="Lọc theo mã…">',
        '<button data-mode="all" class="on">Tất cả</button>',
        '<button data-mode="up">Chỉ xu hướng tăng</button>',
        '<button data-mode="down">Chỉ xu hướng giảm</button>',
        '<button data-mode="flat">Đi ngang</button>',
        "</div>",
        '<div class="scroll">', '<table data-sortable id="all-table">', "<thead>",
        "<tr><th>Mã</th><th class='num'>Giá</th><th class='num'>+/-</th>"
        "<th class='num'>5 phiên</th><th class='num'>20 phiên</th>"
        "<th class='num'>Cường độ</th><th class='num'>ADX</th><th class='num'>RSI</th>"
        "<th class='num'>RVOL</th>"
        "<th class='num'>β VN30</th><th class='num'>Phái sinh</th>"
        "<th>Mẫu hình</th><th class='num'>Tin cậy</th>"
        "<th>Trạng thái</th><th class='num'>Mục tiêu</th><th class='num'>Huỷ</th>"
        "<th>Hộp</th></tr>", "</thead>", "<tbody>",
    ]
    for r in ranking.rows:
        p = r.pattern
        box_cell = (f"{_num(r.box_bottom)}–{_num(r.box_top)}"
                    if r.box_top is not None else "—")
        parts.append(
            f'<tr data-side="{r.trend.side}">'
            f'<td data-v="{_esc(r.symbol)}"><b>{_esc(r.symbol)}</b></td>'
            f'<td class="num" data-v="{r.close if r.close is not None else ""}">'
            f"{_num(r.close)}</td>"
            f'<td class="num" data-v="{r.change_pct if r.change_pct is not None else ""}">'
            f"{_signed_html(r.change_pct)}</td>"
            f'<td class="num" data-v="{r.change_5d if r.change_5d is not None else ""}">'
            f"{_signed_html(r.change_5d)}</td>"
            f'<td class="num" data-v="{r.change_20d if r.change_20d is not None else ""}">'
            f"{_signed_html(r.change_20d)}</td>"
            f'<td class="num" data-v="{r.trend.score}">'
            f"{_side_cell(r.trend.score, r.trend.side)}</td>"
            f'<td class="num" data-v="{r.trend.adx if r.trend.adx is not None else ""}">'
            f"{_num(r.trend.adx, 1)}</td>"
            f'<td class="num" data-v="{r.rsi if r.rsi is not None else ""}">'
            f"{_num(r.rsi, 1)}</td>"
            f'<td class="num" data-v="{r.rvol if r.rvol is not None else ""}">'
            f"{_num(r.rvol, 2)}</td>"
            f'<td class="num" data-v="{r.beta_vn30 if r.beta_vn30 is not None else ""}">'
            f'{"★ " if (r.futures and r.futures.in_vn30) else ""}{_num(r.beta_vn30, 2)}</td>'
            f'<td class="num" data-v="{r.futures_score if r.futures_score is not None else ""}">'
            f"{_num(r.futures_score, 0)}</td>"
            f'<td data-v="{_esc(p.name)}">{BIAS_MARK.get(p.bias, "•")} {_esc(p.name)}</td>'
            f'<td class="num" data-v="{p.confidence}">{p.confidence:.0f}</td>'
            f'<td data-v="{p.rank}"><span class="pill {p.state}">'
            f"{_esc(CONFIDENCE_VN[p.state])}</span></td>"
            f'<td class="num" data-v="{r.target_pct if r.target_pct is not None else ""}">'
            f"{_num(p.target)}</td>"
            f'<td class="num" data-v="{p.invalidation if p.invalidation is not None else ""}">'
            f"{_num(p.invalidation)}</td>"
            f'<td data-v="{r.box_position if r.box_position is not None else ""}">'
            f"{_esc(box_cell)}</td></tr>"
        )
    parts += ["</tbody>", "</table>", "</div>"]

    parts.append('<h2>Chi tiết từng mã</h2><div class="detail">')
    for r in sorted(ranking.rows, key=lambda x: x.symbol):
        p = r.pattern
        parts.append(f"<h3>{_esc(r.symbol)} — {_esc(r.as_of)} · "
                     f"{_side_cell(r.trend.score, r.trend.side)} · {_conf_cell(p)}</h3>")
        parts.append('<div class="card"><ul>')
        parts.append(f"<li><b>Xu hướng:</b> {_esc(r.trend.note)}</li>")
        if r.trend.conflict:
            parts.append("<li>⚠️ EMA đọc <b>"
                         f"{_esc(SIDE_VN[r.trend.ema_side])}</b> còn cấu trúc swing đọc <b>"
                         f"{_esc(SIDE_VN[r.trend.structure_side])}</b> — chỗ lệch này chính "
                         "là thông tin, đừng gộp lại thành một nhãn.</li>")
        parts.append(f"<li><b>Mẫu hình:</b> {_esc(SOURCE_VN.get(p.source, p.source))} · "
                     f"{_esc(p.name)} · {_esc(CONFIDENCE_VN[p.state])} "
                     f"({p.confidence:.0f}/100)</li>")
        if p.note:
            parts.append(f"<li>{_esc(p.note)}</li>")
        if p.missing:
            parts.append(f"<li>Còn thiếu: {_esc(', '.join(p.missing))}</li>")
        for item in r.brief:
            parts.append(f"<li>{_esc_md(item)}</li>")
        if r.futures is not None and r.futures.beta is not None:
            e = r.futures
            share = ("" if e.liquidity_share_pct is None
                     else f" · {e.liquidity_share_pct:.2f}% thanh khoản rổ")
            parts.append(
                f"<li><b>Phái sinh:</b> {_esc(e.channel)} · β {_num(e.beta, 2)} "
                f"(R² {_num(e.r2, 2)}){_esc(share)} · biên độ phiên đáo hạn "
                f"{_num(e.expiry_move_ratio, 2)}× phiên thường</li>"
            )
        parts.append("</ul></div>")
    parts.append("</div>")

    if ranking.skipped:
        parts.append("<h2>Bỏ qua</h2><div class='card'><ul>")
        for note in ranking.skipped:
            parts.append(f"<li>{_esc(note)}</li>")
        parts.append("</ul></div>")

    parts += [
        '<div class="foot">Số liệu kỹ thuật thuần tuý, không phải khuyến nghị đầu tư — '
        "quyết định vào lệnh là của bạn.</div>",
        "</div>", f"<script>{_SORT_JS}</script>", "</body>", "</html>",
    ]

    path = _out_root(out_dir, ranking) / f"{_stem(ranking)}.html"
    path.write_text("\n".join(parts), encoding="utf-8")
    return str(path)
