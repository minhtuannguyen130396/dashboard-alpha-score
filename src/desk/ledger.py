"""Sổ của bàn phân tích — **chỉ thêm, không sửa, không xoá**.

``CLAUDE.md`` đã có một luật cùng họ cho điểm tin: *không backfill được*. Ở đây
nó nặng hơn một bậc. Một điểm tin chấm muộn ít nhất còn đọc đúng bài báo hôm
đó; còn "tháng 3 tôi đã nghĩ gì" thì viết lại hôm nay là viết bởi một người
**đã biết** thị trường sau đó đi đâu. Không có cách nào dựng lại, không có
nguồn nào bán lại. Nên sổ phải chạy từ trước khi có ai đọc nó.

Ba luật đóng thẳng vào code, không nằm ở tài liệu:

1. **Không có ``update()``, không có ``delete()``.** Đổi ý là ghi một ``Entry``
   mới mang ``supersedes``. Cả hai bản cùng nằm trong bảng điểm — đó chính là
   thứ đáng đọc: bàn này đổi ý nhanh cỡ nào, và mỗi lần đổi ý thì sau đó ra sao.
2. **Khoá theo PHIÊN dữ liệu**, không theo ngày hệ thống. Dùng lại nguyên lý
   của ``thesis.load_thesis``: một quan điểm viết cho phiên tuần trước nói về
   một cây nến khác, một mốc kích hoạt khác.
3. **``evidence_hash`` bắt buộc.** Khi soi lại một quan điểm sai, câu hỏi duy
   nhất đáng hỏi là *sai vì đọc thiếu, hay đọc đủ mà suy sai* — hai loại sai
   chữa bằng hai cách khác hẳn nhau, và chỉ hash của gói bằng chứng tách được
   chúng ra.

Và một luật nữa, ở tầng dữ liệu: **``trigger`` + ``invalidation`` + ``horizon``
là bắt buộc**. Một quan điểm không có mốc huỷ và không có hạn thì không bao
giờ sai được; một câu không sai được thì không chấm điểm được, mà không chấm
điểm được thì cuốn sổ này vô nghĩa (§7.7 của plan).

File là nguồn sự thật, ``index.db`` chỉ là cache tra cứu — hỏng thì
``reindex()`` dựng lại từ đĩa, đúng quy ước "file lưu chỉ là cache" của
``forecast.py``.
"""
import hashlib
import json
import re
import sqlite3
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

from src.ta.loader import PROJECT_ROOT, load_prices
from src.ta.thesis import STANCES

LEDGER_DIR = PROJECT_ROOT / "desk" / "ledger"
DB_NAME = "index.db"

#: Bốn cấp quan điểm. Cố ý **không** gộp vào một thang: một nhận định sai về
#: thị trường và một nhận định sai về một mã không cùng một loại sai, và gộp
#: tỷ lệ đúng của chúng lại là giấu đi chỗ bàn này thật sự yếu.
KINDS = {
    "market": "thị trường",
    "sector": "ngành",
    "stock": "mã",
    "book": "sổ",
}

#: Nấc tin cậy — model chọn nấc, ``book.py`` mới đổi nấc thành trọng số. Để
#: model tự viết ra một con số phần trăm là để nó âm thầm quyết định đòn bẩy.
CONFIDENCE = {"cao": "tin cậy cao", "vua": "tin cậy vừa", "thap": "tin cậy thấp"}

#: SQLite mặc định ``busy_timeout = 0``: đọc trúng lúc có người ghi là hỏng
#: tức thì. Cùng lý do đã ghi cho ``news/store.py``.
BUSY_TIMEOUT_MS = 15_000

#: Chỉ số dùng để đếm phiên. Hạn của một quan điểm tính bằng **phiên giao
#: dịch**, không phải ngày lịch — một kỳ nghỉ Tết 9 ngày không được ăn mất
#: một nửa hạn của quan điểm.
SESSION_INDEX = "VNINDEX"

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

OPEN, SUPERSEDED, EXPIRED = "open", "superseded", "expired"

STATUS_LABEL = {
    OPEN: "còn hiệu lực",
    SUPERSEDED: "đã bị thay bằng bản mới",
    EXPIRED: "hết hạn, không được tái khẳng định",
}


