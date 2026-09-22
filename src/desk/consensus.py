"""Các CTCK khác đang nói gì — và họ nói có đúng không.

`/reports/search` là kho báo cáo phân tích của **chính các công ty chứng khoán**:
152 nguồn, 9 danh mục, riêng danh mục *Phân tích công ty* năm 2026 có 5.561 bản.
Repo chưa từng gọi tới. Hai nửa, và nửa sau mới là lý do làm nửa đầu:

**(a) Theo dõi độ phủ.** Ai viết về mã nào, bao lâu một lần. Ba số đo dùng được
ngay: số báo cáo 12 tháng (mã không ai viết là mã không có người mua tổ chức),
**cụm phát hành** (≥3 báo cáo trong 10 phiên tự nó là một sự kiện), và từ khuyến
nghị rút từ tiêu đề + tóm tắt.

**(b) Bảng điểm của các CTCK.** Với mỗi báo cáo, chạy event study quanh ngày
phát hành bằng chính ``news/reaction.py``. Đây là thứ không ai ở thị trường này
công bố, mà dữ liệu thì có sẵn hàng nghìn quan sát.

Bốn chỗ phải nói đúng mức, không được nói quá:

1. **Ngày báo cáo ≠ ngày thông tin ra thị trường** (§7.4 của plan). Khách hàng
   tổ chức đọc trước khi bản đó lên FireAnt, nên cửa sổ đo đã bị dịch, và sai
   lệch đi **một chiều**: nó làm CTCK trông như *viết sau* khi giá đã chạy. Vì
   thế bảng điểm luôn in kèm **CAR trước sự kiện** — phần tăng đã xảy ra trước
   ngày phát hành chính là dấu vết của độ trễ công bố.
2. **Chỉ ~40% bản ghi có từ khuyến nghị**, và **0/40 tóm tắt đọc thử có giá mục
   tiêu** (nó nằm trong thân PDF, mà API không có đường tải file). Nên cột
   khuyến nghị trống nghĩa là *không nói*, không phải *trung lập*; và bàn này
   **không** dựng bảng giá mục tiêu đồng thuận.
3. **Bản quyền.** Lưu và dùng: id, nguồn, ngày, mã, tiêu đề, tóm tắt (để phân
   tích). Không tái xuất bản toàn văn; phần in ra chỉ là tiêu đề + trích đoạn
   ngắn có dẫn nguồn.
4. **Văn bản này là chữ của người khác viết để thuyết phục.** Khi đưa vào prompt
   phải nằm trong ``<untrusted source="...">`` như mọi nội dung internet khác.
"""
import html
import json
import re
import sqlite3
import unicodedata
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from statistics import median
from typing import Any, Dict, List, Optional, Sequence, Tuple

from src.news.fireant import get
from src.ta.loader import PROJECT_ROOT

DB_PATH = PROJECT_ROOT / "desk" / "consensus.db"
BUSY_TIMEOUT_MS = 15_000

#: Danh mục báo cáo (từ ``/reports/categories``, gọi thật 19/09/2026).
CATEGORIES = {
    1: "Phân tích công ty", 2: "Phân tích ngành", 3: "Kinh tế vĩ mô",
    4: "Tổng quan thị trường", 5: "Thị trường thế giới",
    14: "StockBiz & VFP", 15: "Báo cáo FireAnt", 16: "Thị trường trái phiếu",
    17: "Hàng hoá phái sinh",
}
COMPANY_CATEGORY = 1

PAGE_SIZE = 100
MAX_PAGES = 40

#: Cụm phát hành: ngần này báo cáo trong ngần này ngày.
BURST_MIN = 3
BURST_DAYS = 14

#: Dưới ngần này quan sát thì một nguồn **không được phát biểu số** — cùng
#: ngưỡng mà ``news/stats.py`` đã dùng.
MIN_EVENTS = 20

#: Từ khuyến nghị **không nhập nhằng**: chúng gần như không xuất hiện trong văn
#: xuôi thường. Xếp theo độ mạnh để một bản mang nhiều từ lấy được từ dứt khoát
#: nhất.
RATING_WORDS: Tuple[Tuple[str, str], ...] = (
    ("kem kha quan", "KÉM KHẢ QUAN"),
    ("giam ty trong", "GIẢM TỶ TRỌNG"),
    ("kha quan", "KHẢ QUAN"),
    ("tang ty trong", "TĂNG TỶ TRỌNG"),
    ("trung lap", "TRUNG LẬP"),
    ("nam giu", "NẮM GIỮ"),
)

