"""BCTC cấp ngành theo quý — nền tảng, và bẫy nhìn trước đi kèm.

`/icb/{mã}/financial-data?type=quarterly` trả 82 chỉ tiêu mỗi quý, lùi tới
2016 Q3. Đây là thứ `update_fundamentals` ở tầng mã **không** có: bản kia là
snapshot hôm nay, không có chuỗi. Ở cấp ngành thì có chuỗi quý thật, nên câu
"biên lợi nhuận ngành cải thiện quý thứ ba liên tiếp" là phát biểu **kiểm
chứng được**, không phải cảm nhận.

⚠️ **Hai bẫy nhìn trước, và chúng khác nhau.**

1. **Độ trễ công bố.** Quý 2 kết thúc 30/06 nhưng BCTC ra cuối tháng 7. Gắn số
   quý 2 vào ngày 01/07 là cho báo cáo đọc một con số chưa ai biết. `PUBLISH_LAG`
   đẩy mỗi quý sang ngày *có thể biết được*, và `as_of` lọc theo ngày đó chứ
   không theo ngày kết thúc quý. Con số 45 ngày là **giả định**, ghi ra ở đây để
   cãi được: quy định Việt Nam cho phép 20 ngày (30 nếu có công ty con) sau quý,
   nhưng ngành là phép gộp nên nó chỉ đầy đủ khi *mã cuối cùng* đã nộp.

2. **Số bị sửa lại.** FireAnt trả giá trị *hôm nay* của quý 2/2024 — có thể đã
   khác bản công bố lần đầu. Không đóng băng thì một báo cáo hồi tưởng về 2024
   đọc con số của bản sửa. Nên mỗi lượt nạp ghi `macro/snapshots/<mã>/<ngày>.json`
   và `load` chỉ đọc bản **≤ mốc**, trả `None` chứ không rơi về bản mới hơn —
   đúng cách `src/ta/fundamentals.py` đã làm cho tầng mã.
"""
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from statistics import fmean
from typing import Any, Dict, List, Optional, Sequence, Tuple

from src.news.fireant import get
from src.ta.loader import PROJECT_ROOT

SNAPSHOT_DIR = PROJECT_ROOT / "macro" / "snapshots" / "fundamentals"

#: Ngày sau khi quý kết thúc thì số của quý đó coi như thị trường đã biết.
#: Quy định cho phép 20 ngày (30 nếu có công ty con); lấy 45 vì ngành chỉ đầy đủ
#: khi mã cuối cùng đã nộp, và thà trễ một nhịp còn hơn nhìn trước một nhịp.
PUBLISH_LAG = timedelta(days=45)

#: Số quý nạp mặc định — 40 quý là hết chuỗi FireAnt có (2016 Q3 → nay).
DEFAULT_COUNT = 40

#: Chỉ tiêu dùng cho trụ B. Không nạp cả 82 trường vào phân tích: phần lớn là
#: số tuyệt đối của bảng cân đối, và một "tổng tài sản ngành" không so được với
#: ngành khác lẫn với chính nó qua thời gian có lạm phát.
PROFIT_FIELDS = ("ROE", "ROA", "ROS", "GrossMargin", "EBITMargin",
                 "OperatingMargin", "ROIC")
GROWTH_FIELDS = ("EPSGrowth_TTM", "ProfitGrowth_TTM", "SaleGrowth_TTM",
                 "ProfitAfterTaxGrowth_TTM")
VALUATION_FIELDS = ("PE", "PB", "PS", "EVOverEBITDA")
LEVERAGE_FIELDS = ("TotalDebtOverEquity", "InterestCoverageRatio",
                   "CurrentRatio", "QuickRatio")

FIELD_VN = {
    "ROE": "ROE", "ROA": "ROA", "ROS": "Biên lãi ròng",
    "GrossMargin": "Biên gộp", "EBITMargin": "Biên EBIT",
    "OperatingMargin": "Biên hoạt động", "ROIC": "ROIC",
    "EPSGrowth_TTM": "Tăng trưởng EPS (TTM)",
    "ProfitGrowth_TTM": "Tăng trưởng lợi nhuận (TTM)",
    "SaleGrowth_TTM": "Tăng trưởng doanh thu (TTM)",
    "ProfitAfterTaxGrowth_TTM": "Tăng trưởng LNST (TTM)",
    "PE": "P/E", "PB": "P/B", "PS": "P/S", "EVOverEBITDA": "EV/EBITDA",
    "TotalDebtOverEquity": "Nợ/VCSH",
    "InterestCoverageRatio": "Khả năng trả lãi",
    "CurrentRatio": "Thanh toán hiện hành", "QuickRatio": "Thanh toán nhanh",
}


