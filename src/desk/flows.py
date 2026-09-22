"""Dòng tiền — khối ngoại, tự doanh, thoả thuận. 16 năm nằm sẵn trên đĩa.

Mọi ``StockRecord`` từ 2010 đã mang ``buyForeignValue`` / ``sellForeignValue``
/ ``currentForeignRoom`` / ``propTradingNet*`` / ``putthroughValue``, và cho tới
trước module này chúng được dùng ở đúng hai chỗ: một dòng "khối ngoại ròng" của
phiên cuối trong ``snapshot.py`` và phần hợp đồng trong ``futures.py``. Một
khối phân tích CTCK mở bản tin phiên bằng chính con số này.

Bốn quyết định đo đạc, mỗi cái chặn một cách đọc sai:

1. **Chuẩn hoá theo chính mã, không so tuyệt đối.** 300 tỷ ở VCB là chuyện
   thường, ở DGW là chuyện lớn. Bảng xếp theo số tuyệt đối là bảng xếp theo vốn
   hoá, và nó sẽ ra cùng một danh sách mỗi ngày. Mẫu số là **giá trị khớp lệnh
   trung bình 20 phiên của chính mã** (``foreign_net_pct``).
2. **Chỉ lấy phần khớp lệnh.** ``value_bn = totalValue − putthroughValue``, và
   tự doanh lấy ``propTradingNetDealValue`` chứ không lấy ``propTradingNetValue``
   — cùng quy ước ``priceImpactVolume = dealVolume`` đã dùng cho mọi chỉ báo.
   Phiên có tỷ trọng thoả thuận cao là phiên **sang tay**, không phải phiên cung
   cầu, nên ``pt_share_pct`` đứng thành một cột riêng để nhìn thấy điều đó.
3. **Một phiên là nhiễu, chuỗi mới là hành vi.** ``foreign_streak`` đếm số phiên
   liên tiếp cùng dấu.
4. **Hai loại phiên phải mang cờ, không được lặng lẽ vào mẫu** (§7.3 của plan):
   mã **kín room** thì bán ròng của khối ngoại là cơ chế chứ không phải quan
   điểm, và tuần **ETF cơ cấu** sinh ra mua/bán ròng khổng lồ không nói gì về
   doanh nghiệp. Cả hai đi vào ``room_capped`` / ``etf_window``, và
   ``calibrate_flows`` chạy **cả hai bản** — có và không có các phiên đó.

⚠️ Module này **chưa được phép phát biểu** dòng tiền dự báo được điều gì.
``calibrate_flows.py`` là cửa; ``calibration_note()`` của nó phải đi kèm mọi
output có chữ, đúng cách ``macro/score.py`` phải mang ``calibration_note`` theo.

⚠️ Chưa xác minh được ``buyForeignValue`` có gồm phần thoả thuận hay không —
FireAnt không nói, và không tách được từ dữ liệu. Nên một phiên khối ngoại mua
ròng lớn **kèm** ``pt_share_pct`` cao phải đọc kèm nhau; ``SymbolFlow.notes``
nói ra chỗ đó thay vì để người đọc tự đoán.
"""
from dataclasses import asdict, dataclass, field
from datetime import date as date_cls
from datetime import datetime, timedelta
from statistics import fmean
from typing import Any, Dict, List, Optional, Sequence, Tuple

from src.data.stock_data_loader import StockRecord
from src.ta.loader import load_recent, resolve_universe

#: Cửa sổ mẫu số. 20 phiên ≈ một tháng giao dịch — đủ dài để một phiên đột biến
#: không tự nâng mẫu số của chính nó, đủ ngắn để còn nói về thanh khoản hiện tại.
ADV_WINDOW = 20

#: Dưới ngần này phiên thì mẫu số chưa có nghĩa → ``foreign_net_pct = None``.
#: *Chưa đo được* khác *bằng 0*.
MIN_BARS = ADV_WINDOW + 5

#: Room còn lại nhỏ hơn ngần này lần khối lượng khớp trung bình thì coi như kín.
#: Đây là định nghĩa **vận hành** và cố ý không dùng ``freeShares``: room chỉ
#: ràng buộc khi nó không đủ chỗ cho một phần phiên giao dịch, và ``freeShares``
#: là snapshot của hôm nay nên không lùi về 2010 được — mà cả phép hiệu chuẩn
#: thì cần lùi về 2010.
ROOM_CAP_ADV_MULT = 0.5

