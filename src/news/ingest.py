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

#: Xin mốc sự kiện **tới tương lai** ngần này ngày. Ngày giao dịch không hưởng
#: quyền được công bố trước hàng tháng; cắt cửa sổ ở hôm nay là kho không bao
#: giờ có nổi một mốc phía trước, và lịch xúc tác luôn trống phần cổ tức.
MARKS_FORWARD_DAYS = 120

#: Chồng lấn khi nối tiếp lượt trước. Một bài đăng muộn hoặc bị sửa tiêu đề
#: xuất hiện *sau* mốc kho đang dừng, nên nối khít ngay tại mốc đó là bỏ sót.
#: Giá của chồng lấn là vài chục lượt ghi đè — rẻ hơn hẳn một lỗ thủng im lặng.
OVERLAP_DAYS = 3


@dataclass(frozen=True)
class PostsPlan:
    """Phần bài viết của một lượt nạp với tới đâu, và được tiêu bao nhiêu trang.

    Tách khỏi phần giao dịch/mốc sự kiện vì hai bên **đắt khác nhau một bậc**:
    giao dịch + mốc là 2 request/mã cố định, còn bài viết là 1–30 request/mã tuỳ
    kho đang dừng ở đâu. Gộp chung một "mode" thì lượt hằng ngày phải trả giá
    của lượt backfill.
    """
    #: Lùi tối thiểu bao nhiêu ngày. ``None`` = cả kho, không đặt mốc dừng.
    lookback_days: Optional[int]
    #: Trần số trang cho mỗi mã. Chạm trần là lượt nạp bị **cắt cụt**, phải báo.
    max_pages: int


#: Dùng chung tên mode với ``ta/update.py`` để ``/update`` chỉ có MỘT tham số
#: phạm vi: cùng một chữ ``recent`` nói cả "giá lùi 2 tháng" lẫn "tin lùi 45
#: ngày". Hai tầng không cần trùng con số, chỉ cần trùng *ý* — nếu tách tên
#: riêng thì người dùng phải nhớ hai bảng mode cho cùng một câu lệnh.
NEWS_MODES: Dict[str, PostsPlan] = {
    "latest": PostsPlan(lookback_days=7, max_pages=5),
    "recent": PostsPlan(lookback_days=45, max_pages=10),
    "quarter": PostsPlan(lookback_days=120, max_pages=18),
    "full": PostsPlan(lookback_days=None, max_pages=posts_mod.MAX_PAGES),
}

#: Mã chưa có bài nào trong kho thì không có chỗ nào để "nối tiếp" — lùi mặc
#: định xa hơn cửa sổ của mode để lượt đầu tiên không ra một kho chỉ có 7 ngày.
FIRST_RUN_LOOKBACK_DAYS = 400


@dataclass
class SymbolIngest:
    symbol: str
    transactions: int = 0
    marks: int = 0
    #: Số bài **ghi** trong lượt này — gồm cả phần ghi đè do chồng lấn.
    posts: int = 0
    #: Số bài kho chưa từng có. Đây mới là con số trả lời "có gì mới không".
    posts_new: int = 0
    disclosures: int = 0
    #: Mốc lùi đã dùng cho phần bài viết, ``None`` khi nạp cả kho.
    posts_since: Optional[str] = None
    #: Phân trang dừng vì hết ngân sách trang, không phải vì đã lùi đủ xa —
    #: nghĩa là mã này **còn bài chưa nạp**, chạy lại với mode rộng hơn.
    posts_truncated: bool = False
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
    def total_posts_new(self) -> int:
        return sum(s.posts_new for s in self.symbols)

    @property
    def truncated(self) -> List[SymbolIngest]:
        """Mã còn bài chưa nạp vì chạm trần trang."""
        return [s for s in self.symbols if s.posts_truncated]

    @property
    def total_disclosures(self) -> int:
        return sum(s.disclosures for s in self.symbols)

    @property
    def failed(self) -> List[SymbolIngest]:
        return [s for s in self.symbols if not s.ok]


def resume_since(conn, symbol: str, plan: PostsPlan,
                 today: Optional[date] = None) -> Optional[str]:
    """Mốc lùi cho phần bài viết của một mã: **xa hơn** trong hai mốc — cửa sổ
    của mode, và chỗ kho đang thật sự dừng.

    Lấy một mình cửa sổ của mode là chừa một lỗ thủng vĩnh viễn. Đo trên kho
    thật: bài mới nhất là 04/09, chạy ``latest`` (7 ngày) hôm 17/09 thì phân
    trang dừng ngay khi lùi qua 10/09, và các bài 05→09/09 **không bao giờ**
    được nạp — mà không có gì báo, vì lượt chạy vẫn "xong". Lần sau kho càng
    mới thì lỗ càng chắc chắn nằm lại đó. Cùng loại sai với ``gap_days`` của
    ``/update`` giá, nên xử lý cùng kiểu: nối tiếp chỗ đang dừng, và kêu lên
    khi không nối tới nơi.

    Mã chưa có bài nào thì không có gì để nối — lùi ``FIRST_RUN_LOOKBACK_DAYS``
    để lượt đầu tiên ra một kho dùng được, chứ không phải 7 ngày tin.
    """
    if plan.lookback_days is None:
        return None
    today = today or date.today()
    floor = today - timedelta(days=plan.lookback_days)
    newest = store.latest_post_date(conn, symbol)
    if not newest:
        return (today - timedelta(days=FIRST_RUN_LOOKBACK_DAYS)).isoformat()
    resume = date.fromisoformat(newest) - timedelta(days=OVERLAP_DAYS)
    return min(floor, resume).isoformat()


