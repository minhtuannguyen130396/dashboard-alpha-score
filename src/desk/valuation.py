"""Dải định giá của chính mã — P/E và P/B theo phiên, không nhìn trước.

Câu mà mọi báo cáo CTCK mở đầu là *"P/E 12,4 lần, thấp hơn trung vị 5 năm của
chính nó 22%"*. Trước module này repo **không phát biểu được** câu đó: tầng
`ta/fundamentals.py` chỉ giữ ảnh chụp của hôm nay, nên bảng hồi tưởng về ngày
trước lượt đóng băng đầu tiên không có phần định giá.

Ba mảnh ghép lại thành chuỗi, và cả ba đều đã nằm sẵn:

    LNST + vốn góp theo quý   ←  financials.py (/full-financial-reports)
    ngày công bố              ←  timescale_marks trong news/index.db
    giá                       ←  data/<MÃ>/

**Giá phải dùng bản CHƯA điều chỉnh.** ``data/`` lưu giá đã chia ``adjRatio``
(HPG 2015: 3,07 = 53,0 thật ÷ 17,25), còn BCTC thì không điều chỉnh gì cả. Lấy
giá điều chỉnh chia EPS báo cáo là được một chuỗi P/E **nhảy một bậc đúng mỗi
lần doanh nghiệp chia cổ phiếu** — và nó trông hoàn toàn bình thường, giống hệt
một đợt định giá lại của thị trường. Nhân ``adjRatio`` trở lại là hết: cả tử và
mẫu cùng ở hệ thật, và chuỗi đi liền mạch qua mọi lần chia tách vì giá thật
cũng rơi đúng tỷ lệ đó vào ngày giao dịch không hưởng quyền.

Hai chỗ cố tình trả ``None`` thay vì một con số:

* **Lỗ bốn quý** → P/E không định nghĩa được. Một P/E âm không có nghĩa "rẻ",
  và xếp hạng nó cạnh các P/E dương là vô nghĩa.
* **Dưới 12 quý** → ``comparable = False``. Phân vị của sáu quan sát là một con
  số trông như đã đo mà chưa đo gì — cùng ngưỡng mà ``ta/sector.py`` đã dùng cho
  ngành dưới 3 mã.
"""
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from statistics import median
from typing import Any, Dict, List, Optional, Sequence, Tuple

from src.desk import financials as fin_mod
from src.desk.financials import Financials, Quarter
from src.ta.loader import load_prices

#: Dưới ngần này quý đã công bố thì mọi phân vị để trống.
MIN_QUARTERS = 12

#: Các cửa sổ so sánh, tính bằng năm.
WINDOWS: Tuple[int, ...] = (3, 5)

#: Chuỗi P/E nhảy quá ngần này trong một phiên mà giá không nhảy tương ứng là
#: dấu hiệu số cổ phiếu vừa đổi mà kỳ báo cáo chưa phản ánh (hoặc ngược lại).
#: In ra chứ không giấu — chỗ nhảy là chỗ người đọc cần soi.
JUMP_WARN_PCT = 25.0
PRICE_MOVE_PCT = 5.0


@dataclass
class ValuationPoint:
    date: str
    price: float                     # đồng, giá THẬT (đã nhân lại adjRatio)
    eps_ttm: Optional[float] = None  # đồng/cp, 4 quý trượt đã công bố
    pe: Optional[float] = None
    bvps: Optional[float] = None
    pb: Optional[float] = None
    quarter: str = ""                # kỳ gần nhất đã công bố tại phiên đó

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Band:
    """Vị trí hiện tại của một chỉ số trong chính lịch sử của nó."""
    metric: str
    now: Optional[float] = None
    pct: Dict[int, Optional[float]] = field(default_factory=dict)      # {năm: phân vị}
    med: Dict[int, Optional[float]] = field(default_factory=dict)      # {năm: trung vị}
    n: Dict[int, int] = field(default_factory=dict)
    low: Optional[float] = None
    high: Optional[float] = None

    @property
    def comparable(self) -> bool:
        return self.now is not None and any(v for v in self.n.values())

    def read(self, window: int = 5) -> str:
        """Câu đọc — *rẻ hay đắt so với chính nó*, không phải so với ngành."""
        pct, med = self.pct.get(window), self.med.get(window)
        if self.now is None or pct is None or med is None:
            return "chưa đủ dữ liệu để đặt vào dải lịch sử"
        gap = (self.now / med - 1) * 100 if med else None
        where = ("thấp hơn" if gap is not None and gap < 0 else "cao hơn")
        tail = (f", {where} trung vị {window} năm {abs(gap):.0f}%"
                if gap is not None else "")
        return (f"{self.metric} `{self.now:.2f}` — phân vị {pct:.0f} trong "
                f"{window} năm của chính mã{tail}")

    def to_dict(self) -> Dict[str, Any]:
        out = asdict(self)
        out["pct"] = {str(k): v for k, v in self.pct.items()}
        out["med"] = {str(k): v for k, v in self.med.items()}
        out["n"] = {str(k): v for k, v in self.n.items()}
        out["comparable"] = self.comparable
        return out