# ---------------------------------------------------------------------------
@dataclass
class Quarter:
    """Một quý của một ngành."""
    code: str
    year: int
    quarter: int
    values: Dict[str, float] = field(default_factory=dict)

    @property
    def key(self) -> str:
        return f"{self.year}Q{self.quarter}"

    @property
    def period_end(self) -> datetime:
        """Ngày cuối quý — **không** phải ngày thị trường biết số này."""
        month = min(12, self.quarter * 3)
        if month == 12:
            return datetime(self.year, 12, 31)
        return datetime(self.year, month + 1, 1) - timedelta(days=1)

    @property
    def known_from(self) -> datetime:
        """Ngày sớm nhất được phép dùng con số này. Xem ``PUBLISH_LAG``."""
        return self.period_end + PUBLISH_LAG

    def get(self, name: str) -> Optional[float]:
        v = self.values.get(name)
        return None if v is None else float(v)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["key"] = self.key
        d["period_end"] = self.period_end.strftime("%Y-%m-%d")
        d["known_from"] = self.known_from.strftime("%Y-%m-%d")
        return d


def _num(v: Any) -> Optional[float]:
    if v is None or isinstance(v, bool):
        return None
    try:
        out = float(v)
    except (TypeError, ValueError):
        return None
    return out if out == out else None


def fetch(code: str, count: int = DEFAULT_COUNT,
          kind: str = "quarterly") -> List[Quarter]:
    """Chuỗi quý của một ngành, **cũ → mới**."""
    rows = get(f"/icb/{code}/financial-data",
               {"type": kind, "count": count}) or []
    out: List[Quarter] = []
    for row in rows:
        year, quarter = row.get("year"), row.get("quarter")
        if not year:
            continue
        raw = row.get("financialValues") or {}
        vals = {k: _num(v) for k, v in raw.items()}
        vals = {k: v for k, v in vals.items() if v is not None}
        out.append(Quarter(code=str(code), year=int(year),
                           quarter=int(quarter or 0), values=vals))
    out.sort(key=lambda q: (q.year, q.quarter))
    return out


# ---------------------------------------------------------------------------
# Đóng băng theo ngày
# ---------------------------------------------------------------------------
def snapshot_path(code: str, day: datetime,
                  root: Optional[Path] = None) -> Path:
    return ((root or SNAPSHOT_DIR) / str(code)
            / f"{day.strftime('%Y-%m-%d')}.json")


def save(code: str, quarters: Sequence[Quarter],
         day: Optional[datetime] = None,
         root: Optional[Path] = None) -> Path:
    out = snapshot_path(code, day or datetime.now(), root)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps([q.to_dict() for q in quarters],
                              ensure_ascii=False, indent=1), encoding="utf-8")
    return out


def load(code: str, as_of: Optional[datetime] = None,
         root: Optional[Path] = None) -> List[Quarter]:
    """Chuỗi quý **đã biết được** tại ``as_of``.

    Hai lần lọc, và cả hai đều cần:

    1. Bản đóng băng: lấy file có ngày ≤ mốc, mới nhất trong số đó. Không có
       bản nào ≤ mốc thì trả rỗng — **không** rơi về bản mới hơn, vì bản mới
       hơn chứa số đã sửa lại mà ngày đó chưa ai thấy.
    2. Độ trễ công bố: trong bản đó, bỏ mọi quý có ``known_from`` > mốc.
    """
    folder = (root or SNAPSHOT_DIR) / str(code)
    if not folder.is_dir():
        return []
    limit = (as_of or datetime.now()).strftime("%Y-%m-%d")
    files = sorted(f for f in folder.glob("*.json") if f.stem <= limit)
    if not files:
        return []
    try:
        rows = json.loads(files[-1].read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    out = []
    for r in rows:
        q = Quarter(code=str(r.get("code") or code), year=int(r["year"]),
                    quarter=int(r.get("quarter") or 0),
                    values=dict(r.get("values") or {}))
        if q.known_from.strftime("%Y-%m-%d") <= limit:
            out.append(q)
    out.sort(key=lambda q: (q.year, q.quarter))
    return out


# ---------------------------------------------------------------------------
# Đọc trạng thái
# ---------------------------------------------------------------------------
@dataclass
class Metric:
    """Một chỉ tiêu: giá trị mới nhất, xu hướng, và vị trí trong lịch sử."""
    name: str
    label: str
    latest: Optional[float] = None
    previous: Optional[float] = None
    year_ago: Optional[float] = None
    slope: Optional[float] = None        # dấu + độ dốc trên 4 quý gần nhất
    percentile: Optional[float] = None   # vị trí trong chính lịch sử ngành
    n: int = 0

    @property
    def improving(self) -> Optional[bool]:
        return None if self.slope is None else self.slope > 0

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["improving"] = self.improving
        return d


def _slope(values: Sequence[float]) -> Optional[float]:
    """Độ dốc hồi quy tuyến tính đơn giản — dấu của nó mới là thứ dùng tới.

    Dùng **dấu và độ dốc**, không dùng mức: ROE 18% của Năng lượng và 12% của
    Bán lẻ không so nhau được, nhưng "đang tăng" và "đang giảm" thì so được.
    """
    n = len(values)
    if n < 3:
        return None
    xs = list(range(n))
    mx, my = fmean(xs), fmean(values)
    den = sum((x - mx) ** 2 for x in xs)
    if den == 0:
        return None
    return sum((x - mx) * (y - my) for x, y in zip(xs, values)) / den


def _percentile(values: Sequence[float], value: float) -> Optional[float]:
    if len(values) < 8:
        return None
    below = sum(1 for v in values if v < value)
    return below / len(values)


def metric(quarters: Sequence[Quarter], name: str,
           window: int = 4) -> Metric:
    """Một chỉ tiêu đọc trên chuỗi quý đã lọc theo ``as_of``."""
    out = Metric(name=name, label=FIELD_VN.get(name, name))
    series = [(q, q.get(name)) for q in quarters]
    vals = [(q, v) for q, v in series if v is not None]
    out.n = len(vals)
    if not vals:
        return out
    out.latest = vals[-1][1]
    if len(vals) > 1:
        out.previous = vals[-2][1]
    key = (vals[-1][0].year - 1, vals[-1][0].quarter)
    for q, v in vals:
        if (q.year, q.quarter) == key:
            out.year_ago = v
            break
    recent = [v for _, v in vals[-window:]]
    out.slope = _slope(recent)
    out.percentile = _percentile([v for _, v in vals], out.latest)
    return out


@dataclass
class SectorFundamentals:
    """Nền tảng của một ngành tại một mốc — hoặc lời giải thích vì sao trống."""
    code: str
    as_of: str = ""
    latest_quarter: str = ""
    quarters: int = 0
    profit: List[Metric] = field(default_factory=list)
    growth: List[Metric] = field(default_factory=list)
    valuation: List[Metric] = field(default_factory=list)
    leverage: List[Metric] = field(default_factory=list)
    note: str = ""

    @property
    def measured(self) -> bool:
        return self.quarters > 0

    def find(self, name: str) -> Optional[Metric]:
        for group in (self.profit, self.growth, self.valuation, self.leverage):
            for m in group:
                if m.name == name:
                    return m
        return None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "code": self.code, "as_of": self.as_of,
            "latest_quarter": self.latest_quarter, "quarters": self.quarters,
            "profit": [m.to_dict() for m in self.profit],
            "growth": [m.to_dict() for m in self.growth],
            "valuation": [m.to_dict() for m in self.valuation],
            "leverage": [m.to_dict() for m in self.leverage],
            "note": self.note, "measured": self.measured,
        }


