"""BCTC theo quý — lợi nhuận, vốn chủ sở hữu, số cổ phiếu, và NGÀY CÔNG BỐ.

Đây là nguồn mà `documents/plan_analyst_desk.md` §2.3 gọi là chỗ mở khoá lớn
nhất: ``/full-financial-reports`` trả **40 quý trong đúng một request**, nên
chuỗi định giá lịch sử dựng lại được và rẻ. Khác hẳn ``estimates.py`` — cái kia
là snapshot phải đóng băng từng ngày, cái này là dữ liệu quá khứ ổn định, cào
lại lúc nào cũng ra đúng bấy nhiêu.

Bốn quyết định đọc số, mỗi cái chặn một kiểu sai đã thấy khi dò dữ liệu thật:

1. **Khớp theo TÊN DÒNG, không theo id.** Ngân hàng dùng mẫu KQKD khác hẳn
   doanh nghiệp thường: HPG có 21 dòng kết ở *"Lợi nhuận sau thuế của cổ đông
   của công ty mẹ"* (id 21), VCB có 23 dòng và **không có** dòng đó, phải lùi về
   *"Lợi nhuận sau thuế thu nhập doanh nghiệp"* (id 13). Khớp theo id là im lặng
   lấy nhầm dòng cho cả nhóm ngân hàng.
2. **Số cổ phiếu suy từ VỐN GÓP chia mệnh giá 10.000đ**, vì FireAnt không trả
   số cổ phiếu theo quý ở đâu cả. Kiểm trên dữ liệu thật: HPG 76.754 tỷ →
   7,675 tỷ cp, VCB 83.556 tỷ → 8,356 tỷ cp, SSI 25.030 tỷ → 2,503 tỷ cp — khớp
   với số cổ phiếu đang lưu hành. Thứ tự ưu tiên tên dòng quan trọng: SSI có
   *cả hai* "vốn góp của chủ sở hữu" (2,5 tỷ cp — đúng) và "vốn đầu tư của chủ
   sở hữu" (3,04 tỷ cp — đã gồm thặng dư, sai).
3. **Ngày công bố lấy từ ``timescale_marks``**, không tự suy từ cuối quý. Kỳ nào
   không có mốc thì lùi về +45 ngày sau cuối quý **và nói rõ là mốc thay thế**
   (``published_source``) — một ngày ước lượng trông y hệt một ngày thật là kiểu
   sai không ai phát hiện được.
4. **Thiếu thì để ``None``.** Không có dòng lợi nhuận thì quý đó ``npat=None``,
   không phải 0. Trả 0 là biến *không đọc được* thành *doanh nghiệp lỗ hoà vốn*.
"""
import json
import re
import sqlite3
import unicodedata
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from src.news.fireant import get
from src.ta.loader import PROJECT_ROOT

CACHE_DIR = PROJECT_ROOT / "desk" / "financials"
NEWS_DB = PROJECT_ROOT / "news" / "index.db"

#: Số kỳ xin mỗi lượt. 40 quý = 10 năm, và API trả trọn trong một request.
PERIODS = 40

#: Mệnh giá cổ phiếu Việt Nam. Cố định theo luật, không phải tham số điều chỉnh.
PAR_VALUE = 10_000.0

#: Hạn nộp BCTC quý hợp nhất. Dùng làm **mốc thay thế** khi không có mốc thật —
#: cùng con số ``PUBLISH_LAG`` mà tầng vĩ mô đã dùng, và cùng lý do.
PUBLISH_LAG_DAYS = 45

#: Loại báo cáo trong ``/full-financial-reports``.
TYPE_BALANCE, TYPE_INCOME = 1, 2

#: Tên dòng lợi nhuận, xếp theo **độ ưu tiên**. Bản không dấu.
NPAT_PATTERNS: Tuple[str, ...] = (
    "loi nhuan sau thue cua co dong cua cong ty me",
    "loi nhuan sau thue thu nhap doanh nghiep",
    "loi nhuan sau thue",
)
#: Dòng mang các chữ này không bao giờ là lợi nhuận của cổ đông công ty mẹ.
NPAT_EXCLUDE: Tuple[str, ...] = ("khong kiem soat", "truoc thue", "truoc chi phi")

#: Vốn góp theo mệnh giá — thứ tự ưu tiên là phần quan trọng (xem docstring).
SHARE_PATTERNS: Tuple[str, ...] = (
    "von gop cua chu so huu",
    "von dieu le",
    "von dau tu cua chu so huu",
    "von co phan",
)

