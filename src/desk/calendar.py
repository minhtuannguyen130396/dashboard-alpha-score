"""Lịch xúc tác — thứ duy nhất trong cả hệ thống nhìn về phía trước mà không dự báo.

Không có nguồn nào mới phải nạp: tất cả đã nằm trên đĩa, việc của module này là
gộp chúng thành **một dòng thời gian phía trước** và nói rõ cái nào là *sự thật
lịch*, cái nào là *ước lượng*.

| Sự kiện | Nguồn | Chắc chắn? |
|---|---|---|
| Phiên đáo hạn phái sinh | ``ta/futures.expiries_between`` | ✅ thứ Năm thứ ba, là lịch |
| Ngày giao dịch không hưởng quyền | ``timescale_marks`` nhãn `D` | ✅ doanh nghiệp đã công bố |
| Mùa BCTC quý | suy từ **chính lịch các quý trước của mã đó** | ❌ ước lượng |
| Kỳ công bố chỉ số vĩ mô | ``macro/series`` (`next_release`) | ✅ cơ quan thống kê đã hẹn |
| Cửa sổ đăng ký mua/bán của nội bộ | ``holder_transactions`` | ✅ đã đăng ký |

Ranh giới ``certain`` là toàn bộ giá trị của bảng này. Một ngày đáo hạn và một
ngày "chắc khoảng cuối tháng 10 sẽ ra BCTC" in cùng một cột mà không phân biệt
thì cái thứ hai mượn được độ tin cậy của cái thứ nhất.
"""
import sqlite3
from dataclasses import asdict, dataclass, field
from datetime import date as date_cls
from datetime import datetime, timedelta
from pathlib import Path
from statistics import median
from typing import Any, Dict, List, Optional, Sequence

from src.ta.loader import PROJECT_ROOT

NEWS_DB = PROJECT_ROOT / "news" / "index.db"

KIND_LABEL = {
    "dao_han": "đáo hạn phái sinh",
    "gdkhq": "giao dịch không hưởng quyền",
    "bctc": "BCTC quý (ước lượng)",
    "vi_mo": "công bố vĩ mô",
    "noi_bo": "cửa sổ giao dịch nội bộ",
}


@dataclass
class Event:
    date: str
    kind: str
    subject: str
    title: str
    certain: bool = True
    source: str = ""

    @property
    def kind_label(self) -> str:
        return KIND_LABEL.get(self.kind, self.kind)

    def to_dict(self) -> Dict[str, Any]:
        out = asdict(self)
        out["kind_label"] = self.kind_label
        return out


def _rows(sql: str, args: Sequence[Any], db_path: Optional[Path] = None
          ) -> List[tuple]:
    path = db_path or NEWS_DB
    if not Path(path).is_file():
        return []
    try:
        conn = sqlite3.connect(str(path))
        conn.execute("PRAGMA busy_timeout = 15000")
        out = conn.execute(sql, list(args)).fetchall()
        conn.close()
        return out
    except sqlite3.Error:
        return []


# ---------------------------------------------------------------------------
def futures_events(start: date_cls, end: date_cls) -> List[Event]:
    from src.ta import futures as futures_mod
    out = []
    for day in futures_mod.expiries_between(start, end):
        out.append(Event(date=day.strftime("%Y-%m-%d"), kind="dao_han",
                         subject="VN30F1M",
                         title="phiên đáo hạn hợp đồng tháng — basis buộc hội tụ về 0",
                         certain=True, source="lịch (thứ Năm thứ ba)"))
    return out


def dividend_events(symbols: Sequence[str], start: str, end: str,
                    db_path: Optional[Path] = None) -> List[Event]:
    if not symbols:
        return []
    marks = _rows(
        "SELECT symbol, date, raw_title FROM timescale_marks "
        "WHERE label = 'D' AND date >= ? AND date <= ?",
        (start, end + "T23:59:59"), db_path)
    out = []
    want = {s.strip().upper() for s in symbols}
    for symbol, day, title in marks:
        if symbol not in want:
            continue
        head = str(title or "").split("|")[0].strip()
        out.append(Event(date=str(day)[:10], kind="gdkhq", subject=symbol,
                         title=head or "ngày giao dịch không hưởng quyền",
                         certain=True, source="timescale_marks"))
    return out


