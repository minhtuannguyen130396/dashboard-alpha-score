"""Chuỗi vĩ mô — 9 nhóm, và cái bẫy nhìn trước nặng hơn mọi tầng trước.

`/macro-data/{nhóm}/info` trả mỗi chỉ số kèm chuỗi lịch sử đầy đủ, đơn vị,
nguồn, tần suất và **kỳ công bố kế tiếp**. Chín nhóm: GDP, Prices (CPI), Money
(M0/M1/M2, dự trữ ngoại hối), Trade, Business (PMI), Consumer (niềm tin, bán
lẻ, **giá xăng dầu**), Labour, Taxes, InterestRate (17 chỉ số).

⚠️ **Chuỗi vĩ mô đánh dấu theo KỲ DỮ LIỆU, thị trường biết nó theo NGÀY CÔNG
BỐ.** CPI tháng 8 ra giữa tháng 9. Cắt `historicalValue` bằng `as_of` theo kỳ
là cho một báo cáo ngày 31/08 đọc con số chưa ai biết — và sai lệch đó đi một
chiều: nó làm mọi mô hình trông thông minh hơn thực tế. Nên mỗi chỉ số mang
``lag_days`` theo tần suất, và ``observed_at`` = cuối kỳ + độ trễ là thứ `as_of`
lọc theo.

⚠️ **Số vĩ mô bị sửa lại.** GDP quý được điều chỉnh nhiều tháng sau. Nên vẫn
phải đóng băng như `fundamentals`: mỗi lượt nạp ghi một ảnh chụp theo ngày,
`load` đọc bản ≤ mốc và không rơi về bản mới hơn.

Hai lớp lọc đó độc lập nhau và **cần cả hai**: lớp một chặn "đọc một kỳ chưa
công bố", lớp hai chặn "đọc bản đã sửa của một kỳ đã công bố".
"""
import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from statistics import fmean
from typing import Any, Dict, List, Optional, Sequence, Tuple

from src.news.fireant import get
from src.ta.loader import PROJECT_ROOT

SNAPSHOT_DIR = PROJECT_ROOT / "macro" / "snapshots" / "series"

#: Chín nhóm FireAnt phục vụ. Giữ đúng tên API làm khoá; nhãn tiếng Việt riêng.
TYPES = ("GDP", "Prices", "Business", "Trade", "Labour", "Money",
         "Consumer", "Taxes", "InterestRate")

TYPE_VN = {
    "GDP": "GDP", "Prices": "Giá cả", "Business": "Kinh doanh",
    "Trade": "Thương mại", "Labour": "Lao động", "Money": "Tiền tệ",
    "Consumer": "Tiêu dùng", "Taxes": "Thuế", "InterestRate": "Lãi suất",
}

#: Độ trễ công bố theo tần suất. Đây là **giả định**, viết ra để cãi được:
#: lãi suất liên ngân hàng công bố gần như tức thì, CPI ra đầu tháng sau, GDP
#: quý ra ngay sau quý nhưng bị sửa. Chỗ nào không rõ thì chọn phía trễ hơn —
#: trễ một nhịp làm mô hình yếu đi, nhìn trước một nhịp làm nó *sai*.
LAG_BY_FREQUENCY = {
    "hàng ngày": timedelta(days=1),
    "hàng tuần": timedelta(days=7),
    "hàng tháng": timedelta(days=30),
    "hàng quý": timedelta(days=45),
    "hàng năm": timedelta(days=90),
}
DEFAULT_LAG = timedelta(days=30)

_TAG = re.compile(r"<[^>]+>")


def _strip_html(text: str) -> str:
    return _TAG.sub(" ", str(text or "")).replace("&nbsp;", " ").strip()


def _lag_for(frequency: str) -> timedelta:
    key = (frequency or "").strip().lower()
    for name, lag in LAG_BY_FREQUENCY.items():
        if name in key:
            return lag
    return DEFAULT_LAG


def _end_of_month(year: int, month: int) -> datetime:
    if month >= 12:
        return datetime(year, 12, 31)
    return datetime(year, month + 1, 1) - timedelta(days=1)


