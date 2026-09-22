"""Chuỗi quyết định phải khớp — và đây là chỗ code kiểm tra được điều đó.

Không CTCK nào kiểm tự động phần này, và đó là lý do các bản báo cáo của họ hay
tự mâu thuẫn: trang 2 hạ tỷ trọng ngân hàng, trang 9 để ba ngân hàng trong danh
mục khuyến nghị. Một người đọc kỹ bắt được ngay, nhưng người đọc kỹ thì hiếm.

Hai mức, và ranh giới giữa chúng là chủ ý:

* **LOẠI** (``block``) — mâu thuẫn không thể biện minh: tổng tỷ trọng sai, lượt
  quét cờ đỏ ở mức **nghiêm trọng**, mã dưới ngưỡng thanh khoản. Sổ không xuất
  bản được cho tới khi sửa.
* **CẢNH BÁO** (``warn``) — mâu thuẫn *hợp lệ nếu nói ra*: một mã ngược ngành
  đang underweight là một đặt cược có thể đúng, nhưng nó phải được nói thành
  lời chứ không lặng lẽ nằm đó.

Số vi phạm **in ra**, không giấu — đúng luật của ``macro/verdict.py``: giấu đi
thì bộ kiểm tra chỉ làm output *trông* sạch.
"""
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence, Tuple

from src.desk import book as book_mod
from src.desk import ledger as ledger_mod
from src.desk.book import Book
from src.desk.ledger import Standing

BLOCK, WARN = "block", "warn"

#: Sàn tiền mặt khi quan điểm thị trường nghiêng về giảm.
BEARISH_CASH_FLOOR = book_mod.BEARISH_CASH_FLOOR

#: Ngưỡng thanh khoản — dùng lại đúng con số của ``ta/prospect.py`` thay vì đặt
#: một con số thứ hai: hai ngưỡng thanh khoản trong cùng một repo là hai ngưỡng
#: sẽ lệch nhau.
try:                                                           # pragma: no cover
    from src.ta.prospect import LIQUIDITY_MIN_BN as LIQUIDITY_FLOOR_BN
except Exception:                                              # noqa: BLE001
    LIQUIDITY_FLOOR_BN = 20.0


@dataclass
class Check:
    level: str
    code: str
    message: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Report:
    as_of: str
    checks: List[Check] = field(default_factory=list)
    n_positions: int = 0

    @property
    def blocks(self) -> List[Check]:
        return [c for c in self.checks if c.level == BLOCK]

    @property
    def warns(self) -> List[Check]:
        return [c for c in self.checks if c.level == WARN]

    @property
    def publishable(self) -> bool:
        return not self.blocks

    def to_dict(self) -> Dict[str, Any]:
        return {"as_of": self.as_of, "n_positions": self.n_positions,
                "publishable": self.publishable,
                "checks": [c.to_dict() for c in self.checks]}


def _market_stance(as_of: Optional[datetime], root=None) -> Optional[str]:
    rows = ledger_mod.open_entries(kind="market", as_of=as_of, root=root)
    return rows[-1].entry.stance if rows else None


def _underweight_sectors(as_of: Optional[datetime], root=None) -> Dict[str, str]:
    """Ngành nào đang bị hạ tỷ trọng, theo chính sổ."""
    out: Dict[str, str] = {}
    for st in ledger_mod.open_entries(kind="sector", as_of=as_of, root=root):
        out[st.entry.subject] = st.entry.stance
    return out


def redflag_state(symbol: str, as_of: Optional[datetime]
                  ) -> Tuple[Optional[str], List[str]]:
    """``(mức của cả lượt quét, các tiêu đề cờ hình sự/thao túng)``.

    **Mức quyết định chặn, không phải sự có mặt của một từ khoá.** Bộ lọc cờ đỏ
    ưu tiên recall nên nó cố ý bắt thừa rồi *hạ độ tin cậy*; đọc mỗi
    ``Flag.is_critical`` mà bỏ qua mức tổng là chặn gần như mọi mã lớn. Đo thật
    ngày 20/09/2026: FPT bị gắn cờ hình sự vì bài *"Vụ khởi tố bị can Nguyễn
    Thành Nam…"* (độ tin cậy 0,25 — trùng tên, không liên quan doanh nghiệp),
    VCB vì *"Nhân viên ngân hàng 'mượn' 7,2 tỉ đồng"* (0,25 — vai nhân viên), và
    HPG bị chặn trong khi lượt quét của nó chỉ ở mức *cờ vàng*.

    Một validator quá tay còn tệ hơn không có: người dùng sẽ tắt nó. Nên chỉ
    mức ``nghiêm trọng`` mới chặn; cờ hình sự ở mức thấp hơn thành **cảnh báo
    kèm nguyên văn tiêu đề**, để người đọc bác lại trong mười giây.
    """
    try:
        from src.news import redflag as redflag_mod
    except ImportError:                                        # pragma: no cover
        return None, []
    try:
        scan = redflag_mod.build(symbol, as_of=as_of)
    except Exception:                                          # noqa: BLE001
        return None, []
    titles = [f"{f.label}: “{f.title}”"
              for f in (getattr(scan, "flags", None) or []) if f.is_critical]
    return getattr(scan, "level", None), titles


