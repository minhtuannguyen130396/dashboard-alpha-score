"""Nhóm ngành: một mã đang khoẻ hay chỉ đang trôi theo cả ngành của nó.

``ranking.py`` chấm từng mã một, mỗi mã đứng riêng. Module này trả lời câu
đứng ngay sau đó và không trả lời được bằng một dòng: **so với những mã cùng
ngành thì mã này thế nào**. Tăng 8% trong 20 phiên là một con số; tăng 8% khi
trung vị ngành tăng 12% là *tụt lại*. Đúng lập luận mà ``CLAUDE.md`` đã dùng
cho VNINDEX, chỉ đổi mẫu số từ thị trường sang ngành.

Ba quyết định thiết kế:

1. **Không tính lại gì cả.** ``build_view`` nhận đúng những ``SymbolRank`` mà
   ``ranking.build`` vừa dựng. Ngành là một phép gộp trên tập đó, không phải
   một lượt quét thứ hai — 79 mã đã nạp một lần rồi.

2. **Nhãn quy mô không phải nhãn ngành.** ``stock_groups`` trong
   ``list_all_stock.json`` trộn hai loại nhãn: ngành (``tai_chinh``, ``bds``…)
   và quy mô/rổ (``vn30``, ``large_cap``, ``mid_cap``, ``small_cap``). Lấy cả
   cụm làm ngành thì "cùng ngành với FPT" hoá ra là 30 mã VN30. Danh sách
   ``SIZE_TAGS`` chặn đúng chỗ đó.

3. **Ngành 1–2 mã không được gộp im lặng.** ``cham_soc_sk`` có đúng 1 mã trong
   ``data/``, ``cntt`` có 2. Trung vị của một quan sát là chính nó, và "sức
   mạnh tương đối so với ngành" khi đó luôn bằng 0 — một số trông như đã đo
   nhưng không đo gì. Dưới ``MIN_PEERS`` thì ``SectorView`` vẫn dựng nhưng
   ``comparable`` = False và mọi phép so tương đối trả ``None``, kèm ``note``
   nói rõ vì sao. Trả ``None`` là thông tin; trả 0 là bịa.
"""
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from statistics import median
from typing import Any, Dict, List, Optional, Sequence

from src.ta.loader import PROJECT_ROOT, STOCK_LIST_DIR, load_recent

#: Nhãn quy mô / rổ chỉ số — **không** phải ngành. Xem quyết định (2) ở trên.
SIZE_TAGS = {"vn30", "large_cap", "mid_cap", "small_cap"}

#: Dưới ngưỡng này thì mọi phép so với ngành đều vô nghĩa. 3 là mức thấp nhất
#: còn cho trung vị một ý nghĩa (mã đang xét + 2 mã khác).
MIN_PEERS = 3

SECTOR_VN = {
    "tai_chinh": "Tài chính",
    "cong_nghiep": "Công nghiệp",
    "bds": "Bất động sản",
    "tieu_dung_thiet_yeu": "Tiêu dùng thiết yếu",
    "tieu_dung": "Tiêu dùng không thiết yếu",
    "nguyen_vat_lieu": "Nguyên vật liệu",
    "nang_luong": "Năng lượng",
    "dich_vu_tien_ich": "Dịch vụ tiện ích",
    "cntt": "Công nghệ thông tin",
    "cham_soc_sk": "Chăm sóc sức khoẻ",
}

_ALL_STOCK = STOCK_LIST_DIR / "list_all_stock.json"

_MEMBERSHIP: Optional[Dict[str, List[str]]] = None


def _load_membership() -> Dict[str, List[str]]:
    """``{mã: [ngành…]}`` — đọc một lần, nhãn quy mô đã bị lọc bỏ."""
    global _MEMBERSHIP
    if _MEMBERSHIP is None:
        table: Dict[str, List[str]] = {}
        if _ALL_STOCK.is_file():
            with _ALL_STOCK.open("r", encoding="utf-8") as f:
                items = json.load(f)
            for it in items:
                code = (it.get("share_code") or "").strip().upper()
                if not code:
                    continue
                tags = [g for g in it.get("stock_groups") or [] if g not in SIZE_TAGS]
                table[code] = tags
        _MEMBERSHIP = table
    return _MEMBERSHIP