def build(code: str, as_of: Optional[datetime] = None,
          root: Optional[Path] = None) -> SectorFundamentals:
    day = as_of or datetime.now()
    out = SectorFundamentals(code=str(code), as_of=day.strftime("%Y-%m-%d"))
    quarters = load(code, as_of=day, root=root)
    if not quarters:
        out.note = ("chưa có bản đóng băng nào ≤ mốc này — chạy "
                    "`python -m src.macro.fundamentals`. Đây là *chưa đo được*, "
                    "không phải *ngành không có số*.")
        return out
    out.quarters = len(quarters)
    out.latest_quarter = quarters[-1].key
    out.profit = [metric(quarters, f) for f in PROFIT_FIELDS]
    out.growth = [metric(quarters, f) for f in GROWTH_FIELDS]
    out.valuation = [metric(quarters, f) for f in VALUATION_FIELDS]
    out.leverage = [metric(quarters, f) for f in LEVERAGE_FIELDS]
    return out


def update(codes: Sequence[str], count: int = DEFAULT_COUNT,
           day: Optional[datetime] = None,
           root: Optional[Path] = None) -> List[Tuple[str, int, str]]:
    """Nạp và **đóng băng** BCTC ngành cho hôm nay.

    Như `update_fundamentals` ở tầng mã: ngày nào không chạy là ngày đó mất
    vĩnh viễn — không nguồn nào bán lại một ảnh chụp của quá khứ.
    """
    out = []
    for code in codes:
        try:
            quarters = fetch(code, count)
        except Exception as exc:                          # noqa: BLE001
            out.append((str(code), 0, f"{type(exc).__name__}: {exc}"))
            continue
        if quarters:
            save(code, quarters, day, root)
        out.append((str(code), len(quarters),
                    quarters[-1].key if quarters else "—"))
    return out


def _main() -> None:
    import argparse
    from src.macro import icb

    ap = argparse.ArgumentParser(description="Đóng băng BCTC ngành theo quý")
    ap.add_argument("--codes", default="")
    ap.add_argument("--count", type=int, default=DEFAULT_COUNT)
    args = ap.parse_args()

    tree = icb.fetch_tree()
    codes = ([c for c in args.codes.split(",") if c.strip()]
             or icb.distinct_codes(tree))
    names = {i.code: i.name for i in tree}

    print("| Mã | Ngành | Quý nạp được | Quý mới nhất |")
    print("|---|---|---:|---|")
    for code, n, last in update(codes, args.count):
        print(f"| `{code}` | {names.get(code, '')} | {n} | {last} |")
    print()
    print("Mỗi lượt chạy đóng băng một ngày. Ngày không chạy là ngày mất vĩnh viễn.")


if __name__ == "__main__":
    _main()
