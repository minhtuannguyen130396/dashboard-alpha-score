"""Đầu mục tin tức N phiên gần nhất, kèm câu hỏi thật sự khó: *đã vào giá chưa.*

Khác ``news_impact`` (đo vài giao dịch nội bộ gần nhất, mỗi cái một bảng đầy đủ),
module này trả **danh sách đầu mục** của một khoảng phiên, nhóm theo phiên, mỗi
phiên mang một trạng thái đo được. Đây là thứ cắm được vào hồ sơ 1 mã.

Ba quyết định thiết kế, mỗi cái chặn một lỗi cụ thể:

1. **Trạng thái thuộc về PHIÊN, không thuộc về từng tin.** Một phiên thường có
   5–10 bài. Không có cách nào tách phần đóng góp của từng bài vào cùng một cú
   chạy giá, nên gắn "đã vào giá" cho một tiêu đề cụ thể là bịa ra quan hệ nhân
   quả. Đầu mục nằm *dưới* phiên, trạng thái nằm *ở* phiên.

2. **Ngày đăng bài KHÔNG phải phiên bị ảnh hưởng.** Đo trên cả kho: **56% bài
   đăng sau 14:45** — sau giờ ATC. Lấy ngày đăng làm ``t0`` là so tin với một giá
   đóng cửa đã chốt *trước khi tin tồn tại*, và sai lệch đó một chiều: nó biến
   phản ứng thật thành "không phản ứng". ``effective_session`` đẩy các bài đó
   sang phiên kế tiếp.

3. **Nhóm ngành/thị trường cố ý KHÔNG đo.** Một bài điểm tin gắn 15 mã không
   nói gì riêng về mã này; gắn cho nó một abnormal return là đọc nhiễu thành tin.
   Vẫn liệt kê đầu mục — người đọc cần biết là có — nhưng trạng thái để trống.

Ngưỡng ``BIG_MOVE`` phải đọc so với **nền placebo**, không so với 0: §8b của
``Documents/plan_news_pipeline.md`` đo được trung vị placebo −0,33%, nên một CAR
−0,5% không phải bằng chứng của phản ứng tiêu cực. 3% nằm xa hẳn vùng đó.
"""
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Sequence

from src.news import reaction as reaction_mod
from src.news import store as store_mod
from src.news.models import DIRECTION_VN
from src.news.reaction import Reaction
from src.ta.loader import load_prices

#: Số phiên mặc định của cửa sổ đầu mục.
SESSIONS_DEFAULT = 20

#: Giờ đóng cửa phiên khớp lệnh (hết ATC, HOSE). Bài đăng từ mốc này trở đi
#: không thể tác động vào giá đóng cửa hôm đó — sớm nhất là phiên kế tiếp.
CLOSE_HHMM = (14, 45)

#: Ngưỡng "đủ lớn để đáng nói" cho abnormal return trên một cửa sổ vài phiên.
#: Dùng chung với ``format._read_pattern`` — một con số, một chỗ.
BIG_MOVE = 0.03

# --- Nhóm bằng chứng ------------------------------------------------------
# Không phải "mức độ quan trọng của tin" — cái đó cần đọc nội dung, và đọc nội
# dung là GĐ4. Đây là *tin này được chống lưng bằng loại bằng chứng nào*, và nó
# kiểm chứng được bằng ba trường có sẵn trong kho.
GROUP_DISCLOSURE = "cbtt"        # công bố thông tin / có bản ghi có cấu trúc
GROUP_COMPANY = "doanh_nghiep"   # tin về chính doanh nghiệp
GROUP_SECTOR = "nganh"           # điểm tin ngành / thị trường có nhắc mã

GROUP_ORDER = [GROUP_DISCLOSURE, GROUP_COMPANY, GROUP_SECTOR]
GROUP_VN = {
    GROUP_DISCLOSURE: "CBTT / bản ghi có cấu trúc",
    GROUP_COMPANY: "tin doanh nghiệp",
    GROUP_SECTOR: "tin ngành / thị trường",
}