def _parse_period(text: Any) -> Optional[datetime]:
    """Ngày **cuối kỳ** của một quan sát. FireAnt dùng bốn dạng khác nhau.

    Đã đối chiếu thật ngày 16/09/2026, mỗi dạng ứng với một tần suất:

        "9/13"        tháng   → 30/09/2013   (nhóm Prices, Consumer, Money…)
        "Q2/17"       quý     → 30/06/2017   (nhóm Labour)
        1986          năm     → 31/12/1986   (nhóm GDP, Taxes)
        "2026-03-16"  ngày    → chính nó     (nhóm InterestRate)

    Lượt viết đầu chỉ đọc dạng đầu tiên, và hậu quả **không** phải một lỗi ném
    ra: bốn nhóm lặng lẽ trả 0 quan sát, trong đó có `InterestRate` — biến nền
    của Ngân hàng, Bất động sản và Bán lẻ. Một nhóm rỗng trông y hệt một nhóm
    FireAnt không có dữ liệu, nên nó sống sót qua cả lượt kiểm tra đầu.

    Trả **cuối kỳ** chứ không đầu kỳ: chỉ số của tháng 8 mô tả cả tháng 8, nên
    sớm nhất nó có thể tồn tại là 31/08.
    """
    if isinstance(text, (int, float)) and not isinstance(text, bool):
        year = int(text)
        return datetime(year, 12, 31) if 1900 <= year <= 2100 else None

    raw = str(text or "").strip()
    if not raw:
        return None

    # "2026-03-16" — ngày đầy đủ
    if len(raw) == 10 and raw[4] == "-" and raw[7] == "-":
        try:
            return datetime.fromisoformat(raw)
        except ValueError:
            return None

    # "1986" — năm trần dưới dạng chuỗi
    if raw.isdigit() and len(raw) == 4:
        year = int(raw)
        return datetime(year, 12, 31) if 1900 <= year <= 2100 else None

    # "Q2/17" — quý
    if raw[:1].upper() == "Q" and "/" in raw:
        head, _, tail = raw.partition("/")
        try:
            quarter, year = int(head[1:]), int(tail)
        except ValueError:
            return None
        if not 1 <= quarter <= 4:
            return None
        return _end_of_month(year + (2000 if year < 100 else 0), quarter * 3)

    # "9/13" — tháng
    parts = raw.split("/")
    if len(parts) != 2:
        return None
    try:
        month, year = int(parts[0]), int(parts[1])
    except ValueError:
        return None
    if not 1 <= month <= 12:
        return None
    return _end_of_month(year + (2000 if year < 100 else 0), month)


@dataclass
class Observation:
    period: str                 # nguyên văn từ API, ví dụ "8/26"
    period_end: str             # ISO, cuối kỳ
    observed_at: str            # ISO, cuối kỳ + độ trễ — mốc `as_of` lọc theo
    value: float


@dataclass
class Indicator:
    """Một chỉ số vĩ mô, kèm mọi thứ cần để đọc nó mà không bịa."""
    id: int
    type: str
    name: str
    name_vn: str
    unit: str = ""
    frequency: str = ""
    source: str = ""
    lag_days: int = 30
    next_release: str = ""
    history: List[Observation] = field(default_factory=list)

    @property
    def label(self) -> str:
        return self.name_vn or self.name

    def known_at(self, as_of: Optional[datetime] = None) -> List[Observation]:
        """Các quan sát **thị trường đã biết** tại mốc."""
        limit = (as_of or datetime.now()).strftime("%Y-%m-%d")
        return [o for o in self.history if o.observed_at <= limit]

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["label"] = self.label
        return d


