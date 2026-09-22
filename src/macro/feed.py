"""Tin **không gắn mã** — nguồn duy nhất cho phần vĩ mô của tầng này.

Cả kho tin hiện tại vào qua `/symbols/{mã}/posts`, nên một bài về xung đột
Trung Đông chỉ tồn tại nếu FireAnt tình cờ gắn nó cho một mã nào đó. `/posts`
với `groupID` không có ràng buộc ấy: 10 nhóm, trong đó **Hàng hóa**, **Thế
giới**, **Kinh tế**, **Thị trường** là bốn nhóm nói về lực nền chứ không về
doanh nghiệp.

Hai thứ lấy được ở đây mà tầng mã không có:

* **Tin vĩ mô thật.** Không phải một bài điểm tin gắn 15 mã rồi bị
  ``classify_post`` xếp vào ``GROUP_SECTOR`` và bỏ không đo (đúng, ở cấp mã),
  mà là tin vốn dĩ không thuộc về mã nào.
* **Giá hàng hoá thế giới.** ``taggedSymbols`` của nhóm Hàng hóa mang ticker
  toàn cầu kèm giá tại thời điểm đăng: ``BZ=F`` Brent, ``CL=F`` WTI, ``GC=F``
  vàng, ``SI=F`` bạc. ``/symbols/BZ=F/historical-quotes`` trả **rỗng** — đã
  thử — nên đây là đường duy nhất.

  Độ dày của chuỗi này **phụ thuộc số trang đã cào**, và đó là chỗ lượt đầu
  nhầm: nạp 12 trang cho ra 35 điểm ≈ 1 tháng, và cả tầng trên bị dán nhãn
  "chuỗi thưa, không hồi quy được". Nạp 180 trang thì Brent có **472 điểm phủ
  97% phiên sàn** trong 16,5 tháng — đủ dày để hồi quy. Nên nhãn *thưa* phải là
  thứ **đo được** (``QuoteSeries.coverage``), không phải một hằng số ai đó tin
  là đúng ở một thời điểm.

⚠️ Nội dung ở đây đến thẳng từ internet, qua ít bộ lọc hơn tin gắn mã (nhóm
*Thế giới* là tin dịch). Mọi chữ đưa vào prompt phải nằm trong
``<untrusted source="...">`` — xem ``src/macro/verdict.py``.
"""
import json
import re
import sqlite3
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from src.news.fireant import get
from src.news.posts import title_hash
from src.news.store import DB_PATH

#: Nhóm bài. Số là ``postGroupID`` của FireAnt, đã đối chiếu `/posts/groups`.
GROUP_MARKET = 1
GROUP_FINANCE = 2
GROUP_BUSINESS = 3
GROUP_ECONOMY = 4
GROUP_WORLD = 5
GROUP_PROPERTY = 6
GROUP_COMMODITY = 9

GROUP_VN = {
    GROUP_MARKET: "Thị trường", GROUP_FINANCE: "Tài chính",
    GROUP_BUSINESS: "Doanh nghiệp", GROUP_ECONOMY: "Kinh tế",
    GROUP_WORLD: "Thế giới", GROUP_PROPERTY: "Bất động sản",
    GROUP_COMMODITY: "Hàng hóa",
}

#: Nhóm nạp mặc định. Bỏ ``Doanh nghiệp`` (3) vì nó trùng phần lớn với tin đã
#: gắn mã trong kho cũ, và bỏ ``Tiền số``/``Frontalk``/``FInvest`` vì không nói
#: gì về ngành niêm yết.
DEFAULT_GROUPS = (GROUP_MARKET, GROUP_ECONOMY, GROUP_WORLD,
                  GROUP_COMMODITY, GROUP_PROPERTY, GROUP_FINANCE)

PAGE = 50

#: Ticker hàng hoá / chỉ số toàn cầu hay gặp trong ``taggedSymbols``.
COMMODITY_VN = {
    "BZ=F": "Dầu Brent", "CL=F": "Dầu WTI", "GC=F": "Vàng", "SI=F": "Bạc",
    "HG=F": "Đồng", "NG=F": "Khí tự nhiên", "ZC=F": "Ngô", "ZS=F": "Đậu tương",
    "KC=F": "Cà phê", "SB=F": "Đường", "DX-Y.NYB": "Chỉ số USD",
    "^DJI": "Dow Jones", "^GSPC": "S&P 500", "^IXIC": "Nasdaq",
    "^VIX": "VIX",
}

