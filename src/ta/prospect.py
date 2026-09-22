"""Danh sách **triển vọng cao** — một cột thứ tư, đứng cạnh ba cột kia.

``ranking.py`` cố ý *không* cộng ba trục của nó vào nhau, và lý do vẫn đúng
nguyên: cường độ xu hướng, độ tin cậy mẫu hình và phơi nhiễm phái sinh trả lời
ba câu hỏi khác nhau, gộp lại là giấu mất đúng chỗ chúng nói ngược nhau.

Module này làm một việc khác, không phá quy ước đó: nó **lọc** cả rổ xuống một
danh sách ứng viên theo một câu hỏi cụ thể — *mã nào đang có một tư thế tăng
giá đáng nhìn kỹ* — rồi chấm các ứng viên đó bằng một điểm tổng hợp. Ba điều
kiện giữ cho việc này không thành "điểm cổ phiếu" mà ``CLAUDE.md`` cấm:

1. Điểm tổng hợp **luôn in kèm từng thành phần**, mỗi thành phần có trần
   riêng và có câu giải thích của chính nó. Một dòng 72 điểm luôn tháo ra được
   thành "mẫu hình 26 + breakout 21 + RSI 15 + …".
2. Nó **không đụng** tới ba cột cũ. Bảng xếp hạng vẫn nguyên như trước; đây là
   một bảng riêng, một file riêng.
3. Phần tin tức **không cộng vào phần đo được**. ``base_score`` là thứ tính
   được từ giá và sổ sách; ``NewsVerdict.score`` là nhận định của một model
   ngôn ngữ, mang dấu, và luôn hiện ra thành một cột riêng. Cộng lại chỉ ở
   ``total``, và ``total`` không bao giờ đứng một mình.

**RSI: đường cong, không phải cửa sổ.** Yêu cầu là "lý tưởng 0,4–0,6", nhưng
tiêu chí 1 và 2 (mẫu hình tăng + breakout xác nhận bằng volume) tự chúng kéo
RSI lên 62–72 — một mã vừa phá hộp bằng volume 2× gần như không bao giờ còn
RSI 50. Cửa sổ cứng 40–60 sẽ loại đúng những mã mà hai tiêu chí đầu vừa chọn
ra. Nên vùng đầy điểm giữ đúng 40–60 như yêu cầu, rồi **giảm dần** thay vì cắt
phựt: 65 vẫn còn hơn nửa điểm, 75 về 0, trên 85 thành điểm âm thật sự. Cả
đường cong nằm trong ``RSI_CURVE`` — đổi khẩu vị là sửa một chỗ.

**Thanh khoản là cửa, không phải điểm.** Một mẫu hình đẹp trên mã không ai mua
bán được là một mẫu hình không dùng được, và cho nó "ít điểm thanh khoản" thì
nó vẫn trèo lên đầu bảng nhờ các cột khác. Nên nó loại thẳng, và mã bị loại
vẫn được liệt kê kèm lý do — danh sách những mã *suýt* vào cũng là thông tin.
"""
import html as html_escape
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from src.ta import asof as asof_mod
from src.ta import sector as sector_mod
from src.ta.boxes import (
    BREAKOUT_UP_CONFIRMED, BREAKOUT_UP_WEAK, FALSE_BREAKOUT_UP, INSIDE,
)
from src.ta.fundamentals import Fundamentals
from src.ta.loader import PROJECT_ROOT
from src.ta.ranking import (
    BEARISH, BULLISH, CONFIRMED, CONFIDENCE_VN, PARTIAL, PatternRank, Ranking,
    SymbolRank,
)
from src.ta.sector import RelativeStrength, SectorView

REPORT_DIR = PROJECT_ROOT / "reports"
#: Bản trỏ cố định, cùng vai với ``ranking.LATEST_JSON``.
LATEST_JSON = REPORT_DIR / "trien_vong_moi_nhat.json"

#: Giá trị khớp lệnh trung bình 20 phiên, tính bằng **tỷ đồng/phiên**. 20 tỷ
#: loại khoảng 5% mỏng nhất của rổ 79 mã hiện tại — đủ để chặn mã không giao
#: dịch được, chưa tới mức chỉ còn VN30. Tham số của ``build`` nên nâng được.
LIQUIDITY_MIN_BN = 20.0

# --- trần từng thành phần; tổng đúng 100 -----------------------------------
MAX_PATTERN = 30.0
MAX_BREAKOUT = 25.0
MAX_RSI = 15.0
MAX_RS = 12.0
MAX_VALUE = 12.0
MAX_INSIDER = 6.0
#: Trần của phần tin tức, **nằm ngoài 100 điểm trên**. Mang dấu: tin xấu trừ
#: đúng bằng mức tin tốt cộng.
MAX_NEWS = 25.0

#: Trần điểm trừ cờ đỏ — **một nửa** thang đo được, và luôn âm.
#:
#: Con số 50 không phải khẩu vị, nó là một phát biểu về thứ tự: không có mẫu
#: hình nào đẹp tới mức bù được việc chủ tịch đang bị tạm giam. Một mã +80 nhờ
#: mẫu hình + breakout + RSI mà dính án hình sự phải rơi xuống 30 và đứng dưới
#: một mã +45 sạch cờ — vì +80 kia đo cái *đã xảy ra trên biểu đồ*, còn cái cờ
#: nói về cái *sắp xảy ra với doanh nghiệp*, và biểu đồ chưa kịp biết.
#:
#: Nó nằm **trong** ``base_score`` chứ không đứng riêng như ``NewsVerdict``, và
#: chỗ đó có lý: cờ đỏ là một phép **đo** — cùng một kho tin, cùng bộ luật, hai
#: lần chạy ra hai kết quả giống hệt, và mỗi điểm trừ truy được về một tiêu đề
#: có thật. ``NewsVerdict`` thì là *nhận định* của một model ngôn ngữ. Hai thứ
#: khác loại, nên chúng không được gộp — nhưng cái đo được thì thuộc về phần
#: đo được.
MAX_REDFLAG = 50.0

#: Điểm RSI theo mức RSI14. Xem docstring module về lý do không cắt phựt ở 60.
RSI_CURVE: Tuple[Tuple[float, float], ...] = (
    (20.0, -6.0),    # bán tháo, chưa có gì đỡ
    (30.0, 0.0),
    (40.0, MAX_RSI),         # mép dưới vùng lý tưởng người dùng nêu
    (60.0, MAX_RSI),         # mép trên
    (65.0, 9.0),
    (70.0, 4.0),
    (75.0, 0.0),
    (85.0, -12.0),
    (95.0, -20.0),   # quá mua cực đoan — vào lúc này là mua đúng đỉnh nhịp
)

#: Hệ số theo trạng thái mẫu hình. Điểm tin cậy đã phản ánh phần lớn trạng
#: thái rồi, nhưng ``CLAUDE.md`` yêu cầu trạng thái phải xếp trước điểm số:
#: "đã xác nhận 70" phải hơn "chưa xác nhận 95".
STATE_FACTOR = {CONFIRMED: 1.0, PARTIAL: 0.8, "pending": 0.55,
                "conflict": 0.3, "failed": 0.0, "none": 0.0}

EX_LIQUIDITY = "thanh_khoan"
EX_BEARISH = "mau_hinh_giam"
EX_NO_DATA = "thieu_du_lieu"
EXCLUDE_VN = {
    EX_LIQUIDITY: "thanh khoản dưới ngưỡng",
    EX_BEARISH: "mẫu hình giảm đã xác nhận",
    EX_NO_DATA: "thiếu dữ liệu để chấm",
}