class LedgerError(ValueError):
    """Quan điểm không đủ điều kiện vào sổ."""


class LedgerConflict(LedgerError):
    """Đã có một bản khác mang đúng ``entry_id`` này.

    Không phải lỗi ghi đè thông thường: ``entry_id`` mang hash nội dung, nên
    trùng id mà khác nội dung nghĩa là có va chạm hash hoặc có người sửa file
    tay. Cả hai đều phải dừng lại chứ không được âm thầm đè.
    """


# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Entry:
    """Một quan điểm đã phát biểu. ``frozen`` là cố ý — sổ không sửa được."""
    entry_id: str
    kind: str
    subject: str
    session: str                 # PHIÊN DỮ LIỆU, không phải ngày hôm nay
    author: str                  # model/người viết — không biết của ai thì không duyệt được
    stance: str
    headline: str
    trigger: str
    invalidation: str
    horizon_sessions: int
    confidence: str = "vua"
    target: Optional[str] = None
    weight_pct: Optional[float] = None
    evidence_hash: str = ""
    supersedes: Optional[str] = None
    created_at: str = ""
    note: str = ""

    # --- mốc dạng SỐ, tuỳ chọn -------------------------------------------
    # ``trigger`` / ``invalidation`` là câu chữ vì chúng phải đọc được ("đóng
    # cửa > 24.8 **với volume ≥ 1.5× TB20**" — vế thứ hai không nhét vào một
    # con số được). Nhưng ``scorecard.py`` thì cần số để replay. Nên số là
    # **thêm vào**, không thay thế: có thì chấm tự động được, không có thì bảng
    # điểm vẫn đo được lợi suất tương đối nhưng nói rõ là không replay được mốc.
    trigger_level: Optional[float] = None
    invalidation_level: Optional[float] = None
    target_level: Optional[float] = None

    @property
    def kind_label(self) -> str:
        return KINDS.get(self.kind, self.kind)

    @property
    def stance_label(self) -> str:
        return STANCES.get(self.stance, self.stance)

    @property
    def confidence_label(self) -> str:
        return CONFIDENCE.get(self.confidence, self.confidence)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Entry":
        fields = {f for f in cls.__dataclass_fields__}          # noqa: SLF001
        return cls(**{k: v for k, v in data.items() if k in fields})


# ---------------------------------------------------------------------------
def hash_evidence(text: str) -> str:
    """Vân tay của gói bằng chứng mà người viết đã đọc.

    Chuẩn hoá khoảng trắng trước khi băm: cùng một gói render hai lần có thể
    khác nhau ở vài dấu xuống dòng, và một hash đổi vì lý do đó thì vô dụng.
    """
    norm = " ".join((text or "").split())
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()[:16]


def _slug(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "", (text or "").upper())[:16] or "NA"


def _content_hash(parts: Sequence[Any]) -> str:
    raw = "|".join("" if p is None else str(p) for p in parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:8]