#: Trên ngưỡng này thì bài là điểm tin nhiều mã, không phải tin của riêng mã.
MAX_TAGS_COMPANY = 3

# --- Trạng thái "đã vào giá chưa" ----------------------------------------
ST_NO_SESSION = "chua_co_phien"
ST_FRESH = "moi_mot_phien"
ST_PRICED_IN = "da_vao_gia"
ST_RAN_BEFORE = "chay_truoc_tin"
ST_DRIFTING = "con_troi_tiep"
ST_NO_REACT = "chua_phan_ung"
ST_TOO_EARLY = "chua_du_phien"
ST_NOT_MEASURED = "khong_do"
ST_UNMEASURABLE = "khong_do_duoc"

STATUS_VN = {
    ST_NO_SESSION: "chưa có phiên nào",
    ST_FRESH: "mới 1 phiên",
    ST_PRICED_IN: "đã vào giá",
    ST_RAN_BEFORE: "giá chạy trước tin",
    ST_DRIFTING: "còn trôi tiếp",
    ST_NO_REACT: "chưa phản ứng",
    ST_TOO_EARLY: "chưa đủ phiên",
    ST_NOT_MEASURED: "không đo",
    ST_UNMEASURABLE: "không đo được",
}

#: Vì sao trạng thái đó. Câu dài nằm ở ``format.py``; đây là phần ngắn đi kèm nhãn.
STATUS_NOTE = {
    ST_NO_SESSION: "tin ra sau phiên cuối cùng, chưa có giá để đối chiếu",
    ST_FRESH: "mới đóng cửa phiên đầu, cửa sổ tức thì (t0…t+1) chưa đủ",
    ST_PRICED_IN: "phản ứng nằm ở hai phiên đầu",
    ST_RAN_BEFORE: "biến động nằm ở 5 phiên TRƯỚC tin, không phải sau",
    ST_DRIFTING: "hai phiên đầu êm, nhưng 10 phiên sau còn đi tiếp",
    ST_NO_REACT: "đủ 10 phiên sau tin, không cửa sổ nào vượt ngưỡng",
    ST_TOO_EARLY: "tức thì chưa vượt ngưỡng, chưa đủ 10 phiên để xét phần trôi",
    ST_NOT_MEASURED: "tin ngành/thị trường — cố ý không quy về một mã",
    ST_UNMEASURABLE: "không đủ phiên để ước lượng α/β",
}


# ---------------------------------------------------------------------------
# Ánh xạ ngày đăng → phiên bị ảnh hưởng
# ---------------------------------------------------------------------------
def _parse_published(value: str) -> Optional[datetime]:
    """``2026-09-04T21:28:00+07:00`` → datetime theo đúng giờ ghi trong chuỗi.

    Giữ nguyên giờ địa phương (+07) chứ không đổi múi: mốc 14:45 là giờ sàn.
    """
    if not value:
        return None
    text = str(value).strip()
    try:
        return datetime.fromisoformat(text).replace(tzinfo=None)
    except ValueError:
        pass
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(text[:19], fmt)
        except ValueError:
            continue
    return None


def effective_session(published: str, sessions: Sequence[str]) -> Optional[str]:
    """Phiên sớm nhất mà tin này *có thể* tác động vào giá đóng cửa.

    Bài đăng trước 14:45 của một ngày giao dịch thì phiên đó là ứng viên; đăng
    sau đó (hoặc vào ngày nghỉ) thì sớm nhất là phiên kế tiếp. Trả ``None`` khi
    tin ra sau phiên cuối cùng có dữ liệu — chưa có gì để đo, và đó là một câu
    trả lời chứ không phải lỗi.
    """
    dt = _parse_published(published)
    if dt is None:
        return None
    day = dt.strftime("%Y-%m-%d")
    after_close = (dt.hour, dt.minute) >= CLOSE_HHMM
    for s in sessions:
        if s > day or (s == day and not after_close):
            return s
    return None


