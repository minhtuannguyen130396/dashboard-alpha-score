"""Bảng ánh xạ ngành ↔ biến vĩ mô / hàng hoá — **khai báo**, không hard-code.

Cùng cách `Documents/plan_news_pipeline.md` §6 đã chọn cho taxonomy sự kiện:
luật nằm trong JSON nên sửa luật không phải sửa code, và bảng luật **test được
độc lập** bằng một bộ ca mẫu.

Ba quy ước giữ cho bảng này không thành một chỗ bịa:

1. **``chieu`` mặc định là ``khong_ro``, và đó là giá trị hợp lệ.** Bịa một
   chiều tương quan cho đủ bảng là đúng kiểu sai mà cả tầng này chống. Lãi suất
   với Bán lẻ: có lập luận cả hai chiều, nên để ``khong_ro`` và đợi §7 đo.

2. **``chieu`` khai báo là GIẢ THUYẾT, không phải kết luận.** ``measure()`` đo
   lại tương quan thật trên chuỗi; chỗ nào đo ngược với khai báo thì **chính chỗ
   lệch là thông tin**, không phải lỗi cần sửa cho khớp.

3. **Từ khoá lọc tin là bộ lọc THÔ.** Nó thu hẹp vài nghìn bài xuống vài chục
   để model đọc; việc quyết định bài nào *thật sự* nói về ngành nào là của model
   đọc bằng chứng, không phải của một câu ``LIKE``.
"""
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from statistics import fmean, pstdev
from typing import Any, Dict, List, Optional, Sequence, Tuple

from src.ta.loader import STOCK_LIST_DIR

DRIVERS_FILE = "drivers.json"

#: Chiều tác động khai báo.
SAME = "cung"            # biến lên thì ngành thường tốt lên
OPPOSITE = "nguoc"       # biến lên thì ngành thường xấu đi
UNKNOWN = "khong_ro"     # chưa có lập luận một chiều — mặc định

DIRECTION_VN = {SAME: "cùng chiều", OPPOSITE: "ngược chiều",
                UNKNOWN: "chưa rõ chiều"}

#: Nguồn của một biến.
SRC_MACRO = "macro"          # chỉ số vĩ mô theo id (src/macro/series.py)
SRC_COMMODITY = "commodity"  # ticker hàng hoá thế giới (src/macro/feed.py)


@dataclass
class Driver:
    """Một biến nền của một ngành."""
    source: str                  # SRC_MACRO | SRC_COMMODITY
    ref: str                     # id chỉ số vĩ mô, hoặc ticker hàng hoá
    direction: str = UNKNOWN
    reason: str = ""

    @property
    def direction_vn(self) -> str:
        return DIRECTION_VN.get(self.direction, DIRECTION_VN[UNKNOWN])

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["direction_vn"] = self.direction_vn
        return d


@dataclass
class SectorDrivers:
    code: str
    name: str = ""
    drivers: List[Driver] = field(default_factory=list)
    groups: List[int] = field(default_factory=list)      # nhóm tin đáng đọc
    keywords: List[str] = field(default_factory=list)    # bộ lọc thô

    def to_dict(self) -> Dict[str, Any]:
        return {"code": self.code, "name": self.name,
                "drivers": [d.to_dict() for d in self.drivers],
                "groups": list(self.groups),
                "keywords": list(self.keywords)}