#: Từ **một âm tiết hoặc quá thường gặp** — chỉ tính là khuyến nghị khi có ngữ
#: cảnh. Đây không phải sự cẩn thận thừa: đo thật trên kho, *"FPT - MUA: Chủ
#: động thích nghi"* bị đọc thành `BÁN` vì trong tóm tắt có cụm "doanh thu **bán
#: hàng**". Cùng họ với luật cờ đỏ — bỏ dấu xong thì `"an tu"` nằm gọn trong
#: *"cổ phần từ"*, và đệm khoảng trắng hai đầu vẫn chưa đủ khi chính từ đó là
#: một từ thường dùng.
AMBIGUOUS_WORDS: Tuple[Tuple[str, str], ...] = (
    ("mua", "MUA"),
    ("ban", "BÁN"),
    ("tich cuc", "TÍCH CỰC"),
    ("tieu cuc", "TIÊU CỰC"),
    ("theo doi", "THEO DÕI"),
)

#: Cụm báo hiệu câu đang nói về khuyến nghị chứ không phải kể chuyện kinh doanh.
#: Giữ **hẹp**: "duy trì" và "đánh giá" đã phải bỏ vì chúng là từ thường —
#: *"nhu cầu trang sức duy trì tích cực"* không phải một khuyến nghị TÍCH CỰC.
RATING_CUES: Tuple[str, ...] = (
    "khuyen nghi", "gia muc tieu", "dinh gia muc tieu", "quan diem dau tu",
)

#: Phủ định ngay trước từ khuyến nghị làm đảo nghĩa: *"Tình hình kinh doanh
#: **không** khả quan"* không phải khuyến nghị KHẢ QUAN. Gặp phủ định thì **bỏ
#: hẳn**, không đoán chiều ngược — một nhãn sai tệ hơn một cột trống, vì cột
#: trống đã có nghĩa rõ ràng ("không nói").
NEGATORS: Tuple[str, ...] = ("khong", "chua", "chang", "kem phan", "thieu")
NEGATION_WINDOW = 24

_TAG_RE = re.compile(r"<[^>]+>")


def _fold(text: str) -> str:
    norm = unicodedata.normalize("NFD", text or "")
    plain = "".join(c for c in norm if unicodedata.category(c) != "Mn")
    plain = plain.replace("đ", "d").replace("Đ", "D")
    return " " + " ".join(plain.lower().split()) + " "


def strip_html(raw: str) -> str:
    return " ".join(html.unescape(_TAG_RE.sub(" ", raw or "")).split())


# ---------------------------------------------------------------------------
@dataclass
class Report:
    report_id: int
    date: str                       # ISO, ngày phát hành trên FireAnt
    symbol: Optional[str] = None
    source_name: str = ""
    source_id: Optional[int] = None
    category_id: Optional[int] = None
    title: str = ""
    pages: Optional[int] = None
    abstract: str = ""

    @property
    def category(self) -> str:
        return CATEGORIES.get(self.category_id or 0, "—")

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Rating:
    """Từ khuyến nghị **kèm nguyên văn câu chứa nó** — bác lại được."""
    word: str
    quote: str
    where: str          # "tiêu đề" | "tóm tắt"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


_UPPER_TOKEN = re.compile(r"(?<![\wÀ-ỹ])(MUA|BÁN|NẮM GIỮ|THEO DÕI|TÍCH CỰC|TIÊU CỰC)"
                          r"(?![\wÀ-ỹ])")


def extract_rating(report: Report) -> Optional[Rating]:
    """Từ khuyến nghị đầu tiên tìm được, ưu tiên tiêu đề.

    Ba đường, xếp theo độ chắc chắn:

    1. Từ **không nhập nhằng** (``khả quan``, ``trung lập``, ``nắm giữ``…) ở
       bất kỳ đâu.
    2. Từ **viết hoa** trong tiêu đề — CTCK viết *"FPT - MUA: …"*, và chữ hoa
       giữa một tiêu đề thường là chính cái nhãn khuyến nghị.
    3. Từ nhập nhằng trong câu **có cụm báo hiệu** ("khuyến nghị", "giá mục
       tiêu"…) — xem ``RATING_CUES``, và nó cố ý hẹp.

    Cả ba đường đều đi qua ``_negated``: *"Tình hình kinh doanh không khả quan"*
    không phải khuyến nghị KHẢ QUAN.

    Trả ``None`` khi không có — và ``None`` nghĩa là **không nói**, không phải
    *trung lập*. Đo thật trên 40 tóm tắt: chỉ 16 bản mang một từ khuyến nghị.
    """
    for where, text in (("tiêu đề", report.title), ("tóm tắt", report.abstract)):
        folded = _fold(text)
        for needle, label in RATING_WORDS:
            if f" {needle} " in folded and not _negated(folded, needle):
                return Rating(word=label, quote=_sentence_with(text, needle),
                              where=where)

    m = _UPPER_TOKEN.search(report.title or "")
    if m:
        return Rating(word=m.group(1).upper(), quote=(report.title or "").strip(),
                      where="tiêu đề")

    for where, text in (("tiêu đề", report.title), ("tóm tắt", report.abstract)):
        for part in re.split(r"(?<=[.!?;])\s+|\n+", text or ""):
            folded = _fold(part)
            if not any(cue in folded for cue in RATING_CUES):
                continue
            for needle, label in AMBIGUOUS_WORDS:
                if f" {needle} " in folded and not _negated(folded, needle):
                    return Rating(word=label, quote=part.strip()[:220],
                                  where=where)
    return None


