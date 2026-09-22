"""Thị trường phái sinh VN30 — và đường nó chạm vào từng cổ phiếu.

Phái sinh Việt Nam chỉ có **một** sản phẩm đáng kể: hợp đồng tương lai chỉ số
VN30. Nó thanh toán bằng tiền theo chính chỉ số VN30 của phiên đáo hạn, nên
mọi phép đo ở đây lấy **VN30 làm mốc, không phải VNINDEX** — hai chỉ số này
lệch nhau vì VNINDEX còn hàng trăm mã nhỏ không nằm trong rổ phái sinh.

Ba con số module này tính, và lý do từng con số tồn tại:

* **Basis = F − S** (giá hợp đồng trừ chỉ số cơ sở). Phái sinh là chỗ rẻ nhất
  và nhanh nhất để đặt cược vào cả thị trường: T+0, đòn bẩy ~7 lần, bán khống
  không cần vay hàng. Nên kỳ vọng hiện ra ở đây **trước** khi hiện ra ở giá cổ
  phiếu. Chiết khấu (basis âm) dai dẳng nghĩa là bên muốn phòng vệ / bán khống
  chịu trả giá để có vị thế; premium dai dẳng thì ngược lại.
* **Số phiên còn lại tới đáo hạn.** Basis **buộc phải** hội tụ về 0 vào phiên
  đáo hạn — đó là cơ chế, không phải tâm lý. Đọc một con số basis mà không kèm
  quãng đường còn lại là đọc sai: −8 điểm khi còn 18 phiên là chiết khấu thật,
  −8 điểm khi còn 1 phiên gần như chỉ là nhiễu. Vì thế phân vị được tính
  **hai lần**: một lần trên toàn bộ lịch sử, một lần chỉ trên những phiên có
  cùng quãng đường tới đáo hạn (±3 phiên).
* **Giá trị danh nghĩa phái sinh / giá trị khớp lệnh VN30.** Tỷ lệ này nói tiền
  đang đặt cược bằng đòn bẩy gấp mấy lần tiền thật đang mua cổ phiếu trong rổ.

Một cái bẫy phải nhớ: **``VN30F1M`` không phải một hợp đồng.** FireAnt nối
liên tục — sau mỗi phiên đáo hạn, mã này nhảy sang hợp đồng tháng kế tiếp.
Phần trăm thay đổi qua đúng đường nối đó là **giả tạo**, không phải một cú
chạy giá. ``roll_indices()`` đánh dấu các đường nối; mọi phép tính lợi suất
trong file này đều bỏ qua chúng. Basis thì không sao — nó là hiệu hai mức giá
trong *cùng* một phiên.

Module này cố ý **không kết luận**. Nó trả về số và nhãn trạng thái; câu
"thị trường đang bị ép" hay không là việc của tầng trên (``format.py``) và của
người đọc.
"""
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta
from functools import lru_cache
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from src.data.stock_data_loader import StockRecord
from src.ta import asof as asof_mod
from src.ta.loader import load_recent, resolve_universe

#: Chỉ số cơ sở. **Không phải VNINDEX** — hợp đồng thanh toán theo VN30.
SPOT = "VN30"
#: Hợp đồng tháng hiện tại: chuỗi nối liên tục, gánh ~99% thanh khoản phái sinh.
FRONT = "VN30F1M"
#: Tháng kế tiếp — mỏng, chỉ dùng để đọc cấu trúc kỳ hạn.
NEXT_MONTH = "VN30F2M"

#: 100.000 đồng cho mỗi điểm chỉ số.
#:
#: Không dùng trực tiếp ở đâu cả: FireAnt đã trả ``totalValue`` bằng đúng giá
#: trị danh nghĩa. Kiểm chứng trên phiên 04/09/2026 —
#: 207.137 HĐ × 1.976,88 điểm × 100.000 = 40.948 tỷ = đúng ``totalValue``.
#: Ghi lại đây để lần sau không ai phải suy lại con số này từ đầu.
CONTRACT_MULTIPLIER = 100_000

