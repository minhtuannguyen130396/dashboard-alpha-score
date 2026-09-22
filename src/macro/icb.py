"""Chỉ số ngành ICB — nạp về ``data/_ICB_<mã>/`` theo đúng schema giá.

Quyết định kiến trúc lớn nhất của cả tầng vĩ mô, và nó không phải quyết định
mới: ``src/news/benchmark.py`` đã lập tiền lệ khi ghi ``_PROXY_EW`` ra đĩa bằng
**đúng schema FireAnt**, nên ``loader.load_prices`` đọc được mà không sửa một
dòng nào ở tầng dưới. Làm y hệt cho ngành thì đổi lại được toàn bộ ``src/ta/``
chạy trên ngành, miễn phí: EMA, RSI, ADX, chuỗi swing HH/HL, hộp tích luỹ,
trendline, nến tuần. "Ngành Năng lượng vừa phá hộp tích luỹ 8 tuần bằng volume
1,9×" trở thành một câu **đã có sẵn code để nói**.

Cái bẫy đi kèm giống hệt VNINDEX, một nấc gắt hơn vì có tới 31 chỉ số chứ không
phải một: để yên thì ``resolve_universe(None)`` phát chúng ra cho mọi lần quét,
và "ngành Năng lượng" hiện thành một dòng đứng cạnh từng cổ phiếu. Sai hai
đường — không ai *mua* được ngành, và nến của nó là bình quân nên ADX/RSI mượt
hơn mọi thành phần, làm lệch âm thầm mọi phân vị trong ``ranking.py``. Vì thế
registry riêng ``stock_list/sectors.json`` + tiền tố ``_ICB_``, và
``loader.py`` loại khỏi **mọi nhóm**.

⚠️ **Chỉ số ngành KHÔNG dựng từ ``data/``.** Nó chạy theo toàn bộ thành viên
ngành trên cả ba sàn, kể cả mã ta không có và không định mua. Đó là điều đúng —
nó mới thật sự là "ngành" — nhưng mọi báo cáo phải nói ra, nếu không người đọc
sẽ tưởng "Năng lượng +9,2%" là điều gì đó về BSR/PLX/PVD/PVT.
"""
import argparse
import json
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from src.news.fireant import get
from src.ta.loader import DATA_DIR, STOCK_LIST_DIR

#: Tiền tố thư mục dữ liệu. Gạch dưới ở đầu để không bao giờ bị nhầm là mã cổ
#: phiếu, cùng quy ước với ``_PROXY_EW``.
SECTOR_PREFIX = "_ICB_"

#: Registry — ``loader.py`` đọc file này để loại chỉ số ngành khỏi mọi nhóm.
SECTOR_FILE = "sectors.json"

#: Cấp ngành được nạp. Cấp 1 (11 ngành) là bảng chính; cấp 2 (20 nhóm) để khoan
#: xuống — Ngân hàng, Dịch vụ tài chính và Bảo hiểm chạy rất khác nhau nên gộp
#: cả ba vào "Tài chính" là mất đúng phần thông tin đáng xem. Cấp 3–4 thì nhiều
#: nhóm chỉ có một hai mã niêm yết, chỉ số của chúng là nhiễu của vài mã đó.
LEVELS = (1, 2)

#: FireAnt trả cây ngành từ 2015 với mã `60`; các ngành khác chưa chắc đủ dài.
#: Xin sớm hơn không hại gì — API tự cắt ở phiên đầu tiên nó có.
HISTORY_START = "2010-01-01"

#: Dưới ngưỡng này thì chuỗi quá ngắn để chạy bất kỳ chỉ báo nào (EMA50 cần 50,
#: ADX14 cần ~28, phân vị 250 phiên cần 250). Ngành như vậy vẫn ghi ra đĩa
#: nhưng ``survey`` đánh dấu để không ai lỡ đọc nó như một chuỗi đầy đủ.
MIN_SESSIONS = 250


def sector_symbol(code: str) -> str:
    """``"60"`` → ``"_ICB_60"``."""
    return f"{SECTOR_PREFIX}{str(code).strip()}"


def sector_code(symbol: str) -> Optional[str]:
    """``"_ICB_60"`` → ``"60"``; mã cổ phiếu thì trả ``None``."""
    text = str(symbol).strip().upper()
    if not text.startswith(SECTOR_PREFIX):
        return None
    return text[len(SECTOR_PREFIX):] or None