def sector_of(symbol: str) -> Optional[str]:
    """Ngành của một mã, hoặc ``None``.

    Một mã có thể mang nhiều nhãn ngành (``VPL`` là ``vn30`` + ``tieu_dung``);
    sau khi bỏ nhãn quy mô thì thực tế còn đúng một, nên lấy cái đầu tiên.
    """
    tags = _load_membership().get(symbol.strip().upper()) or []
    return tags[0] if tags else None


def sector_label(sector: Optional[str]) -> str:
    if not sector:
        return "chưa phân ngành"
    return SECTOR_VN.get(sector, sector)


def members(sector: str) -> List[str]:
    """Mọi mã mang nhãn ngành này, theo registry (chưa lọc theo ``data/``)."""
    return sorted(sym for sym, tags in _load_membership().items() if sector in tags)


def peers(symbol: str) -> List[str]:
    """Các mã cùng ngành, **không** kể chính nó."""
    sec = sector_of(symbol)
    if not sec:
        return []
    sym = symbol.strip().upper()
    return [s for s in members(sec) if s != sym]


def sectors() -> List[str]:
    """Mọi nhãn ngành có trong registry, theo thứ tự bảng chữ cái."""
    seen = set()
    for tags in _load_membership().values():
        seen.update(tags)
    return sorted(seen)


# ---------------------------------------------------------------------------
# Gộp theo ngành, trên đúng các dòng ranking đã dựng
# ---------------------------------------------------------------------------
@dataclass
class SectorView:
    """Ngành đang ở tư thế nào, và mã này đứng đâu bên trong nó."""
    sector: str
    label: str
    n_rows: int                         # số mã cùng ngành có mặt trong bảng
    comparable: bool                    # đủ mã để so hay không
    breadth_up: Optional[float] = None  # % số mã cùng ngành đang có xu hướng tăng
    median_trend: Optional[float] = None
    median_change_20d: Optional[float] = None
    median_change_5d: Optional[float] = None
    leader: str = ""                    # mã cường độ xu hướng cao nhất ngành
    laggard: str = ""
    rank_in_sector: Optional[int] = None  # thứ hạng của mã theo cường độ, 1 = đầu
    rs_vs_sector: Optional[float] = None  # change_20d của mã − trung vị ngành
    note: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SectorView":
        return cls(**data)


def build_view(symbol: str, rows: Sequence[Any]) -> Optional[SectorView]:
    """Tư thế ngành của ``symbol``, gộp từ ``rows`` (các ``SymbolRank`` đã có).

    ``rows`` cố ý nhận kiểu lỏng: module này chỉ đọc ``symbol``, ``trend.side``,
    ``trend.score`` và ``change_20d`` / ``change_5d``, nên không cần import
    ngược ``ranking`` (và tránh vòng import).
    """
    sym = symbol.strip().upper()
    sec = sector_of(sym)
    if not sec:
        return None

    same = [r for r in rows if sector_of(getattr(r, "symbol", "")) == sec]
    n = len(same)
    label = sector_label(sec)
    if n < MIN_PEERS:
        return SectorView(
            sector=sec, label=label, n_rows=n, comparable=False,
            note=(f"Ngành {label} chỉ có {n} mã trong bảng — dưới {MIN_PEERS} mã thì "
                  "trung vị ngành không nói lên điều gì, nên mọi phép so tương đối "
                  "để trống thay vì trả về 0."),
        )

    trends = [r.trend.score for r in same if r.trend is not None]
    ups = sum(1 for r in same if r.trend is not None and r.trend.side == "up")
    ch20 = [r.change_20d for r in same if r.change_20d is not None]
    ch5 = [r.change_5d for r in same if r.change_5d is not None]

    ordered = sorted(same, key=lambda r: -(r.trend.score if r.trend else 0.0))
    me = next((r for r in same if r.symbol.upper() == sym), None)
    med20 = round(median(ch20), 2) if ch20 else None

    rs = None
    if me is not None and me.change_20d is not None and med20 is not None:
        rs = round(me.change_20d - med20, 2)

    return SectorView(
        sector=sec,
        label=label,
        n_rows=n,
        comparable=True,
        breadth_up=round(100.0 * ups / n, 1),
        median_trend=round(median(trends), 1) if trends else None,
        median_change_20d=med20,
        median_change_5d=round(median(ch5), 2) if ch5 else None,
        leader=ordered[0].symbol if ordered else "",
        laggard=ordered[-1].symbol if ordered else "",
        rank_in_sector=(
            next((i for i, r in enumerate(ordered, 1) if r.symbol.upper() == sym), None)
        ),
        rs_vs_sector=rs,
    )