#: Cửa sổ tính phân vị basis. 250 phiên ≈ 1 năm giao dịch.
BASIS_WINDOW = 250
#: Dung sai khi so hai phiên "cùng quãng đường tới đáo hạn".
MATURITY_TOL = 3
#: Cửa sổ ước lượng beta so với VN30.
BETA_WINDOW = 120
#: Dưới ngưỡng này thì không phát biểu beta — trả None thay vì một con số dựng
#: từ vài chục điểm.
MIN_BETA_BARS = 60
#: Ngưỡng "sắp đáo hạn" tính bằng phiên.
NEAR_EXPIRY_SESSIONS = 3
#: Lịch sử nạp cho phép đo hành vi phiên đáo hạn. Beta chỉ cần 120 phiên, nhưng
#: đáo hạn mỗi tháng một lần — 400 ngày chỉ cho ~13 quan sát, quá ít để trung vị
#: nói được gì. 5 năm cho ~60 kỳ, đủ để một tháng bất thường không lái kết quả.
EXPIRY_LOOKBACK_DAYS = 1825
#: Dưới ngần này kỳ đáo hạn thì không phát biểu tỷ lệ biên độ.
MIN_EXPIRIES = 12


# ---------------------------------------------------------------------------
# Lịch đáo hạn
# ---------------------------------------------------------------------------
def expiry_date(year: int, month: int) -> date:
    """Thứ Năm **thứ ba** của tháng — ngày giao dịch cuối cùng của hợp đồng.

    Đây là quy tắc niêm yết, không phải ước lượng. Nếu hôm đó nghỉ lễ thì phiên
    cuối lùi về phiên liền trước — việc lùi đó do ``expiry_sessions()`` xử lý,
    vì chỉ ở đó mới biết phiên nào thật sự có giao dịch.
    """
    first = date(year, month, 1)
    # weekday(): thứ Hai = 0 … thứ Năm = 3
    first_thursday = first + timedelta(days=(3 - first.weekday()) % 7)
    return first_thursday + timedelta(days=14)


def expiries_between(start: date, end: date) -> List[date]:
    """Mọi ngày đáo hạn theo lịch trong khoảng ``[start, end]``."""
    out: List[date] = []
    year, month = start.year, start.month
    while date(year, month, 1) <= end:
        day = expiry_date(year, month)
        if start <= day <= end:
            out.append(day)
        month += 1
        if month > 12:
            year, month = year + 1, 1
    return out


def expiry_sessions(session_dates: Sequence[date]) -> List[int]:
    """Chỉ số các phiên đáo hạn **có thật** trong chuỗi phiên đưa vào.

    Ngày đáo hạn theo lịch có thể rơi vào ngày nghỉ; phiên cuối cùng khi đó là
    phiên liền trước. Nên ở đây luôn *ép về phiên tại hoặc trước* ngày lịch,
    thay vì đòi khớp đúng ngày.
    """
    if not session_dates:
        return []
    out: List[int] = []
    for cal in expiries_between(session_dates[0], session_dates[-1]):
        hit = None
        for i, d in enumerate(session_dates):
            if d <= cal:
                hit = i
            else:
                break
        if hit is not None and (not out or out[-1] != hit):
            out.append(hit)
    return out


def roll_indices(session_dates: Sequence[date]) -> Set[int]:
    """Các phiên **ngay sau** một phiên đáo hạn — chỗ chuỗi F1M bị nối.

    Lợi suất tính qua đúng những phiên này là chênh lệch giữa *hai hợp đồng
    khác nhau*, không phải một cú chạy giá. Mọi thống kê trong file này loại
    chúng ra.
    """
    return {i + 1 for i in expiry_sessions(session_dates) if i + 1 < len(session_dates)}


def _sessions_to_expiry(session_dates: Sequence[date], i: int,
                        expiry_idx: Sequence[int]) -> Tuple[int, bool]:
    """``(số phiên còn lại, có phải ước lượng không)``.

    Với phiên nằm trong quá khứ thì đếm được chính xác vì các phiên sau nó đã
    có trên đĩa. Với phiên **cuối cùng** thì kỳ đáo hạn tiếp theo chưa xảy ra,
    nên phải đếm ngày làm việc theo lịch — không trừ được ngày lễ, nên con số
    đó là *chặn trên*. Cờ thứ hai nói rõ đang ở trường hợp nào, thay vì trộn
    hai loại số vào nhau.
    """
    for j in expiry_idx:
        if j >= i:
            return j - i, False
    cal = expiry_date(session_dates[i].year, session_dates[i].month)
    if cal < session_dates[i]:
        nxt = session_dates[i].replace(day=1) + timedelta(days=32)
        cal = expiry_date(nxt.year, nxt.month)
    days = 0
    cursor = session_dates[i]
    while cursor < cal:
        cursor += timedelta(days=1)
        if cursor.weekday() < 5:
            days += 1
    return days, True


# ---------------------------------------------------------------------------
# Trợ giúp số học
# ---------------------------------------------------------------------------
def _round(value: Optional[float], digits: int = 2) -> Optional[float]:
    return round(float(value), digits) if value is not None else None