#: Ticker **thật sự có dữ liệu** sau lượt cào 180 trang (16/09/2026). Bảng
#: ``COMMODITY_VN`` ở trên là từ điển tên; bảng này là thực tế. Khai báo một
#: biến nền trỏ vào ticker không có ở đây là khai báo một biến chết — đúng lỗi
#: đã gặp với ``HG=F`` (đồng) và ``NG=F`` (khí), cả hai có **0 điểm**.
TICKERS_WITH_DATA = ("BZ=F", "CL=F", "GC=F", "SI=F", "^DJI", "^GSPC", "^IXIC")

#: Hợp đồng tương lai hàng hoá theo quy ước Yahoo: ``BZ=F``, ``CL=F``…
_FUTURES = re.compile(r"^[A-Z]{1,4}=F$")

#: Chỉ số toàn cầu được nhận thêm ngoài dạng ``=F``. Danh sách **đóng** — mở ra
#: cho mọi chuỗi có dấu chấm là đường để ``US.VFS`` (cổ phiếu VinFast niêm yết
#: Mỹ) lọt vào bảng hàng hoá, đã xảy ra ở lượt nạp đầu tiên.
_INDEX_TICKERS = {"DX-Y.NYB", "^DJI", "^GSPC", "^IXIC", "^VIX"}


def is_commodity_ticker(symbol: str) -> bool:
    """Ticker này là hàng hoá/chỉ số thế giới, hay là một cổ phiếu?

    ``taggedSymbols`` trộn cả hai: một bài nhóm Hàng hóa có thể gắn ``BZ=F``
    lẫn ``US.VFS``. Lọc bằng "có dấu = hoặc dấu ." là để lọt cái thứ hai — và
    một cổ phiếu nằm trong bảng giá hàng hoá thì mọi phép so ngành-với-hàng-hoá
    phía trên đều đọc nhầm nó là một biến nền.
    """
    sym = str(symbol or "").strip().upper()
    return bool(_FUTURES.match(sym)) or sym in _INDEX_TICKERS


#: Bài có ngày xa hơn mốc này ở **tương lai** thì bỏ. Đã gặp thật: một bài của
#: *Tạp chí Diễn đàn doanh nghiệp* mang ngày 16/10/2026 trong khi phiên cuối là
#: 16/09 — gõ nhầm tháng ở CMS của toà soạn. Một bản ghi như vậy hiện ra trong
#: **mọi** báo cáo hồi tưởng như tin "đã biết", tức là nhìn trước không giới
#: hạn. Cho 2 ngày đệm vì múi giờ và bài hẹn giờ đăng.
FUTURE_TOLERANCE_DAYS = 2

