"""Nạp bài viết (tin tức) từ FireAnt — GĐ1 của kế hoạch.

**Quyết định thiết kế quan trọng nhất ở đây là *không* nạp toàn văn.**

Toàn văn nằm ở ``/posts/{postID}``, một request riêng cho mỗi bài. Kho có ~2.500
bài mỗi mã lớn; 79 mã là ~200.000 bài, tức ~200.000 request. Ở nhịp lịch sự 1,2
giây/request thì đó là **66 giờ** — không phải một lượt nạp, mà là một dự án.

Response ``list`` thì rẻ hơn 100 lần (100 bài/request) và đã mang sẵn:

* ``title`` — tiêu đề đầy đủ
* ``description`` — đoạn mở đầu, ~300 ký tự
* ``date`` — ISO có sẵn ``+07:00``
* ``postSource`` — báo gốc
* ``taggedSymbols`` — mã đã gắn sẵn

Đủ để lọc, xếp lịch, khử trùng lặp và đọc lướt. Toàn văn chỉ cần khi người ta
thật sự mở một bài ra đọc, nên nó được nạp **lười** qua ``fetch_body`` và cache
theo ``post_id`` — trả tiền cho đúng bài được đọc, không trả trước cho 200.000
bài sẽ không ai đọc.

⚠️ **Nguồn này KHÔNG thay được ngày công bố giao dịch nội bộ.** Kho ``posts`` là
báo chí tài chính phổ thông (giá thép, hợp đồng, vĩ mô), không phải CBTT. Quét
tháng 5/2025 của HPG: 60 bài, **không bài nào** nhắc tới việc một thành viên HĐQT
bán 8,5 triệu cổ phiếu trong chính tháng đó. Xem §8b của kế hoạch.
"""
import hashlib
import re
import unicodedata
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Sequence

from src.news import fireant

#: Một trang list. Spec cho tối đa lớn hơn nhưng 100 là chỗ API ổn định.
PAGE = 100
#: Trần số trang cho mỗi mã khi backfill. 30 trang = 3.000 bài ≈ hết kho.
MAX_PAGES = 30

# --- Nhận diện CBTT trong feed tin tức ------------------------------------
#
# Đây là mảnh quan trọng nhất của module, và nó không hiển nhiên chút nào.
#
# Feed ``posts`` chủ yếu là báo chí phổ thông, nhưng lẫn trong đó có **các bản
# công bố thông tin được đăng lại nguyên văn**, nhận ra bằng tiền tố mã ở đầu
# tiêu đề:
#
#     "HPG: Báo cáo kết quả giao dịch cổ phiếu của người có liên quan..."
#     "FPT: Thông báo giao dịch cổ phiếu ESOP của Người nội bộ..."
#
# Những bài đó mang thứ mà ``holder-transactions`` **không có**: *ngày tin ra
# thị trường*. Và chúng chia làm hai loại có ý nghĩa khác hẳn nhau — thông báo
# trước khi giao dịch, và báo cáo sau khi xong. Trộn hai loại vào một mốc là
# đo nhầm sự kiện.
DISCLOSURE_PREFIX = re.compile(r"^([A-Z]{3}):\s+")

#: Thông báo *trước*: người nội bộ đăng ký sẽ giao dịch. Đây là mốc thị trường
#: thật sự phản ứng, và nó đến **trước** ``startDate`` của bản ghi giao dịch.
KIND_ANNOUNCE = "thong_bao_giao_dich"
#: Báo cáo *sau*: đã giao dịch xong, bao nhiêu. Đến sau ``endDate``.
KIND_RESULT = "bao_cao_ket_qua"

_RE_ANNOUNCE = re.compile(r"thông báo giao dịch|đăng ký (mua|bán)|muốn (mua|bán)|"
                          r"sắp (mua|bán)|dự kiến (mua|bán)", re.I)
_RE_RESULT = re.compile(r"báo cáo kết quả|kết quả giao dịch|đã (mua|bán)|"
                        r"không mua (đủ|hết)|không bán (đủ|hết)|mua bất thành", re.I)

# Hai điều kiện lọc thêm, cả hai đều **bắt buộc**. Một mình động từ giao dịch
# thì bắt nhầm rất nhiều, và mấy ca dưới đây là bắt được từ dữ liệu thật:
#
#   "HPG: Hòa Phát nhận hồ sơ đăng ký mua nhà ở xã hội tại Hưng Yên"
#       → có "đăng ký mua" nhưng đối tượng là *nhà*, không phải cổ phiếu.
#   "Fubon ETF dự kiến mua, bán cổ phiếu nào kỳ review tháng 9/2026?"
#       → có "cổ phiếu" nhưng chủ thể là *quỹ ETF*, không phải người nội bộ.
#
# Nên phải có **cả** đối tượng là cổ phiếu **và** chủ thể là người nội bộ /
# cổ đông lớn thì mới tính.
_RE_SHARES = re.compile(r"cổ phiếu|\bcp\b|chứng khoán|esop", re.I)
_RE_INSIDER = re.compile(
    r"nội bộ|người có liên quan|cổ đông lớn|lãnh đạo|hđqt|hội đồng quản trị|"
    r"chủ tịch|tổng giám đốc|giám đốc|ban kiểm soát|thành viên|kế toán trưởng|"
    r"esop|con trai|con gái|vợ|chồng|người thân", re.I)


def disclosure_kind(title: str) -> Optional[str]:
    """Bài này là thông báo trước, báo cáo sau, hay không phải giao dịch nội bộ.

    Thứ tự kiểm tra có chủ ý: *kết quả* xét trước *thông báo*, vì một tiêu đề
    kiểu "Báo cáo kết quả giao dịch của người đã đăng ký mua" khớp cả hai mẫu,
    mà nghĩa của nó là kết quả.
    """
    if not title:
        return None
    if not (_RE_SHARES.search(title) and _RE_INSIDER.search(title)):
        return None
    if _RE_RESULT.search(title):
        return KIND_RESULT
    if _RE_ANNOUNCE.search(title):
        return KIND_ANNOUNCE
    return None