def earnings_estimates(symbols: Sequence[str], start: str, end: str,
                       db_path: Optional[Path] = None) -> List[Event]:
    """Mùa BCTC — suy từ **chính lịch các quý trước của từng mã**.

    Không dùng một hạn nộp chung cho cả rổ: đo trên kho thì 60/80 mã nộp đúng
    ngày cuối còn 20 mã nộp sớm tới hai tuần, nên một mốc chung là sai cho đúng
    những mã đáng chú ý nhất. ``certain=False`` — đây là ước lượng.
    """
    if not symbols:
        return []
    want = {s.strip().upper() for s in symbols}
    rows = _rows("SELECT symbol, mark_id, date FROM timescale_marks "
                 "WHERE label = 'F'", (), db_path)
    history: Dict[str, Dict[int, List[int]]] = {}
    for symbol, mark_id, day in rows:
        if symbol not in want:
            continue
        parts = str(mark_id or "").split("_")
        if len(parts) != 3:
            continue
        try:
            year, quarter = int(parts[1]), int(parts[2])
            published = datetime.strptime(str(day)[:10], "%Y-%m-%d")
        except ValueError:
            continue
        # `F_<năm>_0` là báo cáo năm, không phải quý — bỏ qua chứ không ép
        # vào lịch quý, vì nó ra theo hạn khác hẳn.
        if quarter not in (1, 2, 3, 4):
            continue
        end_month = {1: 3, 2: 6, 3: 9, 4: 12}[quarter]
        period_end = datetime(year, end_month, 28) + timedelta(days=4)
        period_end = period_end.replace(day=1) - timedelta(days=1)
        history.setdefault(symbol, {}).setdefault(quarter, []).append(
            (published - period_end).days)

    out: List[Event] = []
    start_dt = datetime.strptime(start, "%Y-%m-%d")
    end_dt = datetime.strptime(end, "%Y-%m-%d")
    for symbol, by_quarter in history.items():
        for quarter, lags in by_quarter.items():
            if len(lags) < 2:
                continue
            lag = int(median(lags))
            for year in (start_dt.year, start_dt.year + 1):
                end_month = {1: 3, 2: 6, 3: 9, 4: 12}[quarter]
                period_end = datetime(year, end_month, 28) + timedelta(days=4)
                period_end = period_end.replace(day=1) - timedelta(days=1)
                guess = period_end + timedelta(days=lag)
                if start_dt <= guess <= end_dt:
                    out.append(Event(
                        date=guess.strftime("%Y-%m-%d"), kind="bctc",
                        subject=symbol,
                        title=f"BCTC Q{quarter}/{year} — ước lượng từ {len(lags)} "
                              f"kỳ trước (trễ trung vị {lag} ngày)",
                        certain=False, source="timescale_marks (suy ra)"))
    return out


#: Đo cả kho ngày 20/09/2026: 96 chỉ số vĩ mô, chỉ 31 có ``next_release``, và
#: mốc **xa nhất trong toàn kho là 2023-12-31** — trường này đã chết ở nguồn.
#: Cùng họ với ``macro_posts.sentiment``: một trường tồn tại nhưng không mang
#: tin, và nếu không nói ra thì lịch vĩ mô trống trông như "kỳ này không có gì
#: công bố" thay vì "nguồn không cho biết".
MACRO_NEXT_RELEASE_DEAD_AFTER = "2024-01-01"