#: Số phiên tối đa dò ngược khi đếm chuỗi cùng dấu.
STREAK_LOOKBACK = 90

#: Tháng ETF cơ cấu (FTSE / VNM ETF hiệu lực vào thứ Sáu tuần thứ ba).
ETF_MONTHS = (3, 6, 9, 12)
#: Số ngày lịch trước ngày hiệu lực còn nằm trong cửa sổ cơ cấu.
ETF_WINDOW_DAYS = 7


def _third_friday(year: int, month: int) -> date_cls:
    d = date_cls(year, month, 1)
    # weekday(): thứ Hai = 0, thứ Sáu = 4
    first_friday = d + timedelta(days=(4 - d.weekday()) % 7)
    return first_friday + timedelta(days=14)


def etf_review_window(day: Any) -> bool:
    """Phiên có nằm trong tuần ETF cơ cấu không.

    **Đây là một phép đoán theo lịch, không phải một sự kiện đã xác minh**: ngày
    hiệu lực của FTSE/VNM ETF là thứ Sáu tuần thứ ba của tháng 3/6/9/12, nhưng
    lượt mua bán thật rải quanh đó và có năm lệch. Cờ này chỉ dùng để **loại
    khỏi mẫu hiệu chuẩn**, không dùng để kết luận gì về một phiên cụ thể.
    """
    if isinstance(day, str):
        try:
            day = datetime.strptime(day[:10], "%Y-%m-%d").date()
        except ValueError:
            return False
    if isinstance(day, datetime):
        day = day.date()
    if not isinstance(day, date_cls) or day.month not in ETF_MONTHS:
        return False
    effective = _third_friday(day.year, day.month)
    return 0 <= (effective - day).days <= ETF_WINDOW_DAYS


# ---------------------------------------------------------------------------
@dataclass
class FlowPoint:
    """Dòng tiền của một mã trong một phiên."""
    date: str
    value_bn: float                       # giá trị KHỚP LỆNH (đã trừ thoả thuận)
    foreign_net_bn: float
    foreign_net_pct: Optional[float] = None   # % giá trị khớp trung bình 20 phiên
    prop_net_bn: Optional[float] = None
    prop_net_pct: Optional[float] = None      # cùng mẫu số với khối ngoại
    pt_share_pct: Optional[float] = None
    room_shares: Optional[float] = None
    room_capped: bool = False
    etf_window: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class SymbolFlow:
    """Chuỗi dòng tiền của một mã, kèm các số đo của phiên cuối."""
    symbol: str
    as_of: str
    n: int = 0
    points: List[FlowPoint] = field(default_factory=list)
    foreign_net_bn: float = 0.0
    foreign_net_pct: Optional[float] = None
    foreign_net_5d_bn: float = 0.0
    foreign_net_20d_bn: float = 0.0
    foreign_streak: int = 0
    prop_net_bn: Optional[float] = None
    prop_net_5d_bn: Optional[float] = None
    prop_available: bool = False
    pt_share_pct: Optional[float] = None
    room_capped: bool = False
    etf_window: bool = False
    adv20_bn: Optional[float] = None
    notes: List[str] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return self.n == 0

    @property
    def streak_label(self) -> str:
        if self.foreign_streak == 0:
            return "không có chuỗi"
        side = "mua ròng" if self.foreign_streak > 0 else "bán ròng"
        return f"{abs(self.foreign_streak)} phiên {side} liên tiếp"

    def to_dict(self) -> Dict[str, Any]:
        out = asdict(self)
        out["points"] = [p.to_dict() for p in self.points]
        out["streak_label"] = self.streak_label
        return out


def _bn(value: Optional[float]) -> float:
    return float(value or 0.0) / 1e9


