"""Sổ lệnh mô phỏng — và luật chống chính mình nằm ngay ở tên module.

> **Trọng số do QUY TẮC tính, không do model đặt.**

Model chọn *mã nào vào sổ* và *ở nấc tin cậy nào* (ba nấc). Từ đó module này
tính phần trăm bằng một công thức cố định. Lý do: một con số trọng số do model
tự viết ra **âm thầm mã hoá đòn bẩy và khẩu vị rủi ro** mà không ai duyệt được,
còn "mã X, tin cậy cao" thì duyệt được. Đúng lý lẽ đã dùng khi bỏ chữ mua/bán
để lấy tư thế + mốc.

Công thức, và vì sao từng mảnh:

* **Nghịch đảo biến động** (``ATR_REF / atr%``) — hai mã cùng nấc tin cậy nhưng
  một mã dao động 2%/phiên và mã kia 6%/phiên không phải cùng một mức rủi ro.
  Cho chúng cùng tỷ trọng là để biến động quyết định kết quả thay cho nhận định.
* **Trần theo mã và theo ngành** — một nhận định đúng không bao giờ đáng giá
  cả cuốn sổ, và ba mã ngân hàng là *một* đặt cược chứ không phải ba.
* **Tiền mặt là phần còn lại, và nó là một vị thế.** Không có dòng tiền mặt thì
  "thận trọng" là câu không sai được.
* **``tang_cho`` ăn nửa trọng số** — tư thế chờ kích hoạt là vị thế chưa vào
  đủ; ghi nó như một vị thế đầy đủ là ghi một điều chưa xảy ra.
"""
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from statistics import fmean
from typing import Any, Dict, List, Optional, Sequence

from src.desk import ledger as ledger_mod
from src.desk.ledger import Entry, Standing
from src.ta.loader import load_recent

#: Hệ số theo nấc tin cậy. Ba nấc, không phải một thang liên tục — một thang
#: liên tục là mời model quay lại tự đặt trọng số bằng đường vòng.
CONFIDENCE_FACTOR = {"cao": 1.0, "vua": 0.6, "thap": 0.35}

#: Tư thế nào được cấp vốn, và ở mức nào.
STANCE_FACTOR = {"tang": 1.0, "tang_cho": 0.5,
                 "trung_lap": 0.0, "dung_ngoai": 0.0, "giam": 0.0}

#: Biến động tham chiếu (%/phiên). Mã đúng bằng mức này thì hệ số rủi ro = 1.
ATR_REF = 2.5

#: Trần một mã và một ngành, tính theo % sổ.
MAX_PER_NAME = 12.0
MAX_PER_SECTOR = 30.0

#: Trần tổng tỷ trọng cổ phiếu. Phần còn lại luôn là tiền mặt.
MAX_INVESTED = 90.0

#: Sàn tiền mặt khi quan điểm thị trường nghiêng về giảm — `consistency.py`
#: kiểm, module này không tự ép: ép ở đây là lặng lẽ sửa nhận định của người viết.
BEARISH_CASH_FLOOR = 30.0


def atr_pct(symbol: str, as_of: Optional[datetime] = None,
            window: int = 14) -> Optional[float]:
    """ATR ``window`` phiên chia giá đóng cửa, tính bằng %.

    Tự tính thay vì gọi ``snapshot`` vì sổ chỉ cần đúng một con số, mà dựng cả
    ``Snapshot`` cho mỗi mã là trả giá gấp nhiều lần cho phần không dùng tới.
    """
    bars = load_recent(symbol, 120, as_of)
    if as_of is not None:
        bars = [b for b in bars if b.date <= as_of]
    if len(bars) < window + 1:
        return None
    trs = []
    for prev, cur in zip(bars[-window - 1:], bars[-window:]):
        trs.append(max(cur.priceHigh - cur.priceLow,
                       abs(cur.priceHigh - prev.priceClose),
                       abs(cur.priceLow - prev.priceClose)))
    close = bars[-1].priceClose
    if not close or not trs:
        return None
    return round(fmean(trs) / close * 100, 2)


def sector_of(symbol: str) -> Optional[str]:
    """Ngành ICB cấp 1 của một mã, đọc lại đúng registry mà tầng vĩ mô dùng."""
    try:
        from src.macro import icb, members
    except ImportError:                                        # pragma: no cover
        return None
    sym = symbol.strip().upper()
    for row in icb.load_registry():
        if int(row.get("level") or 0) != 1 or row.get("duplicate_of"):
            continue
        code = str(row.get("icb_code"))
        if sym in members.in_basket(code):
            return str(row.get("name") or code)
    return None


