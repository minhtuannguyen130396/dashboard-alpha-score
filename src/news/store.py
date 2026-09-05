"""Kho SQLite cho tầng tin tức.

Chọn SQLite vì hợp với triết lý file-based sẵn có của repo (``data/``,
``forecasts/``, ``reports/``): không service chạy nền, một file, rsync được.

Ba quyết định về schema đáng giải thích:

* **``registered_volume`` để NULL được, và NULL khác 0.** Bản ghi trước khoảng
  2014 không có đăng ký vì quy định khi đó chưa bắt buộc. Ép về 0 là biến "không
  đo được" thành "đăng ký rồi không làm" — một tín hiệu bịa ra từ khoảng trống.
* **``first_seen`` ghi một lần, không đổi — nhưng KHÔNG lọc theo nó mặc định.**
  Ngày *mình* thấy bản ghi lần đầu là mốc duy nhất không bịa được, nên nó được
  lưu. Nhưng dùng nó làm bộ lọc ``as_of`` mặc định thì mọi backfill thành vô
  dụng: nạp lịch sử 2023–2026 hôm nay là mọi mốc hồi tưởng trước hôm nay trả về
  rỗng, và phần hiệu chuẩn base rate (§8) chết theo.
  Phân biệt cần giữ: ``first_seen`` chống **nội dung bị sửa sau** — đúng cho bài
  báo, vô nghĩa cho một giao dịch năm 2020 mà API trả về bất biến. Với dữ liệu
  có cấu trúc, **ngày sự kiện** mới là "biết được tới đâu tại thời điểm đó".
  Ai cần chặt hơn thì bật ``strict_first_seen=True``.
* **Ghi là upsert theo khoá tự nhiên.** Chạy lại ``ingest`` nhiều lần phải ra
  cùng một kho, vì thực tế nó sẽ được chạy lại nhiều lần.
"""
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from src.news.models import HolderTransaction, TimescaleMark
from src.ta.loader import PROJECT_ROOT

NEWS_DIR = PROJECT_ROOT / "news"
DB_PATH = NEWS_DIR / "index.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS holder_transactions (
    transaction_id        INTEGER PRIMARY KEY,
    symbol                TEXT    NOT NULL,
    name                  TEXT    NOT NULL,
    position              TEXT,
    direction             INTEGER NOT NULL,
    direction_source      TEXT    NOT NULL,
    registered_volume     REAL,
    execution_volume      REAL,
    start_date            TEXT,
    end_date              TEXT,
    execution_date        TEXT,
    major_holder_id       INTEGER,
    individual_holder_id  INTEGER,
    institution_holder_id INTEGER,
    is_organization       INTEGER,
    first_seen            TEXT    NOT NULL,
    updated_at            TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_ht_symbol      ON holder_transactions(symbol);
CREATE INDEX IF NOT EXISTS ix_ht_start       ON holder_transactions(symbol, start_date);
CREATE INDEX IF NOT EXISTS ix_ht_exec        ON holder_transactions(symbol, execution_date);

CREATE TABLE IF NOT EXISTS timescale_marks (
    mark_id     TEXT    NOT NULL,
    symbol      TEXT    NOT NULL,
    label       TEXT    NOT NULL,
    date        TEXT    NOT NULL,
    raw_title   TEXT    NOT NULL,
    parsed_json TEXT    NOT NULL,
    first_seen  TEXT    NOT NULL,
    updated_at  TEXT    NOT NULL,
    PRIMARY KEY (symbol, mark_id)
);
CREATE INDEX IF NOT EXISTS ix_tm_symbol_date ON timescale_marks(symbol, date);

CREATE TABLE IF NOT EXISTS ingest_log (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol     TEXT NOT NULL,
    kind       TEXT NOT NULL,
    rows       INTEGER NOT NULL,
    ran_at     TEXT NOT NULL,
    note       TEXT
);