@dataclass
class ValuationSeries:
    symbol: str
    as_of: str = ""
    as_of_requested: Optional[str] = None
    points: List[ValuationPoint] = field(default_factory=list)
    pe: Optional[Band] = None
    pb: Optional[Band] = None
    quarters_known: int = 0
    latest_quarter: str = ""
    comparable: bool = False
    notes: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return not self.points

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol, "as_of": self.as_of,
            "as_of_requested": self.as_of_requested,
            "points": [p.to_dict() for p in self.points],
            "pe": self.pe.to_dict() if self.pe else None,
            "pb": self.pb.to_dict() if self.pb else None,
            "quarters_known": self.quarters_known,
            "latest_quarter": self.latest_quarter,
            "comparable": self.comparable,
            "notes": self.notes, "warnings": self.warnings,
        }


# ---------------------------------------------------------------------------
def trailing(quarters: Sequence[Quarter]) -> Tuple[Optional[float], Optional[float],
                                                   Optional[float], str]:
    """``(EPS 4 quý trượt, BVPS, số cp, nhãn kỳ)`` từ các quý **đã công bố**.

    Bốn quý phải **liên tiếp**: một kỳ thiếu ở giữa thì tổng bốn kỳ còn lại
    không phải "bốn quý gần nhất", nó là một con số không tên.
    """
    usable = [q for q in quarters if q.npat is not None][-4:]
    if len(usable) < 4:
        return None, None, None, (quarters[-1].label if quarters else "")
    expected = []
    year, quarter = usable[-1].year, usable[-1].quarter
    for _ in range(4):
        expected.append((year, quarter))
        quarter -= 1
        if quarter == 0:
            year, quarter = year - 1, 4
    if [q.key for q in usable] != list(reversed(expected)):
        return None, None, None, usable[-1].label

    last = quarters[-1]
    shares = next((q.shares for q in reversed(quarters) if q.shares), None)
    equity = next((q.equity for q in reversed(quarters) if q.equity is not None), None)
    if not shares:
        return None, None, None, last.label
    eps = sum(q.npat for q in usable) / shares
    bvps = (equity / shares) if equity else None
    return eps, bvps, shares, last.label


def build(symbol: str, as_of: Optional[datetime] = None,
          as_of_requested: Optional[str] = None,
          years: int = 6, fin: Optional[Financials] = None,
          allow_fetch: bool = True) -> ValuationSeries:
    """Chuỗi P/E – P/B theo phiên cho tới ``as_of``."""
    sym = symbol.strip().upper()
    fin = fin or fin_mod.load_or_build(sym, allow_fetch=allow_fetch)
    out = ValuationSeries(symbol=sym, as_of_requested=as_of_requested)
    if fin is None or fin.is_empty:
        out.notes.append("chưa có BCTC trong kho — chạy `desk_valuation` với "
                         "`refresh=True` hoặc `python -m src.desk.financials`")
        return out
    out.notes.extend(fin.notes)

    end = as_of or datetime.now()
    bars = load_prices(sym, end - timedelta(days=int(365.25 * years) + 30), end)
    bars = [b for b in bars if b.date <= end]
    if not bars:
        out.notes.append("chưa đọc được giá")
        return out

    points: List[ValuationPoint] = []
    for bar in bars:
        day = bar.date.strftime("%Y-%m-%d")
        known = fin.known_at(day)
        if not known:
            continue
        eps, bvps, _shares, label = trailing(known)
        # Giá THẬT: bỏ điều chỉnh, rồi đổi nghìn đồng → đồng.
        price = bar.priceClose * (bar.adjRatio or 1.0) * (bar.unit or 1.0)
        pe = (price / eps) if (eps and eps > 0) else None
        pb = (price / bvps) if (bvps and bvps > 0) else None
        points.append(ValuationPoint(date=day, price=round(price, 1),
                                     eps_ttm=(round(eps) if eps else None),
                                     pe=(round(pe, 2) if pe else None),
                                     bvps=(round(bvps) if bvps else None),
                                     pb=(round(pb, 2) if pb else None),
                                     quarter=label))
    if not points:
        out.notes.append("chưa có kỳ BCTC nào được công bố trước mốc này")
        return out

    out.points = points
    out.as_of = points[-1].date
    out.latest_quarter = points[-1].quarter
    out.quarters_known = len(fin.known_at(out.as_of))
    out.comparable = out.quarters_known >= MIN_QUARTERS
    if not out.comparable:
        out.notes.append(f"mới {out.quarters_known} kỳ đã công bố — dưới "
                         f"{MIN_QUARTERS} kỳ thì phân vị chưa nói được gì")

    out.pe = _band("P/E", points, lambda p: p.pe, out.as_of)
    out.pb = _band("P/B", points, lambda p: p.pb, out.as_of)
    if points[-1].pe is None:
        out.notes.append("lỗ luỹ kế 4 quý — **P/E không định nghĩa được**, "
                         "không phải P/E bằng 0")
    out.warnings.extend(_jump_warnings(points))
    return out