def _returns(records: Sequence[StockRecord]) -> List[Optional[float]]:
    """``r[k]`` = lợi suất của phiên ``k+1`` so với phiên ``k``."""
    out: List[Optional[float]] = []
    for prev, cur in zip(records, records[1:]):
        out.append(cur.priceClose / prev.priceClose - 1.0 if prev.priceClose else None)
    return out


def _ols(y: Sequence[float], x: Sequence[float]) -> Tuple[float, float, float]:
    """``(alpha, beta, r2)`` bằng bình phương nhỏ nhất. Thuần Python."""
    n = len(y)
    if n == 0:
        return 0.0, 0.0, 0.0
    mx, my = sum(x) / n, sum(y) / n
    sxx = sum((xi - mx) ** 2 for xi in x)
    syy = sum((yi - my) ** 2 for yi in y)
    if sxx == 0:
        return my, 0.0, 0.0
    sxy = sum((xi - mx) * (yi - my) for xi, yi in zip(x, y))
    beta = sxy / sxx
    r2 = (sxy * sxy) / (sxx * syy) if syy else 0.0
    return my - beta * mx, beta, r2


def _percentile_of(value: float, sample: Sequence[float]) -> Optional[float]:
    """Bao nhiêu phần trăm quan sát trong mẫu **thấp hơn hoặc bằng** ``value``."""
    if not sample:
        return None
    return round(100.0 * sum(1 for v in sample if v <= value) / len(sample), 1)


def _median(values: Sequence[float]) -> Optional[float]:
    if not values:
        return None
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2


def _align(a: Sequence[StockRecord],
           b: Sequence[StockRecord]) -> Tuple[List[StockRecord], List[StockRecord]]:
    """Chỉ giữ những phiên **cả hai** chuỗi cùng có."""
    by_date = {r.date.date(): r for r in b}
    xs, ys = [], []
    for r in a:
        hit = by_date.get(r.date.date())
        if hit is not None:
            xs.append(r)
            ys.append(hit)
    return xs, ys


# ---------------------------------------------------------------------------
# Chuỗi basis
# ---------------------------------------------------------------------------
@dataclass
class BasisPoint:
    date: str
    spot: float
    front: float
    basis: float
    basis_pct: float
    sessions_to_expiry: int
    estimated_sessions: bool = False
    is_roll: bool = False
    is_expiry: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


def basis_series(as_of: Optional[datetime] = None,
                 lookback_days: int = 800) -> List[BasisPoint]:
    """Chuỗi chênh lệch phái sinh − cơ sở, mỗi phiên một điểm."""
    spot = load_recent(SPOT, lookback_days, as_of)
    front = load_recent(FRONT, lookback_days, as_of)
    if not spot or not front:
        return []
    spot, front = _align(spot, front)
    dates = [r.date.date() for r in spot]
    exp_idx = expiry_sessions(dates)
    exp_set, roll_set = set(exp_idx), roll_indices(dates)

    out: List[BasisPoint] = []
    for i, (s, f) in enumerate(zip(spot, front)):
        if not s.priceClose:
            continue
        left, estimated = _sessions_to_expiry(dates, i, exp_idx)
        basis = f.priceClose - s.priceClose
        out.append(BasisPoint(
            date=s.date.strftime("%Y-%m-%d"),
            spot=round(s.priceClose, 2),
            front=round(f.priceClose, 2),
            basis=round(basis, 2),
            basis_pct=round(basis / s.priceClose * 100, 3),
            sessions_to_expiry=left,
            estimated_sessions=estimated,
            is_roll=i in roll_set,
            is_expiry=i in exp_set,
        ))
    return out


# ---------------------------------------------------------------------------
# Ảnh chụp thị trường phái sinh
# ---------------------------------------------------------------------------
@dataclass
class FuturesSnapshot:
    as_of: str
    as_of_requested: str = ""
    bars: int = 0
    spot: Dict[str, Any] = field(default_factory=dict)
    front: Dict[str, Any] = field(default_factory=dict)
    basis: Dict[str, Any] = field(default_factory=dict)
    term: Dict[str, Any] = field(default_factory=dict)
    flow: Dict[str, Any] = field(default_factory=dict)
    expiry: Dict[str, Any] = field(default_factory=dict)
    readings: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def _flow_sum(records: Sequence[StockRecord], n: int, field_name: str) -> float:
    return sum(getattr(r, field_name) or 0.0 for r in records[-n:])