# ---------------------------------------------------------------------------
# Kiểu dữ liệu
# ---------------------------------------------------------------------------
@dataclass
class NewsItem:
    """Một đầu mục. Cố ý **không** mang toàn văn — xem docstring ``posts.py``."""
    title: str
    published: str                  # nguyên văn ISO từ kho
    session: Optional[str]          # phiên bị ảnh hưởng, sau khi ánh xạ
    group: str
    source: str = ""
    url: str = ""
    post_id: Optional[int] = None
    kind: str = "post"              # post | bctc | co_tuc | giao_dich_noi_bo
    evidence: List[str] = field(default_factory=list)
    tagged_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class SessionNews:
    """Một phiên có tin, kèm phản ứng đo được **của phiên đó**."""
    session: str
    items: List[NewsItem] = field(default_factory=list)
    status: str = ST_NOT_MEASURED
    sessions_after: int = 0
    reaction: Optional[Reaction] = None

    @property
    def top_group(self) -> str:
        for g in GROUP_ORDER:
            if any(i.group == g for i in self.items):
                return g
        return GROUP_SECTOR

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session": self.session,
            "status": self.status,
            "sessions_after": self.sessions_after,
            "items": [i.to_dict() for i in self.items],
            "reaction": self.reaction.to_dict() if self.reaction else None,
        }


@dataclass
class NewsDigest:
    symbol: str
    session_from: str
    session_to: str
    sessions: int
    days: List[SessionNews] = field(default_factory=list)
    n_items: int = 0
    n_hidden: int = 0
    counts: Dict[str, int] = field(default_factory=dict)
    note: str = ""

    @property
    def is_empty(self) -> bool:
        return not self.days

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol, "session_from": self.session_from,
            "session_to": self.session_to, "sessions": self.sessions,
            "n_items": self.n_items, "n_hidden": self.n_hidden,
            "counts": self.counts, "note": self.note,
            "days": [d.to_dict() for d in self.days],
        }


# ---------------------------------------------------------------------------
# Tin tiêu biểu
# ---------------------------------------------------------------------------
@dataclass
class Highlight:
    """Một đầu mục đáng nêu, kèm **ảnh hưởng đã đo được của phiên nó rơi vào**.

    Cố ý chỉ mang tiêu đề + một con số: đây là mục để liếc, không phải mục để
    đọc. Toàn bộ chi tiết (mọi đầu mục của phiên, cả ba cửa sổ CAR, ghi chú
    trần/sàn) vẫn nằm nguyên ở khối đầu mục theo phiên bên dưới.
    """
    title: str
    session: str
    published: str
    status: str
    car_immediate: Optional[float] = None
    car_post: Optional[float] = None
    n_items: int = 1                # phiên đó có mấy đầu mục, để không quy nhân quả
    source: str = ""
    kind: str = "post"

    @property
    def impact(self) -> Optional[float]:
        """Con số lớn hơn trong hai cửa sổ — thước để xếp thứ tự."""
        vals = [abs(v) for v in (self.car_immediate, self.car_post) if v is not None]
        return max(vals) if vals else None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


#: Trạng thái đã **đo xong và thấy có chuyện**. ``ST_NO_REACT`` cố ý không nằm
#: đây: nó là kết luận thật ("đủ 10 phiên, không cửa sổ nào vượt ngưỡng"), nhưng
#: một tin không làm giá nhúc nhích thì không phải *tin tiêu biểu*.
MOVED_STATUSES = (ST_PRICED_IN, ST_RAN_BEFORE, ST_DRIFTING)