def ingest_symbol(conn, symbol: str, marks_start: str = DEFAULT_MARKS_START,
                  marks_end: Optional[str] = None,
                  page_limit: int = 100,
                  with_posts: bool = False,
                  posts_since: Optional[str] = None,
                  posts_max_pages: int = posts_mod.MAX_PAGES,
                  posts_plan: Optional[PostsPlan] = None,
                  today: Optional[date] = None) -> SymbolIngest:
    """Nạp giao dịch cổ đông lớn + mốc sự kiện cho một mã.

    ``with_posts`` bật thêm phần bài viết. Tách riêng vì nó **đắt hơn hẳn**:
    giao dịch và mốc sự kiện là 2 request/mã, còn bài viết là tới 30 request/mã
    khi backfill.

    ``posts_plan`` là đường dùng thường ngày: mốc lùi tính riêng cho từng mã,
    nối tiếp chỗ kho đang dừng. ``posts_since`` là mốc khai tay và **đè** lên
    plan — dành cho lúc muốn nạp đúng một quãng đã biết.
    """
    result = SymbolIngest(symbol=symbol)
    # Mốc sự kiện phải xin TỚI TƯƠNG LAI, không dừng ở hôm nay: ngày giao dịch
    # không hưởng quyền được doanh nghiệp công bố trước hàng tháng, và cắt ở
    # hôm nay là kho **không bao giờ** có một mốc nào phía trước — lịch xúc tác
    # (`src/desk/calendar.py`) khi đó luôn trống phần cổ tức mà không có gì báo.
    end = marks_end or (date.today() + timedelta(days=MARKS_FORWARD_DAYS)).isoformat()

    raw_tx = fireant.holder_transactions(symbol, offset=0, limit=page_limit)
    txs = parse_holder_transactions(raw_tx, symbol)
    result.transactions = store.upsert_holder_transactions(conn, txs)
    store.log_ingest(conn, symbol, "holder_transactions", result.transactions)

    raw_marks = fireant.timescale_marks(symbol, marks_start, end)
    marks = parse_timescale_marks(raw_marks, symbol)
    result.marks = store.upsert_timescale_marks(conn, marks)
    store.log_ingest(conn, symbol, "timescale_marks", result.marks)

    if with_posts:
        since, max_pages = posts_since, posts_max_pages
        if posts_plan is not None:
            max_pages = posts_plan.max_pages
            if since is None:
                since = resume_since(conn, symbol, posts_plan, today=today)
        fetched = posts_mod.fetch_posts_paged(symbol, since=since,
                                              max_pages=max_pages)
        items = posts_mod.dedupe(fetched.posts)
        # Đếm bài mới TRƯỚC khi ghi — sau khi ghi thì mọi bài đều "đã có".
        known = store.known_post_ids(conn, (p.post_id for p in items))
        result.posts_since = since
        result.posts_truncated = fetched.hit_page_cap
        result.posts = store.upsert_posts(conn, items)
        result.posts_new = sum(1 for p in items if p.post_id not in known)
        result.disclosures = sum(1 for p in items if p.is_insider_news)
        store.log_ingest(conn, symbol, "posts", result.posts,
                         note=(f"{result.posts_new} bai moi, "
                               f"{result.disclosures} ve giao dich noi bo"))

    return result


def ingest(symbols: Sequence[str], db_path: Optional[Path] = None,
           marks_start: str = DEFAULT_MARKS_START,
           marks_end: Optional[str] = None,
           progress: Optional[Callable[[SymbolIngest, int, int], None]] = None,
           with_posts: bool = False,
           posts_since: Optional[str] = None,
           posts_mode: str = "latest",
           today: Optional[date] = None) -> IngestResult:
    """Nạp nhiều mã. Một mã hỏng không làm hỏng cả lượt.

    **Commit sau mỗi mã**, không gom vào một transaction cuối lượt. Nạp cả rổ
    mất vài phút vì phải giữ nhịp lịch sự với API; gom hết vào một commit nghĩa
    là đứt giữa chừng thì mất sạch, và trong lúc chạy thì không ai soi được kho
    đã có gì. Trả giá bằng vài chục lần fsync — rẻ hơn nhiều so với phải nạp lại
    từ đầu.
    """
    if posts_mode not in NEWS_MODES:
        raise ValueError(
            f"Unknown posts_mode {posts_mode!r}. Available: {', '.join(NEWS_MODES)}")
    plan = NEWS_MODES[posts_mode]

    out = IngestResult()
    total = len(symbols)
    for i, sym in enumerate(symbols, 1):
        try:
            with store.connect(db_path) as conn:
                item = ingest_symbol(conn, sym, marks_start, marks_end,
                                     with_posts=with_posts,
                                     posts_since=posts_since,
                                     posts_plan=plan, today=today)
        except Exception as exc:                          # noqa: BLE001
            item = SymbolIngest(symbol=sym, error=str(exc))
        out.symbols.append(item)
        if progress:
            progress(item, i, total)
    return out