def macro_events(start: str, end: str) -> List[Event]:
    """Kỳ công bố kế tiếp của các chỉ số vĩ mô đã đóng băng.

    Gần như luôn rỗng, và lý do nằm ở nguồn chứ không ở đây — xem
    ``MACRO_NEXT_RELEASE_DEAD_AFTER``.
    """
    try:
        from src.macro import series as series_mod
    except ImportError:                                        # pragma: no cover
        return []
    root = series_mod.SNAPSHOT_DIR
    if not root.is_dir():
        return []
    out: List[Event] = []
    for folder in sorted(p.name for p in root.glob("*") if p.is_dir()):
        try:
            indicators = series_mod.load(folder)
        except Exception:                                      # noqa: BLE001
            continue
        for ind in indicators or []:
            day = (getattr(ind, "next_release", "") or "")[:10]
            if day and start <= day <= end:
                out.append(Event(date=day, kind="vi_mo",
                                 subject=getattr(ind, "name", folder),
                                 title=f"kỳ công bố kế tiếp — {getattr(ind, 'name', '')}",
                                 certain=True, source=f"macro/{folder}"))
    return out


def insider_windows(symbols: Sequence[str], start: str, end: str,
                    db_path: Optional[Path] = None) -> List[Event]:
    """Cửa sổ đăng ký mua/bán của nội bộ còn đang mở."""
    if not symbols:
        return []
    want = {s.strip().upper() for s in symbols}
    rows = _rows(
        "SELECT symbol, end_date, name, position, direction, registered_volume "
        "FROM holder_transactions WHERE end_date >= ? AND end_date <= ?",
        (start, end), db_path)
    out = []
    for symbol, end_date, name, position, kind, volume in rows:
        if symbol not in want:
            continue
        side = "mua" if kind in (0, 2) else "bán"
        who = " · ".join(x for x in (name, position) if x)
        out.append(Event(date=str(end_date)[:10], kind="noi_bo", subject=symbol,
                         title=f"hạn cuối cửa sổ đăng ký {side}"
                               + (f" — {who}" if who else ""),
                         certain=True, source="holder_transactions"))
    return out


# ---------------------------------------------------------------------------
@dataclass
class Calendar:
    start: str
    end: str
    events: List[Event] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)

    @property
    def certain(self) -> List[Event]:
        return [e for e in self.events if e.certain]

    @property
    def estimated(self) -> List[Event]:
        return [e for e in self.events if not e.certain]

    def to_dict(self) -> Dict[str, Any]:
        return {"start": self.start, "end": self.end,
                "events": [e.to_dict() for e in self.events], "notes": self.notes}


def build(symbols: Optional[Sequence[str]] = None, as_of: Optional[datetime] = None,
          days: int = 30, db_path: Optional[Path] = None) -> Calendar:
    """Lịch xúc tác ``days`` ngày tới. Rỗng là *chưa nạp*, không phải *không có*."""
    from src.ta.loader import resolve_universe
    start_dt = as_of or datetime.now()
    end_dt = start_dt + timedelta(days=days)
    start, end = start_dt.strftime("%Y-%m-%d"), end_dt.strftime("%Y-%m-%d")
    syms = list(symbols) if symbols else resolve_universe(None)

    events: List[Event] = []
    events += futures_events(start_dt.date(), end_dt.date())
    events += dividend_events(syms, start, end, db_path)
    events += earnings_estimates(syms, start, end, db_path)
    events += macro_events(start, end)
    events += insider_windows(syms, start, end, db_path)

    cal = Calendar(start=start, end=end,
                   events=sorted(events, key=lambda e: (e.date, e.kind, e.subject)))
    if not Path(db_path or NEWS_DB).is_file():
        cal.notes.append("chưa có `news/index.db` — thiếu hẳn phần cổ tức, BCTC "
                         "và giao dịch nội bộ")
    if not cal.estimated:
        cal.notes.append("không có mốc BCTC ước lượng nào rơi vào khoảng này")
    if not any(e.kind == "vi_mo" for e in cal.events):
        cal.notes.append(
            "lịch vĩ mô **không dựng được**: `next_release` của FireAnt là "
            "trường chết — 31/96 chỉ số có giá trị và mốc xa nhất cả kho là "
            "2023-12-31. Đây là *nguồn không cho biết*, không phải *kỳ này "
            "không có gì công bố*.")
    return cal