#: Tổng vốn chủ sở hữu, để tính giá trị sổ sách.
#: Ngân hàng không có dòng nào tên "vốn chủ sở hữu" — bảng cân đối của họ gọi
#: đó là **"VIII. Vốn và các quỹ"** (VCB: 248.491 tỷ → BVPS ~29.700đ). Thiếu mẫu
#: này là mất P/B cho đúng 27/80 mã của rổ, mà P/B lại là thước đo *chính* của
#: nhóm ngân hàng.
EQUITY_PATTERNS: Tuple[str, ...] = (
    "nguon von chu so huu",
    "von chu so huu",
    "von va cac quy",
)
EQUITY_EXCLUDE: Tuple[str, ...] = ("von gop", "von dau tu", "thang du", "von khac",
                                   "von dieu le", "quy khac", "no phai tra")

QUARTER_END = {1: (3, 31), 2: (6, 30), 3: (9, 30), 4: (12, 31)}


def _fold(text: str) -> str:
    """Bỏ dấu + gom khoảng trắng. Tên dòng do FireAnt viết cho người đọc."""
    norm = unicodedata.normalize("NFD", text or "")
    plain = "".join(c for c in norm if unicodedata.category(c) != "Mn")
    plain = plain.replace("đ", "d").replace("Đ", "D")
    return " ".join(plain.lower().split())


def _strip_index(name: str) -> str:
    """Bỏ phần đánh số đầu dòng (``1.``, ``B.``, ``VIII.``, ``- ``)."""
    return re.sub(r"^[\s\-–]*(?:[ivxlcdm]+|[a-z]|\d+(?:\.\d+)*)[\.\)]\s*", "",
                  name, flags=re.IGNORECASE).strip()


# ---------------------------------------------------------------------------
@dataclass
class Quarter:
    """Một kỳ báo cáo. Mọi số theo **đồng**, chưa điều chỉnh chia tách."""
    year: int
    quarter: int
    npat: Optional[float] = None       # LNST cổ đông công ty mẹ
    equity: Optional[float] = None
    shares: Optional[float] = None
    published: Optional[str] = None    # ngày công bố (ISO)
    published_source: str = ""         # "mark" | "lag"

    @property
    def label(self) -> str:
        return f"Q{self.quarter}/{self.year}"

    @property
    def key(self) -> Tuple[int, int]:
        return (self.year, self.quarter)

    @property
    def period_end(self) -> str:
        month, day = QUARTER_END[self.quarter]
        return f"{self.year}-{month:02d}-{day:02d}"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Financials:
    symbol: str
    quarters: List[Quarter] = field(default_factory=list)   # cũ → mới
    fetched_at: str = ""
    notes: List[str] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return not self.quarters

    @property
    def n_with_profit(self) -> int:
        return sum(1 for q in self.quarters if q.npat is not None)

    def known_at(self, day: str) -> List[Quarter]:
        """Các quý đã **công bố** tính tới ``day`` — cũ → mới.

        Đây là chỗ duy nhất chặn nhìn trước ở tầng định giá: lấy quý theo *kỳ dữ
        liệu* thay vì theo *ngày công bố* là cho báo cáo ngày 15/07 đọc một con
        số ra ngày 30/07.
        """
        return [q for q in self.quarters if q.published and q.published <= day]

    def to_dict(self) -> Dict[str, Any]:
        return {"symbol": self.symbol, "fetched_at": self.fetched_at,
                "notes": self.notes,
                "quarters": [q.to_dict() for q in self.quarters]}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Financials":
        qs = [Quarter(**{k: v for k, v in q.items()
                         if k in Quarter.__dataclass_fields__})     # noqa: SLF001
              for q in (data.get("quarters") or [])]
        return cls(symbol=str(data.get("symbol") or "").upper(),
                   quarters=qs, fetched_at=str(data.get("fetched_at") or ""),
                   notes=list(data.get("notes") or []))