def build_futures_snapshot(as_of: Optional[datetime] = None,
                           lookback_days: int = 800) -> FuturesSnapshot:
    """Toàn bộ bức tranh phái sinh của phiên gần nhất, dạng dữ liệu thuần."""
    requested = asof_mod.label(as_of)
    spot_recs = load_recent(SPOT, lookback_days, as_of)
    front_recs = load_recent(FRONT, lookback_days, as_of)

    if not spot_recs or not front_recs:
        missing = [s for s, r in ((SPOT, spot_recs), (FRONT, front_recs)) if not r]
        return FuturesSnapshot(
            as_of="-", as_of_requested=requested,
            warnings=[f"Chưa có dữ liệu {', '.join(missing)} — chạy "
                      f"`update_prices_tool` với universe='futures' và 'benchmarks'"],
        )

    points = basis_series(as_of, lookback_days)
    if not points:
        return FuturesSnapshot(
            as_of="-", as_of_requested=requested,
            warnings=["VN30 và VN30F1M không có phiên nào trùng nhau"],
        )

    spot_recs, front_recs = _align(spot_recs, front_recs)
    cur, s_last, f_last = points[-1], spot_recs[-1], front_recs[-1]
    dates = [r.date.date() for r in spot_recs]
    rolls = roll_indices(dates)

    # --- basis: mức, xu hướng, hai phân vị ---------------------------------
    hist = points[-BASIS_WINDOW:]
    same_maturity = [
        p.basis_pct for p in hist
        if abs(p.sessions_to_expiry - cur.sessions_to_expiry) <= MATURITY_TOL
    ]
    avg5 = _median([p.basis for p in points[-5:]])
    avg20 = _median([p.basis for p in points[-20:]])
    streak = 0
    for p in reversed(points):
        if (p.basis >= 0) == (cur.basis >= 0):
            streak += 1
        else:
            break

    # --- cấu trúc kỳ hạn ---------------------------------------------------
    term: Dict[str, Any] = {}
    next_recs = load_recent(NEXT_MONTH, 40, as_of)
    if next_recs and next_recs[-1].date.date() == dates[-1]:
        term = {
            "f2m": round(next_recs[-1].priceClose, 2),
            "spread": round(next_recs[-1].priceClose - f_last.priceClose, 2),
            "contracts": int(next_recs[-1].dealVolume),
        }

    # --- dòng tiền ---------------------------------------------------------
    vols = [r.dealVolume for r in front_recs]
    avg_vol20 = sum(vols[-21:-1]) / 20 if len(vols) >= 21 else (sum(vols) / len(vols))
    notional = f_last.totalValue or 0.0
    spot_value = s_last.totalValue or 0.0
    lev_hist = [
        (f.totalValue or 0.0) / s.totalValue
        for f, s in zip(front_recs[-21:-1], spot_recs[-21:-1]) if s.totalValue
    ]

    # F1M đổi hợp đồng sau đáo hạn nên % thay đổi qua đường nối là giả tạo.
    front_change = None
    if len(front_recs) > 1 and (len(front_recs) - 1) not in rolls and front_recs[-2].priceClose:
        front_change = round(
            (f_last.priceClose / front_recs[-2].priceClose - 1.0) * 100, 2)

    snap = FuturesSnapshot(
        as_of=cur.date,
        as_of_requested=requested,
        bars=len(points),
        spot={
            "symbol": SPOT,
            "close": cur.spot,
            "change_pct": _round(
                (s_last.priceClose / spot_recs[-2].priceClose - 1.0) * 100
                if len(spot_recs) > 1 and spot_recs[-2].priceClose else None),
            "change_5d": _round(
                (s_last.priceClose / spot_recs[-6].priceClose - 1.0) * 100
                if len(spot_recs) > 5 and spot_recs[-6].priceClose else None),
            "value_bn": _round(spot_value / 1e9, 0),
            "foreign_net_bn": _round(
                ((s_last.buyForeignValue or 0) - (s_last.sellForeignValue or 0)) / 1e9, 0),
        },
        front={
            "symbol": FRONT,
            "close": cur.front,
            "change_pct": front_change,
            "contracts": int(f_last.dealVolume),
            "avg_contracts_20": int(avg_vol20) if avg_vol20 else 0,
            "rvol": _round(f_last.dealVolume / avg_vol20) if avg_vol20 else None,
            "notional_bn": _round(notional / 1e9, 0),
            "roll_session": (len(front_recs) - 1) in rolls,
        },
        basis={
            "points": cur.basis,
            "pct": cur.basis_pct,
            "median_5": _round(avg5),
            "median_20": _round(avg20),
            "percentile": _percentile_of(cur.basis_pct, [p.basis_pct for p in hist]),
            "percentile_same_maturity": _percentile_of(cur.basis_pct, same_maturity),
            "n_same_maturity": len(same_maturity),
            "window": len(hist),
            "streak": streak,
            "widening": bool(avg5 is not None and avg20 is not None
                             and abs(avg5) > abs(avg20) and (avg5 >= 0) == (avg20 >= 0)),
        },
        term=term,
        flow={
            "leverage_ratio": _round(notional / spot_value) if spot_value else None,
            "leverage_avg20": _round(sum(lev_hist) / len(lev_hist)) if lev_hist else None,
            "foreign_net_contracts": int(
                (f_last.buyForeignQuantity or 0) - (f_last.sellForeignQuantity or 0)),
            "foreign_net_contracts_5d": int(
                _flow_sum(front_recs, 5, "buyForeignQuantity")
                - _flow_sum(front_recs, 5, "sellForeignQuantity")),
            "prop_net_bn": _round((f_last.propTradingNetValue or 0.0) / 1e9, 1),
            "prop_net_5d_bn": _round(
                _flow_sum(front_recs, 5, "propTradingNetValue") / 1e9, 1),
        },
        expiry={},
    )

    # --- đáo hạn ------------------------------------------------------------
    cur_day = datetime.strptime(cur.date, "%Y-%m-%d").date()
    cal_expiry = expiry_date(cur_day.year, cur_day.month)
    if cal_expiry < cur_day:
        nxt = cur_day.replace(day=1) + timedelta(days=32)
        cal_expiry = expiry_date(nxt.year, nxt.month)
    snap.expiry = {
        "date": cal_expiry.strftime("%Y-%m-%d"),
        "sessions_left": cur.sessions_to_expiry,
        "days_left": (cal_expiry - cur_day).days,
        "estimated": cur.estimated_sessions,
        "is_expiry_today": cur.is_expiry,
        "near": cur.sessions_to_expiry <= NEAR_EXPIRY_SESSIONS,
    }

    snap.readings = _readings(snap)
    if cur.estimated_sessions:
        snap.warnings.append(
            "Số phiên tới đáo hạn là ước lượng theo ngày làm việc (chưa trừ ngày lễ) "
            "— dùng như chặn trên.")
    if snap.front["roll_session"]:
        snap.warnings.append(
            "Phiên này là phiên nối hợp đồng (ngay sau đáo hạn): VN30F1M đã nhảy sang "
            "tháng mới, nên % thay đổi của hợp đồng không có nghĩa và đã bị bỏ trống.")
    return snap