def _indicator(row: Dict[str, Any]) -> Optional[Indicator]:
    ident = row.get("id")
    if ident is None:
        return None
    freq = str(row.get("frequency") or "")
    lag = _lag_for(freq)
    out = Indicator(
        id=int(ident), type=str(row.get("type") or ""),
        name=str(row.get("name") or ""), name_vn=str(row.get("nameVN") or ""),
        unit=str(row.get("unit") or ""), frequency=freq,
        source=_strip_html(row.get("source") or ""),
        lag_days=lag.days,
        next_release=str(row.get("nextRelease") or "")[:10],
    )
    for item in row.get("historicalValue") or []:
        value = item.get("Value")
        if value is None:
            continue                      # kỳ chưa có số — bỏ, không nội suy
        end = _parse_period(item.get("Date"))
        if end is None:
            continue
        try:
            value = float(value)
        except (TypeError, ValueError):
            continue
        out.history.append(Observation(
            period=str(item.get("Date")),
            period_end=end.strftime("%Y-%m-%d"),
            observed_at=(end + lag).strftime("%Y-%m-%d"),
            value=value))
    out.history.sort(key=lambda o: o.period_end)
    return out


def fetch(kind: str) -> List[Indicator]:
    rows = get(f"/macro-data/{kind}/info") or []
    return [i for i in (_indicator(r) for r in rows) if i]


# ---------------------------------------------------------------------------
# Đóng băng
# ---------------------------------------------------------------------------
def snapshot_path(kind: str, day: datetime,
                  root: Optional[Path] = None) -> Path:
    return ((root or SNAPSHOT_DIR) / kind
            / f"{day.strftime('%Y-%m-%d')}.json")


def save(kind: str, indicators: Sequence[Indicator],
         day: Optional[datetime] = None, root: Optional[Path] = None) -> Path:
    out = snapshot_path(kind, day or datetime.now(), root)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps([i.to_dict() for i in indicators],
                              ensure_ascii=False, indent=1), encoding="utf-8")
    return out


def load(kind: str, as_of: Optional[datetime] = None,
         root: Optional[Path] = None) -> List[Indicator]:
    """Bản đóng băng ≤ mốc. Không có thì rỗng — **không** rơi về bản mới hơn."""
    folder = (root or SNAPSHOT_DIR) / kind
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
        ind = Indicator(
            id=int(r["id"]), type=str(r.get("type") or ""),
            name=str(r.get("name") or ""), name_vn=str(r.get("name_vn") or ""),
            unit=str(r.get("unit") or ""), frequency=str(r.get("frequency") or ""),
            source=str(r.get("source") or ""),
            lag_days=int(r.get("lag_days") or 30),
            next_release=str(r.get("next_release") or ""),
            history=[Observation(**o) for o in r.get("history") or []])
        out.append(ind)
    return out


def find(indicators: Sequence[Indicator], ident: int) -> Optional[Indicator]:
    for i in indicators:
        if i.id == ident:
            return i
    return None


def load_one(ident: int, as_of: Optional[datetime] = None,
             root: Optional[Path] = None) -> Optional[Indicator]:
    """Một chỉ số theo id, dò qua cả 9 nhóm."""
    for kind in TYPES:
        hit = find(load(kind, as_of, root), ident)
        if hit:
            return hit
    return None


# ---------------------------------------------------------------------------
# Đọc trạng thái
# ---------------------------------------------------------------------------
@dataclass
class Reading:
    """Một chỉ số đang ở đâu — luôn kèm ngày *biết được*, không phải ngày kỳ."""
    id: int
    label: str
    unit: str = ""
    frequency: str = ""
    source: str = ""
    period: str = ""
    period_end: str = ""
    observed_at: str = ""
    value: Optional[float] = None
    previous: Optional[float] = None
    year_ago: Optional[float] = None
    percentile: Optional[float] = None
    trend_3: Optional[float] = None       # độ dốc 3 kỳ gần nhất
    next_release: str = ""
    stale_days: Optional[int] = None
    note: str = ""

    @property
    def change(self) -> Optional[float]:
        if self.value is None or self.previous is None:
            return None
        return self.value - self.previous

    @property
    def stale(self) -> bool:
        """Số này đã cũ hơn mức bình thường của chính tần suất nó chưa.

        Phải so với tần suất chứ không so với một mốc chung: 45 ngày là bình
        thường với một chỉ số hàng quý và là **rất cũ** với một chỉ số hàng
        ngày. Đã gặp thật — lãi suất liên ngân hàng (hàng ngày) của FireAnt
        dừng ở 16/06/2026, tức **ba tháng** không cập nhật, mà bảng vẫn in nó
        cạnh những con số tươi mà không có dấu hiệu gì. Một số cũ trông y hệt
        một số mới là đúng kiểu sai tệ nhất, vì không ai phát hiện được.
        """
        if self.stale_days is None:
            return False
        return self.stale_days > _stale_limit(self.frequency)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["change"] = self.change
        d["stale"] = self.stale
        return d