# ---------------------------------------------------------------------------
# Bảng mặc định — giả thuyết khởi điểm, §7 đo lại
# ---------------------------------------------------------------------------
# id chỉ số vĩ mô lấy từ `/macro-data/{nhóm}/info`, đã đối chiếu ngày 16/09/2026.
#
# ⚠️ **Phần lớn kho vĩ mô của FireAnt là nghĩa địa.** Kiểm kê cả 96 chỉ số:
# **30 cái quá hạn**, có cái 8020 ngày (lãi suất liên ngân hàng kỳ hạn 12 tháng,
# tần suất "hàng ngày"). Chuỗi *còn sống* nhanh nhất cũng trễ **78 ngày** vì nó
# là chuỗi hàng tháng — FireAnt không có chuỗi vĩ mô nào cập nhật nhanh hơn
# tháng. Khai báo một biến chết ở đây là đưa một con số bốn năm tuổi vào gói
# bằng chứng cho model đọc, nên mọi id dưới đây phải **kiểm tuổi trước khi
# thêm** bằng `python -m src.macro.series` rồi soi cột `Cũ` của
# `macro_dashboard`.

# --- còn sống, trễ 78 ngày (hàng tháng) ---
ID_GASOLINE = 90         # Giá xăng dầu, USD/lít, Petrolimex
ID_RETAIL_SALES = 92     # Doanh số bán lẻ (YoY)
ID_CPI_YOY = 34          # Tỷ lệ lạm phát (YoY)
ID_PMI = 51              # Chỉ số PMI sản xuất
ID_IIP = 49              # Chỉ số sản xuất công nghiệp
ID_POWER_OUTPUT = 46     # Sản lượng điện
ID_TOURISTS = 65         # Lượng khách du lịch
ID_EXPORTS = 59          # Tổng xuất khẩu
ID_TRADE_BALANCE = 54    # Cán cân thương mại
ID_NEW_VEHICLES = 39     # Số xe đăng ký mới

# --- còn sống nhưng chỉ hàng năm, trễ 169 ngày ---
ID_CONSUMER_SPEND = 89   # Chi tiêu người tiêu dùng

# --- QUÁ HẠN, giữ lại vì không có thay thế ---
#: Lãi suất liên ngân hàng qua đêm — **91 ngày** không cập nhật, mà nó là chuỗi
#: "hàng ngày". Cả nhóm `InterestRate` (17 chỉ số) không còn cái nào sống, nên
#: không có gì thay. Giữ lại vì lãi suất vẫn là biến nền thật của ngân hàng và
#: bất động sản, **và** vì `verdict.build_evidence` giờ đính tuổi của nó vào
#: chính câu bằng chứng — model đọc được là số này đã cũ. Bỏ hẳn thì mất một
#: biến có thật; giữ mà im lặng thì tệ hơn cả hai.
ID_INTERBANK_ON = 99

#: Niềm tin người tiêu dùng — **1675 ngày** (4,5 năm). Đã **bỏ khỏi bảng**: một
#: con số của 2022 không nói gì về sức mua hôm nay, và nó từng là biến khai báo
#: duy nhất của ngành `40`. Thay bằng `ID_RETAIL_SALES` (78 ngày).
ID_CONSUMER_CONF_DEAD = 88