def _representative(day: "SessionNews") -> Optional["NewsItem"]:
    """Đầu mục đại diện cho một phiên — **ưu tiên tin của riêng mã**.

    Một phiên có 5–10 bài và không có cách nào tách phần đóng góp của từng bài
    (xem §1 đầu file), nên "đại diện" ở đây chỉ là *chọn cái đáng nêu nhất*,
    không phải *chọn cái gây ra cú chạy*. Thứ tự: CBTT → bài gắn ít mã nhất →
    bài đầu. Điểm tin cả rổ đứng cuối vì nó không nói gì riêng về mã này.
    """
    if not day.items:
        return None
    return sorted(
        day.items,
        key=lambda i: (GROUP_ORDER.index(i.group) if i.group in GROUP_ORDER else 9,
                       i.tagged_count or 0, i.published),
    )[0]


def highlights(digest: "NewsDigest", limit: int = 5) -> List[Highlight]:
    """Vài đầu mục đáng nêu nhất, xếp theo **độ lớn của phản ứng đã đo**.

    Đây là phép **đo**, không phải nhận định: nó không đọc nội dung bài nào,
    chỉ hỏi "phiên này có tin, và giá phiên đó đã đi bao xa so với thị trường".
    Vì thế nó dùng được cho cả rổ mà không cần ai ngồi đọc — khác hẳn phần
    phán quyết cờ đỏ và phần chấm điểm tin.

    Hai chỗ cố ý loại bỏ:

    * **Phiên chưa đo được** (``chưa đủ phiên`` / ``mới 1 phiên`` / ``chưa có
      phiên nào``) — gộp chúng vào đây là nêu một đầu mục "tiêu biểu" dựa trên
      dữ liệu chưa tồn tại.
    * **Phiên chỉ có tin ngành** — bài gắn trên 3 mã là điểm tin cả rổ, quy
      abnormal return của riêng mã này cho nó là đọc nhiễu thành tín hiệu.
    """
    out: List[Highlight] = []
    for day in (digest.days if digest else []):
        if day.status not in MOVED_STATUSES or day.reaction is None:
            continue
        item = _representative(day)
        if item is None or item.group == GROUP_SECTOR:
            continue
        out.append(Highlight(
            title=item.title, session=day.session, published=item.published,
            status=day.status, car_immediate=day.reaction.car_immediate,
            car_post=day.reaction.car_post, n_items=len(day.items),
            source=item.source, kind=item.kind,
        ))
    out.sort(key=lambda h: (-(h.impact or 0.0), h.session))
    return out[:max(1, limit)]


# ---------------------------------------------------------------------------
# Phân nhóm
# ---------------------------------------------------------------------------
def classify_post(row: Dict[str, Any]) -> str:
    """Bài này được chống lưng bằng loại bằng chứng nào.

    Không đọc nội dung — chỉ dùng ba thứ kiểm chứng được: nhãn CBTT của
    ``posts.py``, tiền tố ``MÃ:``, và **số mã được gắn thẻ**. Cái thứ ba là dấu
    hiệu rẻ mà mạnh: một bài gắn 15 mã là điểm tin cả rổ, không phải tin của mã
    này — đo nó như tin riêng là đọc nhiễu thành tín hiệu.
    """
    if row.get("disclosure_kind"):
        return GROUP_DISCLOSURE
    if row.get("is_disclosure"):
        return GROUP_DISCLOSURE
    tags = row.get("tagged_symbols") or []
    if len(tags) <= MAX_TAGS_COMPANY:
        return GROUP_COMPANY
    return GROUP_SECTOR


def _post_evidence(row: Dict[str, Any]) -> List[str]:
    out: List[str] = []
    kind = row.get("disclosure_kind")
    if kind == "thong_bao_giao_dich":
        out.append("thông báo giao dịch nội bộ (trước khi thực hiện)")
    elif kind == "bao_cao_ket_qua":
        out.append("báo cáo kết quả giao dịch nội bộ")
    if row.get("is_disclosure"):
        out.append("bản CBTT đăng lại")
    n = len(row.get("tagged_symbols") or [])
    if n > MAX_TAGS_COMPANY:
        out.append(f"gắn {n} mã")
    return out