#: Bao nhiêu ngày thì một chỉ số của tần suất này coi là **quá hạn**. Rộng gấp
#: ~3 lần chu kỳ tự nhiên cộng độ trễ công bố — đủ chỗ cho một kỳ ra muộn mà
#: không bỏ qua một chuỗi đã ngừng cập nhật.
STALE_LIMIT = {
    "hàng ngày": 10,
    "hàng tuần": 30,
    "hàng tháng": 100,
    "hàng quý": 200,
    "hàng năm": 550,
}
DEFAULT_STALE_LIMIT = 120


def _stale_limit(frequency: str) -> int:
    key = (frequency or "").strip().lower()
    for name, limit in STALE_LIMIT.items():
        if name in key:
            return limit
    return DEFAULT_STALE_LIMIT


def read(indicator: Indicator, as_of: Optional[datetime] = None) -> Reading:
    day = as_of or datetime.now()
    out = Reading(id=indicator.id, label=indicator.label, unit=indicator.unit,
                  frequency=indicator.frequency, source=indicator.source,
                  next_release=indicator.next_release)
    known = indicator.known_at(day)
    if not known:
        out.note = ("chưa có kỳ nào công bố trước mốc này — *chưa đo được*, "
                    "không phải *đi ngang*")
        return out
    last = known[-1]
    out.period, out.period_end = last.period, last.period_end
    out.observed_at, out.value = last.observed_at, last.value
    if len(known) > 1:
        out.previous = known[-2].value

    target = last.period_end[5:]
    year = int(last.period_end[:4]) - 1
    for o in known:
        if o.period_end[:4] == str(year) and o.period_end[5:7] == target[:2]:
            out.year_ago = o.value
            break

    vals = [o.value for o in known]
    if len(vals) >= 8:
        out.percentile = sum(1 for v in vals if v < last.value) / len(vals)
    if len(vals) >= 3:
        recent = vals[-3:]
        out.trend_3 = round((recent[-1] - recent[0]) / 2.0, 4)

    try:
        out.stale_days = (day - datetime.fromisoformat(last.observed_at)).days
    except ValueError:
        out.stale_days = None
    return out


def update(types: Sequence[str] = TYPES, day: Optional[datetime] = None,
           root: Optional[Path] = None) -> List[Tuple[str, int, str]]:
    out = []
    for kind in types:
        try:
            items = fetch(kind)
        except Exception as exc:                          # noqa: BLE001
            out.append((kind, 0, f"{type(exc).__name__}: {exc}"))
            continue
        if items:
            save(kind, items, day, root)
        n_obs = sum(len(i.history) for i in items)
        out.append((kind, len(items), f"{n_obs} quan sát"))
    return out


def _main() -> None:
    import argparse
    ap = argparse.ArgumentParser(description="Đóng băng chuỗi vĩ mô theo ngày")
    ap.add_argument("--types", default="")
    args = ap.parse_args()
    kinds = [t for t in args.types.split(",") if t.strip()] or list(TYPES)

    print("| Nhóm | Chỉ số | Ghi chú |")
    print("|---|---:|---|")
    for kind, n, note in update(kinds):
        print(f"| {TYPE_VN.get(kind, kind)} (`{kind}`) | {n} | {note} |")
    print()
    print("Mỗi lượt chạy đóng băng một ngày. Chuỗi vĩ mô bị sửa lại sau khi "
          "công bố, nên bản của hôm nay không thay được bản của hôm qua.")


if __name__ == "__main__":
    _main()