def _readings(snap: FuturesSnapshot) -> List[str]:
    """Các câu mô tả **trạng thái**, mỗi câu mang theo con số đẻ ra nó.

    Cố ý không có câu nào nói "nên mua" hay "nên bán": đây là mô tả tư thế của
    thị trường phái sinh, không phải khuyến nghị.
    """
    out: List[str] = []
    b, f, e = snap.basis, snap.flow, snap.expiry

    pct = b.get("percentile_same_maturity")
    scope = f"so với {b.get('n_same_maturity')} phiên cùng quãng đường tới đáo hạn"
    if pct is None:
        pct, scope = b.get("percentile"), f"so với {b.get('window')} phiên gần nhất"
    if pct is not None:
        if b["points"] < 0 and pct <= 20:
            out.append(f"Chiết khấu **{abs(b['points']):.1f} điểm** ({b['pct']:+.2f}%) — "
                       f"nằm ở nhóm {pct:.0f}% thấp nhất {scope}")
        elif b["points"] > 0 and pct >= 80:
            out.append(f"Premium **{b['points']:.1f} điểm** ({b['pct']:+.2f}%) — "
                       f"phân vị {pct:.0f}% {scope}")
        else:
            out.append(f"Basis {b['points']:+.1f} điểm ({b['pct']:+.2f}%) — phân vị "
                       f"{pct:.0f}%, quanh mức thường thấy {scope}")
    if b.get("streak", 0) >= 3:
        side = "premium" if b["points"] >= 0 else "chiết khấu"
        out.append(f"Đã **{b['streak']} phiên liên tiếp** giữ {side}"
                   + (" và đang nới rộng" if b.get("widening") else ""))

    lev, lev20 = f.get("leverage_ratio"), f.get("leverage_avg20")
    if lev is not None:
        tail = f" (trung bình 20 phiên: {lev20:.2f}×)" if lev20 else ""
        out.append(f"Giá trị danh nghĩa phái sinh gấp **{lev:.2f}×** giá trị khớp lệnh "
                   f"rổ VN30{tail}")
    rvol = snap.front.get("rvol")
    if rvol and rvol >= 1.3:
        out.append(f"Thanh khoản phái sinh nóng — {snap.front['contracts']:,} hợp đồng, "
                   f"gấp {rvol:.2f}× trung bình 20 phiên")

    prop5 = f.get("prop_net_5d_bn")
    if prop5 is not None and abs(prop5) >= 50:
        side = "mua ròng" if prop5 > 0 else "bán ròng"
        out.append(f"Tự doanh {side} phái sinh **{abs(prop5):,.0f} tỷ** trong 5 phiên")
    fg5 = f.get("foreign_net_contracts_5d")
    if fg5 is not None and abs(fg5) >= 1000:
        side = "mua ròng" if fg5 > 0 else "bán ròng"
        out.append(f"Khối ngoại {side} **{abs(fg5):,} hợp đồng** trong 5 phiên")

    if e.get("is_expiry_today"):
        out.append("⚠️ **Hôm nay là phiên đáo hạn** — giá thanh toán tính theo chỉ số "
                   "VN30 cuối phiên, nên biên độ ATC của các mã vốn hoá lớn thường rộng "
                   "bất thường")
    elif e.get("near"):
        out.append(f"⚠️ Còn **{e['sessions_left']} phiên** tới đáo hạn "
                   f"({e['date']}) — basis buộc phải hội tụ về 0")
    return out