def make_entry(kind: str, subject: str, session: str, author: str, stance: str,
               headline: str, trigger: str, invalidation: str,
               horizon_sessions: int, confidence: str = "vua",
               target: Optional[str] = None, weight_pct: Optional[float] = None,
               evidence_hash: str = "", supersedes: Optional[str] = None,
               note: str = "", created_at: Optional[str] = None,
               trigger_level: Optional[float] = None,
               invalidation_level: Optional[float] = None,
               target_level: Optional[float] = None) -> Entry:
    """Dựng + **kiểm tra** một quan điểm trước khi nó có quyền vào sổ.

    Mọi thông báo lỗi nói ra *vì sao* điều kiện đó tồn tại, không chỉ nói là
    thiếu: người đọc lỗi này là một model đang viết nhận định, và nó sửa được
    nếu biết lý do.
    """
    kind = (kind or "").strip().lower()
    if kind not in KINDS:
        raise LedgerError(f"`kind` phải là một trong {sorted(KINDS)}, nhận '{kind}'")

    subject = (subject or "").strip().upper()
    if not subject:
        raise LedgerError("`subject` trống — không biết quan điểm này nói về cái gì")

    session = (session or "").strip()
    if not _DATE_RE.match(session):
        raise LedgerError("`session` phải là phiên dữ liệu dạng YYYY-MM-DD "
                          "(phiên cuối của gói bằng chứng, không phải ngày hôm nay)")

    author = (author or "").strip()
    if not author:
        raise LedgerError("`author` trống — một nhận định không biết của ai thì "
                          "không duyệt được")

    stance = (stance or "").strip().lower()
    if stance not in STANCES:
        raise LedgerError(f"`stance` phải là một trong {sorted(STANCES)}")

    confidence = (confidence or "").strip().lower()
    if confidence not in CONFIDENCE:
        raise LedgerError(f"`confidence` phải là một trong {sorted(CONFIDENCE)} — "
                          "nấc tin cậy, không phải phần trăm; trọng số do "
                          "`book.py` tính từ nấc này")

    headline = (headline or "").strip()
    if not headline:
        raise LedgerError("`headline` trống — sổ ghi kết luận, không ghi số liệu")

    trigger = (trigger or "").strip()
    invalidation = (invalidation or "").strip()
    if not trigger or not invalidation:
        raise LedgerError("`trigger` và `invalidation` đều bắt buộc: một quan điểm "
                          "không có mốc huỷ thì không bao giờ sai được, và một câu "
                          "không sai được thì không chấm điểm được")

    try:
        horizon_sessions = int(horizon_sessions)
    except (TypeError, ValueError):
        raise LedgerError("`horizon_sessions` phải là số phiên") from None
    if horizon_sessions < 1:
        raise LedgerError("`horizon_sessions` phải ≥ 1 — sổ không có cửa ra thì "
                          "mọi vị thế thua đều 'vẫn đang chờ' và tỷ lệ đúng luôn đẹp")

    if weight_pct is not None:
        weight_pct = float(weight_pct)
        if not 0.0 <= weight_pct <= 100.0:
            raise LedgerError("`weight_pct` nằm ngoài 0–100")

    if not (evidence_hash or "").strip():
        raise LedgerError("`evidence_hash` trống — phải nói rõ đã đọc gói bằng "
                          "chứng nào (dùng `hash_evidence` trên chính gói đó)")

    created_at = created_at or datetime.now().isoformat(timespec="seconds")
    digest = _content_hash([kind, subject, session, author, stance, headline,
                            trigger, invalidation, target, horizon_sessions,
                            confidence, weight_pct, evidence_hash, supersedes, note,
                            trigger_level, invalidation_level, target_level])
    entry_id = f"{kind}-{_slug(subject)}-{session}-{digest}"
    return Entry(entry_id=entry_id, kind=kind, subject=subject, session=session,
                 author=author, stance=stance, headline=headline, trigger=trigger,
                 invalidation=invalidation, horizon_sessions=horizon_sessions,
                 confidence=confidence, target=(target or None),
                 weight_pct=weight_pct, evidence_hash=evidence_hash.strip(),
                 supersedes=(supersedes or None), created_at=created_at, note=note,
                 trigger_level=trigger_level,
                 invalidation_level=invalidation_level,
                 target_level=target_level)


# ---------------------------------------------------------------------------
def _root(root: Optional[Path] = None) -> Path:
    return root or LEDGER_DIR


def path_for(entry: Entry, root: Optional[Path] = None) -> Path:
    year = entry.session[:4]
    return _root(root) / year / entry.kind / f"{entry.entry_id}.json"