def _liquidity_bn(symbol: str, as_of: Optional[datetime]) -> Optional[float]:
    from src.desk.flows import build_symbol_flow
    flow = build_symbol_flow(symbol, as_of=as_of)
    return flow.adv20_bn


def check(book: Optional[Book] = None, as_of: Optional[datetime] = None,
          root=None, with_redflags: bool = True) -> Report:
    """Chạy toàn bộ kiểm tra chéo trước khi xuất bất kỳ sản phẩm nào."""
    b = book or book_mod.build(as_of=as_of, root=root)
    rep = Report(as_of=b.as_of, n_positions=len(b.positions))

    # 1) tổng tỷ trọng + tiền mặt phải bằng 100
    total = round(b.invested_pct + b.cash_pct, 1)
    if abs(total - 100.0) > 0.5:
        rep.checks.append(Check(BLOCK, "tong_ty_trong",
                                f"tổng tỷ trọng + tiền mặt = {total}%, không phải "
                                "100% — một sổ không cộng lại thành một là một sổ "
                                "không đọc được"))

    # 2) quan điểm thị trường nghiêng giảm mà vẫn đầy cổ phiếu
    stance = _market_stance(as_of, root)
    if stance in ("giam", "dung_ngoai") and b.cash_pct < BEARISH_CASH_FLOOR:
        rep.checks.append(Check(
            WARN, "tien_mat_vs_quan_diem",
            f"quan điểm thị trường `{stance}` nhưng tiền mặt chỉ {b.cash_pct:g}% "
            f"(dưới {BEARISH_CASH_FLOOR:g}%) — hai con số này phải đứng cạnh nhau "
            "trong bản in, không phải mỗi cái một trang"))

    # 3) mã ngược ngành đang hạ tỷ trọng
    uw = {k: v for k, v in _underweight_sectors(as_of, root).items()
          if v in ("giam", "dung_ngoai")}
    for pos in b.positions:
        for subject, sector_stance in uw.items():
            if pos.sector and (subject in pos.sector or pos.sector in subject):
                rep.checks.append(Check(
                    WARN, "nguoc_nganh",
                    f"{pos.symbol} nằm trong sổ nhưng ngành {pos.sector} đang "
                    f"`{sector_stance}` — hợp lệ nếu quan điểm mã nói rõ **vì sao "
                    "ngược ngành**, nhưng phải nói"))

    # 4) cờ đỏ — mức quyết định chặn, không phải sự có mặt của một từ khoá
    if with_redflags:
        try:
            from src.news.redflag import LEVEL_CRITICAL
        except ImportError:                                    # pragma: no cover
            LEVEL_CRITICAL = "nghiem_trong"
        for pos in b.positions:
            level, titles = redflag_state(pos.symbol, as_of)
            if level == LEVEL_CRITICAL:
                rep.checks.append(Check(
                    BLOCK, "co_do",
                    f"{pos.symbol} — lượt quét cờ đỏ ở mức **nghiêm trọng**. "
                    + (titles[0] if titles else "")
                    + " Một vụ khởi tố làm mọi con số phía dưới đổi nghĩa."))
            elif titles:
                rep.checks.append(Check(
                    WARN, "co_do_nhe",
                    f"{pos.symbol} có cờ hình sự/thao túng ở mức dưới nghiêm "
                    f"trọng — {titles[0]}. Bộ lọc ưu tiên bắt thừa, nên đọc "
                    "nguyên văn rồi bác nếu không liên quan; **lờ đi thì không**."))

    # 5) thanh khoản
    for pos in b.positions:
        adv = _liquidity_bn(pos.symbol, as_of)
        if adv is not None and adv < LIQUIDITY_FLOOR_BN:
            rep.checks.append(Check(
                BLOCK, "thanh_khoan",
                f"{pos.symbol} khớp lệnh TB20 chỉ {adv:,.1f} tỷ/phiên, dưới ngưỡng "
                f"{LIQUIDITY_FLOOR_BN:g} tỷ — một mẫu hình đẹp trên mã không ai "
                "giao dịch được là mẫu hình không dùng được"))
    return rep