# ---------------------------------------------------------------------------
def _pick_row(rows: Sequence[dict], patterns: Sequence[str],
              exclude: Sequence[str] = ()) -> Optional[dict]:
    """Dòng khớp mẫu **đầu tiên theo thứ tự ưu tiên của ``patterns``**.

    Duyệt hết bảng cho mẫu thứ nhất rồi mới sang mẫu thứ hai — không duyệt bảng
    một lượt rồi lấy dòng nào khớp bất kỳ mẫu nào, vì SSI có cả "vốn góp" lẫn
    "vốn đầu tư" và thứ tự bảng không phải thứ tự đúng.
    """
    prepared = []
    for row in rows:
        folded = _fold(_strip_index(str(row.get("name") or "")))
        if any(bad in folded for bad in exclude):
            continue
        prepared.append((folded, row))
    for pattern in patterns:
        for folded, row in prepared:
            if folded.startswith(pattern) or folded == pattern:
                return row
        for folded, row in prepared:
            if pattern in folded:
                return row
    return None


def _values(row: Optional[dict]) -> Dict[Tuple[int, int], Optional[float]]:
    out: Dict[Tuple[int, int], Optional[float]] = {}
    for item in ((row or {}).get("values") or []):
        try:
            year, quarter = int(item.get("year")), int(item.get("quarter"))
        except (TypeError, ValueError):
            continue
        if quarter not in QUARTER_END:
            continue
        value = item.get("value")
        out[(year, quarter)] = float(value) if value is not None else None
    return out


def parse_statements(income_rows: Sequence[dict], balance_rows: Sequence[dict]
                     ) -> Tuple[List[Quarter], List[str]]:
    """Hai bảng thô → chuỗi quý. **Không mạng, không đĩa** nên test chạy fixture."""
    notes: List[str] = []
    npat_row = _pick_row(income_rows, NPAT_PATTERNS, NPAT_EXCLUDE)
    share_row = _pick_row(balance_rows, SHARE_PATTERNS)
    equity_row = _pick_row(balance_rows, EQUITY_PATTERNS, EQUITY_EXCLUDE)

    if npat_row is None:
        notes.append("không tìm thấy dòng lợi nhuận sau thuế trong KQKD")
    if share_row is None:
        notes.append("không tìm thấy dòng vốn góp — không suy ra được số cổ phiếu")
    if equity_row is None:
        notes.append("không tìm thấy dòng vốn chủ sở hữu — không tính được P/B")

    npat = _values(npat_row)
    shares_cap = _values(share_row)
    equity = _values(equity_row)

    keys = sorted(set(npat) | set(shares_cap) | set(equity))
    quarters = []
    for year, quarter in keys:
        cap = shares_cap.get((year, quarter))
        quarters.append(Quarter(
            year=year, quarter=quarter,
            npat=npat.get((year, quarter)),
            equity=equity.get((year, quarter)),
            shares=(cap / PAR_VALUE if cap else None),
        ))
    return quarters, notes


def fetch_statements(symbol: str, periods: int = PERIODS
                     ) -> Tuple[List[dict], List[dict]]:
    sym = symbol.strip().upper()
    today = datetime.now()
    # Kỳ gần nhất *có thể* đã có: quý của hôm nay. API tự cắt phần chưa tồn tại.
    quarter = (today.month - 1) // 3 + 1
    params = {"year": today.year, "quarter": quarter, "limit": periods}
    income = get(f"/symbols/{sym}/full-financial-reports",
                 dict(params, type=TYPE_INCOME)) or []
    balance = get(f"/symbols/{sym}/full-financial-reports",
                  dict(params, type=TYPE_BALANCE)) or []
    return list(income), list(balance)


# ---------------------------------------------------------------------------
def publish_dates(symbol: str, db_path: Optional[Path] = None
                  ) -> Dict[Tuple[int, int], str]:
    """``{(năm, quý): ngày công bố}`` từ ``timescale_marks`` đã nạp sẵn.

    Kho tin là nơi duy nhất có ngày này; không có kho thì trả rỗng và tầng trên
    lùi về mốc thay thế — nhưng phải **biết** là đã lùi.
    """
    path = db_path or NEWS_DB
    if not Path(path).is_file():
        return {}
    out: Dict[Tuple[int, int], str] = {}
    try:
        conn = sqlite3.connect(str(path))
        conn.execute("PRAGMA busy_timeout = 15000")
        rows = conn.execute(
            "SELECT mark_id, date FROM timescale_marks "
            "WHERE symbol = ? AND label = 'F'", (symbol.strip().upper(),)).fetchall()
        conn.close()
    except sqlite3.Error:
        return {}
    for mark_id, date in rows:
        m = re.match(r"^F_(\d{4})_(\d)$", str(mark_id or ""))
        if not m or not date:
            continue
        out[(int(m.group(1)), int(m.group(2)))] = str(date)[:10]
    return out