def build_points(bars: Sequence[StockRecord]) -> List[FlowPoint]:
    """Chuỗi ``FlowPoint`` từ chuỗi nến. Không mạng, không đĩa."""
    out: List[FlowPoint] = []
    values: List[float] = []
    volumes: List[float] = []
    for rec in bars:
        pt_value = _bn(getattr(rec, "putthroughValue", 0.0))
        total_value = _bn(getattr(rec, "totalValue", 0.0))
        deal_value = max(total_value - pt_value, 0.0)
        values.append(deal_value)
        volumes.append(float(getattr(rec, "dealVolume", 0.0) or 0.0))

        window = values[-(ADV_WINDOW + 1):-1]
        adv = fmean(window) if len(window) >= ADV_WINDOW else None
        vol_window = volumes[-(ADV_WINDOW + 1):-1]
        advol = fmean(vol_window) if len(vol_window) >= ADV_WINDOW else None

        net = _bn(rec.buyForeignValue) - _bn(rec.sellForeignValue)
        prop_raw = getattr(rec, "propTradingNetDealValue", None)
        room = getattr(rec, "currentForeignRoom", None)
        out.append(FlowPoint(
            date=rec.date.strftime("%Y-%m-%d"),
            value_bn=round(deal_value, 3),
            foreign_net_bn=round(net, 3),
            foreign_net_pct=(round(net / adv * 100, 1) if adv else None),
            prop_net_bn=(round(_bn(prop_raw), 3) if prop_raw is not None else None),
            prop_net_pct=(round(_bn(prop_raw) / adv * 100, 1)
                          if prop_raw is not None and adv else None),
            pt_share_pct=(round(pt_value / total_value * 100, 1)
                          if total_value > 0 else None),
            room_shares=(float(room) if room is not None else None),
            room_capped=bool(room is not None and advol
                             and float(room) < ROOM_CAP_ADV_MULT * advol),
            etf_window=etf_review_window(rec.date),
        ))
    return out


def _streak(points: Sequence[FlowPoint]) -> int:
    if not points:
        return 0
    last = points[-1].foreign_net_bn
    if last == 0:
        return 0
    sign = 1 if last > 0 else -1
    count = 0
    for p in reversed(points[-STREAK_LOOKBACK:]):
        if (p.foreign_net_bn > 0) == (sign > 0) and p.foreign_net_bn != 0:
            count += 1
        else:
            break
    return count * sign


def build_symbol_flow(symbol: str, as_of: Optional[datetime] = None,
                      lookback_days: int = 400,
                      bars: Optional[Sequence[StockRecord]] = None) -> SymbolFlow:
    """Dòng tiền của một mã tới ``as_of``.

    Chuỗi rỗng trả về ``SymbolFlow`` rỗng chứ không ném lỗi — một mã thiếu dữ
    liệu không được giết cả bảng, và ``is_empty`` nói rõ là *chưa đọc được*.
    """
    sym = symbol.strip().upper()
    recs = list(bars) if bars is not None else load_recent(sym, lookback_days, as_of)
    if as_of is not None:
        recs = [r for r in recs if r.date <= as_of]
    if not recs:
        return SymbolFlow(symbol=sym, as_of="", notes=["chưa đọc được giá"])

    points = build_points(recs)
    last = points[-1]
    props = [p.prop_net_bn for p in points if p.prop_net_bn is not None]
    notes: List[str] = []
    if len(points) < MIN_BARS:
        notes.append(f"mới {len(points)} phiên — chưa đủ {MIN_BARS} phiên để "
                     "chuẩn hoá, cột % để trống")
    if last.room_capped:
        notes.append("room ngoại gần kín: bán ròng ở đây là cơ chế, không phải "
                     "quan điểm")
    if last.etf_window:
        notes.append("nằm trong tuần ETF cơ cấu (phép đoán theo lịch) — dòng "
                     "tiền phiên này không nói về doanh nghiệp")
    if last.pt_share_pct is not None and last.pt_share_pct >= 30:
        notes.append(f"thoả thuận chiếm {last.pt_share_pct:g}% giá trị phiên — "
                     "phiên sang tay, đọc kèm khi nhìn số ròng")
    if not props:
        notes.append("chưa có số tự doanh trong khoảng này")

    return SymbolFlow(
        symbol=sym,
        as_of=last.date,
        n=len(points),
        points=points,
        foreign_net_bn=last.foreign_net_bn,
        foreign_net_pct=last.foreign_net_pct,
        foreign_net_5d_bn=round(sum(p.foreign_net_bn for p in points[-5:]), 2),
        foreign_net_20d_bn=round(sum(p.foreign_net_bn for p in points[-20:]), 2),
        foreign_streak=_streak(points),
        prop_net_bn=last.prop_net_bn,
        prop_net_5d_bn=(round(sum(p.prop_net_bn or 0.0 for p in points[-5:]), 3)
                        if props else None),
        prop_available=bool(props),
        pt_share_pct=last.pt_share_pct,
        room_capped=last.room_capped,
        etf_window=last.etf_window,
        adv20_bn=(round(fmean([p.value_bn for p in points[-ADV_WINDOW:]]), 2)
                  if len(points) >= ADV_WINDOW else None),
        notes=notes,
    )