_DEFAULT: Dict[str, Dict[str, Any]] = {
    "60": {
        "name": "Năng lượng",
        "drivers": [
            (SRC_COMMODITY, "BZ=F", SAME,
             "Dầu Brent — đầu ra của thăm dò/khai thác, và là mỏ neo giá bán "
             "của lọc dầu. Khai báo cùng chiều vì phần khai thác lớn hơn phần "
             "chịu chi phí đầu vào trong rổ niêm yết."),
            (SRC_COMMODITY, "CL=F", SAME, "Dầu WTI — biến đi gần như song song Brent."),
            (SRC_MACRO, str(ID_GASOLINE), SAME,
             "Giá xăng dầu bán lẻ trong nước — theo tháng, đã điều tiết, nên "
             "trễ và mượt hơn giá thế giới."),
        ],
        "groups": [9, 5, 4],
        "keywords": ["giá dầu", "dầu thô", "brent", "opec", "lọc dầu", "xăng dầu",
                     "khí đốt", "dầu khí", "trung đông"],
    },
    "55": {
        "name": "Vật liệu cơ bản",
        # `HG=F` (đồng) đã bị bỏ: kho tin **không có điểm nào** cho ticker này
        # sau lượt cào 180 trang. Chỉ 4 hàng hoá thật sự xuất hiện — Brent,
        # WTI, vàng, bạc. Khai báo một ticker không có dữ liệu là khai báo một
        # biến chết, cùng lỗi với các chỉ số vĩ mô đã ngừng cập nhật.
        "drivers": [(SRC_MACRO, str(ID_IIP), SAME,
                     "Sản xuất công nghiệp — cầu của vật liệu cơ bản.")],
        "groups": [9, 5, 4],
        "keywords": ["giá thép", "quặng", "hrc", "thép", "than", "nhôm", "đồng",
                     "hoá chất", "phân bón", "urê", "cao su"],
    },
    "5510": {
        "name": "Tài nguyên cơ bản",
        "drivers": [(SRC_MACRO, str(ID_IIP), SAME,
                     "Sản xuất công nghiệp — cầu của thép và than.")],
        "groups": [9, 5, 4],
        "keywords": ["giá thép", "quặng sắt", "hrc", "thép", "than", "nhôm"],
    },
    "5520": {
        "name": "Hóa chất",
        "drivers": [(SRC_COMMODITY, "BZ=F", OPPOSITE,
                     "Dầu là **đầu vào** của hoá dầu và phân đạm — dầu lên thì "
                     "biên co lại. Ngược chiều với ngành Năng lượng, và chính "
                     "sự ngược đó là lý do hai ngành không được gộp.")],
        "groups": [9, 4],
        "keywords": ["phân bón", "urê", "dap", "hoá chất", "photpho", "giá khí"],
    },
    "3010": {
        "name": "Ngân hàng",
        "drivers": [
            (SRC_MACRO, str(ID_INTERBANK_ON), UNKNOWN,
             "Lãi suất liên ngân hàng: lãi lên thì NIM có thể giãn, nhưng chi "
             "phí vốn và nợ xấu cũng lên. Hai chiều đều có lập luận nên để "
             "chưa rõ — §7 đo."),
        ],
        "groups": [2, 4, 1],
        "keywords": ["lãi suất", "tín dụng", "room tín dụng", "nợ xấu", "ngân hàng",
                     "ngân hàng nhà nước", "tỷ giá", "trái phiếu"],
    },
    "30": {
        "name": "Tài chính",
        "drivers": [(SRC_MACRO, str(ID_INTERBANK_ON), UNKNOWN,
                     "Xem ghi chú ở ngành `3010`.")],
        "groups": [2, 4, 1],
        "keywords": ["lãi suất", "tín dụng", "chứng khoán", "bảo hiểm", "trái phiếu"],
    },
    "3020": {
        "name": "Dịch vụ tài chính",
        "drivers": [],
        "groups": [1, 2],
        "keywords": ["thanh khoản", "margin", "nâng hạng", "ftse", "msci",
                     "công ty chứng khoán", "krx"],
    },
    "3030": {"name": "Bảo hiểm", "drivers": [], "groups": [2, 4],
             "keywords": ["bảo hiểm", "lãi suất", "trái phiếu chính phủ"]},
    "35": {
        "name": "Bất động sản",
        "drivers": [(SRC_MACRO, str(ID_INTERBANK_ON), OPPOSITE,
                     "Lãi suất lên thì chi phí vốn và sức mua nhà cùng giảm.")],
        "groups": [6, 4, 2],
        "keywords": ["bất động sản", "pháp lý dự án", "luật đất đai", "tín dụng bđs",
                     "nhà ở xã hội", "quy hoạch", "giải ngân đầu tư công"],
    },
    "5010": {
        "name": "Xây dựng và vật liệu xây dựng",
        "drivers": [],
        "groups": [4, 6],
        "keywords": ["đầu tư công", "giải ngân", "cao tốc", "sân bay", "xi măng",
                     "giá thép", "quy hoạch"],
    },
    "50": {"name": "Công nghiệp", "drivers": [
               (SRC_MACRO, str(ID_PMI), SAME, "PMI sản xuất — đơn hàng mới của ngành."),
               (SRC_MACRO, str(ID_IIP), SAME, "Chỉ số sản xuất công nghiệp.")],
           "groups": [4, 5],
           "keywords": ["pmi", "đầu tư công", "xuất khẩu", "logistics", "cảng biển",
                        "cước vận tải", "khu công nghiệp"]},
    "5020": {"name": "Sản phẩm & dịch vụ công nghiệp", "drivers": [
                 (SRC_MACRO, str(ID_PMI), SAME, "PMI sản xuất."),
                 (SRC_MACRO, str(ID_EXPORTS), SAME,
                  "Tổng xuất khẩu — cầu của logistics và cảng biển.")],
             "groups": [4, 5],
             "keywords": ["pmi", "logistics", "cảng", "cước vận tải", "xuất khẩu"]},
    "45": {
        "name": "Hàng tiêu dùng cơ bản",
        "drivers": [(SRC_MACRO, str(ID_RETAIL_SALES), SAME,
                     "Doanh số bán lẻ — cầu cuối, 78 ngày."),
                    (SRC_MACRO, str(ID_CPI_YOY), UNKNOWN,
                     "Lạm phát: giá bán tăng theo nhưng sức mua giảm — hai "
                     "chiều đều có lập luận."),
                    (SRC_MACRO, str(ID_CONSUMER_SPEND), SAME,
                     "Chi tiêu tiêu dùng — chỉ hàng năm, trễ 169 ngày.")],
        "groups": [4, 9],
        "keywords": ["giá heo", "giá gạo", "thực phẩm", "bán lẻ", "cpi",
                     "sức mua", "xuất khẩu nông sản"],
    },
    "4510": {"name": "Thực phẩm và đồ uống", "drivers": [
                 (SRC_MACRO, str(ID_CONSUMER_SPEND), SAME, "Cầu cuối.")],
             "groups": [4, 9],
             "keywords": ["giá heo", "giá sữa", "giá đường", "bia", "thực phẩm", "cpi"]},
    "40": {
        "name": "Hàng tiêu dùng không thiết yếu",
        "drivers": [(SRC_MACRO, str(ID_RETAIL_SALES), SAME,
                     "Doanh số bán lẻ — cầu cuối của ngành. Thay cho Niềm tin "
                     "tiêu dùng (id 88), chuỗi đó đã chết 4,5 năm."),
                    (SRC_MACRO, str(ID_NEW_VEHICLES), SAME,
                     "Số xe đăng ký mới — chỉ báo chi tiêu lớn của hộ gia đình.")],
        "groups": [4],
        "keywords": ["sức mua", "bán lẻ", "doanh số", "du lịch", "ô tô"],
    },
    "4040": {"name": "Bán lẻ", "drivers": [
                 (SRC_MACRO, str(ID_RETAIL_SALES), SAME,
                  "Doanh số bán lẻ — chính là doanh thu của ngành."),
                 (SRC_MACRO, str(ID_INTERBANK_ON), UNKNOWN,
                  "Lãi suất tác động qua cả sức mua lẫn chi phí vốn — chưa rõ "
                  "chiều. ⚠️ chuỗi này đang quá hạn 91 ngày.")],
             "groups": [4],
             "keywords": ["bán lẻ", "sức mua", "doanh số", "điện máy", "trang sức"]},
    "4050": {"name": "Du lịch và giải trí", "drivers": [
                 (SRC_MACRO, str(ID_TOURISTS), SAME,
                  "Lượng khách du lịch — cầu trực tiếp của ngành.")],
             "groups": [4, 5],
             "keywords": ["khách quốc tế", "du lịch", "hàng không", "visa",
                          "giá nhiên liệu bay"]},
    "4010": {"name": "Ôtô và linh kiện", "drivers": [
                 (SRC_MACRO, str(ID_NEW_VEHICLES), SAME,
                  "Số xe đăng ký mới — doanh số thật của ngành.")],
             "groups": [4],
             "keywords": ["ô tô", "xe điện", "đăng ký xe", "thuế trước bạ"]},
    "4020": {"name": "Hàng tiêu dùng cá nhân và gia đình", "drivers": [],
             "groups": [4], "keywords": ["sức mua", "tiêu dùng", "xuất khẩu"]},
    "4030": {"name": "Truyền thông", "drivers": [], "groups": [4],
             "keywords": ["quảng cáo", "truyền thông", "giải trí"]},
    "4520": {"name": "Cửa hàng tiện lợi", "drivers": [], "groups": [4],
             "keywords": ["bán lẻ", "sức mua", "cpi"]},
    "10": {"name": "Công nghệ", "drivers": [], "groups": [5, 4],
           "keywords": ["chuyển đổi số", "bán dẫn", "ai", "trung tâm dữ liệu",
                        "phần mềm", "xuất khẩu phần mềm", "viễn thông"]},
    "15": {"name": "Viễn thông", "drivers": [], "groups": [4, 5],
           "keywords": ["viễn thông", "5g", "tần số", "hạ tầng số"]},
    "20": {"name": "Chăm sóc sức khỏe", "drivers": [], "groups": [4],
           "keywords": ["dược", "đấu thầu thuốc", "bảo hiểm y tế", "bệnh viện"]},
    "65": {"name": "Các dịch vụ hạ tầng", "drivers": [
               (SRC_MACRO, str(ID_POWER_OUTPUT), SAME,
                "Sản lượng điện — sản lượng thật của ngành. Thay cho `NG=F` "
                "(khí tự nhiên): kho tin không có điểm nào cho ticker đó.")],
           "groups": [4, 9],
           "keywords": ["giá điện", "evn", "quy hoạch điện", "thuỷ điện",
                        "nhiệt điện", "điện gió", "el niño", "la nina", "nước về"]},
}