def _connect(root: Optional[Path] = None) -> sqlite3.Connection:
    base = _root(root)
    base.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(base / DB_NAME)
    conn.execute(f"PRAGMA busy_timeout = {BUSY_TIMEOUT_MS}")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS entries (
            entry_id TEXT PRIMARY KEY,
            kind TEXT NOT NULL,
            subject TEXT NOT NULL,
            session TEXT NOT NULL,
            author TEXT NOT NULL,
            stance TEXT NOT NULL,
            confidence TEXT,
            weight_pct REAL,
            horizon_sessions INTEGER NOT NULL,
            supersedes TEXT,
            created_at TEXT,
            path TEXT NOT NULL
        )""")
    conn.execute("CREATE INDEX IF NOT EXISTS ix_entries_subject "
                 "ON entries (kind, subject, session)")
    conn.commit()
    return conn


def _index(conn: sqlite3.Connection, entry: Entry, path: Path) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO entries (entry_id, kind, subject, session, author,"
        " stance, confidence, weight_pct, horizon_sessions, supersedes, created_at,"
        " path) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (entry.entry_id, entry.kind, entry.subject, entry.session, entry.author,
         entry.stance, entry.confidence, entry.weight_pct, entry.horizon_sessions,
         entry.supersedes, entry.created_at, str(path)))
    conn.commit()


def append(entry: Entry, root: Optional[Path] = None) -> Path:
    """Ghi một quan điểm vào sổ. Đây là hàm ghi **duy nhất** của module.

    Ghi lại đúng bản đã có là no-op (chạy lại một lượt không rải file trùng);
    trùng id mà khác nội dung thì dừng, vì đó là dấu hiệu có người sửa tay.
    """
    if entry.supersedes:
        old = load(entry.supersedes, root)
        if old is None:
            raise LedgerError(f"`supersedes` trỏ tới '{entry.supersedes}' không có "
                              "trong sổ — không thay được một bản không tồn tại")
        if old.kind != entry.kind or old.subject != entry.subject:
            raise LedgerError("bản bị thay phải cùng `kind` và `subject`: thay một "
                              f"quan điểm về {old.subject} bằng quan điểm về "
                              f"{entry.subject} là hai chuyện khác nhau")

    path = path_for(entry, root)
    payload = json.dumps(entry.to_dict(), ensure_ascii=False, indent=1)
    if path.is_file():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            existing = None
        if existing != entry.to_dict():
            raise LedgerConflict(
                f"'{entry.entry_id}' đã có trên đĩa với nội dung khác. Sổ không "
                "sửa được — ghi bản mới kèm `supersedes` nếu muốn đổi ý.")
        return path

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(payload, encoding="utf-8")
    conn = _connect(root)
    try:
        _index(conn, entry, path)
    finally:
        conn.close()
    return path


def load(entry_id: str, root: Optional[Path] = None) -> Optional[Entry]:
    for path in _root(root).rglob(f"{entry_id}.json"):
        try:
            return Entry.from_dict(json.loads(path.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, OSError):
            return None
    return None


def _scan_files(root: Optional[Path] = None) -> List[Entry]:
    out: List[Entry] = []
    for path in sorted(_root(root).rglob("*.json")):
        try:
            out.append(Entry.from_dict(json.loads(path.read_text(encoding="utf-8"))))
        except (json.JSONDecodeError, OSError, TypeError):
            continue
    return out


def reindex(root: Optional[Path] = None) -> int:
    """Dựng lại ``index.db`` từ file. File là nguồn sự thật, db chỉ là cache."""
    entries = _scan_files(root)
    conn = _connect(root)
    try:
        conn.execute("DELETE FROM entries")
        for e in entries:
            _index(conn, e, path_for(e, root))
    finally:
        conn.close()
    return len(entries)


def all_entries(kind: Optional[str] = None, subject: Optional[str] = None,
                root: Optional[Path] = None) -> List[Entry]:
    """Mọi quan điểm đã ghi, cũ → mới theo phiên rồi tới lúc tạo."""
    rows = _scan_files(root)
    if kind:
        rows = [e for e in rows if e.kind == kind.strip().lower()]
    if subject:
        want = subject.strip().upper()
        rows = [e for e in rows if e.subject == want]
    return sorted(rows, key=lambda e: (e.session, e.created_at, e.entry_id))


# ---------------------------------------------------------------------------
def _session_dates(as_of: Optional[datetime] = None) -> List[str]:
    end = as_of or datetime.now()
    bars = load_prices(SESSION_INDEX, datetime(2010, 1, 1), end)
    return [b.date.strftime("%Y-%m-%d") for b in bars]


def sessions_since(session: str, as_of: Optional[datetime] = None,
                   calendar: Optional[Sequence[str]] = None) -> Optional[int]:
    """Số **phiên giao dịch** đã trôi qua kể từ ``session``.

    ``None`` khi chưa đọc được lịch phiên — *chưa đo được* khác *bằng 0*, và
    một quan điểm bị tính nhầm là còn 0 phiên tuổi thì không bao giờ hết hạn.
    """
    days = list(calendar) if calendar is not None else _session_dates(as_of)
    if not days:
        return None
    limit = (as_of or datetime.now()).strftime("%Y-%m-%d")
    days = [d for d in days if d <= limit]
    after = [d for d in days if d > session]
    return len(after)


@dataclass
class Standing:
    """Trạng thái của một quan điểm tại một mốc — dẫn xuất, không lưu trên đĩa."""
    entry: Entry
    status: str
    age_sessions: Optional[int] = None
    replaced_by: Optional[str] = None

    @property
    def status_label(self) -> str:
        return STATUS_LABEL.get(self.status, self.status)

    def to_dict(self) -> Dict[str, Any]:
        return {"entry": self.entry.to_dict(), "status": self.status,
                "age_sessions": self.age_sessions, "replaced_by": self.replaced_by}


def standings(entries: Optional[Sequence[Entry]] = None,
              as_of: Optional[datetime] = None,
              root: Optional[Path] = None,
              calendar: Optional[Sequence[str]] = None) -> List[Standing]:
    """Trạng thái của từng quan điểm tại ``as_of``.

    Quan điểm tạo **sau** mốc bị loại hẳn — cùng luật hồi tưởng của
    ``check_forecasts``: bản replay không được thấy thứ nó chưa thể biết.
    """
    rows = list(entries if entries is not None else all_entries(root=root))
    limit = (as_of or datetime.now()).strftime("%Y-%m-%d")
    rows = [e for e in rows if e.session <= limit]
    replaced: Dict[str, str] = {}
    for e in rows:
        if e.supersedes:
            replaced[e.supersedes] = e.entry_id

    days = list(calendar) if calendar is not None else _session_dates(as_of)
    out: List[Standing] = []
    for e in rows:
        age = sessions_since(e.session, as_of, calendar=days)
        if e.entry_id in replaced:
            status = SUPERSEDED
        elif age is not None and age > e.horizon_sessions:
            status = EXPIRED
        else:
            status = OPEN
        out.append(Standing(entry=e, status=status, age_sessions=age,
                            replaced_by=replaced.get(e.entry_id)))
    return sorted(out, key=lambda s: (s.entry.session, s.entry.entry_id))


def open_entries(kind: Optional[str] = None, as_of: Optional[datetime] = None,
                 root: Optional[Path] = None,
                 calendar: Optional[Sequence[str]] = None) -> List[Standing]:
    rows = all_entries(kind=kind, root=root)
    return [s for s in standings(rows, as_of, root, calendar) if s.status == OPEN]


def history(subject: str, kind: Optional[str] = None,
            root: Optional[Path] = None) -> List[Entry]:
    """Chuỗi quan điểm về một đối tượng, cũ → mới. Kể cả bản đã bị thay."""
    return all_entries(kind=kind, subject=subject, root=root)


def chain_of(entry_id: str, root: Optional[Path] = None) -> List[Entry]:
    """Lần ngược chuỗi ``supersedes`` — bản hiện tại đứng cuối."""
    seen: List[Entry] = []
    cur = load(entry_id, root)
    guard = 0
    while cur is not None and guard < 200:
        seen.append(cur)
        cur = load(cur.supersedes, root) if cur.supersedes else None
        guard += 1
    return list(reversed(seen))


def stats(as_of: Optional[datetime] = None, root: Optional[Path] = None
          ) -> Dict[str, Any]:
    """Đếm đầu sổ. Chưa phải bảng điểm — chấm điểm là việc của ``scorecard.py``."""
    rows = standings(as_of=as_of, root=root)
    by_kind: Dict[str, Dict[str, int]] = {}
    for s in rows:
        slot = by_kind.setdefault(s.entry.kind, {OPEN: 0, SUPERSEDED: 0, EXPIRED: 0})
        slot[s.status] += 1
    sessions = sorted({s.entry.session for s in rows})
    return {
        "n": len(rows),
        "by_kind": by_kind,
        "first_session": sessions[0] if sessions else None,
        "last_session": sessions[-1] if sessions else None,
        "authors": sorted({s.entry.author for s in rows}),
    }