# ---------------------------------------------------------------------------
@dataclass
class MarketFlow:
    """Gộp cả rổ. Nhãn phải nói rõ **rổ**, không phải cả sàn."""
    as_of: str
    n_symbols: int = 0
    foreign_net_bn: float = 0.0
    foreign_net_5d_bn: float = 0.0
    prop_net_bn: Optional[float] = None
    value_bn: float = 0.0
    buyers: int = 0                  # số mã khối ngoại mua ròng phiên cuối
    sellers: int = 0
    sessions_lag: List[str] = field(default_factory=list)   # mã dừng ở phiên khác

    @property
    def breadth_pct(self) -> Optional[float]:
        total = self.buyers + self.sellers
        return round(self.buyers / total * 100, 1) if total else None

    def to_dict(self) -> Dict[str, Any]:
        out = asdict(self)
        out["breadth_pct"] = self.breadth_pct
        return out


@dataclass
class SectorFlow:
    code: str
    name: str = ""
    n_members: int = 0          # thành viên **trong rổ ``data/``**
    n_total: int = 0            # thành viên thật của ngành, cả ba sàn
    foreign_net_bn: float = 0.0
    foreign_net_5d_bn: float = 0.0
    value_bn: float = 0.0

    @property
    def foreign_net_pct(self) -> Optional[float]:
        """Ròng của ngành tính theo chính thanh khoản ngành — cùng lý lẽ cấp mã."""
        return round(self.foreign_net_bn / self.value_bn * 100, 1) if self.value_bn else None

    @property
    def coverage_pct(self) -> Optional[float]:
        return round(self.n_members / self.n_total * 100) if self.n_total else None

    @property
    def thin(self) -> bool:
        """Dưới 3 mã trong rổ thì con số này là của mấy cái tên cụ thể, không
        phải của ngành — cùng ngưỡng ``MIN_PEERS`` mà ``ta/sector.py`` đã dùng."""
        return self.n_members < 3

    def to_dict(self) -> Dict[str, Any]:
        out = asdict(self)
        out["foreign_net_pct"] = self.foreign_net_pct
        out["coverage_pct"] = self.coverage_pct
        out["thin"] = self.thin
        return out


@dataclass
class FlowBoard:
    as_of: str
    as_of_requested: Optional[str] = None
    rows: List[SymbolFlow] = field(default_factory=list)
    market: Optional[MarketFlow] = None
    sectors: List[SectorFlow] = field(default_factory=list)
    skipped: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "as_of": self.as_of,
            "as_of_requested": self.as_of_requested,
            "rows": [r.to_dict() for r in self.rows],
            "market": self.market.to_dict() if self.market else None,
            "sectors": [s.to_dict() for s in self.sectors],
            "skipped": self.skipped,
        }