def _ramp(value: float, curve: Sequence[Tuple[float, float]]) -> float:
    """Nội suy tuyến tính từng khúc, giữ phẳng ngoài hai đầu."""
    if value <= curve[0][0]:
        return curve[0][1]
    for (x0, y0), (x1, y1) in zip(curve, curve[1:]):
        if value <= x1:
            span = x1 - x0
            return y0 if span == 0 else y0 + (y1 - y0) * (value - x0) / span
    return curve[-1][1]


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


@dataclass(frozen=True)
class BoxFacts:
    """Bốn sự kiện của hộp mà điểm breakout cần, tách khỏi ``Box``.

    ``SymbolRank`` đã mang sẵn cả bốn, nên dựng từ nó là xong — không phải
    dựng lại ``Structure`` cho 79 mã chỉ để đọc bốn trường. Kiểu này cũng
    duck-type đúng với ``boxes.Box`` thật, nên test truyền thẳng ``Box`` vào
    ``breakout_points`` vẫn chạy.
    """
    state: str = ""
    breakout_volume_x: Optional[float] = None
    bars_since_breakout: Optional[int] = None
    position_pct: Optional[float] = None
    retest_held: Optional[bool] = None

    @property
    def retest(self):
        """Đứng thay ``Box.retest`` — chỉ trường ``held`` được đọc tới."""
        if self.retest_held is None:
            return None
        return type("_R", (), {"held": self.retest_held})()

    @classmethod
    def of(cls, row: "SymbolRank") -> "BoxFacts":
        return cls(
            state=getattr(row, "box_state", "") or "",
            breakout_volume_x=getattr(row, "box_breakout_volume_x", None),
            bars_since_breakout=getattr(row, "box_bars_since_breakout", None),
            position_pct=getattr(row, "box_position", None),
            retest_held=getattr(row, "box_retest_held", None),
        )


# ---------------------------------------------------------------------------
# cấu trúc
# ---------------------------------------------------------------------------
@dataclass
class Component:
    """Một thành phần điểm — luôn mang theo trần và lý do của chính nó."""
    key: str
    label: str
    points: float
    max_points: float
    note: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class NewsVerdict:
    """Nhận định của model ngôn ngữ về tin tức + triển vọng ngành.

    Cố ý **không** phải một công thức. Một dòng "lãi ròng giảm 50% nhưng vượt
    20% kế hoạch năm" không có luật regex nào đọc đúng được (§9.9 của plan), và
    đó chính là chỗ model ngôn ngữ hơn hẳn. Đổi lại, mọi trường ở đây là *ý
    kiến* — nên chúng đứng riêng khỏi ``base_score``, mang theo ``source`` để
    biết ai chấm, và ``evidence_sessions`` để truy ngược về phiên đã đọc.
    """
    score: float                      # -25..+25
    label: str = ""                   # một cụm: "tin tốt rõ", "trung tính"…
    summary: str = ""
    good: List[str] = field(default_factory=list)
    bad: List[str] = field(default_factory=list)
    sector_outlook: str = ""
    confidence: str = ""              # cao | trung bình | thấp
    source: str = ""                  # "claude" | "gemini:<model>"
    scored_at: str = ""
    as_of: str = ""
    n_items: int = 0
    evidence_sessions: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "NewsVerdict":
        known = set(cls.__dataclass_fields__)
        raw = {k: v for k, v in (data or {}).items() if k in known}
        raw["score"] = _clamp(float(raw.get("score") or 0.0), -MAX_NEWS, MAX_NEWS)
        return cls(**raw)


@dataclass
class ProspectRow:
    """Một ứng viên, kèm mọi thứ đã dùng để chấm nó."""
    symbol: str
    as_of: str
    close: Optional[float]
    change_20d: Optional[float]
    rsi: Optional[float]
    rvol: Optional[float]
    liquidity_bn: Optional[float]
    components: List[Component] = field(default_factory=list)
    base_score: float = 0.0
    news: Optional[NewsVerdict] = None
    sector: Optional[SectorView] = None
    rs: Optional[RelativeStrength] = None
    fundamentals: Optional[Fundamentals] = None
    insider_label: str = ""
    #: ``src.news.redflag.RedFlags`` — ``None`` = chưa quét được, khác với một
    #: ``RedFlags`` rỗng (đã quét, không thấy gì).
    redflags: Optional[Any] = None
    pattern_name: str = ""
    pattern_state: str = ""
    trigger: Optional[float] = None
    target: Optional[float] = None
    invalidation: Optional[float] = None
    excluded: str = ""                # khoá lý do loại, rỗng = còn trong danh sách
    excluded_note: str = ""
    warnings: List[str] = field(default_factory=list)

    @property
    def total(self) -> float:
        """Điểm đo được + nhận định tin. Không bao giờ in một mình."""
        return round(self.base_score + (self.news.score if self.news else 0.0), 1)

    @property
    def news_scored(self) -> bool:
        return self.news is not None

    @property
    def sector_label(self) -> str:
        return self.sector.label if self.sector else sector_mod.sector_label(
            sector_mod.sector_of(self.symbol))

    def component(self, key: str) -> Optional[Component]:
        return next((c for c in self.components if c.key == key), None)

    @property
    def why(self) -> str:
        """Các thành phần có điểm, xếp từ đóng góp lớn nhất."""
        parts = sorted((c for c in self.components if abs(c.points) >= 0.5),
                       key=lambda c: -abs(c.points))
        return " · ".join(f"{c.label} {c.points:+.0f}" for c in parts)

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol, "as_of": self.as_of, "close": self.close,
            "change_20d": self.change_20d, "rsi": self.rsi, "rvol": self.rvol,
            "liquidity_bn": self.liquidity_bn,
            "components": [c.to_dict() for c in self.components],
            "base_score": self.base_score, "total": self.total,
            "news": self.news.to_dict() if self.news else None,
            "sector": self.sector.to_dict() if self.sector else None,
            "rs": self.rs.to_dict() if self.rs else None,
            "fundamentals": self.fundamentals.to_dict() if self.fundamentals else None,
            "insider_label": self.insider_label,
            "redflags": self.redflags.to_dict() if self.redflags else None,
            "pattern_name": self.pattern_name, "pattern_state": self.pattern_state,
            "trigger": self.trigger, "target": self.target,
            "invalidation": self.invalidation,
            "excluded": self.excluded, "excluded_note": self.excluded_note,
            "warnings": list(self.warnings),
            "why": self.why,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ProspectRow":
        raw = dict(data)
        for derived in ("total", "why"):
            raw.pop(derived, None)
        raw["components"] = [Component(**c) for c in raw.get("components") or []]
        news = raw.get("news")
        raw["news"] = NewsVerdict.from_dict(news) if news else None
        sec = raw.get("sector")
        raw["sector"] = SectorView.from_dict(sec) if sec else None
        rs = raw.get("rs")
        raw["rs"] = RelativeStrength.from_dict(rs) if rs else None
        fund = raw.get("fundamentals")
        raw["fundamentals"] = Fundamentals.from_dict(fund) if fund else None
        rflags = raw.get("redflags")
        if rflags:
            from src.news.redflag import RedFlags
            raw["redflags"] = RedFlags.from_dict(rflags)
        else:
            raw["redflags"] = None
        known = set(cls.__dataclass_fields__)
        return cls(**{k: v for k, v in raw.items() if k in known})