SCHEMA = """
CREATE TABLE IF NOT EXISTS macro_posts (
    post_id      INTEGER PRIMARY KEY,
    group_id     INTEGER NOT NULL,
    group_name   TEXT,
    title        TEXT    NOT NULL,
    description  TEXT,
    date         TEXT    NOT NULL,
    source       TEXT,
    source_url   TEXT,
    tagged       TEXT,
    sentiment    INTEGER,
    title_hash   TEXT    NOT NULL,
    first_seen   TEXT    NOT NULL,
    updated_at   TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_macro_posts_group_date ON macro_posts(group_id, date);
CREATE INDEX IF NOT EXISTS ix_macro_posts_date       ON macro_posts(date);
CREATE INDEX IF NOT EXISTS ix_macro_posts_hash       ON macro_posts(title_hash);

CREATE TABLE IF NOT EXISTS macro_quotes (
    ticker   TEXT    NOT NULL,
    date     TEXT    NOT NULL,
    price    REAL    NOT NULL,
    change   REAL,
    pct      REAL,
    post_id  INTEGER,
    PRIMARY KEY (ticker, date)
);
CREATE INDEX IF NOT EXISTS ix_macro_quotes_ticker ON macro_quotes(ticker, date);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


#: Chờ bao lâu khi kho đang bị một tiến trình khác ghi, trước khi báo lỗi.
#:
#: Mặc định của sqlite3 là **0** — đọc trúng lúc có người ghi là ném
#: ``OperationalError: database is locked`` ngay lập tức. Đã gặp thật: lượt cào
#: nền làm `build_dossier` không đọc được kho tin, và hồ sơ in ra *"chưa quét
#: được cờ đỏ"* — đúng cái nhãn dành cho "kho hỏng", cho một kho hoàn toàn khoẻ
#: mạnh chỉ đang bận. Người đọc không có cách nào phân biệt.
BUSY_TIMEOUT_MS = 15_000


@contextmanager
def connect(db_path: Optional[Path] = None):
    """Dùng chung file với ``src/news/store.py`` — hai bảng riêng, một kho."""
    path = Path(db_path) if db_path else DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=BUSY_TIMEOUT_MS / 1000)
    conn.row_factory = sqlite3.Row
    conn.execute(f"PRAGMA busy_timeout = {BUSY_TIMEOUT_MS}")
    try:
        conn.executescript(SCHEMA)
        _migrate(conn)
        yield conn
        conn.commit()
    finally:
        conn.close()


def _migrate(conn: sqlite3.Connection) -> None:
    """Thêm cột vào kho đã có. ``CREATE TABLE IF NOT EXISTS`` không làm việc đó.

    Không migrate thì mọi lượt đọc ``sentiment`` trên kho cũ ném
    ``OperationalError`` — và nó ném ở tận tầng gọi, xa chỗ gây ra.
    """
    have = {r[1] for r in conn.execute("PRAGMA table_info(macro_posts)")}
    if "sentiment" not in have:
        conn.execute("ALTER TABLE macro_posts ADD COLUMN sentiment INTEGER")


def _is_future(date: str, now: Optional[datetime] = None) -> bool:
    """Bài mang ngày ở tương lai — bỏ, và bỏ **im lặng** là đúng ở đây.

    Nguồn tin gõ nhầm tháng là chuyện xảy ra thật, không phải giả định. Một bản
    ghi như vậy hiện ra trong mọi báo cáo hồi tưởng như tin đã biết, tức là
    nhìn trước không giới hạn — và không có cách nào phát hiện từ phía đọc.
    """
    try:
        when = datetime.fromisoformat(str(date)).replace(tzinfo=None)
    except ValueError:
        return False
    cutoff = (now or datetime.now()) + timedelta(days=FUTURE_TOLERANCE_DAYS)
    return when > cutoff


# ---------------------------------------------------------------------------
@dataclass
class MacroPost:
    post_id: int
    group_id: int
    group_name: str
    title: str
    description: str
    date: str
    source: str = ""
    source_url: str = ""
    tagged: List[Dict[str, Any]] = field(default_factory=list)
    #: Sắc thái do **FireAnt gán lúc đăng**, không phải do model nào chấm lại.
    #:
    #: Giá trị đó mới là chỗ đáng giá: nó tồn tại từ thời điểm bài ra, nên
    #: backfill được 16 tháng mà **không dính nhìn trước** — khác hẳn điểm của
    #: một model ngôn ngữ chấm hôm nay cho tin tháng 3, thứ đã biết thị trường
    #: đi đâu sau đó. Nhờ vậy nó kiểm được **ngay**, thay vì phải đợi sáu tháng
    #: tích luỹ như điểm LLM.
    #:
    #: ``None`` = FireAnt không gán, khác hẳn ``0`` = gán là trung tính.
    sentiment: Optional[int] = None

    @property
    def session(self) -> str:
        return self.date[:10]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _parse(row: Dict[str, Any], group_id: int,
           now: Optional[datetime] = None) -> Optional[MacroPost]:
    pid = row.get("postID")
    title = str(row.get("title") or "").strip()
    date = str(row.get("date") or "")
    if pid is None or not title or not date:
        return None
    if _is_future(date, now):
        return None
    group = row.get("postGroup") or {}
    tagged = []
    for t in row.get("taggedSymbols") or []:
        sym = str(t.get("symbol") or "").strip()
        if not sym:
            continue
        tagged.append({"symbol": sym, "price": t.get("price"),
                       "change": t.get("change"),
                       "pct": t.get("percentChange")})
    raw_sent = row.get("sentiment")
    try:
        sentiment = None if raw_sent is None else int(raw_sent)
    except (TypeError, ValueError):
        sentiment = None
    return MacroPost(
        sentiment=sentiment,
        post_id=int(pid), group_id=int(group.get("postGroupID") or group_id),
        group_name=str(group.get("name") or GROUP_VN.get(group_id, "")),
        title=title, description=str(row.get("description") or "")[:2000],
        date=date,
        source=str((row.get("postSource") or {}).get("name") or ""),
        source_url=str(row.get("postSourceUrl") or row.get("contentURL") or ""),
        tagged=tagged)


def fetch(group_id: int, pages: int = 4, limit: int = PAGE,
          since: Optional[str] = None) -> List[MacroPost]:
    """Bài của một nhóm, mới → cũ.

    ``since`` (ISO ``YYYY-MM-DD``) dừng sớm khi đã lùi đủ xa — nhịp hàng ngày
    chỉ cần vài chục bài mới, không cần cào lại cả kho mỗi lượt.
    """
    out: List[MacroPost] = []
    now = datetime.now()
    for page in range(pages):
        rows = get("/posts", {"groupID": group_id, "type": 1,
                              "offset": page * limit, "limit": limit}) or []
        if not rows:
            break
        stop = False
        for row in rows:
            post = _parse(row, group_id, now)
            if post is None:
                continue
            if since and post.session < since:
                stop = True
                continue
            out.append(post)
        if stop:
            break
    return out


def upsert(conn: sqlite3.Connection, posts: Iterable[MacroPost]) -> int:
    """Ghi bài; ``first_seen`` giữ nguyên ở lần ghi sau."""
    now = _now()
    n = 0
    for p in posts:
        conn.execute(
            """INSERT INTO macro_posts (post_id, group_id, group_name, title,
                    description, date, source, source_url, tagged, sentiment,
                    title_hash, first_seen, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(post_id) DO UPDATE SET
                    title=excluded.title, description=excluded.description,
                    source=excluded.source, source_url=excluded.source_url,
                    tagged=excluded.tagged, sentiment=excluded.sentiment,
                    updated_at=excluded.updated_at""",
            (p.post_id, p.group_id, p.group_name, p.title, p.description,
             p.date, p.source, p.source_url,
             json.dumps(p.tagged, ensure_ascii=False), p.sentiment,
             title_hash(p.title), now, now))
        n += 1
    return n


def upsert_quotes(conn: sqlite3.Connection, posts: Iterable[MacroPost]) -> int:
    """Rút giá hàng hoá từ ``taggedSymbols`` thành một chuỗi thưa.

    Một ngày có thể có nhiều bài cùng nhắc ``BZ=F`` với giá hơi khác nhau (bài
    đăng lúc 9h và 21h). Giữ **bản cuối trong ngày** — nó gần giá đóng cửa thế
    giới nhất. ``INSERT OR REPLACE`` theo khoá ``(ticker, date)`` làm đúng điều
    đó khi bài được duyệt theo thứ tự thời gian tăng dần.
    """
    n = 0
    for p in sorted(posts, key=lambda x: x.date):
        for t in p.tagged:
            sym, price = t.get("symbol"), t.get("price")
            if not sym or price is None or not is_commodity_ticker(sym):
                continue                  # mã cổ phiếu — không phải hàng hoá
            try:
                price = float(price)
            except (TypeError, ValueError):
                continue
            conn.execute(
                """INSERT OR REPLACE INTO macro_quotes
                   (ticker, date, price, change, pct, post_id)
                   VALUES (?,?,?,?,?,?)""",
                (sym, p.session, price, t.get("change"), t.get("pct"),
                 p.post_id))
            n += 1
    return n


def load_posts(conn: sqlite3.Connection, groups: Optional[Sequence[int]] = None,
               since: Optional[str] = None, until: Optional[str] = None,
               keywords: Optional[Sequence[str]] = None,
               limit: int = 200) -> List[MacroPost]:
    """Bài trong khoảng phiên, lọc theo nhóm và từ khoá.

    Lọc từ khoá chạy trên **tiêu đề + mô tả**, không phân biệt hoa thường. Đây
    là bộ lọc thô có chủ ý: việc quyết định bài nào *thật sự* nói về ngành nào
    là việc của model đọc bằng chứng, không phải của một câu SQL.
    """
    sql = ["SELECT * FROM macro_posts WHERE 1=1"]
    args: List[Any] = []
    if groups:
        sql.append(f"AND group_id IN ({','.join('?' * len(groups))})")
        args.extend(groups)
    if since:
        sql.append("AND date >= ?")
        args.append(since)
    if until:
        sql.append("AND date <= ?")
        args.append(until + "T23:59:59")
    if keywords:
        terms = []
        for kw in keywords:
            terms.append("(LOWER(title) LIKE ? OR LOWER(description) LIKE ?)")
            args.extend([f"%{kw.lower()}%"] * 2)
        sql.append(f"AND ({' OR '.join(terms)})")
    sql.append("ORDER BY date DESC LIMIT ?")
    args.append(limit)

    out = []
    for row in conn.execute(" ".join(sql), args):
        out.append(MacroPost(
            post_id=row["post_id"], group_id=row["group_id"],
            group_name=row["group_name"] or "", title=row["title"],
            description=row["description"] or "", date=row["date"],
            source=row["source"] or "", source_url=row["source_url"] or "",
            tagged=json.loads(row["tagged"] or "[]"),
            sentiment=row["sentiment"]))
    return out


#: Dưới độ phủ này thì chuỗi coi là thưa và không dùng cho phép đo cần chuỗi
#: liên tục (hồi quy, beta). 80% phiên sàn là mức còn đọc được xu hướng mà lỗ
#: hổng chưa làm lệch hệ thống.
DENSE_COVERAGE = 0.80


@dataclass
class QuoteSeries:
    """Chuỗi giá của một ticker hàng hoá, **lấy mẫu theo ngày có tin**.

    ``sparse`` từng là hằng số ``True`` với lý do "để chỗ dùng không quên" — và
    nó thành một lời nói dối ngay khi số trang cào tăng lên: Brent đi từ 35
    điểm (1 tháng) lên 472 điểm phủ **97% phiên sàn**, nhưng thuộc tính vẫn
    khai là thưa, và cả tài liệu lẫn gói bằng chứng vẫn dán nhãn "không đủ để
    hồi quy beta". Một cảnh báo sai chỗ làm người đọc bỏ qua cả những cảnh báo
    đúng, nên nó phải **đo**, không **khẳng định**.
    """
    ticker: str
    label: str
    points: List[Tuple[str, float]] = field(default_factory=list)
    #: Số phiên sàn trong cùng khoảng, để tính độ phủ. Không truyền thì
    #: ``coverage`` trả ``None`` — *chưa đo được*, không phải *dày*.
    trading_days: Optional[int] = None
    #: Số phiên sàn **thật sự có giá** — tử số của độ phủ.
    days_hit: Optional[int] = None

    @property
    def coverage(self) -> Optional[float]:
        """Bao nhiêu phần **phiên sàn** có giá.

        Tử số là số phiên sàn *giao* với chuỗi, không phải tổng số điểm. Lấy
        ``len(points) / trading_days`` rồi cắt ở 1.0 là sai kiểu: chuỗi này có
        cả điểm cuối tuần (tin giá dầu ra cả thứ Bảy), nên Brent cho
        472/342 = 138% → cắt thành "100%", che mất việc chỉ 331 phiên sàn thật
        sự có giá. Một chuỗi toàn điểm cuối tuần sẽ báo phủ 100% mà không khớp
        một phiên nào.
        """
        if not self.trading_days or self.days_hit is None:
            return None
        return self.days_hit / self.trading_days

    @property
    def sparse(self) -> Optional[bool]:
        """``None`` = chưa đo được độ phủ. Không mặc định thành "dày"."""
        cov = self.coverage
        return None if cov is None else cov < DENSE_COVERAGE

    @property
    def density_note(self) -> str:
        cov = self.coverage
        if cov is None:
            return (f"{len(self.points)} điểm, **chưa đo được độ phủ** so với "
                    f"lịch phiên")
        if cov < DENSE_COVERAGE:
            return (f"{len(self.points)} điểm, phủ {cov:.0%} phiên sàn — "
                    f"**chuỗi thưa**, đủ đọc xu hướng, không đủ hồi quy")
        return f"{len(self.points)} điểm, phủ {cov:.0%} phiên sàn"

    def change_pct(self, sessions: int) -> Optional[float]:
        """% thay đổi qua ``sessions`` **điểm dữ liệu**, không phải phiên sàn.

        Vẫn là điểm dữ liệu kể cả khi chuỗi đã dày: 20 điểm có thể trải trên 24
        ngày lịch. Khác biệt nhỏ đi khi độ phủ lên cao, nhưng không biến mất.
        """
        if len(self.points) <= sessions:
            return None
        old = self.points[-1 - sessions][1]
        if old == 0:
            return None
        return (self.points[-1][1] / old - 1) * 100

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["coverage"] = self.coverage
        d["sparse"] = self.sparse
        return d


def load_quotes(conn: sqlite3.Connection, ticker: str,
                since: Optional[str] = None,
                until: Optional[str] = None) -> QuoteSeries:
    sql = ["SELECT date, price FROM macro_quotes WHERE ticker = ?"]
    args: List[Any] = [ticker]
    if since:
        sql.append("AND date >= ?")
        args.append(since)
    if until:
        sql.append("AND date <= ?")
        args.append(until)
    sql.append("ORDER BY date")
    rows = conn.execute(" ".join(sql), args).fetchall()
    points = [(r["date"], float(r["price"])) for r in rows]
    total, hit = _session_overlap(points)
    return QuoteSeries(ticker=ticker,
                       label=COMMODITY_VN.get(ticker, ticker),
                       points=points, trading_days=total, days_hit=hit)


def _session_overlap(points: Sequence[Tuple[str, float]]
                     ) -> Tuple[Optional[int], Optional[int]]:
    """``(số phiên sàn trong khoảng, số phiên có giá)``.

    Dùng lịch phiên **thật** của VNINDEX chứ không đếm ngày lịch trừ cuối tuần:
    nghỉ Tết là chín phiên, và một mẫu số sai làm độ phủ trông cao hơn thực tế.
    """
    if len(points) < 2:
        return None, None
    from datetime import datetime as _dt
    from src.ta.loader import load_prices
    try:
        lo = _dt.fromisoformat(points[0][0])
        hi = _dt.fromisoformat(points[-1][0])
        sessions = {r.date.strftime("%Y-%m-%d")
                    for r in load_prices("VNINDEX", lo, hi)}
    except Exception:                                      # noqa: BLE001
        return None, None
    if not sessions:
        return None, None
    return len(sessions), len(sessions & {d for d, _ in points})


def update(groups: Sequence[int] = DEFAULT_GROUPS, pages: int = 4,
           since: Optional[str] = None,
           db_path: Optional[Path] = None) -> List[Tuple[int, int, int]]:
    """Nạp tin nhóm + rút giá hàng hoá. Trả ``(nhóm, số bài, số điểm giá)``."""
    out = []
    for gid in groups:
        # Một kết nối **cho mỗi nhóm**, không phải một cho cả lượt.
        #
        # Gộp cả lượt vào một transaction thì kho bị khoá suốt thời gian cào —
        # 6 nhóm × 180 trang × 1,2 giây là **hơn hai mươi phút**, và trong cả
        # khoảng đó mọi tiến trình khác đọc kho đều hỏng. Đã xảy ra: lượt cào
        # nền làm một test của `dossier` đỏ vì `build_dossier` không đọc nổi
        # kho tin. Nhịp tuần chạy 07:00 sáng Chủ nhật hoàn toàn có thể trùng
        # lúc người dùng đang mở báo cáo.
        #
        # Chia nhỏ còn được thêm một thứ: cào tới nhóm thứ tư mới hỏng thì ba
        # nhóm đầu đã nằm trên đĩa, không mất trắng.
        try:
            posts = fetch(gid, pages=pages, since=since)
        except Exception:                                  # noqa: BLE001
            out.append((gid, 0, 0))
            continue
        with connect(db_path) as conn:
            n = upsert(conn, posts)
            q = upsert_quotes(conn, posts)
        out.append((gid, n, q))
    return out


def _main() -> None:
    import argparse
    ap = argparse.ArgumentParser(description="Nạp tin nhóm (không gắn mã)")
    ap.add_argument("--pages", type=int, default=4)
    ap.add_argument("--since", default="",
                    help="lùi tới ngày này thì dừng (YYYY-MM-DD)")
    ap.add_argument("--groups", default="")
    args = ap.parse_args()

    groups = ([int(g) for g in args.groups.split(",") if g.strip()]
              or list(DEFAULT_GROUPS))
    rows = update(groups, pages=args.pages, since=args.since or None)

    print("| Nhóm | Bài | Điểm giá hàng hoá |")
    print("|---|---:|---:|")
    for gid, n, q in rows:
        print(f"| {GROUP_VN.get(gid, gid)} (`{gid}`) | {n} | {q} |")
    with connect() as conn:
        tickers = conn.execute(
            "SELECT ticker, COUNT(*) n, MIN(date) a, MAX(date) b "
            "FROM macro_quotes GROUP BY ticker ORDER BY n DESC").fetchall()
    if tickers:
        print("\n| Hàng hoá | Điểm | Từ | Đến | Độ dày |")
        print("|---|---:|---|---|---|")
        with connect() as conn:
            for t in tickers:
                q = load_quotes(conn, t["ticker"])
                print(f"| {q.label} (`{t['ticker']}`) | {t['n']} | {t['a']} | "
                      f"{t['b']} | {q.density_note} |")
        print("\nĐộ dày đo theo lịch phiên VNINDEX, không phải ngày lịch. "
              "Chuỗi dưới 80% phiên sàn bị đánh dấu **thưa** ở mọi chỗ dùng.")


if __name__ == "__main__":
    _main()