def _sector_rollup(rows: Sequence[SymbolFlow],
                   levels: Sequence[int] = (1,)) -> List[SectorFlow]:
    """Gộp theo ngành ICB. Bỏ qua lặng lẽ nếu chưa nạp danh sách thành viên.

    Không tự dựng lại danh sách ngành ở đây: ``macro/members.py`` đã là chỗ duy
    nhất biết mã nào thuộc ngành nào, và dựng lần thứ hai là để hai chỗ lệch nhau.

    **Mặc định chỉ gộp ở cấp 1.** Trong rổ 80 mã, rất nhiều ngành cấp 2 có đúng
    những thành viên của ngành cấp 1 mẹ (Hàng tiêu dùng cơ bản ≡ Thực phẩm và đồ
    uống: cùng 7 mã), nên in cả hai là in **một thông tin dưới hai cái tên** và
    nó ăn hai suất trong bảng "ngành được mua ròng mạnh nhất" — đúng cái bẫy mà
    ``duplicate_of`` của registry chặn ở tầng chuỗi giá, nhưng ở đây trùng vì
    *thành viên trong rổ* chứ không vì chuỗi. Nên chặn thêm một lớp: tập thành
    viên trùng nhau thì chỉ giữ dòng đầu tiên.
    """
    try:
        from src.macro import icb, members
    except ImportError:                                        # pragma: no cover
        return []
    registry = icb.load_registry()
    if not registry:
        return []
    # ``duplicate_of`` khác None nghĩa là chuỗi này trùng khít một ngành khác
    # (sáu ngành cấp 1 chỉ có đúng một con cấp 2). Gộp cả hai là đếm một ngành
    # hai lần dưới hai cái tên.
    want_levels = set(levels)
    codes = [str(r.get("icb_code")) for r in registry
             if not r.get("duplicate_of") and int(r.get("level") or 0) in want_levels]
    names = {str(r.get("icb_code")): str(r.get("name") or "") for r in registry}

    by_symbol = {r.symbol: r for r in rows}
    seen_members: Dict[Tuple[str, ...], str] = {}
    out: List[SectorFlow] = []
    for code in codes:
        member_syms = sorted(s for s in members.in_basket(code) if s in by_symbol)
        if not member_syms:
            continue
        key = tuple(member_syms)
        if key in seen_members:
            continue
        seen_members[key] = code
        mine = [by_symbol[s] for s in member_syms]
        out.append(SectorFlow(
            code=code,
            name=names.get(code, code),
            n_members=len(mine),
            n_total=len(members.load(code)),
            foreign_net_bn=round(sum(r.foreign_net_bn for r in mine), 2),
            foreign_net_5d_bn=round(sum(r.foreign_net_5d_bn for r in mine), 2),
            value_bn=round(sum(r.adv20_bn or 0.0 for r in mine), 2),
        ))
    return sorted(out, key=lambda s: s.foreign_net_bn, reverse=True)


def build_board(universe: Optional[str] = None, as_of: Optional[datetime] = None,
                as_of_requested: Optional[str] = None,
                lookback_days: int = 400, with_sectors: bool = True) -> FlowBoard:
    """Bảng dòng tiền cho cả rổ.

    Rổ ở đây là rổ cổ phiếu — benchmark, phái sinh và chỉ số ngành đã bị
    ``resolve_universe`` loại từ trước, và đó là đúng: một chỉ số không có khối
    ngoại mua ròng của riêng nó.
    """
    symbols = resolve_universe(universe)
    rows: List[SymbolFlow] = []
    skipped: List[str] = []
    for sym in symbols:
        flow = build_symbol_flow(sym, as_of=as_of, lookback_days=lookback_days)
        if flow.is_empty:
            skipped.append(sym)
            continue
        rows.append(flow)

    if not rows:
        return FlowBoard(as_of="", as_of_requested=as_of_requested, skipped=skipped)

    sessions = sorted({r.as_of for r in rows})
    latest = sessions[-1]
    props = [r.prop_net_bn for r in rows if r.prop_net_bn is not None]
    market = MarketFlow(
        as_of=latest,
        n_symbols=len(rows),
        foreign_net_bn=round(sum(r.foreign_net_bn for r in rows), 2),
        foreign_net_5d_bn=round(sum(r.foreign_net_5d_bn for r in rows), 2),
        prop_net_bn=(round(sum(props), 2) if props else None),
        value_bn=round(sum(r.adv20_bn or 0.0 for r in rows), 2),
        buyers=sum(1 for r in rows if r.foreign_net_bn > 0),
        sellers=sum(1 for r in rows if r.foreign_net_bn < 0),
        sessions_lag=sorted(r.symbol for r in rows if r.as_of != latest),
    )
    return FlowBoard(as_of=latest, as_of_requested=as_of_requested, rows=rows,
                     market=market,
                     sectors=_sector_rollup(rows) if with_sectors else [],
                     skipped=skipped)


SORT_KEYS = {
    "rong": lambda r: r.foreign_net_bn,
    "rong_pct": lambda r: (r.foreign_net_pct if r.foreign_net_pct is not None else 0.0),
    "rong_5d": lambda r: r.foreign_net_5d_bn,
    "rong_20d": lambda r: r.foreign_net_20d_bn,
    "chuoi": lambda r: r.foreign_streak,
    "tu_doanh": lambda r: (r.prop_net_bn or 0.0),
    "thoa_thuan": lambda r: (r.pt_share_pct or 0.0),
}


def sort_rows(rows: Sequence[SymbolFlow], by: str = "rong_pct",
              descending: bool = True) -> List[SymbolFlow]:
    key = SORT_KEYS.get((by or "").strip().lower(), SORT_KEYS["rong_pct"])
    return sorted(rows, key=key, reverse=descending)