def is_sector(symbol: str) -> bool:
    return sector_code(symbol) is not None


# ---------------------------------------------------------------------------
# Cây ngành
# ---------------------------------------------------------------------------
@dataclass
class Industry:
    """Một nút trong cây ICB."""
    code: str
    level: int
    name: str
    parent: Optional[str] = None

    @property
    def symbol(self) -> str:
        return sector_symbol(self.code)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _parent_code(code: str) -> Optional[str]:
    """Mã cha trong ICB là chính nó cắt bớt 2 chữ số cuối."""
    return code[:-2] if len(code) > 2 else None


def fetch_tree(levels: Sequence[int] = LEVELS) -> List[Industry]:
    """Cây ngành ICB, lọc theo cấp.

    ``/icb`` trả 250 dòng cả 4 cấp; cấp 3–4 chia nhỏ tới mức nhiều nhóm chỉ có
    một hai mã niêm yết, nên mặc định chỉ lấy cấp 1–2 (§LEVELS).
    """
    rows = get("/icb") or []
    want = set(levels)
    out: List[Industry] = []
    for row in rows:
        try:
            level = int(row.get("level") or 0)
        except (TypeError, ValueError):
            continue
        code = str(row.get("industryCode") or "").strip()
        if level not in want or not code:
            continue
        out.append(Industry(code=code, level=level,
                            name=str(row.get("name") or "").strip(),
                            parent=_parent_code(code) if level > 1 else None))
    out.sort(key=lambda i: (i.level, i.code))
    return out


# ---------------------------------------------------------------------------
# Chuỗi chỉ số → schema giá
# ---------------------------------------------------------------------------
def _num(value: Any) -> float:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return 0.0
    return out if out == out else 0.0     # NaN → 0