def _band(metric: str, points: Sequence[ValuationPoint], pick, as_of: str) -> Band:
    band = Band(metric=metric, now=pick(points[-1]))
    end = datetime.strptime(as_of, "%Y-%m-%d")
    for window in WINDOWS:
        floor = (end - timedelta(days=int(365.25 * window))).strftime("%Y-%m-%d")
        values = [v for v in (pick(p) for p in points if p.date >= floor)
                  if v is not None]
        band.n[window] = len(values)
        if len(values) < 60 or band.now is None:      # dưới ~3 tháng phiên
            band.pct[window] = None
            band.med[window] = None
            continue
        below = sum(1 for v in values if v < band.now)
        band.pct[window] = round(below / len(values) * 100, 1)
        band.med[window] = round(median(values), 2)
    all_values = [v for v in (pick(p) for p in points) if v is not None]
    if all_values:
        band.low, band.high = round(min(all_values), 2), round(max(all_values), 2)
    return band


def _jump_warnings(points: Sequence[ValuationPoint]) -> List[str]:
    """Chỗ P/E nhảy mà giá không nhảy — nói ra, không làm mượt.

    Hai nguyên nhân, và module này **không đoán** là cái nào: (a) bình thường —
    một quý cũ rơi khỏi cửa sổ bốn quý trượt và quý mới thay vào có lợi nhuận
    khác hẳn, chuyện này đúng và phải xảy ra; (b) đáng ngờ — số cổ phiếu vừa
    đổi mà kỳ báo cáo chưa phản ánh, hoặc ngược lại. Cờ này chỉ đánh dấu **chỗ
    chuỗi gãy** để người đọc soi, không phát biểu nguyên nhân.
    """
    out: List[str] = []
    for prev, cur in zip(points, points[1:]):
        if not (prev.pe and cur.pe and prev.price):
            continue
        pe_move = abs(cur.pe / prev.pe - 1) * 100
        price_move = abs(cur.price / prev.price - 1) * 100
        if pe_move >= JUMP_WARN_PCT and price_move < PRICE_MOVE_PCT:
            cause = ("kỳ báo cáo vừa đổi" if prev.quarter != cur.quarter
                     else "kỳ báo cáo KHÔNG đổi — đáng soi")
            out.append(f"{cur.date}: P/E nhảy {pe_move:.0f}% trong khi giá chỉ đổi "
                       f"{price_move:.1f}% ({prev.quarter} → {cur.quarter}, {cause})")
    return out[-3:]


def cross_check(series: ValuationSeries, reported_eps: Optional[float]
                ) -> Optional[str]:
    """Đối chiếu EPS tự tính với EPS FireAnt công bố — miễn phí và bắt được lỗi.

    Lệch quá 25% nghĩa là một trong hai bên đang đọc khác định nghĩa (thường là
    dòng lợi nhuận: hợp nhất hay riêng lẻ, trước hay sau lợi ích cổ đông thiểu
    số). Không tự sửa — nói ra để người đọc biết đang đứng ở đâu.
    """
    if series.is_empty or not reported_eps:
        return None
    mine = series.points[-1].eps_ttm
    if not mine:
        return None
    gap = abs(mine / reported_eps - 1) * 100
    if gap < 25:
        return None
    return (f"EPS tự tính `{mine:,.0f}` lệch {gap:.0f}% so với EPS FireAnt công bố "
            f"`{reported_eps:,.0f}` — kiểm lại dòng lợi nhuận đang dùng")