def _from_spec(code: str, spec: Dict[str, Any]) -> SectorDrivers:
    return SectorDrivers(
        code=code, name=str(spec.get("name") or ""),
        drivers=[Driver(source=s, ref=r, direction=d, reason=why)
                 for s, r, d, why in spec.get("drivers") or []],
        groups=list(spec.get("groups") or []),
        keywords=list(spec.get("keywords") or []))


def default_table() -> Dict[str, SectorDrivers]:
    return {code: _from_spec(code, spec) for code, spec in _DEFAULT.items()}


def write(table: Optional[Dict[str, SectorDrivers]] = None,
          path: Optional[Path] = None) -> Path:
    out = path or (STOCK_LIST_DIR / DRIVERS_FILE)
    data = {code: sd.to_dict()
            for code, sd in sorted((table or default_table()).items())}
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2),
                   encoding="utf-8")
    return out


def load(path: Optional[Path] = None) -> Dict[str, SectorDrivers]:
    """Đọc bảng; thiếu file thì trả bảng mặc định thay vì rỗng.

    Rỗng ở đây nguy hiểm hơn là sai: một ngành không có biến nào sẽ lặng lẽ
    thành "ngành không chịu lực nền nào", thay vì "chưa ai khai báo".
    """
    src = path or (STOCK_LIST_DIR / DRIVERS_FILE)
    if not src.is_file():
        return default_table()
    try:
        data = json.loads(src.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return default_table()
    out: Dict[str, SectorDrivers] = {}
    for code, spec in data.items():
        out[str(code)] = SectorDrivers(
            code=str(code), name=str(spec.get("name") or ""),
            drivers=[Driver(source=d.get("source", ""), ref=str(d.get("ref", "")),
                            direction=d.get("direction", UNKNOWN),
                            reason=d.get("reason", ""))
                     for d in spec.get("drivers") or []],
            groups=[int(g) for g in spec.get("groups") or []],
            keywords=[str(k) for k in spec.get("keywords") or []])
    return out


def for_sector(code: str, path: Optional[Path] = None) -> SectorDrivers:
    table = load(path)
    return table.get(str(code)) or SectorDrivers(code=str(code))


# ---------------------------------------------------------------------------
# Đo lại chiều đã khai báo
# ---------------------------------------------------------------------------
@dataclass
class DriverCheck:
    """Chiều khai báo so với chiều đo được trên dữ liệu."""
    code: str
    ref: str
    declared: str
    n: int = 0
    correlation: Optional[float] = None
    measured: str = UNKNOWN
    agrees: Optional[bool] = None
    note: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


#: Dưới ngưỡng này thì tương quan không đủ để gọi là một chiều.
MIN_ABS_CORR = 0.15
MIN_POINTS = 24


def _corr(xs: Sequence[float], ys: Sequence[float]) -> Optional[float]:
    if len(xs) < 3:
        return None
    mx, my = fmean(xs), fmean(ys)
    sx, sy = pstdev(xs), pstdev(ys)
    if sx == 0 or sy == 0:
        return None
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / (len(xs) * sx * sy)


def check(code: str, driver: Driver,
          sector_points: Sequence[Tuple[str, float]],
          driver_points: Sequence[Tuple[str, float]]) -> DriverCheck:
    """Đo tương quan **lợi suất** giữa ngành và biến, trên ngày khớp nhau.

    Đo trên lợi suất chứ không trên mức: hai chuỗi cùng có xu hướng tăng dài
    hạn sẽ cho tương quan mức gần 1 mà không nói gì về quan hệ giữa chúng —
    đó là tương quan giả cổ điển.
    """
    out = DriverCheck(code=str(code), ref=driver.ref, declared=driver.direction)
    a = dict(sector_points)
    b = dict(driver_points)
    both = sorted(set(a) & set(b))
    if len(both) < MIN_POINTS + 1:
        out.n = len(both)
        out.note = f"chỉ {len(both)} ngày khớp — chưa đủ để đo"
        return out

    ra, rb = [], []
    for prev, cur in zip(both, both[1:]):
        if a[prev] and b[prev]:
            ra.append(a[cur] / a[prev] - 1)
            rb.append(b[cur] / b[prev] - 1)
    out.n = len(ra)
    out.correlation = _corr(ra, rb)
    if out.correlation is None:
        out.note = "không tính được tương quan"
        return out
    if abs(out.correlation) < MIN_ABS_CORR:
        out.measured = UNKNOWN
        out.note = f"|r| = {abs(out.correlation):.2f} < {MIN_ABS_CORR} — không đủ để gọi là một chiều"
    else:
        out.measured = SAME if out.correlation > 0 else OPPOSITE
    if driver.direction == UNKNOWN or out.measured == UNKNOWN:
        out.agrees = None       # không so được, và đó là câu trả lời đúng
    else:
        out.agrees = (driver.direction == out.measured)
    return out


def _main() -> None:
    path = write()
    table = load()
    n_drivers = sum(len(sd.drivers) for sd in table.values())
    unknown = sum(1 for sd in table.values() for d in sd.drivers
                  if d.direction == UNKNOWN)
    print(f"Đã ghi {path}")
    print(f"{len(table)} ngành · {n_drivers} biến · {unknown} biến để `khong_ro`")
    print()
    print("| Ngành | Biến | Chiều khai báo |")
    print("|---|---|---|")
    for code, sd in sorted(table.items()):
        for d in sd.drivers:
            print(f"| `{code}` {sd.name} | {d.source}:{d.ref} | {d.direction_vn} |")
    print()
    print("Chiều ở đây là **giả thuyết**. `drivers.check()` đo lại trên dữ liệu; "
          "chỗ nào đo ngược với khai báo thì chính chỗ lệch là thông tin.")


if __name__ == "__main__":
    _main()