# ---------------------------------------------------------------------------
# Trạng thái
# ---------------------------------------------------------------------------
def classify_status(reaction: Optional[Reaction], sessions_after: int) -> str:
    """Phản ứng đã đo được tới đâu — thứ tự kiểm tra có chủ ý.

    Tức thì xét **trước** rò rỉ: khi cả hai cửa sổ đều lớn thì cái đáng gọi tên
    là phản ứng tại tin, còn phần trước là bối cảnh. Đảo lại thì mọi tin ra sau
    một nhịp tăng đều bị dán nhãn "chạy trước tin".
    """
    if reaction is None:
        return ST_NO_SESSION
    if reaction.beta is None:
        return ST_UNMEASURABLE
    if sessions_after < 1:
        return ST_FRESH

    imm, pre, post = (reaction.car_immediate, reaction.car_pre,
                      reaction.car_post)
    if imm is not None and abs(imm) >= BIG_MOVE:
        return ST_PRICED_IN
    if pre is not None and abs(pre) >= BIG_MOVE:
        return ST_RAN_BEFORE
    if sessions_after >= 10:
        if post is not None and abs(post) >= BIG_MOVE:
            return ST_DRIFTING
        return ST_NO_REACT
    return ST_TOO_EARLY


# ---------------------------------------------------------------------------
# Dựng digest
# ---------------------------------------------------------------------------
def _sessions_for(symbol: str, count: int,
                  as_of: Optional[datetime]) -> List[str]:
    """``count`` phiên gần nhất tính tới ``as_of`` (hoặc tới hết dữ liệu)."""
    end = as_of or datetime.now()
    # Đủ rộng cho cả kỳ nghỉ Tết: 20 phiên ~ 28 ngày lịch, nhân bốn cho chắc.
    start = end - timedelta(days=max(60, count * 4))
    recs = load_prices(symbol, start, end)
    return [r.date.strftime("%Y-%m-%d") for r in recs][-count:]


def _mark_items(rows: Sequence[Dict[str, Any]],
                sessions: Sequence[str]) -> List[NewsItem]:
    """BCTC / cổ tức từ ``timescale_marks`` — mốc có **ngày công bố thật**."""
    window = set(sessions)
    out: List[NewsItem] = []
    for r in rows:
        day = str(r.get("date") or "")[:10]
        if day not in window:
            continue
        kind = {"F": "bctc", "D": "co_tuc"}.get(r.get("label"), "khac")
        out.append(NewsItem(
            title=r.get("raw_title") or "(không có tiêu đề)",
            published=day, session=day, group=GROUP_DISCLOSURE,
            source="FireAnt timescale-marks", kind=kind,
            evidence=["ngày công bố thật, không phải mốc thay thế"],
        ))
    return out


def _transaction_items(rows: Sequence[Dict[str, Any]],
                       sessions: Sequence[str]) -> List[NewsItem]:
    """Giao dịch nội bộ / cổ đông lớn mở cửa sổ đăng ký trong khoảng phiên.

    ``start_date`` là **mốc thay thế** cho ngày công bố (§2b) — nói rõ ở
    ``evidence`` chứ không im lặng dùng nó như ngày thật.
    """
    window = set(sessions)
    out: List[NewsItem] = []
    for r in rows:
        day = str(r.get("start_date") or r.get("execution_date") or "")[:10]
        if day not in window:
            continue
        who = r.get("name") or "?"
        role = r.get("position") or "cổ đông lớn"
        direction = DIRECTION_VN.get(r.get("direction"), "?")
        reg = r.get("registered_volume")
        amount = f"đăng ký {reg:,.0f} cp" if reg else "không có đăng ký"
        out.append(NewsItem(
            title=f"{who} ({role}) — {direction} {amount}",
            published=day, session=day, group=GROUP_DISCLOSURE,
            source="FireAnt holder-transactions", kind="giao_dich_noi_bo",
            evidence=["ngày mở cửa sổ đăng ký — mốc thay thế cho ngày công bố"],
        ))
    return out