@dataclass
class Position:
    symbol: str
    stance: str
    confidence: str
    weight_pct: float
    raw_weight: float = 0.0
    atr_pct: Optional[float] = None
    sector: Optional[str] = None
    entry_id: str = ""
    headline: str = ""
    capped_by: str = ""              # "mã" | "ngành" | "" — nói ra chỗ bị cắt

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Book:
    as_of: str
    positions: List[Position] = field(default_factory=list)
    cash_pct: float = 100.0
    notes: List[str] = field(default_factory=list)

    @property
    def invested_pct(self) -> float:
        return round(sum(p.weight_pct for p in self.positions), 1)

    @property
    def by_sector(self) -> Dict[str, float]:
        out: Dict[str, float] = {}
        for p in self.positions:
            out[p.sector or "chưa phân ngành"] = round(
                out.get(p.sector or "chưa phân ngành", 0.0) + p.weight_pct, 1)
        return out

    def to_dict(self) -> Dict[str, Any]:
        return {"as_of": self.as_of, "cash_pct": self.cash_pct,
                "invested_pct": self.invested_pct,
                "positions": [p.to_dict() for p in self.positions],
                "by_sector": self.by_sector, "notes": self.notes}


def build(as_of: Optional[datetime] = None,
          standings: Optional[Sequence[Standing]] = None,
          root=None) -> Book:
    """Dựng sổ từ các quan điểm **cấp mã đang còn hiệu lực**."""
    rows = list(standings if standings is not None
                else ledger_mod.open_entries(kind="stock", as_of=as_of, root=root))
    day = (as_of or datetime.now()).strftime("%Y-%m-%d")
    book = Book(as_of=day)
    if not rows:
        book.notes.append("chưa có quan điểm cấp mã nào còn hiệu lực — sổ **toàn "
                          "tiền mặt**, và đó là *chưa ai viết gì*, không phải một "
                          "quyết định phòng thủ")
        return book

    raw: List[Position] = []
    for st in rows:
        e: Entry = st.entry
        stance_factor = STANCE_FACTOR.get(e.stance, 0.0)
        if stance_factor <= 0:
            continue
        vol = atr_pct(e.subject, as_of)
        risk_factor = (ATR_REF / vol) if vol else 1.0
        weight = (CONFIDENCE_FACTOR.get(e.confidence, 0.6) * stance_factor
                  * risk_factor * MAX_PER_NAME)
        raw.append(Position(symbol=e.subject, stance=e.stance,
                            confidence=e.confidence, weight_pct=weight,
                            raw_weight=round(weight, 2), atr_pct=vol,
                            sector=sector_of(e.subject), entry_id=e.entry_id,
                            headline=e.headline))
    if not raw:
        book.notes.append("mọi quan điểm đang mở đều là trung lập / đứng ngoài / "
                          "giảm — sổ toàn tiền mặt theo đúng những gì đã viết")
        return book

    # 1) trần theo mã
    for p in raw:
        if p.weight_pct > MAX_PER_NAME:
            p.weight_pct, p.capped_by = MAX_PER_NAME, "mã"

    # 2) trần theo ngành — cắt theo tỷ lệ trong chính ngành đó
    by_sector: Dict[str, List[Position]] = {}
    for p in raw:
        by_sector.setdefault(p.sector or "chưa phân ngành", []).append(p)
    for sector, group in by_sector.items():
        total = sum(p.weight_pct for p in group)
        if total > MAX_PER_SECTOR:
            scale = MAX_PER_SECTOR / total
            for p in group:
                p.weight_pct *= scale
                p.capped_by = p.capped_by or "ngành"
            book.notes.append(f"ngành {sector} chạm trần {MAX_PER_SECTOR:g}% — "
                              f"{len(group)} mã bị cắt theo tỷ lệ")

    # 3) trần tổng
    total = sum(p.weight_pct for p in raw)
    if total > MAX_INVESTED:
        scale = MAX_INVESTED / total
        for p in raw:
            p.weight_pct *= scale
        book.notes.append(f"tổng tỷ trọng chạm trần {MAX_INVESTED:g}% — cắt đều "
                          "theo tỷ lệ")

    for p in raw:
        p.weight_pct = round(p.weight_pct, 1)
    book.positions = sorted(raw, key=lambda p: p.weight_pct, reverse=True)
    book.cash_pct = round(100.0 - book.invested_pct, 1)
    missing_vol = [p.symbol for p in raw if p.atr_pct is None]
    if missing_vol:
        book.notes.append("chưa đo được biến động của " + ", ".join(missing_vol)
                          + " — các mã này dùng hệ số rủi ro 1, tức **chưa hiệu "
                            "chỉnh theo biến động**")
    return book