def _lag_date(q: Quarter) -> str:
    end = datetime.strptime(q.period_end, "%Y-%m-%d")
    return (end + timedelta(days=PUBLISH_LAG_DAYS)).strftime("%Y-%m-%d")


def attach_publish_dates(quarters: Sequence[Quarter], marks: Dict[Tuple[int, int], str]
                         ) -> List[Quarter]:
    """Gắn ngày công bố; kỳ không có mốc dùng mốc thay thế **và tự khai**."""
    out = []
    for q in quarters:
        real = marks.get(q.key)
        q.published = real or _lag_date(q)
        q.published_source = "mark" if real else "lag"
        out.append(q)
    return out


def cache_path(symbol: str, root: Optional[Path] = None) -> Path:
    return (root or CACHE_DIR) / f"{symbol.strip().upper()}.json"


def save(fin: Financials, root: Optional[Path] = None) -> Path:
    path = cache_path(fin.symbol, root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(fin.to_dict(), ensure_ascii=False, indent=1),
                    encoding="utf-8")
    return path


def load(symbol: str, root: Optional[Path] = None) -> Optional[Financials]:
    path = cache_path(symbol, root)
    if not path.is_file():
        return None
    try:
        return Financials.from_dict(json.loads(path.read_text(encoding="utf-8")))
    except (json.JSONDecodeError, OSError, TypeError):
        return None


def build(symbol: str, db_path: Optional[Path] = None) -> Financials:
    """Nạp từ API + gắn ngày công bố. Một lượt mạng, hai request."""
    sym = symbol.strip().upper()
    income, balance = fetch_statements(sym)
    quarters, notes = parse_statements(income, balance)
    marks = publish_dates(sym, db_path)
    quarters = attach_publish_dates(quarters, marks)
    if not marks:
        notes.append("kho tin chưa có mốc BCTC — mọi ngày công bố là mốc thay thế "
                     f"(+{PUBLISH_LAG_DAYS} ngày sau cuối quý)")
    else:
        fallback = sum(1 for q in quarters if q.published_source == "lag")
        if fallback:
            notes.append(f"{fallback}/{len(quarters)} kỳ dùng mốc công bố thay thế")
    return Financials(symbol=sym, quarters=quarters, notes=notes,
                      fetched_at=datetime.now().strftime("%Y-%m-%d %H:%M"))


def refresh(symbols: Sequence[str], root: Optional[Path] = None
            ) -> Tuple[int, List[str]]:
    done, errors = 0, []
    for sym in symbols:
        try:
            fin = build(sym)
            if fin.is_empty:
                errors.append(f"{sym}: FireAnt trả rỗng")
                continue
            save(fin, root)
            done += 1
        except Exception as exc:        # noqa: BLE001 — một mã lỗi không giết cả lượt
            errors.append(f"{sym}: {exc}")
    return done, errors


def load_or_build(symbol: str, root: Optional[Path] = None,
                  allow_fetch: bool = True) -> Optional[Financials]:
    fin = load(symbol, root)
    if fin is not None or not allow_fetch:
        return fin
    fin = build(symbol)
    if not fin.is_empty:
        save(fin, root)
    return fin


def _main(argv: Optional[Sequence[str]] = None) -> int:       # pragma: no cover
    """``python -m src.desk.financials [rổ]`` — nạp BCTC quý cho cả rổ.

    Khác ``src.desk.freeze``: kho này **cào lại được**, nên chạy lại chỉ tốn
    thời gian chứ không mất gì. Hai request mỗi mã.
    """
    import sys
    from src.ta.loader import resolve_universe
    args = list(argv if argv is not None else sys.argv[1:])
    symbols = resolve_universe(args[0] if args else None)
    started = datetime.now()
    print(f"[{started:%Y-%m-%d %H:%M}] nạp BCTC quý cho {len(symbols)} mã")
    done, errors = refresh(symbols)
    print(f"  xong {done}/{len(symbols)} mã trong "
          f"{(datetime.now() - started).seconds}s")
    for err in errors:
        print(f"  ⚠️ {err}")
    return 0 if done else 1


if __name__ == "__main__":                                    # pragma: no cover
    raise SystemExit(_main())