@dataclass
class ProspectBoard:
    as_of: str
    generated: str
    universe: str
    rows: List[ProspectRow] = field(default_factory=list)
    excluded: List[ProspectRow] = field(default_factory=list)
    as_of_requested: str = ""
    min_liquidity_bn: float = LIQUIDITY_MIN_BN
    notes: List[str] = field(default_factory=list)
    html_path: str = ""
    json_path: str = ""

    @property
    def scored_rows(self) -> List[ProspectRow]:
        """Ứng viên, xếp theo tổng điểm — mã đã có điểm tin đứng trước."""
        return sorted(self.rows, key=lambda r: (-r.total, r.symbol))

    @property
    def n_news_scored(self) -> int:
        return sum(1 for r in self.rows if r.news_scored)

    def get(self, symbol: str) -> Optional[ProspectRow]:
        sym = symbol.strip().upper()
        return next((r for r in self.rows + self.excluded
                     if r.symbol.upper() == sym), None)

    def to_dict(self) -> dict:
        return {
            "as_of": self.as_of, "generated": self.generated,
            "universe": self.universe, "as_of_requested": self.as_of_requested,
            "min_liquidity_bn": self.min_liquidity_bn, "notes": list(self.notes),
            "html_path": self.html_path, "json_path": self.json_path,
            "rows": [r.to_dict() for r in self.rows],
            "excluded": [r.to_dict() for r in self.excluded],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ProspectBoard":
        raw = dict(data)
        raw["rows"] = [ProspectRow.from_dict(r) for r in raw.get("rows") or []]
        raw["excluded"] = [ProspectRow.from_dict(r) for r in raw.get("excluded") or []]
        known = set(cls.__dataclass_fields__)
        return cls(**{k: v for k, v in raw.items() if k in known})


# ---------------------------------------------------------------------------
# từng thành phần điểm
# ---------------------------------------------------------------------------
def pattern_points(pattern: PatternRank) -> Component:
    """Tiêu chí 1 — mẫu hình tăng giá, và bằng chứng của nó đã tới đâu."""
    if pattern.bias != BULLISH or pattern.state in ("failed", "none"):
        why = ("mẫu hình giảm" if pattern.bias == BEARISH
               else "không có mẫu hình tăng nào đang chạy")
        return Component("pattern", "Mẫu hình tăng", 0.0, MAX_PATTERN, why)
    factor = STATE_FACTOR.get(pattern.state, 0.0)
    pts = round(MAX_PATTERN * (pattern.confidence / 100.0) * factor, 1)
    note = f"{pattern.name} — {CONFIDENCE_VN.get(pattern.state, pattern.state)}"
    if pattern.missing:
        note += f" (còn thiếu: {', '.join(pattern.missing[:2])})"
    return Component("pattern", "Mẫu hình tăng", pts, MAX_PATTERN, note)


def breakout_points(box, pattern: PatternRank,
                    rvol: Optional[float]) -> Component:
    """Tiêu chí 2 — đã phá mốc chưa, và volume có xác nhận không.

    Hộp tích luỹ là chỗ đọc được thẳng nhất: nó mang sẵn ``breakout_volume_x``
    (volume phiên phá so với nền). Khi mẫu hình đến từ mô hình đảo chiều chứ
    không phải hộp, phiên phá neckline vẫn là một cú phá — nhưng bội số volume
    lúc đó nằm trong tầng hợp lưu, không lộ ra thành số, nên rơi về ``rvol``
    phiên gần nhất và nói rõ đó là số thay thế.
    """
    state = getattr(box, "state", None)
    vol_x = getattr(box, "breakout_volume_x", None)
    bars = getattr(box, "bars_since_breakout", None)

    if state == BREAKOUT_UP_CONFIRMED:
        pts = 16.0
        note = "đã phá cạnh trên hộp, xác nhận"
        if vol_x:
            bonus = _ramp(vol_x, ((1.0, 0.0), (1.5, 4.0), (2.5, 7.0)))
            pts += bonus
            note += f", volume {vol_x:.1f}× nền"
        retest = getattr(box, "retest", None)
        if retest is not None and getattr(retest, "held", False):
            pts += 2.0
            note += ", retest giữ được"
        if bars is not None and bars > 15:
            pts -= 4.0
            note += f" (đã {bars} phiên — không còn mới)"
        return Component("breakout", "Breakout + volume",
                         round(_clamp(pts, 0.0, MAX_BREAKOUT), 1), MAX_BREAKOUT, note)

    if state == BREAKOUT_UP_WEAK:
        return Component("breakout", "Breakout + volume", 8.0, MAX_BREAKOUT,
                         "đã phá cạnh trên nhưng volume chưa xác nhận")

    if state == FALSE_BREAKOUT_UP:
        return Component("breakout", "Breakout + volume", 0.0, MAX_BREAKOUT,
                         "phá lên rồi tụt lại vào hộp — breakout hỏng")

    # Mô hình đảo chiều đã xác nhận: phiên phá neckline là cú phá thật.
    if pattern.bias == BULLISH and pattern.state == CONFIRMED \
            and pattern.bars_since_break is not None:
        pts = 12.0
        note = f"đã phá mốc kích hoạt {pattern.bars_since_break} phiên trước"
        if rvol:
            bonus = _ramp(rvol, ((1.0, 0.0), (1.5, 3.0), (2.5, 5.0)))
            pts += bonus
            note += f", RVOL hiện tại {rvol:.1f}× (số thay thế cho volume phiên phá)"
        return Component("breakout", "Breakout + volume",
                         round(_clamp(pts, 0.0, MAX_BREAKOUT), 1), MAX_BREAKOUT, note)

    if state == INSIDE:
        pos = getattr(box, "position_pct", None)
        if pos is not None and pos >= 85:
            return Component("breakout", "Breakout + volume", 4.0, MAX_BREAKOUT,
                             f"còn trong hộp, sát cạnh trên ({pos:.0f}%) — chưa phá")
        return Component("breakout", "Breakout + volume", 0.0, MAX_BREAKOUT,
                         "còn nằm trong hộp tích luỹ")

    return Component("breakout", "Breakout + volume", 0.0, MAX_BREAKOUT,
                     "chưa có cú phá mốc nào đo được")


def rsi_points(rsi: Optional[float]) -> Component:
    """Tiêu chí 3 — RSI, đủ điểm ở 40–60 rồi giảm dần, quá mua thì âm."""
    if rsi is None:
        return Component("rsi", "RSI14", 0.0, MAX_RSI, "không tính được RSI")
    pts = round(_ramp(rsi, RSI_CURVE), 1)
    if 40 <= rsi <= 60:
        note = f"RSI {rsi:.1f} — trong vùng lý tưởng 40–60"
    elif rsi > 60:
        note = (f"RSI {rsi:.1f} — trên vùng lý tưởng"
                + (", quá mua, trừ điểm" if pts < 0 else ", còn chấp nhận được"))
    else:
        note = f"RSI {rsi:.1f} — dưới vùng lý tưởng, động lượng còn yếu"
    return Component("rsi", "RSI14", pts, MAX_RSI, note)


def rs_points(rs: Optional[RelativeStrength]) -> Component:
    """Tiêu chí 5a — khoẻ hơn thị trường và hơn chính ngành của nó bao nhiêu."""
    if rs is None or (rs.vs_market is None and rs.vs_sector is None):
        return Component("rs", "Sức mạnh tương đối", 0.0, MAX_RS,
                         "chưa so được (thiếu mốc thị trường hoặc ngành quá ít mã)")
    curve = ((-10.0, -4.0), (0.0, 0.0), (10.0, 6.0))
    pts, bits = 0.0, []
    if rs.vs_market is not None:
        pts += _ramp(rs.vs_market, curve)
        bits.append(f"thị trường {rs.vs_market:+.1f}pp")
    if rs.vs_sector is not None:
        pts += _ramp(rs.vs_sector, curve)
        bits.append(f"ngành {rs.vs_sector:+.1f}pp")
    return Component("rs", "Sức mạnh tương đối",
                     round(_clamp(pts, -8.0, MAX_RS), 1), MAX_RS,
                     f"{rs.sessions} phiên, hơn/kém " + " · ".join(bits))


def valuation_points(fund: Optional[Fundamentals]) -> Component:
    """Tiêu chí 5b — định giá và chất lượng so với **trung bình ngành**.

    Mẫu số là ``industryValue`` của chính FireAnt, không phải trung bình 79 mã
    trong ``data/``: ngành thật có hàng trăm mã, còn rổ ở đây là một lát cắt.
    """
    if fund is None or fund.is_empty:
        return Component("value", "Định giá vs ngành", 0.0, MAX_VALUE,
                         "chưa có ảnh chụp chỉ số cơ bản")
    curve = ((-30.0, -2.0), (0.0, 0.0), (30.0, 3.0))
    pts, bits, seen = 0.0, [], 0
    from src.ta.fundamentals import QUALITY_KEYS, VALUATION_KEYS
    for key in VALUATION_KEYS + QUALITY_KEYS:
        gap = fund.gap(key)
        if gap is None:
            continue
        seen += 1
        pts += _ramp(gap, curve)
        bits.append(f"{key} {gap:+.0f}%")
    if not seen:
        return Component("value", "Định giá vs ngành", 0.0, MAX_VALUE,
                         "ảnh chụp không có chỉ số so ngành nào đọc được")
    stale = ""
    if fund.stale_days:
        stale = f" · ảnh chụp cách {fund.stale_days} ngày"
    return Component("value", "Định giá vs ngành",
                     round(_clamp(pts, -6.0, MAX_VALUE), 1), MAX_VALUE,
                     "so ngành: " + " · ".join(bits) + stale)


def redflag_points(rf) -> Component:
    """Tiêu chí 6 — sự kiện pháp lý/quản trị đủ nặng để lật ngược tư thế.

    Thành phần **duy nhất chỉ mang dấu âm** trong bảng này, và là thành phần
    duy nhất có thể một mình quyết định thứ hạng. ``note`` luôn mang theo tiêu
    đề của cờ nặng nhất: một điểm trừ 50 mà không nói vì sao thì không khác gì
    một lời đồn.

    **Phán quyết của model không làm cột này thành nhận định**, và ranh giới đó
    phải giữ: một cờ bị bác chỉ *thôi trừ điểm*, nó **không bao giờ cộng điểm**,
    kể cả khi model kết luận tin đó có lợi cho mã. Ý kiến "tin này tốt" vẫn chỉ
    sống ở ``NewsVerdict.score`` — chỗ duy nhất được phép mang nhận định, và nó
    chỉ gặp ``base_score`` ở ``total``. Model quyết định *cờ có áp cho mã này
    không* và *nặng tới đâu*; độ lớn vẫn do trọng số nhóm và ``LEVEL_FACTOR``
    của code tính ra.

    Năm trạng thái, năm câu khác nhau — gộp bất kỳ hai cái nào là nói về dữ
    liệu chưa tồn tại hoặc giấu mất việc đã có người can thiệp.
    """
    if rf is None:
        return Component("redflag", "Cờ đỏ", 0.0, MAX_REDFLAG,
                         "⚠️ chưa quét được kho tin — đây là *chưa biết*, "
                         "không phải *không có cờ*")
    dismissed = getattr(rf, "dismissed", None) or []
    who = ", ".join(getattr(rf, "judged_by", None) or []) or "model"
    if rf.is_empty and dismissed:
        return Component(
            "redflag", "Cờ đỏ", 0.0, MAX_REDFLAG,
            f"{len(dismissed)} ứng viên đều bị {who} bác sau khi đọc nguyên văn "
            f"(máy chấm −{rf.penalty_raw:.0f} trước đó) — khác với *không có cờ nào*")
    if rf.is_empty:
        return Component("redflag", "Cờ đỏ", 0.0, MAX_REDFLAG,
                         f"không có cờ nào trong {rf.window_days} ngày "
                         f"({rf.n_scanned} bài đã quét)")
    top = rf.flags[0]
    groups = ", ".join(f.label for f in rf.flags[:3])
    state = f" · ⏳ {rf.n_pending}/{len(rf.flags)} **chưa ai đọc**" \
        if rf.n_pending else f" · đã qua lượt đọc của {who}"
    if dismissed:
        state += f" · {len(dismissed)} ứng viên khác đã bị bác"
    return Component(
        "redflag", "Cờ đỏ", -round(rf.penalty, 1), MAX_REDFLAG,
        f"{rf.level_label} · {len(rf.flags)} đầu mục ({groups}){state} · nặng "
        f"nhất: “{top.title.strip()}” ({top.published[:10]})")


def insider_points(flow) -> Component:
    """Tiêu chí 5c — người trong nhà đang mua hay bán, chuẩn hoá theo free float."""
    if flow is None or flow.is_empty:
        return Component("insider", "Giao dịch nội bộ", 0.0, MAX_INSIDER,
                         "không có giao dịch nội bộ trong 90 ngày")
    ratio = flow.net_ratio_pct
    if ratio is None:
        return Component("insider", "Giao dịch nội bộ", 0.0, MAX_INSIDER,
                         "có giao dịch nhưng thiếu freeShares để chuẩn hoá — "
                         "chưa so được giữa các mã")
    pts = _ramp(ratio, ((-0.5, -6.0), (0.0, 0.0), (0.5, 6.0)))
    if flow.registered_only:
        # Đăng ký là ý định, chưa phải sự thật. Vẫn tính, nhưng nửa trọng số.
        pts *= 0.5
    return Component("insider", "Giao dịch nội bộ",
                     round(_clamp(pts, -MAX_INSIDER, MAX_INSIDER), 1),
                     MAX_INSIDER, flow.label)


# ---------------------------------------------------------------------------
# chấm một dòng
# ---------------------------------------------------------------------------
def score_row(row: SymbolRank, box=None,
              fund: Optional[Fundamentals] = None,
              view: Optional[SectorView] = None,
              rs: Optional[RelativeStrength] = None,
              insider_flow=None, redflags=None,
              min_liquidity_bn: float = LIQUIDITY_MIN_BN) -> ProspectRow:
    """Một ``SymbolRank`` → một ``ProspectRow`` đã chấm xong phần đo được."""
    liquidity = getattr(row, "avg_value_bn", None)
    out = ProspectRow(
        symbol=row.symbol, as_of=row.as_of, close=row.close,
        change_20d=row.change_20d, rsi=row.rsi, rvol=row.rvol,
        liquidity_bn=liquidity,
        sector=view, rs=rs, fundamentals=fund, redflags=redflags,
        insider_label=(insider_flow.label if insider_flow else ""),
        pattern_name=row.pattern.name, pattern_state=row.pattern.state,
        trigger=row.pattern.trigger, target=row.pattern.target,
        invalidation=row.pattern.invalidation,
    )

    if liquidity is None:
        # Không đo được thanh khoản thì không phải "đạt ngưỡng" — để lọt qua
        # cửa là biến một khoảng trống dữ liệu thành một lời xác nhận.
        out.excluded = EX_NO_DATA
        out.excluded_note = ("không tính được giá trị khớp lệnh trung bình 20 phiên "
                             "nên chưa qua được cửa thanh khoản")
    elif liquidity < min_liquidity_bn:
        out.excluded = EX_LIQUIDITY
        out.excluded_note = (f"giá trị khớp lệnh trung bình {liquidity:.0f} tỷ/phiên, "
                             f"dưới ngưỡng {min_liquidity_bn:.0f} tỷ")
    elif row.pattern.bias == BEARISH and row.pattern.state in (CONFIRMED, PARTIAL):
        out.excluded = EX_BEARISH
        out.excluded_note = (f"{row.pattern.name} — "
                             f"{CONFIDENCE_VN.get(row.pattern.state, row.pattern.state)}")

    out.components = [
        pattern_points(row.pattern),
        breakout_points(box if box is not None else BoxFacts.of(row),
                        row.pattern, row.rvol),
        rsi_points(row.rsi),
        rs_points(rs),
        valuation_points(fund),
        insider_points(insider_flow),
        redflag_points(redflags),
    ]
    out.base_score = round(sum(c.points for c in out.components), 1)

    if redflags is None:
        out.warnings.append("chưa quét được cờ đỏ — điểm của mã này chưa trừ "
                            "phần sự kiện pháp lý/quản trị")
    elif redflags.has_critical:
        top = redflags.flags[0]
        out.warnings.append(
            f"🚩 CỜ ĐỎ HÌNH SỰ/THAO TÚNG: “{top.title.strip()}” "
            f"({top.published[:10]}) — đọc trước khi đọc mẫu hình")
    elif not redflags.is_empty:
        out.warnings.append(f"🚩 {redflags.headline}")
    if row.trend.conflict:
        out.warnings.append("EMA và cấu trúc swing đang nói ngược nhau")
    if view is not None and not view.comparable:
        out.warnings.append(view.note)
    if fund is None:
        out.warnings.append("chưa có ảnh chụp chỉ số cơ bản — phần định giá bằng 0")
    elif fund.stale_days and fund.stale_days > 30:
        out.warnings.append(
            f"ảnh chụp chỉ số cơ bản đã cũ {fund.stale_days} ngày")
    return out


def build(ranking: Ranking,
          min_liquidity_bn: float = LIQUIDITY_MIN_BN,
          as_of: Optional[datetime] = None,
          boxes: Optional[Dict[str, Any]] = None,
          news_scores: Optional[Dict[str, NewsVerdict]] = None,
          load_fundamentals: bool = True,
          load_insiders: bool = True,
          load_redflags: bool = True,
          rs_sessions: int = 20) -> ProspectBoard:
    """Cả rổ → danh sách triển vọng cao, **không tính lại gì từ giá**.

    ``ranking`` là kết quả ``ranking.build`` vừa chạy (hoặc đọc lại từ JSON).
    Ba nguồn còn lại — chỉ số cơ bản, ngành, giao dịch nội bộ — rẻ và đọc từ
    file, nên nạp thẳng ở đây.
    """
    from src.ta import fundamentals as fund_mod

    board = ProspectBoard(
        as_of=ranking.as_of,
        generated=datetime.now().strftime("%Y-%m-%d %H:%M"),
        universe=ranking.universe,
        as_of_requested=getattr(ranking, "as_of_requested", ""),
        min_liquidity_bn=min_liquidity_bn,
    )
    if not ranking.rows:
        board.notes.append("Bảng xếp hạng rỗng — chạy `build_ranking` trước.")
        return board

    views = sector_mod.build_all_views(ranking.rows)
    market = sector_mod.market_change(rs_sessions, as_of)
    if market is None:
        board.notes.append(
            "Không đọc được VNINDEX nên phần 'khoẻ hơn thị trường' để trống — "
            "chạy `/update` để nạp chỉ số.")

    # Cờ đỏ quét **một lượt cho cả rổ, trên một kết nối**: mở 79 kết nối
    # SQLite để hỏi cùng một bảng là trả giá cho không.
    flags_by_symbol: Dict[str, Any] = {}
    if load_redflags:
        from src.news import redflag as redflag_mod
        from src.news import rulings as rulings_mod
        try:
            flags_by_symbol = rulings_mod.apply_many(redflag_mod.build_many(
                [r.symbol for r in ranking.rows], as_of=as_of))
        except Exception as exc:        # noqa: BLE001
            board.notes.append(
                f"Không quét được cờ đỏ ({type(exc).__name__}) — cột cờ đỏ để "
                f"trống cho toàn bảng. Đó là *chưa biết*, không phải *sạch cờ*.")

    # Cả rổ 79 mã thì không ai ngồi đọc hết, nên phần lớn ứng viên ở đây **chưa
    # ai đọc** — và bảng phải nói ra điều đó thay vì để một điểm trừ do cụm từ
    # chấm trông như một điểm trừ đã được duyệt. Phán quyết từ những lần
    # `/report` trước vẫn dùng lại được miễn phí (chúng khoá theo bài, không
    # theo phiên hay theo báo cáo), nên con số này giảm dần theo thời gian.
    pending = sum(getattr(rf, "n_pending", 0) for rf in flags_by_symbol.values())
    if pending:
        n_sym = sum(1 for rf in flags_by_symbol.values()
                    if getattr(rf, "n_pending", 0))
        board.notes.append(
            f"⏳ **{pending} ứng viên cờ đỏ ở {n_sym} mã chưa model nào đọc** — "
            f"điểm trừ của chúng do bộ lọc cụm từ chấm, mà bộ lọc đó không phân "
            f"biệt được tin xấu *với mã này* và tin xấu *với một mã khác trong "
            f"cùng bài*. Dùng `prospect_evidence` → `prospect_score_news` để "
            f"phán quyết cho danh sách ngắn.")

    n_fund = 0
    for row in ranking.rows:
        view = views.get(row.symbol.upper())
        fund = fund_mod.load(row.symbol, as_of) if load_fundamentals else None
        if fund is not None:
            n_fund += 1
        rs = sector_mod.relative_strength(
            row.change_20d,
            view.median_change_20d if view and view.comparable else None,
            sessions=rs_sessions, as_of=as_of, market=market,
        )
        flow = None
        if load_insiders:
            from src.news import insider as insider_mod
            try:
                flow = insider_mod.build(
                    row.symbol, as_of=as_of,
                    free_shares=fund.free_shares if fund else None)
            except Exception:           # kho tin thiếu không được giết cả bảng
                flow = None
        scored = score_row(
            row, box=(boxes or {}).get(row.symbol.upper()),
            fund=fund, view=view, rs=rs, insider_flow=flow,
            redflags=flags_by_symbol.get(row.symbol.upper()),
            min_liquidity_bn=min_liquidity_bn,
        )
        if news_scores and scored.symbol.upper() in news_scores:
            scored.news = news_scores[scored.symbol.upper()]
        (board.excluded if scored.excluded else board.rows).append(scored)

    board.rows.sort(key=lambda r: (-r.total, r.symbol))
    board.excluded.sort(key=lambda r: (r.excluded, -r.base_score))
    if n_fund == 0 and load_fundamentals:
        board.notes.append(
            "Chưa có ảnh chụp chỉ số cơ bản nào trong `news/snapshots/` — cột "
            "'định giá vs ngành' bằng 0 cho toàn bảng. Chạy `update_fundamentals` "
            "để bắt đầu đóng băng (FireAnt chỉ trả trạng thái hôm nay, không có "
            "chuỗi lịch sử, nên không nạp từ hôm nay thì không dựng lại được).")
    elif n_fund < len(ranking.rows):
        board.notes.append(
            f"Chỉ {n_fund}/{len(ranking.rows)} mã có ảnh chụp chỉ số cơ bản tại mốc này.")
    return board


def shortlist(board: ProspectBoard, top: int = 15) -> List[ProspectRow]:
    """``top`` mã đầu bảng theo điểm đo được — tập sẽ được đọc tin kỹ.

    Xếp theo ``base_score`` chứ không theo ``total``: vòng này chọn *ai đáng
    đọc tin*, mà điểm tin thì chưa có. Dùng ``total`` ở đây là để điểm của lượt
    trước quyết định lượt sau đọc gì — một vòng lặp tự khẳng định.
    """
    ranked = sorted(board.rows, key=lambda r: (-r.base_score, r.symbol))
    return ranked[:max(1, top)]


def apply_news(board: ProspectBoard,
               verdicts: Dict[str, NewsVerdict]) -> ProspectBoard:
    """Gắn nhận định tin vào bảng đã dựng và xếp lại theo tổng điểm."""
    for row in board.rows + board.excluded:
        verdict = verdicts.get(row.symbol.upper())
        if verdict is not None:
            row.news = verdict
    board.rows.sort(key=lambda r: (-r.total, r.symbol))
    return board


def apply_flag_rulings(board: ProspectBoard,
                       scans: Dict[str, Any]) -> List[str]:
    """Phán quyết cờ đỏ vừa lưu → chấm lại cột cờ đỏ của bảng đã dựng.

    Không dựng lại cả bảng, và cũng không cần: ``base_score`` đúng bằng tổng
    các thành phần, nên thay **một** thành phần rồi cộng lại là xong — rẻ hơn
    một lượt quét 79 mã, và quan trọng hơn là nó không đụng vào sáu cột còn
    lại, nên không có cách nào một lượt chấm điểm tin lặng lẽ làm đổi điểm mẫu
    hình hay điểm RSI.

    Chạy **trước** ``apply_news`` ở tầng gọi: nó đổi ``base_score``, mà
    ``total`` = ``base_score`` + điểm tin. Ngược thứ tự thì bảng ghi ra mang
    điểm tin mới nhưng vẫn mang điểm trừ của bộ lọc cụm từ.

    Trả về danh sách mã đã đổi điểm, để tầng gọi in ra thay vì báo "xong".
    """
    from src.news import rulings as rulings_mod

    changed: List[str] = []
    judged = rulings_mod.apply_many(scans or {})
    for row in board.rows + board.excluded:
        rf = judged.get(row.symbol.upper())
        if rf is None:
            continue
        before = row.base_score
        row.redflags = rf
        row.components = [redflag_points(rf) if c.key == "redflag" else c
                          for c in row.components]
        row.base_score = round(sum(c.points for c in row.components), 1)
        if abs(row.base_score - before) >= 0.05:
            changed.append(f"{row.symbol} {before:+.0f} → {row.base_score:+.0f}")
    board.rows.sort(key=lambda r: (-r.total, r.symbol))
    return changed


# ---------------------------------------------------------------------------
# file
# ---------------------------------------------------------------------------
def _out_root(out_dir: Optional[str], board: Optional[ProspectBoard] = None) -> Path:
    if out_dir:
        return Path(out_dir)
    if board and board.as_of_requested:
        return REPORT_DIR / f"asof_{board.as_of_requested.replace('/', '-')}"
    return REPORT_DIR / datetime.now().strftime("%Y-%m-%d")


def _stem(board: ProspectBoard) -> str:
    """Cùng luật đặt tên với ``ranking._stem`` — một danh sách mã dài không
    được biến thành một tên file dài bằng cả dòng lệnh."""
    from src.ta.ranking import _norm

    tag = _norm(board.universe) or "tuy_chon"
    return (f"trien_vong_{tag[:24]}_"
            f"{asof_mod.file_tag(asof_mod.parse(board.as_of_requested))}")


def save_json(board: ProspectBoard, out_dir: Optional[str] = None) -> str:
    root = _out_root(out_dir, board)
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"{_stem(board)}.json"
    board.json_path = str(path)
    with path.open("w", encoding="utf-8") as f:
        json.dump(board.to_dict(), f, ensure_ascii=False, indent=1)
    # Bảng hồi tưởng không đụng con trỏ của phiên thật — cùng quy ước với
    # ``ranking.save_json``.
    if not board.as_of_requested:
        LATEST_JSON.parent.mkdir(parents=True, exist_ok=True)
        with LATEST_JSON.open("w", encoding="utf-8") as f:
            json.dump(board.to_dict(), f, ensure_ascii=False, indent=1)
    return str(path)


def load_board(path: Optional[str] = None,
               as_of: Optional[datetime] = None) -> Optional[ProspectBoard]:
    """Đọc lại bảng đã dựng. Không có ``path`` thì tìm bản trỏ tương ứng mốc."""
    if path:
        target = Path(path)
    elif as_of is not None:
        root = REPORT_DIR / f"asof_{asof_mod.label(as_of).replace('/', '-')}"
        found = sorted(root.glob("trien_vong_*.json")) if root.is_dir() else []
        if not found:
            return None
        target = found[-1]
    else:
        target = LATEST_JSON
    if not target.is_file():
        return None
    with target.open("r", encoding="utf-8") as f:
        return ProspectBoard.from_dict(json.load(f))


# ---------------------------------------------------------------------------
# bảng HTML
# ---------------------------------------------------------------------------
PROSPECT_CSS = """
.score { font-size: 20px; font-weight: 700; }
.score .split { font-size: 12px; font-weight: 400; color: #8b949e; display: block; }
.comp { display: flex; gap: 3px; align-items: center; }
.comp i { display: inline-block; height: 14px; border-radius: 2px; font-style: normal; }
.comp .pos { background: #3fb950; } .comp .neg { background: #f85149; }
.comp .zero { background: #30363d; width: 3px; }
.newsbox { border-left: 3px solid #58a6ff; padding: 6px 12px; margin: 8px 0;
           background: #0d1117; border-radius: 0 6px 6px 0; }
.newsbox.warn { border-left-color: #e3b341; }
.newsbox.unscored { border-left-color: #30363d; color: #6e7681; }
.newsbox .who { font-size: 12px; color: #8b949e; }
.newsbox .who, .rfbox .who { font-size: 12px; color: #8b949e; }
.rfbox { border-left: 3px solid #30363d; padding: 6px 12px; margin: 8px 0;
         background: #0d1117; border-radius: 0 6px 6px 0; }
.rfbox.critical { border-left-color: #f85149; background: #1d1113; }
.rfbox.critical > b { color: #ffa198; }
.rfbox.warn { border-left-color: #e3b341; background: #1b1810; }
.rfbox.warn > b { color: #e3b341; }
.rfbox.clean > b { color: #3fb950; }
.rfbox.unscanned { color: #6e7681; }
.rflist { margin: 6px 0 0; padding-left: 18px; }
.rflist li { margin: 4px 0; font-size: 13px; }
.rflist .who { display: block; }
/* Khối "đã bác" lùi hẳn về sau: nó còn ở đây để bác lại được, không phải để
   đọc. Một dòng mỗi cái, màu mờ, không tranh chỗ với phần còn hiệu lực. */
.rfbac { margin-top: 8px; padding-top: 6px; border-top: 1px dashed #30363d;
         font-size: 12px; color: #8b949e; }
.rfbac > b { color: #8b949e; font-weight: 600; }
.rfbac .rflist li { color: #8b949e; font-size: 12px; }
td .flagcell { color: #f85149; font-weight: 700; }
td .flagcell.warn { color: #e3b341; }
td .flagcell.clean { color: #3fb950; font-weight: 400; }
.excluded td { color: #6e7681; }
.gap-pos { color: #3fb950; } .gap-neg { color: #f85149; }
"""


def _esc(value: Any) -> str:
    return html_escape.escape(str(value if value is not None else ""))


def _num(value: Optional[float], digits: int = 2) -> str:
    return "—" if value is None else f"{value:,.{digits}f}"


def _bars(row: ProspectRow) -> str:
    """Sáu thành phần thành sáu vạch — nhìn một cái là thấy điểm đến từ đâu."""
    cells = []
    for c in row.components:
        if abs(c.points) < 0.05:
            cells.append('<i class="zero" title="%s: 0"></i>' % _esc(c.label))
            continue
        width = max(3, int(round(abs(c.points) / c.max_points * 34)))
        cls = "pos" if c.points > 0 else "neg"
        cells.append('<i class="%s" style="width:%dpx" title="%s %+.1f/%.0f — %s"></i>'
                     % (cls, width, _esc(c.label), c.points, c.max_points, _esc(c.note)))
    return '<span class="comp">' + "".join(cells) + "</span>"


def _flag_cell(row: ProspectRow) -> str:
    """Ô cờ đỏ trong bảng — ngắn nhất có thể mà vẫn phân biệt được ba trạng thái."""
    from src.news.redflag import LEVEL_CRITICAL

    rf = row.redflags
    if rf is None:
        return '<span class="flagcell warn" title="chưa quét được">?</span>'
    if rf.is_empty:
        return '<span class="flagcell clean" title="đã quét, không có cờ">—</span>'
    cls = "flagcell" if rf.level == LEVEL_CRITICAL else "flagcell warn"
    tip = "; ".join(f.title.strip()[:70] for f in rf.flags[:3])
    return (f'<span class="{cls}" title="{_esc(tip)}">🚩 −{rf.penalty:.0f}'
            f'<span class="who"> {_esc(rf.flags[0].label)}</span></span>')


def _redflag_html(row: ProspectRow) -> str:
    """Khối cờ đỏ của một dòng — **luôn in**, kể cả khi sạch.

    Khác với dải cảnh báo ở hồ sơ 1 mã (chỉ hiện khi có cờ), ở đây ô trống là
    thông tin: người đọc đang so 12 mã cạnh nhau và cần biết mã nào *đã được
    quét và sạch*, khác với mã nào *chưa quét được*.
    """
    rf = row.redflags
    if rf is None:
        return ('<div class="rfbox unscanned"><b>Cờ đỏ — chưa quét được.</b> '
                '<span class="who">Kho tin không đọc được tại mốc này. Đây '
                'KHÔNG phải "đã quét và sạch cờ".</span></div>')
    dismissed = getattr(rf, "dismissed", None) or []
    who = ", ".join(getattr(rf, "judged_by", None) or []) or "model"
    # Ứng viên đã bác chỉ còn **một dòng**: phần lý lẽ của bộ lọc vừa bị bác thì
    # không còn là thứ ai cần đọc lại. Giữ tiêu đề + lý do bác là đủ để bác lại.
    bac = ""
    if dismissed:
        rows = "".join(
            f'<li>“{_esc(f.title.strip())}” — '
            f'{_esc(str((f.ruling or {}).get("reason") or "đã bác"))}</li>'
            for f in dismissed[:4])
        bac = (f'<div class="rfbac"><b>{len(dismissed)} ứng viên đã bị {_esc(who)} '
               f'bác</b> (máy chấm −{rf.penalty_raw:.0f} trước đó)'
               f'<ul class="rflist">{rows}</ul></div>')

    if rf.is_empty:
        if dismissed:
            return (f'<div class="rfbox clean"><b>Cờ đỏ — không còn, sau khi đọc.</b>'
                    f'{bac}</div>')
        return (f'<div class="rfbox clean"><b>Cờ đỏ — không có.</b> '
                f'<span class="who">Đã quét {rf.n_scanned} bài trong '
                f'{rf.window_days} ngày.</span></div>')

    from src.news.redflag import LEVEL_CRITICAL
    cls = "rfbox critical" if rf.level == LEVEL_CRITICAL else "rfbox warn"
    items = "".join(
        f'<li><b>[{_esc(f.label)}]</b> {_esc(f.title.strip())}'
        f'<span class="who">{_esc(f.published[:10])} · {f.age_days} ngày trước '
        f'· −{f.score:.0f} điểm · '
        + ("⏳ chưa ai đọc" if not f.ruling
           else f'✅ {_esc(str((f.ruling or {}).get("source") or "model"))} đã đọc')
        + (f' · {_esc(f.notes[0])}' if f.notes and not f.ruling else "")
        + "</span></li>"
        for f in rf.flags[:6]
    )
    more = (f'<div class="who">… còn {len(rf.flags) - 6} đầu mục nữa trong '
            f'file JSON.</div>' if len(rf.flags) > 6 else "")
    head = f'🚩 {_esc(rf.level_label)} · −{rf.penalty:.0f} điểm'
    if rf.penalty_raw and abs(rf.penalty_raw - rf.penalty) >= 0.5:
        head += f' <span class="who">(máy chấm −{rf.penalty_raw:.0f})</span>'
    return (f'<div class="{cls}"><b>{head}</b>'
            f'<ul class="rflist">{items}</ul>{more}{bac}</div>')


def _news_html(row: ProspectRow) -> str:
    n = row.news
    if n is None:
        # Lớp riêng, không dùng chung với `warn`: "chưa ai đọc" và "đã đọc và
        # thấy tin xấu" là hai chuyện khác hẳn, cho chúng cùng một màu vàng là
        # đúng lỗi mà quy ước "chưa đo được ≠ đã đo và thấy phẳng" cấm.
        return ('<div class="newsbox unscored"><b>Tin — chưa chấm.</b> '
                '<span class="who">Điểm của mã này mới chỉ là phần đo được. '
                'Đây KHÔNG phải "đã đọc và thấy trung tính".</span></div>')
    cls = "newsbox" if n.score >= 0 else "newsbox warn"
    bits = [f'<div class="{cls}"><b>Tin {n.score:+.0f}</b> — {_esc(n.label)}',
            f'<div class="who">độ chắc chắn {_esc(n.confidence or "—")} · '
            f'chấm bởi {_esc(n.source or "?")} lúc {_esc(n.scored_at)}'
            + (f" · đọc {n.n_items} đầu mục" if n.n_items else "") + "</div>",
            f"<p>{_esc(n.summary)}</p>"]
    if n.good:
        bits.append("<ul>" + "".join(f"<li>✅ {_esc(g)}</li>" for g in n.good) + "</ul>")
    if n.bad:
        bits.append("<ul>" + "".join(f"<li>⚠️ {_esc(b)}</li>" for b in n.bad) + "</ul>")
    if n.sector_outlook:
        bits.append(f"<p>🔭 <b>Triển vọng ngành:</b> {_esc(n.sector_outlook)}</p>")
    bits.append("</div>")
    return "".join(bits)


def _fundamentals_html(fund: Optional[Fundamentals]) -> str:
    if fund is None or fund.is_empty:
        return ('<div class="sub">Chưa có ảnh chụp chỉ số cơ bản tại mốc này — '
                'không suy ra được là “trung tính”.</div>')
    rows = []
    for key in ("P/E", "P/B", "P/S", "ROE", "ROA", "%Lãi ròng", "Nợ/VCSH", "TT Hiện hành"):
        ind = fund.get(key)
        if ind is None or ind.value is None:
            continue
        gap = ind.gap_pct
        cell = "—" if gap is None else (
            f'<span class="{"gap-pos" if gap >= 0 else "gap-neg"}">{gap:+.0f}%</span>')
        rows.append(f"<tr><td>{_esc(key)}</td><td class='num'>{_num(ind.value)}</td>"
                    f"<td class='num'>{_num(ind.industry)}</td>"
                    f"<td class='num'>{cell}</td></tr>")
    stale = (f" · ảnh chụp {fund.snapshot_date}"
             + (f", cách mốc {fund.stale_days} ngày" if fund.stale_days else ""))
    return ('<div class="scroll"><table>'
            "<tr><th>Chỉ số</th><th class='num'>Mã</th>"
            "<th class='num'>Trung bình ngành</th>"
            "<th class='num'>Chênh (dương = tốt hơn)</th></tr>"
            + "".join(rows) + "</table></div>"
            + f'<div class="sub">Nguồn: FireAnt financial-indicators{_esc(stale)}</div>')


def write_html(board: ProspectBoard, out_dir: Optional[str] = None,
               top: int = 20) -> Optional[str]:
    """Bảng triển vọng cao ra file HTML tự chứa.

    Dùng lại ``REPORT_CSS`` + ``RANK_CSS`` + ``_SORT_JS`` của bảng xếp hạng, nên
    hai bảng trông như một bộ và cột nào cũng bấm để sắp xếp được.
    """
    from src.ta.format import DISCLAIMER
    from src.ta.ranking import RANK_CSS, _SORT_JS
    from src.ta.report import REPORT_CSS

    if not board.rows and not board.excluded:
        return None
    rows = board.scored_rows[:max(1, top)]

    parts: List[str] = [
        "<!DOCTYPE html>", '<html lang="vi">', "<head>", '<meta charset="UTF-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        f"<title>Triển vọng cao {_esc(board.as_of)}</title>",
        f"<style>{REPORT_CSS}{RANK_CSS}{PROSPECT_CSS}</style>",
        "</head>", "<body>", '<div class="wrap">',
        f"<h1>Triển vọng cao — {_esc(board.as_of)}</h1>",
        f'<div class="sub">{len(board.rows)} ứng viên trên '
        f"{len(board.rows) + len(board.excluded)} mã · nhóm "
        f"<b>{_esc(board.universe)}</b> · dựng lúc {_esc(board.generated)} · "
        f"đã chấm tin {board.n_news_scored}/{len(board.rows)} mã</div>",
    ]
    if board.as_of_requested:
        from src.ta.report import _asof_html
        parts.append(_asof_html(board.as_of_requested, board.as_of))

    parts.append(
        '<div class="card"><b>Điểm này là hai vế cộng lại, và luôn hiện cả hai.</b>'
        "<ul>"
        "<li><b>Phần đo được (0–100)</b> — mẫu hình tăng 30 · breakout + volume 25 · "
        "RSI 15 · sức mạnh tương đối 12 · định giá so với ngành 12 · giao dịch nội bộ 6.</li>"
        f"<li><b>Cờ đỏ (0…−{MAX_REDFLAG:.0f})</b> — sự kiện pháp lý, quản trị và triển "
        "vọng quét được trong 180 ngày: khởi tố, điều tra, thao túng, xử phạt, huỷ "
        "niêm yết, chậm trả trái phiếu, ý kiến kiểm toán, tin đồn xấu. Đây là "
        "<i>phép đo</i> chứ không phải ý kiến — mỗi điểm trừ truy được về một tiêu đề "
        "có thật, in ngay dưới mỗi mã. Nó nằm trong phần đo được và có thể một mình "
        "quyết định thứ hạng: một mã +80 nhờ mẫu hình mà dính án hình sự về 30, đứng "
        "dưới một mã +45 sạch cờ.</li>"
        f"<li><b>Phần tin (−{MAX_NEWS:.0f}…+{MAX_NEWS:.0f})</b> — nhận định của model "
        "ngôn ngữ trên gói bằng chứng (tin của mã, tin ngành, phản ứng giá đã đo). "
        "Đây là <i>ý kiến</i>, không phải phép đo, nên nó đứng riêng một cột.</li>"
        "<li><b>Ba cột của bảng xếp hạng</b> (cường độ xu hướng · độ tin cậy mẫu hình · "
        "phơi nhiễm phái sinh) không nằm trong con số này và không bị nó thay thế.</li>"
        f"<li><b>Thanh khoản là cửa vào</b>, không phải điểm: dưới "
        f"{board.min_liquidity_bn:.0f} tỷ/phiên là loại thẳng, vì một mẫu hình đẹp trên "
        "mã không giao dịch được là mẫu hình không dùng được.</li>"
        "<li><b>RSI</b> đủ điểm ở 40–60, giảm dần lên trên, và <b>âm</b> từ 75 trở lên.</li>"
        "</ul></div>")

    if board.notes:
        parts.append('<div class="card"><b>Khoảng trống trong bảng này</b><ul>'
                     + "".join(f"<li>{_esc(n)}</li>" for n in board.notes)
                     + "</ul></div>")

    parts += ["<h2>Danh sách</h2>", '<div class="scroll">', "<table>",
              "<tr><th>#</th><th>Mã</th><th>Ngành</th><th class='num'>Điểm</th>"
              "<th>Cờ đỏ</th>"
              "<th>Thành phần</th><th class='num'>RSI</th><th class='num'>RVOL</th>"
              "<th class='num'>Thanh khoản</th><th class='num'>20 phiên</th>"
              "<th>Mẫu hình</th><th class='num'>Mục tiêu</th></tr>"]
    for i, r in enumerate(rows, 1):
        split = (f"đo {r.base_score:.0f} · tin {r.news.score:+.0f}" if r.news
                 else "đo, chưa chấm tin")
        parts.append(
            f"<tr><td>{i}</td><td><b>{_esc(r.symbol)}</b></td>"
            f"<td>{_esc(r.sector_label)}</td>"
            f"<td class='num'><span class='score'>{r.total:.0f}"
            f"<span class='split'>{_esc(split)}</span></span></td>"
            f"<td>{_flag_cell(r)}</td>"
            f"<td>{_bars(r)}</td>"
            f"<td class='num'>{_num(r.rsi, 1)}</td>"
            f"<td class='num'>{_num(r.rvol)}×</td>"
            f"<td class='num'>{_num(r.liquidity_bn, 0)} tỷ</td>"
            f"<td class='num'>{_num(r.change_20d)}%</td>"
            f"<td>{_esc(r.pattern_name)}</td>"
            f"<td class='num'>{_num(r.target)}</td></tr>")
    parts += ["</table>", "</div>"]

    parts.append("<h2>Vì sao từng mã vào danh sách</h2>")
    parts.append('<div class="detail">')
    for i, r in enumerate(rows, 1):
        parts.append(f"<h3>{i}. {_esc(r.symbol)} — {r.total:.0f} điểm "
                     f"<span class='sub'>({_esc(r.sector_label)})</span></h3>")
        parts.append('<div class="card">')
        parts.append(
            f'<div class="sub">Giá {_num(r.close)} · RSI {_num(r.rsi, 1)} · '
            f"RVOL {_num(r.rvol)}× · thanh khoản {_num(r.liquidity_bn, 0)} tỷ/phiên · "
            f"20 phiên {_num(r.change_20d)}%</div>")
        parts.append("<ul>")
        for c in r.components:
            parts.append(f"<li><b>{_esc(c.label)} {c.points:+.1f}/{c.max_points:.0f}</b>"
                         f" — {_esc(c.note)}</li>")
        if r.trigger or r.target or r.invalidation:
            parts.append(f"<li><b>Mốc giá</b> — kích hoạt {_num(r.trigger)} · "
                         f"mục tiêu {_num(r.target)} · huỷ nếu mất {_num(r.invalidation)}</li>")
        for w in r.warnings:
            parts.append(f"<li>⚠️ {_esc(w)}</li>")
        parts.append("</ul>")
        parts.append(_redflag_html(r))
        parts.append(_news_html(r))
        parts.append("<b>Chỉ số cơ bản so với ngành</b>")
        parts.append(_fundamentals_html(r.fundamentals))
        parts.append("</div>")
    parts.append("</div>")

    if board.excluded:
        parts += ["<h2>Bị loại khỏi danh sách</h2>",
                  '<div class="sub">Danh sách những mã <i>suýt</i> vào cũng là thông '
                  "tin — nên chúng nằm đây kèm lý do, không bị xoá đi.</div>",
                  '<div class="scroll">', '<table class="excluded">',
                  "<tr><th>Mã</th><th>Lý do</th><th>Chi tiết</th>"
                  "<th class='num'>Điểm đo được</th></tr>"]
        for r in board.excluded:
            parts.append(
                f"<tr><td><b>{_esc(r.symbol)}</b></td>"
                f"<td>{_esc(EXCLUDE_VN.get(r.excluded, r.excluded))}</td>"
                f"<td>{_esc(r.excluded_note)}</td>"
                f"<td class='num'>{r.base_score:.0f}</td></tr>")
        parts += ["</table>", "</div>"]

    parts += [f'<div class="sub">{_esc(DISCLAIMER.strip("_"))}</div>',
              "</div>", f"<script>{_SORT_JS}</script>", "</body>", "</html>"]

    root = _out_root(out_dir, board)
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"{_stem(board)}.html"
    path.write_text("\n".join(parts), encoding="utf-8")
    board.html_path = str(path)
    return str(path)
