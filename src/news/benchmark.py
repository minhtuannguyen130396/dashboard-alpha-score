"""Dựng chỉ số đối chứng **đều tay** (equal-weight) từ chính dữ liệu giá đã có.

Vì sao cần thêm một benchmark khi đã có VNINDEX: VNINDEX là chỉ số **trọng số vốn
hoá**, nên nó gần với "vài mã lớn nhất đang làm gì" hơn là "một cổ phiếu trung
bình đang làm gì". Đo được: chạy event study trên **ngày ngẫu nhiên** với
benchmark VNINDEX cho trung vị abnormal return **−0,29%**, không phải 0. Một mã
bất kỳ, một ngày bất kỳ, "kém thị trường" một cách máy móc.

Cái đang đo lại là 79 mã riêng lẻ, mỗi giao dịch nội bộ một quan sát, không phân
biệt lớn nhỏ. So một rổ đều tay với một chỉ số bị vài mã lớn chi phối là so lệch
đơn vị, và phần lệch đó chui thẳng vào mọi con số abnormal return.

Chỉ số này trả lời đúng câu cần hỏi: *"so với một cổ phiếu trung bình thì mã này
đi thế nào"*.

**Không thay VNINDEX.** VNINDEX vẫn là mẫu số đúng cho câu "mã này mạnh hay yếu
hơn thị trường" — đúng vai mà ``CLAUDE.md`` giao cho nó. Hai chỉ số trả lời hai
câu khác nhau, và khi chúng lệch nhau nhiều thì **chính chỗ lệch là thông tin**:
nghĩa là nhóm vốn hoá lớn đang chạy khác phần còn lại của thị trường.

Ghi ra đúng schema FireAnt trong ``data/_PROXY_EW/`` để ``loader.load_prices``
đọc được mà không phải sửa một dòng nào ở tầng dưới.
"""
import json
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from src.data.stock_data_loader import StockRecord
from src.ta.loader import DATA_DIR, load_prices, resolve_universe

#: Mã của chỉ số đối chứng. Gạch dưới ở đầu để không bao giờ bị nhầm là cổ phiếu.
PROXY_SYMBOL = "_PROXY_EW"

#: Mức khởi điểm của chỉ số. Con số tuỳ ý — chỉ tỷ lệ thay đổi mới có nghĩa.
BASE_LEVEL = 1000.0

#: Số mã tối thiểu phải có mặt trong một phiên thì phiên đó mới được tính.
#: Những năm đầu chỉ vài mã niêm yết; trung bình của 3 mã không phải "thị trường",
#: nó là nhiễu của 3 mã đó.
MIN_MEMBERS = 20


@dataclass
class ProxyBuild:
    symbol: str
    sessions: int = 0
    first_date: Optional[str] = None
    last_date: Optional[str] = None
    members_min: int = 0
    members_max: int = 0
    skipped_thin: int = 0        # phiên bị bỏ vì quá ít mã
    files_written: int = 0


def daily_returns(symbols: Sequence[str], start: datetime, end: datetime
                  ) -> Dict[datetime, List[float]]:
    """Gom lợi suất từng phiên của từng mã, khoá theo ngày.

    Mã nào chưa niêm yết ở phiên đó thì đơn giản là không có mặt — đúng như thực
    tế, và **không** phải là chỗ để nội suy. Đây cũng là lý do phải đếm số thành
    viên mỗi phiên rồi bỏ những phiên quá mỏng.
    """
    by_day: Dict[datetime, List[float]] = defaultdict(list)
    for sym in symbols:
        recs = load_prices(sym, start, end)
        for prev, cur in zip(recs, recs[1:]):
            if prev.priceClose and cur.priceClose:
                by_day[cur.date].append(cur.priceClose / prev.priceClose - 1.0)
    return by_day


def build_series(symbols: Sequence[str], start: datetime, end: datetime,
                 min_members: int = MIN_MEMBERS
                 ) -> Tuple[List[Tuple[datetime, float, int, float]], int]:
    """Chuỗi ``(ngày, mức chỉ số, số thành viên, lợi suất phiên)``.

    Chỉ số dựng bằng cách **cộng dồn lợi suất trung bình từng phiên**, không phải
    trung bình giá. Trung bình giá thì một mã giá 200 nghìn lấn át một mã giá 8
    nghìn, tức lại thành trọng số theo giá — đúng thứ đang muốn tránh.
    """
    by_day = daily_returns(symbols, start, end)
    level = BASE_LEVEL
    out: List[Tuple[datetime, float, int, float]] = []
    skipped = 0
    for day in sorted(by_day):
        rets = by_day[day]
        if len(rets) < min_members:
            skipped += 1
            continue
        r = sum(rets) / len(rets)
        level *= (1.0 + r)
        out.append((day, level, len(rets), r))
    return out, skipped