def _record_json(code: str, row: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Một phiên của chỉ số ngành, viết đúng schema thô ``record_from_json`` đọc.

    Ba chỗ cần giải thích, vì cả ba đều là lựa chọn chứ không phải ánh xạ hiển
    nhiên:

    * ``adjRatio = 1.0`` — chỉ số không chia tách, y hệt VNINDEX.
    * ``priceAverage = IndexClose`` — API không trả giá bình quân cho ngành.
      Đây **không** phải bịa: chính FireAnt trả VNINDEX với
      ``priceAverage == priceClose``, nên ta theo đúng quy ước của nguồn thay
      vì tự chế một VWAP không có dữ liệu để tính.
    * ``unit = 1.0`` — điểm chỉ số, không phải nghìn đồng. Để 1000 như cổ phiếu
      là mọi chỗ hiển thị giá sẽ nhân sai 1000 lần.

    Các trường **riêng của ngành** (dòng tiền chủ động, PE/PB, vốn hoá) giữ
    nguyên trong cùng bản ghi: ``record_from_json`` đọc theo khoá cố định nên
    khoá lạ bị bỏ qua vô hại, và vứt chúng đi thì phải nạp lại cả chuỗi mới có.
    """
    values = row.get("indexValues") or {}
    close = _num(values.get("IndexClose"))
    if close <= 0:
        return None                      # phiên rỗng — API có trả vài cái
    raw_date = str(row.get("date") or "")
    if not raw_date:
        return None
    volume = _num(values.get("Volume"))
    return {
        "date": raw_date,
        "symbol": sector_symbol(code),
        "priceOpen": _num(values.get("IndexOpen")) or close,
        "priceHigh": _num(values.get("IndexHigh")) or close,
        "priceLow": _num(values.get("IndexLow")) or close,
        "priceClose": close,
        "priceAverage": close,
        "priceBasic": _num(values.get("IndexPrev")) or close,
        # priceImpactVolume = dealVolume (quy ước của repo). Ngành không tách
        # được thoả thuận khỏi khớp lệnh, nên hai con số bằng nhau và
        # putthrough để 0 — trả 0 đúng hơn là chia bừa.
        "totalVolume": volume,
        "dealVolume": volume,
        "putthroughVolume": 0.0,
        "totalValue": _num(values.get("Value")),
        "putthroughValue": 0.0,
        "buyForeignQuantity": _num(values.get("BuyForeignQuantity")),
        "buyForeignValue": _num(values.get("BuyForeignValue")),
        "sellForeignQuantity": _num(values.get("SellForeignQuantity")),
        "sellForeignValue": _num(values.get("SellForeignValue")),
        "buyCount": 0.0,
        "buyQuantity": _num(values.get("BuyQuantity")),
        "sellCount": 0.0,
        "sellQuantity": _num(values.get("SellQuantity")),
        "adjRatio": 1.0,
        "currentForeignRoom": 0.0,
        "propTradingNetDealValue": None,
        "propTradingNetPTValue": None,
        "propTradingNetValue": None,
        "unit": 1.0,
        # --- riêng của ngành, StockRecord không có chỗ chứa ---
        "icbPositiveMoneyFlow": _num(values.get("PositiveMoneyFlow")),
        "icbNegativeMoneyFlow": _num(values.get("NegativeMoneyFlow")),
        "icbNeutralMoneyFlow": _num(values.get("NeutralMoneyFlow")),
        "icbPE": _num(values.get("PE")),
        "icbPB": _num(values.get("PB")),
        "icbPS": _num(values.get("PS")),
        "icbMarketCap": _num(values.get("MarketCap")),
    }


def fetch_index(code: str, start: str = HISTORY_START,
                end: Optional[str] = None) -> List[Dict[str, Any]]:
    """Chuỗi phiên của một ngành, đã chuyển sang schema giá và sắp theo ngày."""
    end = end or datetime.now().strftime("%Y-%m-%d")
    rows = get(f"/icb/{code}/historical-index",
               {"startDate": start, "endDate": end}) or []
    out = [r for r in (_record_json(code, row) for row in rows) if r]
    out.sort(key=lambda r: r["date"])
    return out


def write_index(code: str, records: Sequence[Dict[str, Any]],
                data_dir: Optional[Path] = None) -> int:
    """Ghi ra ``data/_ICB_<mã>/<năm>/<năm>-<tháng>-01.json``.

    Cùng bố cục file với mọi mã khác, nên ``loader._load_year`` và cơ chế cache
    theo chữ ký file dùng lại được nguyên vẹn.
    """
    root = (data_dir or DATA_DIR) / sector_symbol(code)
    months: Dict[Tuple[int, int], List[dict]] = defaultdict(list)
    for rec in records:
        day = datetime.fromisoformat(rec["date"])
        months[(day.year, day.month)].append(rec)
    for (year, month), items in sorted(months.items()):
        folder = root / str(year)
        folder.mkdir(parents=True, exist_ok=True)
        (folder / f"{year}-{month:02d}-01.json").write_text(
            json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    return len(months)


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------
_NOTE = (
    "KHONG PHAI MOT MA CO PHIEU. Day la CHI SO NGANH ICB do FireAnt tinh tren "
    "TOAN BO thanh vien nganh o ca ba san — khong phai tu ro 76 ma trong data/. "
    "Khong bao gio dua vao ro quet/xep hang: khong ai mua duoc mot nganh, va "
    "nen cua no la so binh quan nen ADX/RSI/swing deu muot hon moi ma thanh "
    "phan, tron vao la lech am tham moi phan vi trong ranking.py. Lay duoc chi "
    "bang cach goi dich danh hoac nhom 'sectors'."
)


def duplicate_map(industries: Sequence[Industry]) -> Dict[str, str]:
    """Ngành cấp 2 nào **chính là** cha của nó, khoá con → mã cha.

    Sáu trong mười một ngành cấp 1 có đúng **một** con cấp 2, và khi đó FireAnt
    trả hai chuỗi trùng khít từng phiên — đã đối chiếu 400 phiên gần nhất trên
    cả sáu cặp: `10`≡`1010` Công nghệ, `15`≡`1510` Viễn thông, `20`≡`2010` Chăm
    sóc sức khoẻ, `35`≡`3510` Bất động sản, `60`≡`6010` Năng lượng, `65`≡`6510`
    Dịch vụ hạ tầng.

    Không đánh dấu thì một bảng "5 ngành mạnh nhất" hiện *Năng lượng* hai lần,
    ăn hai suất bằng đúng một thông tin — và người đọc không có cách nào biết,
    vì hai dòng mang hai cái tên khác nhau. Nên 31 mã ngành chỉ là **25 chuỗi
    phân biệt**, và mọi phép xếp hạng phải chạy trên 25.
    """
    children: Dict[str, List[str]] = defaultdict(list)
    for ind in industries:
        if ind.level == 2 and ind.parent:
            children[ind.parent].append(ind.code)
    return {kids[0]: parent for parent, kids in children.items()
            if len(kids) == 1}


def distinct_codes(industries: Sequence[Industry]) -> List[str]:
    """Mã ngành sau khi bỏ bản trùng — giữ **cấp 1**, bỏ con trùng khít nó."""
    dup = duplicate_map(industries)
    return [i.code for i in industries if i.code not in dup]


def write_registry(industries: Sequence[Industry],
                   members: Optional[Dict[str, int]] = None,
                   sessions: Optional[Dict[str, int]] = None,
                   path: Optional[Path] = None) -> Path:
    """Ghi ``stock_list/sectors.json`` — cùng hình dạng ``benchmarks.json``.

    ``share_code`` mang tiền tố ``_ICB_`` vì đó là **tên thư mục trong
    ``data/``**, thứ mà ``loader`` so khớp. Mã ICB trần nằm ở ``icb_code``.

    ``duplicate_of`` là trường quan trọng nhất ở đây — xem ``duplicate_map``.
    """
    out = path or (STOCK_LIST_DIR / SECTOR_FILE)
    dup = duplicate_map(industries)
    items = []
    for ind in industries:
        items.append({
            "share_code": ind.symbol,
            "icb_code": ind.code,
            "level": ind.level,
            "parent": ind.parent,
            "name": ind.name,
            "san": "tong hop",
            "kind": "sector_index",
            "role": "sector_benchmark",
            "duplicate_of": dup.get(ind.code),
            "members": (members or {}).get(ind.code),
            "sessions": (sessions or {}).get(ind.code),
            "note": _NOTE + (
                f" TRUNG KHIT voi _ICB_{dup[ind.code]} (nganh cap 1 chi co dung "
                f"mot con cap 2 nen hai chuoi giong het nhau) — KHONG duoc xep "
                f"hang ca hai, se dem mot nganh hai lan."
                if ind.code in dup else ""),
        })
    out.write_text(json.dumps(items, ensure_ascii=False, indent=2),
                   encoding="utf-8")
    return out


def load_registry(path: Optional[Path] = None) -> List[Dict[str, Any]]:
    src = path or (STOCK_LIST_DIR / SECTOR_FILE)
    if not src.is_file():
        return []
    try:
        return json.loads(src.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []


# ---------------------------------------------------------------------------
# Nạp cả tầng
# ---------------------------------------------------------------------------
@dataclass
class SectorBuild:
    """Kết quả một lượt nạp — đủ để soi lại mà không phải mở file."""
    code: str
    name: str
    level: int
    sessions: int = 0
    first_date: Optional[str] = None
    last_date: Optional[str] = None
    members: Optional[int] = None
    files_written: int = 0
    thin: bool = False               # chuỗi ngắn hơn MIN_SESSIONS
    duplicate_of: Optional[str] = None   # trùng khít ngành cấp 1 nào
    error: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def fetch_members(code: str) -> List[str]:
    """Mã nào thuộc ngành này — **cả sàn**, không riêng rổ ``data/``."""
    rows = get(f"/icb/{code}/symbols") or []
    return [str(s).strip().upper() for s in rows if str(s).strip()]


def update(levels: Sequence[int] = LEVELS, start: str = HISTORY_START,
           end: Optional[str] = None, codes: Optional[Sequence[str]] = None,
           with_members: bool = True,
           data_dir: Optional[Path] = None) -> List[SectorBuild]:
    """Nạp chỉ số cho cả cây ngành, ghi đĩa, rồi dựng lại registry.

    Một ngành hỏng **không** làm hỏng cả lượt: lỗi vào ``SectorBuild.error`` và
    vòng lặp đi tiếp. Ngành thiếu dữ liệu vẫn tốt hơn là không có ngành nào.
    """
    tree = fetch_tree(levels)
    if codes:
        want = {str(c).strip() for c in codes}
        tree = [i for i in tree if i.code in want]

    builds: List[SectorBuild] = []
    member_counts: Dict[str, int] = {}
    session_counts: Dict[str, int] = {}
    dup = duplicate_map(tree)

    for ind in tree:
        out = SectorBuild(code=ind.code, name=ind.name, level=ind.level,
                          duplicate_of=dup.get(ind.code))
        try:
            records = fetch_index(ind.code, start, end)
            out.sessions = len(records)
            if records:
                out.first_date = records[0]["date"][:10]
                out.last_date = records[-1]["date"][:10]
                out.files_written = write_index(ind.code, records, data_dir)
                session_counts[ind.code] = len(records)
            out.thin = 0 < out.sessions < MIN_SESSIONS
            if with_members:
                members = fetch_members(ind.code)
                out.members = len(members)
                member_counts[ind.code] = len(members)
        except Exception as exc:                      # noqa: BLE001
            out.error = f"{type(exc).__name__}: {exc}"
        builds.append(out)

    write_registry(tree, member_counts, session_counts)
    return builds


def format_builds(builds: Sequence[SectorBuild]) -> str:
    """Bảng kiểm kê — đây là thứ trả lời "ngành nào đủ dữ liệu để phân tích"."""
    lines = ["| Mã ICB | Cấp | Ngành | Phiên | Từ | Đến | Thành viên | Ghi chú |",
             "|---|---|---|---|---|---|---|---|"]
    for b in sorted(builds, key=lambda x: (x.level, x.code)):
        note = b.error or ("⚠️ chuỗi ngắn" if b.thin else
                           ("⚠️ không có phiên nào" if not b.sessions else ""))
        lines.append(
            f"| `{b.code}` | {b.level} | {b.name} | {b.sessions} | "
            f"{b.first_date or '—'} | {b.last_date or '—'} | "
            f"{b.members if b.members is not None else '—'} | {note} |")
    ok = [b for b in builds if b.sessions >= MIN_SESSIONS and not b.error]
    dup = [b for b in builds if b.duplicate_of]
    lines += ["", f"**{len(ok)}/{len(builds)} ngành có từ {MIN_SESSIONS} phiên trở lên.**"]
    if dup:
        pairs = ", ".join(f"`{b.code}`≡`{b.duplicate_of}`" for b in dup)
        lines += ["",
                  f"⚠️ **{len(dup)} mã ngành là bản trùng** của ngành cấp 1 ({pairs}) — "
                  f"ngành cấp 1 chỉ có đúng một con cấp 2 nên hai chuỗi giống hệt nhau. "
                  f"Còn **{len(builds) - len(dup)} chuỗi phân biệt**; xếp hạng phải chạy "
                  f"trên tập đó, không phải trên {len(builds)}."]
    lines += ["",
              "Chỉ số ngành tính trên **toàn bộ** thành viên ngành ở cả ba sàn, "
              "không phải từ rổ trong `data/` — cột *Thành viên* là số mã thật "
              "của ngành."]
    return "\n".join(lines)


def _main() -> None:
    ap = argparse.ArgumentParser(description="Nạp chỉ số ngành ICB về data/_ICB_*/")
    ap.add_argument("--survey", action="store_true",
                    help="chỉ kiểm kê độ phủ, không ghi đĩa")
    ap.add_argument("--codes", default="", help="mã ICB, ngăn bằng dấu phẩy")
    ap.add_argument("--start", default=HISTORY_START)
    ap.add_argument("--levels", default="1,2")
    args = ap.parse_args()

    levels = tuple(int(x) for x in args.levels.split(",") if x.strip())
    codes = [c for c in args.codes.split(",") if c.strip()] or None

    if args.survey:
        tree = fetch_tree(levels)
        if codes:
            tree = [i for i in tree if i.code in set(codes)]
        builds = []
        for ind in tree:
            b = SectorBuild(code=ind.code, name=ind.name, level=ind.level)
            try:
                rows = fetch_index(ind.code, args.start)
                b.sessions = len(rows)
                if rows:
                    b.first_date, b.last_date = rows[0]["date"][:10], rows[-1]["date"][:10]
                b.thin = 0 < b.sessions < MIN_SESSIONS
            except Exception as exc:                  # noqa: BLE001
                b.error = f"{type(exc).__name__}: {exc}"
            builds.append(b)
    else:
        builds = update(levels, args.start, codes=codes)

    print(format_builds(builds))


if __name__ == "__main__":
    _main()