# ---------------------------------------------------------------------------
# Mức chịu ảnh hưởng của từng mã
# ---------------------------------------------------------------------------
@dataclass
class SymbolExposure:
    symbol: str
    in_vn30: bool = False
    beta: Optional[float] = None
    r2: Optional[float] = None
    n_bars: int = 0
    rs_20: Optional[float] = None          # lợi suất 20 phiên trừ đi VN30
    rs_60: Optional[float] = None
    liquidity_share_pct: Optional[float] = None
    expiry_move_ratio: Optional[float] = None   # |lợi suất| phiên đáo hạn / phiên thường
    expiry_vol_ratio: Optional[float] = None
    n_expiries: int = 0
    score: float = 0.0
    channel: str = ""
    note: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@lru_cache(maxsize=8)
def _vn30_liquidity(as_of_key: str) -> Dict[str, float]:
    """Tỷ trọng **thanh khoản** của từng mã trong rổ VN30, 20 phiên gần nhất.

    Đây **không phải trọng số chỉ số** — trọng số VN30 tính theo vốn hoá free
    float có giới hạn trần 10%, và dữ liệu đó không có trong ``data/``. Cái đo
    được ở đây trả lời một câu khác nhưng cũng cần: khi rổ arbitrage bị mua
    hoặc bán cả lô, **tiền rơi vào đâu nhiều nhất**. Ai đọc bảng này cũng phải
    thấy khác biệt đó, nên nhãn phải nói đúng chữ "thanh khoản".
    """
    cutoff = datetime.strptime(as_of_key, "%Y-%m-%d") if as_of_key else None
    values: Dict[str, float] = {}
    for sym in resolve_universe("vn30"):
        recs = load_recent(sym, 60, cutoff)
        if not recs:
            continue
        window = recs[-20:]
        values[sym] = sum(r.totalValue or 0.0 for r in window) / len(window)
    total = sum(values.values())
    if not total:
        return {}
    return {k: round(v / total * 100, 2) for k, v in values.items()}


def vn30_liquidity_share(as_of: Optional[datetime] = None) -> Dict[str, float]:
    """Bản công khai của ``_vn30_liquidity``, và là chỗ để **hâm nóng cache**.

    ``ranking.build()`` chấm điểm cả rổ bằng 8 luồng. Nếu để mỗi luồng tự chạm
    vào cache lần đầu thì cả 8 cùng thấy cache trống và cùng đi nạp 30 mã —
    `lru_cache` không có khoá, nó chỉ bảo đảm *kết quả* dùng lại được, không
    bảo đảm chỉ tính một lần. Gọi hàm này một lần trước khi mở pool là xong.
    """
    return _vn30_liquidity(as_of.strftime("%Y-%m-%d") if as_of else "")