def is_disclosure(title: str, symbol: str) -> bool:
    """Bài có phải bản công bố được đăng lại (tiền tố ``MÃ: ``) hay không."""
    m = DISCLOSURE_PREFIX.match(title or "")
    return bool(m and m.group(1) == symbol.upper())


@dataclass
class Post:
    """Một bài viết. ``body`` để trống cho tới khi ai đó thật sự cần đọc."""
    post_id: int
    symbol: str
    title: str
    description: str
    date: str
    source: str
    source_url: str
    tagged_symbols: List[str] = field(default_factory=list)
    post_group: str = ""
    fireant_sentiment: Optional[int] = None
    is_ai_generated: bool = False
    body: Optional[str] = None          # nạp lười, xem fetch_body()
    title_hash: str = ""
    is_disclosure: bool = False         # bản CBTT đăng lại (tiền tố "MÃ: ")
    disclosure_kind: Optional[str] = None   # KIND_ANNOUNCE | KIND_RESULT

    @property
    def is_insider_news(self) -> bool:
        """Bài này có nói về giao dịch nội bộ không — dùng để ghép với
        ``holder_transactions`` và lấy ngày công bố thật."""
        return self.disclosure_kind is not None

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["is_insider_news"] = self.is_insider_news
        return d


def _norm_title(title: str) -> str:
    """Chuẩn hoá tiêu đề để so trùng: bỏ dấu, bỏ ký tự lạ, gộp khoảng trắng.

    Báo Việt Nam chép chéo nhau rất nhiều — cùng một tin ra 8 bản với tiêu đề
    lệch vài dấu câu. So chuỗi thô thì 8 bản đó thành 8 tin khác nhau và mọi
    phép đếm "mức độ chú ý" bị thổi lên 8 lần.
    """
    text = unicodedata.normalize("NFD", title or "")
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    text = text.replace("đ", "d").replace("Đ", "D").lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def title_hash(title: str) -> str:
    return hashlib.sha256(_norm_title(title).encode("utf-8")).hexdigest()[:16]


def parse_post(row: dict, symbol: str) -> Optional[Post]:
    """Một bản ghi ``list`` -> ``Post``. Bỏ bài thiếu id hoặc thiếu ngày.

    Thiếu ngày thì bài đó vô dụng cho mọi việc tầng này làm (xếp lịch, cắt theo
    ``as_of``, đo phản ứng), nên giữ lại chỉ tổ lẫn vào thống kê.
    """
    if not row or row.get("postID") is None:
        return None
    when = row.get("date")
    if not when:
        return None
    src = row.get("postSource") or {}
    group = row.get("postGroup") or {}
    title = row.get("title") or ""
    return Post(
        post_id=int(row["postID"]),
        symbol=symbol,
        title=title,
        description=row.get("description") or "",
        date=when,
        source=src.get("name") or "",
        source_url=src.get("url") or "",
        tagged_symbols=[t.get("symbol") for t in (row.get("taggedSymbols") or [])
                        if t.get("symbol")],
        post_group=group.get("name") or "",
        fireant_sentiment=row.get("sentiment"),
        is_ai_generated=bool(row.get("isAIGenerated")),
        title_hash=title_hash(title),
        is_disclosure=is_disclosure(title, symbol),
        disclosure_kind=disclosure_kind(title),
    )


def parse_posts(rows: Sequence[dict], symbol: str) -> List[Post]:
    out = [parse_post(r, symbol) for r in rows or []]
    return [p for p in out if p is not None]


def fetch_posts(symbol: str, kind: int = 1, max_pages: int = MAX_PAGES,
                since: Optional[str] = None) -> List[Post]:
    """Nạp bài của một mã, phân trang cho tới khi hết kho hoặc chạm ``since``.

    ``since`` (ISO ``YYYY-MM-DD``) dừng sớm khi đã lùi đủ xa — lượt nạp hằng ngày
    chỉ cần vài trang đầu, không phải quét lại 3,5 năm mỗi lần.
    """
    out: List[Post] = []
    for page in range(max_pages):
        rows = fireant.posts(symbol, kind=kind, offset=page * PAGE, limit=PAGE)
        if not rows:
            break
        batch = parse_posts(rows, symbol)
        out += batch
        if since and batch and batch[-1].date[:10] < since:
            break
    return out


def fetch_body(post_id: int) -> Optional[str]:
    """Toàn văn một bài — **một request riêng**, chỉ gọi khi thật sự cần đọc.

    Trả HTML thô. Việc gỡ thẻ để ra text thuần là của tầng trên, vì cùng một
    chuỗi HTML có thể muốn render lại (báo cáo) hoặc muốn text phẳng (tìm kiếm).
    """
    detail = fireant.post_detail(post_id)
    if not detail:
        return None
    return detail.get("originalContent") or detail.get("content") or ""


def dedupe(posts: Sequence[Post]) -> List[Post]:
    """Giữ bản sớm nhất của mỗi tiêu đề, bỏ các bản chép lại.

    Bản *sớm nhất* mới là bản gốc; giữ bản mới nhất là ghi nhận sai ngày tin ra
    thị trường, và ngày đó là thứ mọi phép đo phản ứng dựa vào.
    """
    best: Dict[str, Post] = {}
    for p in posts:
        cur = best.get(p.title_hash)
        if cur is None or p.date < cur.date:
            best[p.title_hash] = p
    return sorted(best.values(), key=lambda p: p.date, reverse=True)
