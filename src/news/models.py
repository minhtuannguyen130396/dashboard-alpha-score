"""Kiểu dữ liệu của tầng tin tức — JSON-serializable, giống ``Snapshot`` bên ``ta``.

Ba kiểu ở đây tương ứng ba thứ FireAnt trả về có cấu trúc sẵn (nhóm A và B của
taxonomy): giao dịch của cổ đông lớn, mốc sự kiện theo thời gian, và bài viết.

Điểm chung: mỗi bản ghi mang theo **nguồn của những gì nó khẳng định**. Chiều
mua/bán đến từ enum trong đặc tả API thì ghi ``swagger_enum``; ngày dùng làm
``t0`` cho event study là ngày công bố thật hay chỉ là mốc thay thế thì ghi rõ ở
``t0_source``. Không có hai trường đó thì sau này không ai phân biệt được số
chắc chắn với số suy đoán.
"""
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from typing import Any, Dict, Optional

# --- Chiều giao dịch: enum lấy nguyên từ /swagger/docs/v1 -------------------
# MajorHolderTransaction.type — "Loại giao dịch (Purchased = Mua, Sold = Bán,
# StockRightPurchased = Mua quyền mua, StockRightSold = Bán quyền mua)"
PURCHASED = 0
SOLD = 1
STOCK_RIGHT_PURCHASED = 2
STOCK_RIGHT_SOLD = 3

DIRECTION_VN = {
    PURCHASED: "mua",
    SOLD: "bán",
    STOCK_RIGHT_PURCHASED: "mua quyền mua",
    STOCK_RIGHT_SOLD: "bán quyền mua",
}

#: Nguồn xác định chiều mua/bán (§9.12). Xếp từ chắc chắn xuống suy đoán.
SRC_SWAGGER = "swagger_enum"
SRC_CROSS_REF = "cross_ref_news"
SRC_WEAK = "inferred_weak"

#: Nguồn của mốc ``t0`` dùng cho event study (§2b hạn chế b).
T0_POST = "post_date"                # ngày bài báo — chuẩn nhất
T0_MARK = "timescale_mark"           # ngày công bố BCTC/cổ tức từ timescale-marks
T0_START_PROXY = "start_date_proxy"   # mốc thay thế: ngày bắt đầu đăng ký


@dataclass
class HolderTransaction:
    """Một lần cổ đông lớn / người nội bộ đăng ký và (có thể) thực hiện giao dịch.

    Hai con số làm nên giá trị của bản ghi này là ``registered_volume`` và
    ``execution_volume``. Tỷ lệ giữa chúng nói lên *ý định gặp kết quả* — thứ
    đọc tin bằng NLP rất khó rút ra.

    ``registered_volume is None`` **khác** ``registered_volume == 0``: cái đầu là
    bản ghi cũ từ thời chưa bắt buộc đăng ký trước, nên tỷ lệ thực hiện không
    định nghĩa được; cái sau là đăng ký 0 (thực tế không xảy ra). Gộp hai cái
    này lại là bịa ra tín hiệu "đăng ký rồi không làm" từ một khoảng trống.
    """
    transaction_id: int
    symbol: str
    name: str
    position: Optional[str]           # None = cổ đông lớn không giữ chức vụ
    direction: int                    # PURCHASED / SOLD / STOCK_RIGHT_*
    direction_source: str             # §9.12
    registered_volume: Optional[float]
    execution_volume: Optional[float]
    start_date: Optional[str]
    end_date: Optional[str]
    execution_date: Optional[str]
    major_holder_id: Optional[int] = None
    individual_holder_id: Optional[int] = None
    institution_holder_id: Optional[int] = None
    is_organization: Optional[bool] = None

    @property
    def execution_rate(self) -> Optional[float]:
        """exec / reg, hoặc ``None`` khi không có đăng ký để mà so."""
        if not self.registered_volume:
            return None
        if self.execution_volume is None:
            return None
        return self.execution_volume / self.registered_volume

    @property
    def is_insider(self) -> bool:
        """Có chức vụ = người nội bộ; không có = cổ đông lớn thuần tuý."""
        return bool(self.position)

    @property
    def t0(self) -> Optional[str]:
        """Mốc dùng cho event study, kèm cảnh báo ở ``t0_source``.

        API không trả ngày công bố. ``start_date`` là mốc thay thế gần nhất —
        công bố thường sát ngày bắt đầu đăng ký — nhưng phải nói rõ là thay thế.
        """
        return self.start_date or self.execution_date

    @property
    def t0_source(self) -> str:
        return T0_START_PROXY

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["execution_rate"] = self.execution_rate
        d["is_insider"] = self.is_insider
        d["direction_vn"] = DIRECTION_VN.get(self.direction, "?")
        return d


@dataclass
class TimescaleMark:
    """Mốc sự kiện FireAnt dựng sẵn cho chart: BCTC, cổ tức.

    ``title`` là **chuỗi viết cho người đọc**, các phần ngăn bằng ``|``. Parse
    được nhưng giòn — format đổi là gãy. Nên ``raw_title`` luôn được giữ nguyên
    bên cạnh phần đã parse, và phần parse chỉ là tiện ích chứ không phải nguồn
    sự thật.
    """
    mark_id: str
    symbol: str
    label: str                # "F" = báo cáo tài chính, "D" = cổ tức
    date: str
    raw_title: str
    parsed: Dict[str, Any] = field(default_factory=dict)

    LABEL_FINANCIAL = "F"
    LABEL_DIVIDEND = "D"

    @property
    def kind(self) -> str:
        return {"F": "bctc", "D": "co_tuc"}.get(self.label, "khac")

    @property
    def t0_source(self) -> str:
        """Khác ``HolderTransaction``: đây là ngày công bố thật, không phải proxy."""
        return T0_MARK

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["kind"] = self.kind
        return d