def symbol_exposure(symbol: str, as_of: Optional[datetime] = None,
                    window: int = BETA_WINDOW) -> SymbolExposure:
    """Mã này chịu ảnh hưởng của dòng tiền phái sinh qua đường nào, và bao nhiêu.

    Bốn thành phần, cố ý in ra rời nhau chứ không chỉ gộp thành điểm:

    * **Có nằm trong rổ VN30 không** — đây là kênh *cơ học*. Hợp đồng thanh
      toán theo VN30, nên khi ai đó chênh lệch giá giữa phái sinh và cơ sở,
      lệnh rơi đúng vào 30 mã đó chứ không rơi vào phần còn lại của sàn.
    * **Beta so với VN30** — mã ngoài rổ vẫn chịu ảnh hưởng, nhưng qua tâm lý
      chung. Beta nói phần đó lớn cỡ nào.
    * **Tỷ trọng thanh khoản trong rổ** — lệnh rổ rơi vào đâu nhiều nhất.
    * **Hành vi phiên đáo hạn** — đo thẳng: những phiên đáo hạn trong quá khứ,
      biên độ của mã này có rộng hơn phiên thường không.
    """
    sym = symbol.strip().upper()
    lookback = max(EXPIRY_LOOKBACK_DAYS, window * 3)
    recs = load_recent(sym, lookback, as_of)
    spot = load_recent(SPOT, lookback, as_of)
    out = SymbolExposure(symbol=sym)
    if not recs:
        out.note = f"không có dữ liệu giá cho {sym}"
        return out
    if not spot:
        out.note = f"chưa có dữ liệu {SPOT} — chạy update_prices_tool universe='benchmarks'"
        return out

    out.in_vn30 = sym in set(resolve_universe("vn30"))
    a, b = _align(recs, spot)
    r_sym, r_spot = _returns(a), _returns(b)
    pairs = [(y, x) for y, x in zip(r_sym[-window:], r_spot[-window:])
             if y is not None and x is not None]
    out.n_bars = len(pairs)
    if out.n_bars >= MIN_BETA_BARS:
        _, beta, r2 = _ols([p[0] for p in pairs], [p[1] for p in pairs])
        out.beta, out.r2 = round(beta, 2), round(r2, 2)
    else:
        out.note = f"chỉ có {out.n_bars} phiên khớp với {SPOT} (cần ≥ {MIN_BETA_BARS})"

    for n, attr in ((20, "rs_20"), (60, "rs_60")):
        if len(a) > n and a[-n - 1].priceClose and b[-n - 1].priceClose:
            setattr(out, attr, round(
                (a[-1].priceClose / a[-n - 1].priceClose
                 - b[-1].priceClose / b[-n - 1].priceClose) * 100, 2))

    out.liquidity_share_pct = vn30_liquidity_share(as_of).get(sym)

    # Hành vi phiên đáo hạn, đo bằng trung vị để một phiên sốc không kéo lệch.
    # Mẫu nền là **toàn bộ** cửa sổ 5 năm, không phải 120 phiên của beta: so một
    # nhúm phiên đáo hạn với một nền hẹp là so với chính giai đoạn đang xét.
    dates = [r.date.date() for r in recs]
    exp_idx = [i for i in expiry_sessions(dates) if i > 0]
    rets = _returns(recs)
    all_abs = [abs(r) for r in rets if r is not None]
    exp_abs = [abs(rets[i - 1]) for i in exp_idx
               if 0 < i <= len(rets) and rets[i - 1] is not None]
    out.n_expiries = len(exp_abs)
    base_abs, base_exp = _median(all_abs), _median(exp_abs)
    if base_abs and base_exp is not None and out.n_expiries >= MIN_EXPIRIES:
        out.expiry_move_ratio = round(base_exp / base_abs, 2)
        vols = [r.dealVolume for r in recs if r.dealVolume]
        exp_vols = [recs[i].dealVolume for i in exp_idx if recs[i].dealVolume]
        med_v, med_ev = _median(vols), _median(exp_vols)
        if med_v and med_ev:
            out.expiry_vol_ratio = round(med_ev / med_v, 2)

    out.score, out.channel = _exposure_score(out)
    return out


