"""Nạp dữ liệu có cấu trúc của FireAnt vào kho — GĐ1b của kế hoạch.

Đây là đường ngắn nhất tới giá trị thật của tầng tin tức: dữ liệu đã có cấu
trúc, đã có nhãn Mua/Bán chính chủ, không cần chuẩn hoá ngày, không cần gắn mã,
không cần khử trùng lặp. Toàn bộ nhóm A và B của taxonomy nằm ở đây, không tốn
một dòng regex nào ngoài việc parse chuỗi ``title`` của mốc sự kiện.

Lỗi một mã không được giết cả lượt — cùng nguyên tắc với ``ta/update.py``: một
mã lỗi mạng thì ghi lại rồi đi tiếp, vì lượt nạp 80 mã mà chết ở mã thứ 3 là
lượt nạp vô dụng.
"""
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence

from src.news import fireant, store
from src.news import posts as posts_mod
from src.news.parse import parse_holder_transactions, parse_timescale_marks

#: Lùi xa mặc định khi backfill mốc sự kiện. Kho tin FireAnt chỉ về ~2023,
#: nhưng timescale-marks bám theo BCTC nên lùi được xa hơn.
DEFAULT_MARKS_START = "2015-01-01"


@dataclass
class SymbolIngest:
    symbol: str
    transactions: int = 0
    marks: int = 0
    posts: int = 0
    disclosures: int = 0
    error: Optional[str] = None

    @property
    def ok(self) -> bool:
        return self.error is None


@dataclass
class IngestResult:
    symbols: List[SymbolIngest] = field(default_factory=list)

    @property
    def total_transactions(self) -> int:
        return sum(s.transactions for s in self.symbols)

    @property
    def total_marks(self) -> int:
        return sum(s.marks for s in self.symbols)

    @property
    def total_posts(self) -> int:
        return sum(s.posts for s in self.symbols)

    @property
    def total_disclosures(self) -> int:
        return sum(s.disclosures for s in self.symbols)

    @property
    def failed(self) -> List[SymbolIngest]:
        return [s for s in self.symbols if not s.ok]


def ingest_symbol(conn, symbol: str, marks_start: str = DEFAULT_MARKS_START,
                  marks_end: Optional[str] = None,
                  page_limit: int = 100,
                  with_posts: bool = False,
                  posts_since: Optional[str] = None,
                  posts_max_pages: int = posts_mod.MAX_PAGES) -> SymbolIngest:
    """Nạp giao dịch cổ đông lớn + mốc sự kiện cho một mã.

    ``with_posts`` bật thêm phần bài viết. Tách riêng vì nó **đắt hơn hẳn**:
    giao dịch và mốc sự kiện là 2 request/mã, còn bài viết là tới 30 request/mã
    khi backfill. Lượt nạp hằng ngày nên truyền ``posts_since`` để dừng sớm.
    """
    result = SymbolIngest(symbol=symbol)
    end = marks_end or date.today().isoformat()

    raw_tx = fireant.holder_transactions(symbol, offset=0, limit=page_limit)
    txs = parse_holder_transactions(raw_tx, symbol)
    result.transactions = store.upsert_holder_transactions(conn, txs)
    store.log_ingest(conn, symbol, "holder_transactions", result.transactions)

    raw_marks = fireant.timescale_marks(symbol, marks_start, end)
    marks = parse_timescale_marks(raw_marks, symbol)
    result.marks = store.upsert_timescale_marks(conn, marks)
    store.log_ingest(conn, symbol, "timescale_marks", result.marks)

    if with_posts:
        items = posts_mod.fetch_posts(symbol, since=posts_since,
                                      max_pages=posts_max_pages)
        items = posts_mod.dedupe(items)
        result.posts = store.upsert_posts(conn, items)
        result.disclosures = sum(1 for p in items if p.is_insider_news)
        store.log_ingest(conn, symbol, "posts", result.posts,
                         note=f"{result.disclosures} bai ve giao dich noi bo")

    return result


def ingest(symbols: Sequence[str], db_path: Optional[Path] = None,
           marks_start: str = DEFAULT_MARKS_START,
           marks_end: Optional[str] = None,
           progress: Optional[Callable[[SymbolIngest, int, int], None]] = None,
           with_posts: bool = False,
           posts_since: Optional[str] = None) -> IngestResult:
    """Nạp nhiều mã. Một mã hỏng không làm hỏng cả lượt.

    **Commit sau mỗi mã**, không gom vào một transaction cuối lượt. Nạp cả rổ
    mất vài phút vì phải giữ nhịp lịch sự với API; gom hết vào một commit nghĩa
    là đứt giữa chừng thì mất sạch, và trong lúc chạy thì không ai soi được kho
    đã có gì. Trả giá bằng vài chục lần fsync — rẻ hơn nhiều so với phải nạp lại
    từ đầu.
    """
    out = IngestResult()
    total = len(symbols)
    for i, sym in enumerate(symbols, 1):
        try:
            with store.connect(db_path) as conn:
                item = ingest_symbol(conn, sym, marks_start, marks_end,
                                     with_posts=with_posts,
                                     posts_since=posts_since)
        except Exception as exc:                          # noqa: BLE001
            item = SymbolIngest(symbol=sym, error=str(exc))
        out.symbols.append(item)
        if progress:
            progress(item, i, total)
    return out