def build_digest(symbol: str, sessions: int = SESSIONS_DEFAULT,
                 as_of: Optional[datetime] = None,
                 session_dates: Optional[Sequence[str]] = None,
                 db_path=None, measure: bool = True,
                 max_per_session: int = 4) -> NewsDigest:
    """Đầu mục ``sessions`` phiên gần nhất của một mã, kèm trạng thái mỗi phiên.

    ``session_dates`` cho phép tầng gọi truyền sẵn danh sách phiên (hồ sơ 1 mã
    đã có ``structure.records``, khỏi nạp lại). ``measure=False`` bỏ hẳn phần
    event study — nhanh hơn nhiều khi chỉ cần liệt kê đầu mục.
    """
    sym = symbol.strip().upper()
    dates = list(session_dates)[-sessions:] if session_dates \
        else _sessions_for(sym, sessions, as_of)
    if not dates:
        return NewsDigest(symbol=sym, session_from="", session_to="",
                          sessions=0, note=f"không có dữ liệu giá cho {sym}")

    lo, hi = dates[0], dates[-1]
    index = {d: i for i, d in enumerate(dates)}
    cutoff = hi

    with store_mod.connect(db_path) as conn:
        post_rows = store_mod.load_posts(conn, sym, as_of=cutoff, limit=400)
        marks = store_mod.load_marks(conn, sym, as_of=cutoff)
        txs = store_mod.load_holder_transactions(conn, sym, as_of=cutoff)

    items: List[NewsItem] = []
    for row in post_rows:
        published = str(row.get("date") or "")
        if published[:10] < lo:
            continue
        items.append(NewsItem(
            title=row.get("title") or "(không có tiêu đề)",
            published=published,
            session=effective_session(published, dates),
            group=classify_post(row), source=row.get("source") or "",
            url=row.get("source_url") or "", post_id=row.get("post_id"),
            kind="post", evidence=_post_evidence(row),
            tagged_count=len(row.get("tagged_symbols") or []),
        ))
    items += _mark_items(marks, dates)
    items += _transaction_items(txs, dates)

    counts: Dict[str, int] = {g: 0 for g in GROUP_ORDER}
    for it in items:
        counts[it.group] = counts.get(it.group, 0) + 1

    # Gom theo phiên. Tin chưa có phiên (ra sau phiên cuối) đi vào một nhóm
    # riêng đứng đầu — đó là tin *mới nhất*, không phải tin bị lỗi.
    by_session: Dict[Optional[str], List[NewsItem]] = {}
    for it in items:
        by_session.setdefault(it.session, []).append(it)

    days: List[SessionNews] = []
    n_hidden = 0
    for session in sorted((s for s in by_session if s), reverse=True):
        ordered = sorted(by_session[session],
                         key=lambda i: (GROUP_ORDER.index(i.group), i.published))
        shown = ordered[:max_per_session]
        n_hidden += len(ordered) - len(shown)
        node = SessionNews(session=session, items=shown,
                           sessions_after=len(dates) - 1 - index[session])
        # Nhóm ngành/thị trường không được đo — xem docstring module.
        if node.top_group == GROUP_SECTOR:
            node.status = ST_NOT_MEASURED
        elif measure:
            node.reaction = reaction_mod.measure(sym, session, as_of=as_of)
            node.status = classify_status(node.reaction, node.sessions_after)
        else:
            node.status = ST_NOT_MEASURED
        days.append(node)

    if None in by_session:
        pending = sorted(by_session[None], key=lambda i: i.published,
                         reverse=True)
        n_hidden += max(0, len(pending) - max_per_session)
        days.insert(0, SessionNews(session="", items=pending[:max_per_session],
                                   status=ST_NO_SESSION, sessions_after=-1))

    return NewsDigest(symbol=sym, session_from=lo, session_to=hi,
                      sessions=len(dates), days=days, n_items=len(items),
                      n_hidden=n_hidden, counts=counts)