def _record_json(day: datetime, level: float, prev_level: float,
                 members: int) -> dict:
    """Một phiên của chỉ số, viết đúng schema thô mà ``record_from_json`` đọc.

    ``adjRatio = 1.0`` vì chỉ số không chia tách. Các trường OHLC đều bằng mức
    đóng cửa: chỉ số này **không có dữ liệu trong phiên**, và bịa ra một biên độ
    giả còn tệ hơn là để phẳng. ``priceBasic`` là mức phiên trước, đúng nghĩa
    "giá tham chiếu".
    """
    return {
        "date": day.isoformat(),
        "symbol": PROXY_SYMBOL,
        "priceHigh": level, "priceLow": level, "priceOpen": level,
        "priceAverage": level, "priceClose": level, "priceBasic": prev_level,
        "totalVolume": float(members), "dealVolume": float(members),
        "putthroughVolume": 0.0,
        "totalValue": 0.0, "putthroughValue": 0.0,
        "buyForeignQuantity": 0.0, "buyForeignValue": 0.0,
        "sellForeignQuantity": 0.0, "sellForeignValue": 0.0,
        "buyCount": 0.0, "buyQuantity": 0.0,
        "sellCount": 0.0, "sellQuantity": 0.0,
        "adjRatio": 1.0, "currentForeignRoom": 0.0,
        "propTradingNetDealValue": 0.0, "propTradingNetPTValue": 0.0,
        "propTradingNetValue": 0.0, "unit": 1000.0,
    }


def write_proxy(series: Sequence[Tuple[datetime, float, int, float]],
                data_dir: Optional[Path] = None) -> int:
    """Ghi chuỗi ra ``data/_PROXY_EW/<năm>/<năm>-<tháng>-01.json``.

    Cùng bố cục file với mọi mã khác, nên ``loader._load_year`` và cơ chế cache
    theo chữ ký file dùng lại được nguyên vẹn.
    """
    root = (data_dir or DATA_DIR) / PROXY_SYMBOL
    months: Dict[Tuple[int, int], List[dict]] = defaultdict(list)
    prev = BASE_LEVEL
    for day, level, members, _ in series:
        months[(day.year, day.month)].append(
            _record_json(day, level, prev, members))
        prev = level
    for (year, month), items in sorted(months.items()):
        folder = root / str(year)
        folder.mkdir(parents=True, exist_ok=True)
        (folder / f"{year}-{month:02d}-01.json").write_text(
            json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    return len(months)


def build(symbols: Optional[Sequence[str]] = None,
          start: Optional[datetime] = None, end: Optional[datetime] = None,
          min_members: int = MIN_MEMBERS,
          data_dir: Optional[Path] = None) -> ProxyBuild:
    """Dựng và ghi chỉ số đối chứng. Trả về tóm tắt để soi lại.

    ⚠️ **Hạn chế phải nói thẳng: có survivorship bias.** ``data/`` chỉ chứa những
    mã còn trong rổ *hôm nay*; mã đã huỷ niêm yết hoặc rơi khỏi danh sách theo
    dõi thì không có mặt ở bất kỳ phiên nào trong quá khứ. Nên chỉ số này hơi
    lạc quan so với một rổ đều tay thật. Nó vẫn là mẫu số đúng hơn VNINDEX cho
    việc đang làm — nhưng "đúng hơn" không phải "sạch".
    """
    syms = list(symbols) if symbols else resolve_universe("all")
    start = start or datetime(2010, 1, 1)
    end = end or datetime.now()

    series, skipped = build_series(syms, start, end, min_members)
    out = ProxyBuild(symbol=PROXY_SYMBOL, sessions=len(series),
                     skipped_thin=skipped)
    if series:
        out.first_date = series[0][0].strftime("%Y-%m-%d")
        out.last_date = series[-1][0].strftime("%Y-%m-%d")
        counts = [m for _, _, m, _ in series]
        out.members_min, out.members_max = min(counts), max(counts)
        out.files_written = write_proxy(series, data_dir)
    return out