def build_all_views(rows: Sequence[Any]) -> Dict[str, SectorView]:
    """``{mã: SectorView}`` cho mọi mã trong ``rows`` có nhãn ngành."""
    out: Dict[str, SectorView] = {}
    for row in rows:
        sym = getattr(row, "symbol", "")
        view = build_view(sym, rows)
        if view is not None:
            out[sym.upper()] = view
    return out


# ---------------------------------------------------------------------------
# Sức mạnh tương đối so với thị trường
# ---------------------------------------------------------------------------
#: Mốc thị trường cho sức mạnh tương đối. VNINDEX chứ không phải VN30: câu hỏi
#: ở đây là "khoẻ hơn thị trường chung không", còn VN30 là mốc của phái sinh
#: (``futures.py`` đã dùng nó cho beta, và hai câu hỏi đó khác nhau).
MARKET_BENCHMARK = "VNINDEX"


def _pct_change(symbol: str, sessions: int, as_of: Optional[datetime]) -> Optional[float]:
    """% thay đổi qua ``sessions`` phiên gần nhất, tính trên giá đóng cửa."""
    recs = load_recent(symbol, lookback_days=max(90, sessions * 3), as_of=as_of)
    if len(recs) <= sessions:
        return None
    now, then = recs[-1].priceClose, recs[-1 - sessions].priceClose
    if not then:
        return None
    return round((now / then - 1.0) * 100.0, 2)


def market_change(sessions: int = 20, as_of: Optional[datetime] = None) -> Optional[float]:
    """% thay đổi của VNINDEX qua ``sessions`` phiên — mẫu số của mọi phép so."""
    return _pct_change(MARKET_BENCHMARK, sessions, as_of)


@dataclass
class RelativeStrength:
    """Mã này chạy hơn thị trường và hơn ngành bao nhiêu điểm phần trăm."""
    sessions: int
    symbol_change: Optional[float] = None
    market_change: Optional[float] = None
    sector_change: Optional[float] = None
    vs_market: Optional[float] = None
    vs_sector: Optional[float] = None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RelativeStrength":
        return cls(**data)


#: "Chưa truyền" khác "đã tính và không có". Nếu dùng ``None`` cho cả hai thì
#: một lượt dựng bảng mà VNINDEX vắng mặt sẽ đi nạp lại chỉ số **79 lần**, mỗi
#: lần lại trượt, thay vì chấp nhận một lần rằng không có mốc.
UNSET = object()


def relative_strength(symbol_change: Optional[float],
                      sector_change: Optional[float],
                      sessions: int = 20,
                      as_of: Optional[datetime] = None,
                      market: Any = UNSET) -> RelativeStrength:
    """Ghép ba con số lại. ``market`` truyền sẵn để khỏi nạp VNINDEX 79 lần."""
    mkt = market_change(sessions, as_of) if market is UNSET else market
    return RelativeStrength(
        sessions=sessions,
        symbol_change=symbol_change,
        market_change=mkt,
        sector_change=sector_change,
        vs_market=(round(symbol_change - mkt, 2)
                   if symbol_change is not None and mkt is not None else None),
        vs_sector=(round(symbol_change - sector_change, 2)
                   if symbol_change is not None and sector_change is not None else None),
    )