CREATE TABLE IF NOT EXISTS posts (
    post_id            INTEGER PRIMARY KEY,
    symbol             TEXT    NOT NULL,
    title              TEXT    NOT NULL,
    description        TEXT    NOT NULL,
    date               TEXT    NOT NULL,
    source             TEXT,
    source_url         TEXT,
    tagged_symbols     TEXT,
    post_group         TEXT,
    fireant_sentiment  INTEGER,
    is_ai_generated    INTEGER,
    is_disclosure      INTEGER NOT NULL DEFAULT 0,
    disclosure_kind    TEXT,
    body               TEXT,
    title_hash         TEXT    NOT NULL,
    first_seen         TEXT    NOT NULL,
    updated_at         TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_posts_symbol_date ON posts(symbol, date);
CREATE INDEX IF NOT EXISTS ix_posts_disclosure  ON posts(symbol, is_disclosure, date);
CREATE INDEX IF NOT EXISTS ix_posts_titlehash   ON posts(title_hash);
"""



def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@contextmanager
def connect(db_path: Optional[Path] = None):
    """Mở kết nối, tạo schema nếu chưa có. Đóng và commit khi thoát."""
    path = Path(db_path) if db_path else DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    try:
        conn.executescript(SCHEMA)
        yield conn
        conn.commit()
    finally:
        conn.close()


def upsert_holder_transactions(conn: sqlite3.Connection,
                               items: Iterable[HolderTransaction]) -> int:
    """Ghi/cập nhật giao dịch. ``first_seen`` giữ nguyên ở lần ghi sau."""
    now = _now()
    rows = 0
    for it in items:
        conn.execute(
            """
            INSERT INTO holder_transactions (
                transaction_id, symbol, name, position, direction, direction_source,
                registered_volume, execution_volume, start_date, end_date,
                execution_date, major_holder_id, individual_holder_id,
                institution_holder_id, is_organization, first_seen, updated_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(transaction_id) DO UPDATE SET
                symbol=excluded.symbol,
                name=excluded.name,
                position=excluded.position,
                direction=excluded.direction,
                direction_source=excluded.direction_source,
                registered_volume=excluded.registered_volume,
                execution_volume=excluded.execution_volume,
                start_date=excluded.start_date,
                end_date=excluded.end_date,
                execution_date=excluded.execution_date,
                updated_at=excluded.updated_at
            """,
            (it.transaction_id, it.symbol, it.name, it.position, it.direction,
             it.direction_source, it.registered_volume, it.execution_volume,
             it.start_date, it.end_date, it.execution_date, it.major_holder_id,
             it.individual_holder_id, it.institution_holder_id,
             None if it.is_organization is None else int(it.is_organization),
             now, now),
        )
        rows += 1
    return rows


def upsert_timescale_marks(conn: sqlite3.Connection,
                           items: Iterable[TimescaleMark]) -> int:
    now = _now()
    rows = 0
    for it in items:
        conn.execute(
            """
            INSERT INTO timescale_marks (
                mark_id, symbol, label, date, raw_title, parsed_json,
                first_seen, updated_at
            ) VALUES (?,?,?,?,?,?,?,?)
            ON CONFLICT(symbol, mark_id) DO UPDATE SET
                label=excluded.label,
                date=excluded.date,
                raw_title=excluded.raw_title,
                parsed_json=excluded.parsed_json,
                updated_at=excluded.updated_at
            """,
            (it.mark_id, it.symbol, it.label, it.date, it.raw_title,
             json.dumps(it.parsed, ensure_ascii=False), now, now),
        )
        rows += 1
    return rows


def log_ingest(conn: sqlite3.Connection, symbol: str, kind: str,
               rows: int, note: str = "") -> None:
    conn.execute(
        "INSERT INTO ingest_log (symbol, kind, rows, ran_at, note) VALUES (?,?,?,?,?)",
        (symbol, kind, rows, _now(), note),
    )


# --- Đọc ------------------------------------------------------------------

def load_holder_transactions(conn: sqlite3.Connection, symbol: str,
                             as_of: Optional[str] = None,
                             strict_first_seen: bool = False) -> List[Dict[str, Any]]:
    """Giao dịch của một mã, mới nhất trước.

    ``as_of`` cắt theo **ngày sự kiện** (``start_date``) — đó là "biết được tới
    đâu tại thời điểm đó" cho dữ liệu có cấu trúc bất biến.

    ``strict_first_seen`` thêm vế ``first_seen <= as_of``. Chỉ bật khi thật sự
    cần mô phỏng "kho lúc đó có gì" (ví dụ kiểm tra xem một chiến lược có phụ
    thuộc dữ liệu nạp muộn không). Bật mặc định là giết backfill: xem docstring
    module.
    """
    sql = "SELECT * FROM holder_transactions WHERE symbol = ?"
    params: List[Any] = [symbol]
    if as_of:
        sql += " AND (start_date IS NULL OR date(start_date) <= date(?))"
        params.append(as_of)
        if strict_first_seen:
            sql += " AND date(first_seen) <= date(?)"
            params.append(as_of)
    sql += " ORDER BY COALESCE(start_date, execution_date) DESC"
    return [dict(r) for r in conn.execute(sql, params).fetchall()]


def load_marks(conn: sqlite3.Connection, symbol: str,
               as_of: Optional[str] = None,
               strict_first_seen: bool = False) -> List[Dict[str, Any]]:
    sql = "SELECT * FROM timescale_marks WHERE symbol = ?"
    params: List[Any] = [symbol]
    if as_of:
        sql += " AND date(date) <= date(?)"
        params.append(as_of)
        if strict_first_seen:
            sql += " AND date(first_seen) <= date(?)"
            params.append(as_of)
    sql += " ORDER BY date DESC"
    out = []
    for r in conn.execute(sql, params).fetchall():
        d = dict(r)
        try:
            d["parsed"] = json.loads(d.pop("parsed_json"))
        except (json.JSONDecodeError, KeyError):
            d["parsed"] = {}
        out.append(d)
    return out


def symbols_in_store(conn: sqlite3.Connection) -> List[str]:
    rows = conn.execute(
        "SELECT DISTINCT symbol FROM holder_transactions ORDER BY symbol"
    ).fetchall()
    return [r["symbol"] for r in rows]


def upsert_posts(conn: sqlite3.Connection, items) -> int:
    """Ghi/cập nhật bài viết. ``body`` chỉ ghi đè khi lần này thật sự có nạp
    toàn văn — nạp lười nghĩa là phần lớn lượt ghi để ``body=None``, và ghi đè
    bằng None sẽ xoá mất toàn văn đã tốn một request để lấy về."""
    now = _now()
    rows = 0
    for it in items:
        conn.execute(
            """
            INSERT INTO posts (
                post_id, symbol, title, description, date, source, source_url,
                tagged_symbols, post_group, fireant_sentiment, is_ai_generated,
                is_disclosure, disclosure_kind, body, title_hash,
                first_seen, updated_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(post_id) DO UPDATE SET
                title=excluded.title,
                description=excluded.description,
                date=excluded.date,
                source=excluded.source,
                is_disclosure=excluded.is_disclosure,
                disclosure_kind=excluded.disclosure_kind,
                body=COALESCE(excluded.body, posts.body),
                title_hash=excluded.title_hash,
                updated_at=excluded.updated_at
            """,
            (it.post_id, it.symbol, it.title, it.description, it.date,
             it.source, it.source_url, json.dumps(it.tagged_symbols, ensure_ascii=False),
             it.post_group, it.fireant_sentiment, int(it.is_ai_generated),
             int(it.is_disclosure), it.disclosure_kind, it.body, it.title_hash,
             now, now),
        )
        rows += 1
    return rows


def load_posts(conn: sqlite3.Connection, symbol: str,
               as_of: Optional[str] = None, insider_only: bool = False,
               limit: int = 200) -> List[Dict[str, Any]]:
    """Bài viết của một mã, mới nhất trước.

    ``insider_only`` giữ lại đúng những bài nói về giao dịch nội bộ — đó là tập
    dùng để ghép với ``holder_transactions`` và lấy **ngày công bố thật**, thứ
    mà bản thân bảng giao dịch không có.
    """
    sql = "SELECT * FROM posts WHERE symbol = ?"
    params: List[Any] = [symbol]
    if insider_only:
        sql += " AND disclosure_kind IS NOT NULL"
    if as_of:
        sql += " AND date(substr(date,1,10)) <= date(?)"
        params.append(as_of)
    sql += " ORDER BY date DESC LIMIT ?"
    params.append(max(1, limit))
    out = []
    for r in conn.execute(sql, params).fetchall():
        d = dict(r)
        try:
            d["tagged_symbols"] = json.loads(d.get("tagged_symbols") or "[]")
        except json.JSONDecodeError:
            d["tagged_symbols"] = []
        out.append(d)
    return out