def _negated(folded: str, needle: str) -> bool:
    """Có phủ định ngay trước từ khuyến nghị không."""
    idx = folded.find(f" {needle} ")
    if idx < 0:
        return False
    before = folded[max(0, idx - NEGATION_WINDOW):idx + 1]
    return any(f" {neg} " in before for neg in NEGATORS)


def _sentence_with(text: str, needle: str) -> str:
    for part in re.split(r"(?<=[.!?;])\s+|\n+", text or ""):
        if needle in _fold(part):
            return part.strip()[:220]
    return (text or "").strip()[:220]


# ---------------------------------------------------------------------------
def _connect(path: Optional[Path] = None) -> sqlite3.Connection:
    target = path or DB_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(target))
    conn.execute(f"PRAGMA busy_timeout = {BUSY_TIMEOUT_MS}")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS reports (
            report_id INTEGER PRIMARY KEY,
            date TEXT NOT NULL,
            symbol TEXT,
            source_id INTEGER,
            source_name TEXT,
            category_id INTEGER,
            title TEXT,
            pages INTEGER,
            abstract TEXT,
            fetched_at TEXT
        )""")
    conn.execute("CREATE INDEX IF NOT EXISTS ix_reports_symbol "
                 "ON reports (symbol, date)")
    conn.commit()
    return conn


def parse_report(row: Dict[str, Any]) -> Optional[Report]:
    try:
        rid = int(row.get("reportID"))
    except (TypeError, ValueError):
        return None
    date = str(row.get("date") or "")[:10]
    if not date:
        return None
    sym = (row.get("symbol") or "").strip().upper() or None
    return Report(report_id=rid, date=date, symbol=sym,
                  source_name=str(row.get("sourceName") or ""),
                  source_id=row.get("sourceID"),
                  category_id=row.get("categoryID"),
                  title=str(row.get("title") or "").strip(),
                  pages=row.get("pages"))


def search(start: str, end: str, category_id: Optional[int] = COMPANY_CATEGORY,
           symbol: Optional[str] = None, max_pages: int = MAX_PAGES
           ) -> Tuple[List[Report], bool]:
    """Danh sách báo cáo trong khoảng. Trả ``(rows, hit_page_cap)``.

    Cờ thứ hai theo đúng luật đã có ở tầng tin: một lượt **bị cắt cụt vì hết
    ngân sách trang** trông y hệt một lượt đã lấy hết, nên lý do dừng phải đi
    cùng dữ liệu.
    """
    out: List[Report] = []
    seen = set()
    offset = 0
    hit_cap = False
    for page in range(max_pages):
        params = {"startDate": start, "endDate": end,
                  "offset": offset, "limit": PAGE_SIZE}
        if category_id:
            params["categoryID"] = category_id
        if symbol:
            params["symbol"] = symbol.strip().upper()
        payload = get("/reports/search", params) or {}
        rows = payload.get("reports") or []
        for row in rows:
            rep = parse_report(row)
            if rep and rep.report_id not in seen:
                seen.add(rep.report_id)
                out.append(rep)
        if len(rows) < PAGE_SIZE:
            break
        offset += PAGE_SIZE
        if page == max_pages - 1:
            hit_cap = True
    return out, hit_cap


def fetch_abstract(report_id: int) -> str:
    """Tóm tắt do chính chuyên viên viết. Một request cho mỗi báo cáo."""
    payload = get(f"/reports/{int(report_id)}") or {}
    return strip_html(payload.get("description") or "")


def save(reports: Sequence[Report], path: Optional[Path] = None) -> int:
    """Upsert theo ``report_id``. Giữ tóm tắt cũ nếu lượt này không có."""
    if not reports:
        return 0
    now = datetime.now().isoformat(timespec="seconds")
    conn = _connect(path)
    try:
        for rep in reports:
            conn.execute(
                "INSERT INTO reports (report_id, date, symbol, source_id, "
                " source_name, category_id, title, pages, abstract, fetched_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?) "
                "ON CONFLICT(report_id) DO UPDATE SET "
                " date=excluded.date, symbol=excluded.symbol, "
                " source_name=excluded.source_name, title=excluded.title, "
                " abstract=CASE WHEN excluded.abstract != '' "
                "          THEN excluded.abstract ELSE reports.abstract END",
                (rep.report_id, rep.date, rep.symbol, rep.source_id,
                 rep.source_name, rep.category_id, rep.title, rep.pages,
                 rep.abstract, now))
        conn.commit()
    finally:
        conn.close()
    return len(reports)


def load(symbol: Optional[str] = None, since: Optional[str] = None,
         until: Optional[str] = None, category_id: Optional[int] = None,
         path: Optional[Path] = None) -> List[Report]:
    where, args = [], []
    if symbol:
        where.append("symbol = ?")
        args.append(symbol.strip().upper())
    if since:
        where.append("date >= ?")
        args.append(since)
    if until:
        where.append("date <= ?")
        args.append(until)
    if category_id:
        where.append("category_id = ?")
        args.append(category_id)
    sql = ("SELECT report_id, date, symbol, source_id, source_name, category_id,"
           " title, pages, abstract FROM reports")
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY date"
    try:
        conn = _connect(path)
        rows = conn.execute(sql, args).fetchall()
        conn.close()
    except sqlite3.Error:
        return []
    return [Report(report_id=r[0], date=r[1], symbol=r[2], source_id=r[3],
                   source_name=r[4] or "", category_id=r[5], title=r[6] or "",
                   pages=r[7], abstract=r[8] or "") for r in rows]


def update(days: int = 90, category_id: Optional[int] = COMPANY_CATEGORY,
           with_abstracts: int = 40, path: Optional[Path] = None
           ) -> Dict[str, Any]:
    """Nạp báo cáo mới + tóm tắt cho ``with_abstracts`` bản mới nhất chưa có.

    Tóm tắt đắt hơn một bậc (một request mỗi bản) nên có ngân sách riêng, đúng
    cách ``news/ingest.py`` tách phần bài viết khỏi phần giao dịch.
    """
    end = datetime.now()
    start = end - timedelta(days=days)
    rows, hit_cap = search(start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d"),
                           category_id=category_id)
    known = {r.report_id for r in load(path=path)}
    new = [r for r in rows if r.report_id not in known]
    save(rows, path)

    missing = [r for r in load(path=path)
               if not r.abstract and r.date >= start.strftime("%Y-%m-%d")]
    missing.sort(key=lambda r: r.date, reverse=True)
    fetched = 0
    for rep in missing[:max(0, with_abstracts)]:
        try:
            rep.abstract = fetch_abstract(rep.report_id)
        except Exception:                                      # noqa: BLE001
            continue
        if rep.abstract:
            save([rep], path)
            fetched += 1
    return {"seen": len(rows), "new": len(new), "abstracts": fetched,
            "abstracts_missing": max(0, len(missing) - with_abstracts),
            "hit_page_cap": hit_cap,
            "window": f"{start:%Y-%m-%d} → {end:%Y-%m-%d}"}


# ---------------------------------------------------------------------------
@dataclass
class Burst:
    start: str
    end: str
    n: int
    sources: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def find_bursts(reports: Sequence[Report], min_n: int = BURST_MIN,
                window_days: int = BURST_DAYS) -> List[Burst]:
    """Cụm ≥ ``min_n`` báo cáo trong ``window_days`` ngày — tự nó là một sự kiện."""
    rows = sorted(reports, key=lambda r: r.date)
    out: List[Burst] = []
    for i, first in enumerate(rows):
        limit = (datetime.strptime(first.date, "%Y-%m-%d")
                 + timedelta(days=window_days)).strftime("%Y-%m-%d")
        window = [r for r in rows[i:] if r.date <= limit]
        if len(window) < min_n:
            continue
        if out and window[-1].date <= out[-1].end:
            continue
        out.append(Burst(start=first.date, end=window[-1].date, n=len(window),
                         sources=sorted({r.source_name for r in window if r.source_name})))
    return out


@dataclass
class Coverage:
    symbol: str
    as_of: str
    months: int
    n: int = 0
    sources: List[str] = field(default_factory=list)
    last_date: Optional[str] = None
    latest: List[Report] = field(default_factory=list)
    ratings: List[Rating] = field(default_factory=list)
    bursts: List[Burst] = field(default_factory=list)
    note: str = ""

    @property
    def covered(self) -> bool:
        return self.n > 0

    def to_dict(self) -> Dict[str, Any]:
        return {"symbol": self.symbol, "as_of": self.as_of, "months": self.months,
                "n": self.n, "sources": self.sources, "last_date": self.last_date,
                "latest": [r.to_dict() for r in self.latest],
                "ratings": [r.to_dict() for r in self.ratings],
                "bursts": [b.to_dict() for b in self.bursts], "note": self.note}


def coverage(symbol: str, as_of: Optional[datetime] = None, months: int = 12,
             limit: int = 6, path: Optional[Path] = None) -> Coverage:
    end = as_of or datetime.now()
    since = (end - timedelta(days=int(30.44 * months))).strftime("%Y-%m-%d")
    rows = load(symbol=symbol, since=since, until=end.strftime("%Y-%m-%d"),
                path=path)
    cov = Coverage(symbol=symbol.strip().upper(),
                   as_of=end.strftime("%Y-%m-%d"), months=months, n=len(rows))
    if not rows:
        cov.note = ("chưa có báo cáo nào trong kho cho mã này — *chưa nạp* hay "
                    "*không ai viết* là hai chuyện, chạy `desk_consensus` với "
                    "`refresh=True` để phân biệt")
        return cov
    cov.sources = sorted({r.source_name for r in rows if r.source_name})
    cov.last_date = rows[-1].date
    cov.latest = list(reversed(rows))[:limit]
    cov.ratings = [r for r in (extract_rating(rep) for rep in cov.latest) if r]
    cov.bursts = find_bursts(rows)
    return cov


# ---------------------------------------------------------------------------
@dataclass
class SourceScore:
    """Base rate của một nguồn. Không có phán quyết, chỉ số đo + cỡ mẫu."""
    source: str
    n: int = 0
    car_pre: Optional[float] = None         # CAR[-5..-1] — dấu vết độ trễ công bố
    car_immediate: Optional[float] = None   # AR[t0] + AR[t+1]
    car_post: Optional[float] = None        # CAR[+1..+10]
    hit_rate: Optional[float] = None        # % bản có CAR sau > 0
    enough: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def source_scorecard(reports: Sequence[Report], as_of: Optional[datetime] = None,
                     min_events: int = MIN_EVENTS) -> List[SourceScore]:
    """Sau báo cáo của từng nguồn thì giá thật sự đi đâu.

    Dùng ``news.reaction.measure`` — **có truyền ``as_of``**, theo đúng luật đã
    ghi: mặc định nó nạp tới ``t0 + 40 ngày`` bất kể mốc hồi tưởng.
    """
    from src.news import reaction as reaction_mod

    by_source: Dict[str, List[Tuple[float, float, float]]] = {}
    for rep in reports:
        if not rep.symbol or not rep.source_name:
            continue
        try:
            r = reaction_mod.measure(rep.symbol, rep.date, as_of=as_of)
        except Exception:                                      # noqa: BLE001
            continue
        if r.car_post is None or r.car_immediate is None:
            continue
        by_source.setdefault(rep.source_name, []).append(
            (r.car_pre or 0.0, r.car_immediate, r.car_post))

    out: List[SourceScore] = []
    for source, rows in by_source.items():
        score = SourceScore(source=source, n=len(rows),
                            enough=len(rows) >= min_events)
        if score.enough:
            score.car_pre = round(median(x[0] for x in rows) * 100, 2)
            score.car_immediate = round(median(x[1] for x in rows) * 100, 2)
            score.car_post = round(median(x[2] for x in rows) * 100, 2)
            score.hit_rate = round(
                sum(1 for x in rows if x[2] > 0) / len(rows) * 100, 1)
        out.append(score)
    return sorted(out, key=lambda s: (s.enough, s.n), reverse=True)


def _main(argv: Optional[Sequence[str]] = None) -> int:       # pragma: no cover
    import sys
    args = list(argv if argv is not None else sys.argv[1:])
    days = int(args[0]) if args else 90
    started = datetime.now()
    print(f"[{started:%Y-%m-%d %H:%M}] nạp báo cáo CTCK {days} ngày gần nhất")
    result = update(days=days)
    print(json.dumps(result, ensure_ascii=False, indent=1))
    if result.get("hit_page_cap"):
        print("  ⚠️ dừng vì hết ngân sách trang — **vẫn còn báo cáo chưa nạp**")
    print(f"  {(datetime.now() - started).seconds}s")
    return 0


if __name__ == "__main__":                                    # pragma: no cover
    raise SystemExit(_main())