def _exposure_score(exp: SymbolExposure) -> Tuple[float, str]:
    """Điểm 0–100 để **sắp thứ tự**, không phải xác suất.

    Bốn thành phần vẫn được in riêng ngay cạnh điểm trong ``format.py``: gộp
    lại mà giấu thành phần đi thì một mã ngoài rổ có beta cao trông y hệt một
    mã trong rổ có beta thấp, trong khi hai trường hợp đó chịu ảnh hưởng qua
    hai đường hoàn toàn khác nhau.
    """
    score = 40.0 if exp.in_vn30 else 0.0
    if exp.beta is not None:
        score += min(max(exp.beta, 0.0), 2.0) / 2.0 * 30.0
    if exp.liquidity_share_pct is not None:
        score += min(exp.liquidity_share_pct / 10.0, 1.0) * 20.0
    if exp.expiry_move_ratio is not None:
        score += min(max(exp.expiry_move_ratio - 1.0, 0.0) / 0.5, 1.0) * 10.0

    if exp.in_vn30:
        channel = "Cơ học — nằm trong rổ thanh toán, lệnh arbitrage rơi thẳng vào"
    elif exp.beta is not None and exp.beta >= 1.0:
        channel = "Gián tiếp — ngoài rổ, nhưng đi theo thị trường mạnh hơn trung bình"
    else:
        channel = "Gián tiếp — ngoài rổ, ít đi theo thị trường"
    return round(score, 1), channel


def basket_exposure(spec: Optional[str] = None,
                    as_of: Optional[datetime] = None) -> List[SymbolExposure]:
    """``symbol_exposure`` cho cả nhóm, xếp theo điểm giảm dần."""
    rows = [symbol_exposure(s, as_of) for s in resolve_universe(spec)]
    return sorted(rows, key=lambda r: -r.score)


# ---------------------------------------------------------------------------
# Bằng chứng: basis đã đi trước hay đi sau?
# ---------------------------------------------------------------------------
@dataclass
class BasisBucket:
    label: str
    n: int
    median_fwd: Dict[str, Optional[float]] = field(default_factory=dict)
    share_up: Dict[str, Optional[float]] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


def basis_forward_stats(as_of: Optional[datetime] = None,
                        lookback_days: int = 3600,
                        horizons: Sequence[int] = (1, 3, 5)
                        ) -> Tuple[List[BasisBucket], str]:
    """Sau mỗi mức basis, **VN30 thật sự đi đâu** trong 1/3/5 phiên tiếp theo.

    Đây là phần bắt câu chuyện "basis chiết khấu là điềm xấu" phải trả lời bằng
    số. Cách đọc kết quả có hai chỗ dễ sai, nên cả hai đều được nói thẳng ra:

    * **Các quan sát chồng lấn nhau.** Lợi suất 5 phiên tới của hôm nay và của
      ngày mai dùng chung 4 phiên. ``n`` vì thế **không phải** số quan sát độc
      lập — nó lớn hơn nhiều lần con số đó.
    * **Trung vị, không phải trung bình.** Một phiên sập 5% kéo trung bình đi
      xa hơn nhiều so với mức nó thật sự đại diện.
    """
    points = basis_series(as_of, lookback_days)
    if len(points) < 200:
        return [], (f"chỉ có {len(points)} phiên có cả {SPOT} và {FRONT} "
                    "— chưa đủ để thống kê")

    values = sorted(p.basis_pct for p in points)
    n = len(values)
    cuts = [values[int(n * q)] for q in (0.2, 0.4, 0.6, 0.8)]
    labels = [
        f"Chiết khấu sâu (basis ≤ {cuts[0]:+.2f}%)",
        f"Chiết khấu ({cuts[0]:+.2f}% … {cuts[1]:+.2f}%)",
        f"Trung tính ({cuts[1]:+.2f}% … {cuts[2]:+.2f}%)",
        f"Premium ({cuts[2]:+.2f}% … {cuts[3]:+.2f}%)",
        f"Premium cao (basis > {cuts[3]:+.2f}%)",
    ]
    groups: List[List[int]] = [[] for _ in labels]
    for i, p in enumerate(points):
        k = sum(1 for c in cuts if p.basis_pct > c)
        groups[k].append(i)

    buckets: List[BasisBucket] = []
    for label, idxs in zip(labels, groups):
        bucket = BasisBucket(label=label, n=len(idxs))
        for h in horizons:
            fwd = [
                points[i + h].spot / points[i].spot - 1.0
                for i in idxs if i + h < len(points) and points[i].spot
            ]
            key = f"{h}p"
            if len(fwd) >= 20:
                med = _median(fwd)
                bucket.median_fwd[key] = round(med * 100, 3) if med is not None else None
                bucket.share_up[key] = round(
                    100.0 * sum(1 for v in fwd if v > 0) / len(fwd), 1)
            else:
                bucket.median_fwd[key] = None
                bucket.share_up[key] = None
        buckets.append(bucket)

    note = (f"{len(points)} phiên, từ {points[0].date} đến {points[-1].date}. "
            f"Lợi suất là của **{SPOT}**, không phải của một mã.")
    return buckets, note
