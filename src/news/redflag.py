"""Cờ đỏ — sự kiện đủ nặng để lật ngược một tư thế kỹ thuật đẹp.

Một mã có mẫu hình cốc-tay-cầm đã xác nhận, breakout bằng volume 2,3×, RSI 58
là một mã đứng đầu mọi bảng xếp hạng ở đây. Nếu chủ tịch của nó vừa bị khởi tố
tuần trước thì cả bảng xếp hạng đó nói sai, và nó sai theo cách tệ nhất: **im
lặng**. Không có ô nào trống để người đọc nhận ra là thiếu.

Lớp này chặn đúng chỗ đó. Nó **không** chấm sắc thái tin — đó là việc §9.9 của
plan đã kết luận là model ngôn ngữ phải làm, và kết luận ấy vẫn đúng: không
lexicon nào đọc được *"lãi ròng giảm 50% nhưng vượt 20% kế hoạch năm"*. Việc ở
đây khác hẳn về bản chất:

* **Phát hiện sự kiện có tên, không phải đoán cảm xúc.** "Bị khởi tố", "huỷ
  niêm yết", "ý kiến ngoại trừ của kiểm toán" là những hạng mục đóng, gọi tên
  được, và tiếng Việt tài chính gọi chúng bằng một tập cụm từ hữu hạn.
* **Đầu ra là một cờ kèm NGUYÊN VĂN tiêu đề**, không phải một con số trôi nổi.
  Người đọc bác lại được bằng chính câu đã kích hoạt cờ — thứ mà một điểm sắc
  thái không cho phép.

Bốn quyết định thiết kế, mỗi cái chặn một kiểu bỏ sót:

1. **Ưu tiên recall, chấp nhận cờ thừa.** Cái giá hai bên không đối xứng: một
   cờ thừa tốn của người đọc mười giây để bác; một cờ thiếu là mua vào một
   doanh nghiệp đang bị điều tra mà không biết. Nên cụm từ nào còn lưỡng lự thì
   giữ lại, và **hạ độ tin cậy** thay vì loại bỏ.

2. **Quét cả bài lưu dưới mã khác.** ``store.load_posts_mentioning`` — 4.725
   bài tin doanh nghiệp trong kho hiện tại vô hình với chính mã của chúng vì
   bảng ``posts`` chỉ có một cột ``symbol``. Với việc đếm đầu mục thì mất vài
   bài là chuyện nhỏ; với việc quét cờ đỏ thì bỏ sót một tiêu đề khởi tố là
   hỏng cả lớp.

3. **Quét cả ``description``, không chỉ ``title``.** Toàn văn chưa nạp bài nào,
   nhưng ``description`` (~157 ký tự trung bình) có ở 57.645/57.928 bài — gấp
   đôi bề mặt chữ mà không tốn thêm một request nào.

4. **So chuỗi trên văn bản ĐÃ BỎ DẤU.** "huỷ" và "hủy" là hai chuỗi Unicode
   khác nhau và cả hai đều xuất hiện trong kho; so có dấu là tự tạo ra một lỗ
   hổng theo kiểu gõ. Bỏ dấu rồi so cũng chịu được lỗi thiếu dấu của báo mạng.

**Cụm từ, không phải từ đơn.** Bẫy lớn nhất của tiếng Việt: "bắt" nằm trong
"bắt đầu", "bắt tay", "bắt nhịp", "bắt đáy", "bắt buộc" — quét từ đơn là gắn cờ
hình sự cho một nửa số tin. Mọi mẫu ở đây đều là cụm đã đủ nghĩa, và những cụm
đa nghĩa ("điều tra", "cảnh báo") phải kèm **ngữ cảnh bắt buộc** trong
``requires_any``.
"""
import unicodedata
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Sequence, Tuple

from src.news import store as store_mod

#: Trần điểm trừ. Bằng đúng **một nửa** thang đo được của ``prospect`` (0–100):
#: một mã +80 nhờ mẫu hình mà dính án hình sự phải rơi về 30, không phải rơi về
#: 78. Con số này là chốt chặn, không phải mục tiêu — phần lớn cờ không tới đó.
MAX_PENALTY = 50.0

#: Cửa sổ quét mặc định, tính bằng **ngày lịch**. Dài hơn hẳn 20 phiên của
#: ``digest``: một vụ khởi tố năm tháng trước vẫn đang quyết định doanh nghiệp
#: đó vận hành thế nào, trong khi một đầu mục tin thường thì không.
WINDOW_DAYS = 180

#: Mức cờ, theo tổng điểm trừ sau khi đã nhân độ tin cậy và độ cũ.
LEVEL_CRITICAL = "nghiem_trong"
LEVEL_WARN = "canh_bao"
LEVEL_NOTE = "luu_y"
LEVEL_CLEAN = "sach"

LEVEL_VN = {
    LEVEL_CRITICAL: "CỜ ĐỎ NGHIÊM TRỌNG",
    LEVEL_WARN: "CỜ ĐỎ — CẢNH BÁO",
    LEVEL_NOTE: "Cờ vàng — lưu ý",
    LEVEL_CLEAN: "không có cờ đỏ trong cửa sổ",
}

LEVEL_CRITICAL_MIN = 30.0
LEVEL_WARN_MIN = 12.0

#: Trọng số của các cờ **sau cờ nặng nhất**, và trần của tổng phần đuôi tính
#: theo cờ nặng nhất. Xem ``aggregate``.
EXTRA_WEIGHT = 0.35
EXTRA_CAP_RATIO = 0.5


def _fold(text: str) -> str:
    """Bỏ dấu, hạ chữ thường, gộp khoảng trắng, **đệm hai đầu bằng khoảng trắng**.

    Phần đệm không phải tiểu tiết: mọi phép so ở đây là so nguyên tiếng, và
    cách rẻ nhất để có ranh giới tiếng là bọc cả chuỗi lẫn mẫu bằng khoảng
    trắng. Không có nó thì ``"an tu"`` (án tù) khớp vào *"cổ phần từ"*, và một
    lần đo trên kho cho thấy đúng cụm đó gắn cờ hình sự cho **1.532 bài** —
    gần như toàn bộ là nghị quyết tăng vốn.
    """
    raw = unicodedata.normalize("NFD", str(text or ""))
    raw = "".join(c for c in raw if unicodedata.category(c) != "Mn")
    raw = raw.replace("đ", "d").replace("Đ", "d").lower()
    for ch in ",.;:!?()[]{}\"'“”‘’–—/\\|":
        raw = raw.replace(ch, " ")
    return " " + " ".join(raw.split()) + " "


def _has(text: str, phrase: str) -> bool:
    """``phrase`` xuất hiện trong ``text`` **đúng theo ranh giới tiếng**."""
    return f" {phrase.strip()} " in text


# ---------------------------------------------------------------------------
# luật
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Rule:
    """Một nhóm sự kiện, cùng trọng số và cùng cách nhận ra.

    ``requires_any`` là chỗ chặn dương tính giả của những cụm đa nghĩa: "điều
    tra" một mình có thể là điều tra thị trường, "cảnh báo" một mình có thể là
    cảnh báo thời tiết. Có ngữ cảnh mới tính.
    """
    key: str
    label: str
    weight: float
    phrases: Tuple[str, ...]
    requires_any: Tuple[str, ...] = ()
    excludes: Tuple[str, ...] = ()
    why: str = ""

    def match(self, text: str) -> Optional[str]:
        """Cụm đầu tiên khớp, hoặc ``None``. ``text`` phải đã qua ``_fold``."""
        hit = next((p for p in self.phrases if _has(text, p)), None)
        if hit is None:
            return None
        if any(_has(text, x) for x in self.excludes):
            return None
        if self.requires_any and not any(_has(text, r) for r in self.requires_any):
            return None
        return hit


#: Ngữ cảnh "cơ quan chức năng đang làm việc" — dùng lại cho nhiều luật.
#:
#: Cố ý **không** chứa "thanh tra": luật ``dieu_tra`` đã có "thanh tra" trong
#: ``phrases``, và để nó ở cả hai chỗ thì điều kiện ngữ cảnh tự thoả mãn chính
#: nó — một `requires_any` luôn đúng là một `requires_any` không tồn tại.
_AUTHORITY = (
    "cong an", "canh sat", "c03", "c01", "c46", "bo cong an", "vien kiem sat",
    "toa an", "hinh su", "vu an", "khoi to", "kiem toan nha nuoc",
    "uy ban chung khoan", "ubck", "co quan dieu tra", "cuc thue", "tong cuc thue",
    "thanh tra chinh phu", "quan ly thi truong", "so giao dich",
    "hose", "hnx", "upcom",
)

RULES: Tuple[Rule, ...] = (
    Rule(
        key="hinh_su", label="Hình sự", weight=50.0,
        why="đã có quyết định tố tụng — loại tin không tự hết theo thời gian",
        phrases=(
            "khoi to", "bi bat", "bat tam giam", "tam giam", "bat giu",
            "bi tam giu", "tam giu hinh su", "truy na", "truy to", "kham xet",
            "bi can", "bi cao", "hau toa", "linh an", "lanh an", "tuyen an",
            "an tu giam", "ra dau thu",
            "cam di khoi noi cu tru", "phong toa tai san", "ke bien tai san",
            "tam hoan xuat canh", "cam xuat canh", "bat giam",
        ),
        # Ba cụm đã bị bỏ khỏi danh sách trên vì bỏ dấu xong chúng trùng khít
        # với một cụm vô hại, và cả ba đều được đo trên kho trước khi bỏ:
        #   "phat tu"  ≡ "phạt từ"  — *"đề nghị xử phạt từ 2 đến 3 tỷ"*
        #   "an tu"    ≡ "ần từ"    — *"tăng vốn cổ phần từ NVCSH"* (1.532 bài)
        #   "nam tu"   ≡ "năm từ"   — *"thêm nhiệm kỳ 3 năm từ 2025"* (125 bài)
        # Bản án thật gần như luôn đi kèm "xét xử", "tuyên án" hoặc "án tù giam".
        # "xet xu" đã chuyển xuống nhóm kiện tụng: toà xử cả vụ dân sự lẫn vụ
        # hình sự, mà một tranh chấp hợp đồng không phải −50 điểm. Một phiên
        # toà hình sự thật thì gần như luôn kèm "bị cáo", "tuyên án" hoặc
        # "khởi tố", nên nó vẫn rơi vào đây qua đường khác.
        excludes=("bi bat buoc", "bat den", "bat dau", "bat tay", "bat nhip",
                  "bat day", "bat song", "bat tai", "muon danh", "mao danh"),
    ),
    Rule(
        key="thao_tung", label="Thao túng / gian lận", weight=45.0,
        why="hành vi nhắm thẳng vào giá cổ phiếu hoặc vào số liệu công bố",
        phrases=(
            "thao tung", "lam gia co phieu", "thoi gia co phieu", "bom xa",
            "cong bo thong tin sai", "thong tin sai lech", "che giau thong tin",
            "gian lan", "lua dao", "chiem doat", "giao dich noi gian",
            "giao dich chui", "ban chui", "mua chui",
            "bao cao tai chinh sai lech", "khai khong", "nguy tao",
        ),
        # Doanh nghiệp **là nạn nhân** thì không phải cờ đỏ của doanh nghiệp:
        # *"Vincom bị đối tượng xấu mạo danh với mục đích lừa đảo"* là chuyện
        # khác hẳn *"Chủ tịch bị cáo buộc lừa đảo chiếm đoạt tài sản"*.
        excludes=("mao danh", "gia mao", "bi lua dao", "lua dao qua mang",
                  "canh bao lua dao", "nan nhan", "gia danh", "muon danh",
                  "sap bay", "chong gian lan", "quan ly gian lan",
                  "phong chong gian lan", "phong ngua gian lan"),
    ),
    Rule(
        key="no_nan", label="Mất khả năng thanh toán", weight=34.0,
        why="chậm trả gốc/lãi là tín hiệu thanh khoản doanh nghiệp, không phải tin xấu thường",
        phrases=(
            "cham thanh toan", "cham tra lai", "cham tra goc", "cham tra no",
            "chua thanh toan goc", "qua han thanh toan", "no qua han",
            "mat kha nang thanh toan", "vo no", "khat no", "gia han trai phieu",
            "hoan doi trai phieu", "dinh chi thanh toan", "ban giai chap",
            "trai phieu qua han",
        ),
        # Với ngân hàng thì mua bán nợ xấu là **nghề**, không phải tai nạn:
        # "Sacombank tìm người mua khoản nợ 59,7 tỷ" là một thông báo đấu giá.
        # Không loại ra thì cả nhóm ngân hàng mang cờ thanh khoản thường trực.
        excludes=("ban khoan no", "mua khoan no", "dau gia khoan no",
                  "rao ban khoan no", "xu ly no xau", "thu hoi no"),
    ),
    Rule(
        key="dieu_tra", label="Điều tra / thanh tra", weight=32.0,
        why="chưa có kết luận, nhưng cơ quan chức năng đã vào cuộc",
        phrases=(
            "dieu tra", "thanh tra", "trieu tap", "xac minh dau hieu",
            "dau hieu vi pham", "dau hieu bat thuong", "lam viec voi co quan",
            "yeu cau giai trinh", "ket luan thanh tra", "kiem tra thue",
        ),
        requires_any=_AUTHORITY,
        excludes=("dieu tra thi truong", "dieu tra nguoi tieu dung",
                  "dieu tra dan so", "khao sat dieu tra"),
    ),
    Rule(
        key="niem_yet", label="Tình trạng niêm yết", weight=28.0,
        why="sàn đã ra quyết định hạn chế — ảnh hưởng trực tiếp tới khả năng giao dịch",
        phrases=(
            "huy niem yet", "huy bo niem yet", "dinh chi giao dich",
            "han che giao dich", "dien canh bao", "dien kiem soat",
            "dua vao dien", "chuyen sang dien", "kiem soat dac biet",
            "cat margin", "khong duoc giao dich ky quy",
            "khong du dieu kien ky quy", "chuyen san upcom",
            "roi ro huy niem yet",
        ),
        requires_any=("co phieu", "chung khoan", "niem yet", "hose", "hnx",
                      "upcom", "ky quy", "margin", "giao dich", "so giao dich"),
        # Trái phiếu đáo hạn thì **phải** huỷ niêm yết — đó là kết thúc bình
        # thường của một lô trái phiếu, không phải chế tài với cổ phiếu.
        excludes=("huy niem yet trai phieu",),
    ),
    Rule(
        key="kiem_toan", label="Kiểm toán / công bố thông tin", weight=26.0,
        why="số liệu doanh nghiệp tự công bố không được kiểm toán xác nhận",
        phrases=(
            "y kien ngoai tru", "ngoai tru cua kiem toan", "tu choi dua ra y kien",
            "tu choi cho y kien", "nghi ngo kha nang hoat dong lien tuc",
            "van de can nhan manh", "nhan manh", "dieu chinh hoi to", "hoi to",
            "chenh lech sau kiem toan", "lech sau kiem toan",
            "giam sau kiem toan", "lo sau kiem toan", "tu lai thanh lo",
            "tu lai sang lo", "cham nop bao cao tai chinh",
            "cham cong bo thong tin", "vi pham cong bo thong tin",
            "dinh chinh thong tin",
        ),
        requires_any=("kiem toan", "bao cao tai chinh", "bctc",
                      "cong bo thong tin", "hoat dong lien tuc"),
    ),
    Rule(
        key="che_tai", label="Xử phạt / chế tài", weight=25.0,
        why="đã có quyết định hành chính — mức phạt nhỏ nhưng lý do phạt thì không nhỏ",
        phrases=(
            "xu phat", "bi phat", "phat tien", "quyet dinh xu phat",
            "vi pham hanh chinh", "truy thu thue", "cuong che thue",
            "cuong che hoa don", "no thue", "dinh chi hoat dong",
            "thu hoi giay phep", "rut giay phep", "thu hoi du an",
            "cham dut du an", "cam dam nhiem chuc vu", "tuoc giay phep",
        ),
        # "chuẩn bị phát hành" → "bi phat hanh"; "đòi nợ thuê" → "no thue".
        # Hai cụm này bỏ dấu xong trùng khít với "bị phạt" và "nợ thuế".
        excludes=("bi phat hanh", "chuan bi phat hanh", "doi no thue",
                  "dich vu doi no", "huy bo phat", "huy bo quyet dinh"),
    ),
    Rule(
        key="trien_vong", label="Triển vọng kinh doanh xấu", weight=20.0,
        why="phần đo được của báo cáo chỉ thấy giá; chỗ này là lý do phía sau giá",
        phrases=(
            "bao lo", "thua lo", "lo rong", "lo sau thue", "lo luy ke", "lo nang",
            "chuyen lo", "lo quy", "lo ky luc", "loi nhuan giam", "lai giam",
            "sut giam loi nhuan", "loi nhuan lao doc", "lai lao doc",
            "doanh thu lao doc", "ha du bao", "ha muc tieu", "ha khuyen nghi",
            "dieu chinh giam ke hoach", "giam ke hoach loi nhuan",
            "khong hoan thanh ke hoach", "mat hop dong", "huy hop dong",
            "cham dut hop dong", "tam dung du an", "dinh chi du an",
            "dong cua nha may", "tam dung san xuat", "sa thai",
            "cat giam nhan su", "thu hoi san pham", "boi thuong thiet hai",
        ),
        # "dung du an" đã bị bỏ: nó nằm gọn trong *"xây **dựng dự án**"* — 32
        # bài, gần hết là tin khởi công. "hop dong lao dong" loại đúng các
        # quyết định thôi việc của một cá nhân, vốn thuộc nhóm quản trị.
        excludes=("lai suat giam", "lo trinh", "hop dong lao dong"),
    ),
    Rule(
        key="phong_ve", label="Phòng vệ thương mại / kiện tụng", weight=16.0,
        why="áp thuế ở thị trường xuất khẩu chính là cú sốc biên lợi nhuận, không phải tin ngành chung",
        phrases=(
            "chong ban pha gia", "chong tro cap", "thue doi khang", "ap thue",
            "rao can thuong mai", "bi kien", "bi khoi kien", "tranh chap hop dong",
            "trong tai quoc te", "xet xu", "ra toa", "thua kien",
        ),
        # "khoi kien" trơ trọi bắt cả chiều ngược: *"Vingroup khởi kiện 68 cá
        # nhân đưa tin sai sự thật"* là doanh nghiệp **đi kiện**, không phải bị
        # kiện. Chỉ giữ "bi khoi kien" và "bi kien".
    ),
    Rule(
        key="tin_don", label="Tin đồn", weight=15.0,
        why="thị trường phản ứng với tin đồn trước khi nó được xác nhận hay bác bỏ",
        phrases=(
            "tin don", "don doan", "that thiet", "bac bo thong tin", "bac bo tin",
            "phu nhan thong tin", "xon xao", "lum xum", "nghi van", "thuc hu",
        ),
        # "dậy sóng" đã bị bỏ: trong tiếng báo chứng khoán nó tả một **nhịp
        # tăng** ("cổ phiếu ngân hàng đồng loạt dậy sóng"), không tả tai tiếng.
    ),
    Rule(
        key="quan_tri", label="Biến động lãnh đạo", weight=11.0,
        why="một đơn từ nhiệm là chuyện thường; một loạt đơn cùng lúc thì không",
        phrases=(
            "tu nhiem", "xin tu chuc", "tu chuc", "mien nhiem", "bai nhiem",
            "don tu nhiem", "thay tong giam doc", "thay ceo",
        ),
        # Đây là luật duy nhất mà cụm từ **một mình không đủ**, và lý do nằm ở
        # số đếm: "từ nhiệm" khớp 280 bài, "miễn nhiệm" 215 — gần hết là nghị
        # quyết thay người bình thường. Gắn cờ cho tất cả là biến cờ vàng thành
        # nền, mà một cái cờ lúc nào cũng bật thì không ai còn nhìn nó nữa. Cái
        # đáng đọc là **nhiều người cùng lúc**, hoặc từ nhiệm đi kèm tố tụng.
        requires_any=("dong loat", "hang loat", "loat lanh dao", "bat ngo",
                      "dot ngot", "lien tiep", "khoi to", "bi bat", "dieu tra",
                      "toan bo", "cung luc", "ca chu tich", "3 thanh vien",
                      "4 thanh vien", "5 thanh vien"),
    ),
    Rule(
        key="bat_thuong", label="Giải trình biến động giá", weight=10.0,
        why="chính sàn đã hỏi doanh nghiệp vì sao giá chạy — một phép đo bất thường do bên thứ ba làm",
        phrases=("giai trinh", "ban giai trinh"),
        requires_any=("tang tran", "giam san", "bien dong gia", "lien tiep",
                      "5 phien", "co phieu tang", "co phieu giam"),
    ),
)

RULES_BY_KEY: Dict[str, Rule] = {r.key: r for r in RULES}

#: Cụm phủ định. Có nó thì cờ **nhẹ đi một nửa**, không biến mất: "doanh nghiệp
#: bác bỏ tin bị điều tra" nghĩa là tin đó đã tồn tại và giá đã phản ứng với nó.
#: Riêng nhóm ``tin_don`` không áp dụng — với nhóm đó, "bác bỏ" chính là cái cớ
#: để gắn cờ, hạ tiếp một lần nữa là trừ hai lần cho cùng một chữ.
NEGATIONS = ("khong bi", "chua bi", "khong lien quan", "bac bo", "phu nhan",
             "khong co viec", "bac thong tin", "that thiet", "dinh chinh")
NEGATION_EXEMPT = {"tin_don"}

#: Bài mang tiền tố mã khác ("PAT: Khởi tố Chủ tịch…") vẫn được giữ — công ty
#: mẹ/con dính nhau là chuyện thật — nhưng độ tin cậy giảm còn một nửa.
OTHER_PREFIX_FACTOR = 0.5

#: Những luật mà **ai là chủ thể** quyết định nghĩa của tin. "Khởi tố" trong
#: một bài có thể là chủ tịch của chính doanh nghiệp này, có thể là giám đốc
#: một công ty khác được nhắc trong bài, có thể là kẻ lừa đảo mà ngân hàng này
#: đang cảnh báo khách hàng. Ba trường hợp đó cùng một cụm từ và ngược nghĩa
#: nhau hoàn toàn.
SUBJECT_SENSITIVE = {"hinh_su", "thao_tung", "dieu_tra", "che_tai"}

#: Chức danh trong chính doanh nghiệp. Có một trong số này thì bài đang nói về
#: **người của công ty**, không phải một bên thứ ba được nhắc tên.
SUBJECT_ROLES = (
    "chu tich", "tong giam doc", "pho tong giam doc", "giam doc",
    "hdqt", "hoi dong quan tri", "ban kiem soat", "ke toan truong",
    "lanh dao", "nguoi noi bo", "co dong lon", "thanh vien hdqt",
    "nguoi sang lap", "chu tich hdqt", "ban lanh dao", "cuu chu tich",
    "cuu tong giam doc", "nguyen chu tich", "nguyen tong giam doc",
    "pho chu tich", "tong cong ty", "cong ty me", "cong ty con",
)

#: Bài mà doanh nghiệp đứng ở vai **nạn nhân, nguyên đơn, hoặc người đi cảnh
#: báo**. Đây là nguồn dương tính giả lớn nhất của cả lớp, và nó tập trung ở
#: nhóm ngân hàng: *"ACB cảnh báo 30 kịch bản lừa đảo trực tuyến"*,
#: *"TPBank được Bộ Công an trao Bằng khen"*, *"Hoà Phát đề nghị điều tra thép
#: Trung Quốc bán phá giá"*. Cùng từ khoá, ngược hẳn vai.
PR_VICTIM = (
    "canh bao", "khuyen cao", "kich ban lua dao", "thu doan", "bang khen",
    "khen thuong", "trao bang khen", "phoi hop voi co quan", "ho tro dieu tra",
    "de nghi dieu tra", "yeu cau dieu tra", "khoi xuong dieu tra",
    "bao ve khach hang", "an toan khi", "phong chong toi pham",
    "nang cao canh giac", "chiem doat tai san cua khach", "lua dao truc tuyen",
    "tin nhan gia mao", "website gia mao",
)


def classify(text: str) -> List[Tuple[Rule, str]]:
    """Mọi luật khớp với một đoạn văn bản, nặng trước nhẹ sau."""
    folded = _fold(text)
    out: List[Tuple[Rule, str]] = []
    for rule in RULES:
        hit = rule.match(folded)
        if hit is not None:
            out.append((rule, hit))
    out.sort(key=lambda x: -x[0].weight)
    return out


# ---------------------------------------------------------------------------
# kiểu dữ liệu
# ---------------------------------------------------------------------------
@dataclass
class Flag:
    """Một **ứng viên** cờ: một tiêu đề có thật, một luật, và điểm trừ của máy.

    Cố ý gọi là ứng viên chứ không phải kết luận. Bộ luật ở trên chỉ trả lời
    được *"tiêu đề này có chứa một sự kiện có tên không"*; câu còn lại — *"sự
    kiện đó nghiêng về phía nào **đối với mã đang xét**"* — là việc của
    ``rulings.py``, vì không cụm từ nào đọc được nó (một cuộc điều tra chống
    bán phá giá là tin xấu với bên bị điều tra và tin tốt với bên đề nghị).
    """
    key: str
    label: str
    title: str
    published: str
    session: str = ""
    source: str = ""
    url: str = ""
    post_id: Optional[int] = None
    matched: str = ""                 # cụm đã kích hoạt cờ
    tagged_count: int = 0
    age_days: int = 0
    weight: float = 0.0
    confidence: float = 1.0
    softened: bool = False            # có vế phủ định trong chính tiêu đề
    from_other_symbol: bool = False   # bài đang lưu dưới mã khác
    score: float = 0.0                # điểm đang có hiệu lực, luôn ≥ 0
    #: Điểm của **máy** (weight × confidence × decay), giữ nguyên kể cả sau khi
    #: model chấm lại. Không có nó thì không in được câu "máy chấm −30 → sau
    #: khi đọc −0", mà đúng câu đó mới cho người duyệt thấy có người đã can
    #: thiệp và can thiệp bao nhiêu.
    raw_score: float = 0.0
    title_hash: str = ""              # khoá khử trùng lặp, cũng là khoá phán quyết
    #: ``src.news.rulings.Ruling`` đã hoá dict, hoặc ``None`` = **chưa ai đọc**.
    #: ``None`` không phải "đã đọc và thấy không sao" — hai trạng thái khác nhau
    #: và mọi chỗ in ra phải giữ đúng phân biệt đó.
    ruling: Optional[Dict[str, Any]] = None
    notes: List[str] = field(default_factory=list)

    @property
    def is_critical(self) -> bool:
        return self.key in ("hinh_su", "thao_tung")

    @property
    def ref(self) -> str:
        """Khoá bền của ứng viên này, để model trỏ vào khi phán quyết.

        ``post_id`` khi có — nó là khoá chính của bảng ``posts``. Bài không có
        id (bản ghi cũ) lùi về ``title_hash``, vẫn bền qua các lượt quét vì nó
        tính từ chính tiêu đề.
        """
        if self.post_id is not None:
            return str(self.post_id)
        return f"t{(self.title_hash or _fold(self.title))[:16]}"

    def to_dict(self) -> dict:
        out = asdict(self)
        out["ref"] = self.ref
        return out


@dataclass
class RedFlags:
    """Kết quả quét của một mã trong một cửa sổ."""
    symbol: str
    as_of: str
    window_days: int = WINDOW_DAYS
    flags: List[Flag] = field(default_factory=list)
    penalty: float = 0.0              # điểm trừ, **luôn ≥ 0**
    level: str = LEVEL_CLEAN
    n_scanned: int = 0
    note: str = ""
    #: Ứng viên đã bị model bác (không liên quan / với mã này là tin có lợi).
    #: **Không** bị xoá: một cờ bị bác vẫn phải đọc lại được kèm tên người bác
    #: và lý do, nếu không thì cái bác trở thành thứ không bác lại được.
    dismissed: List[Flag] = field(default_factory=list)
    #: Điểm trừ nếu **không ai đọc** — tức bản thuần cụm từ. In cạnh ``penalty``
    #: để thấy phần chênh là do người can thiệp, không phải do dữ liệu đổi.
    penalty_raw: float = 0.0
    n_judged: int = 0                 # số ứng viên đã có phán quyết
    judged_by: List[str] = field(default_factory=list)   # tên model đã phán

    @property
    def is_empty(self) -> bool:
        return not self.flags

    @property
    def n_candidates(self) -> int:
        """Tổng ứng viên máy bắt được, kể cả những cái đã bị bác."""
        return len(self.flags) + len(self.dismissed)

    @property
    def n_pending(self) -> int:
        """Ứng viên **chưa ai đọc** — vẫn đang mang điểm trừ của máy."""
        return sum(1 for f in self.flags if not f.ruling)

    @property
    def fully_judged(self) -> bool:
        return self.n_candidates > 0 and self.n_pending == 0

    @property
    def level_label(self) -> str:
        return LEVEL_VN.get(self.level, self.level)

    @property
    def keys(self) -> List[str]:
        """Các nhóm đã dính, nặng trước — dùng cho nhãn một dòng."""
        seen: List[str] = []
        for f in self.flags:
            if f.key not in seen:
                seen.append(f.key)
        return seen

    @property
    def headline(self) -> str:
        """Một dòng: mức cờ + các nhóm đã dính. Rỗng khi sạch."""
        if self.is_empty:
            return ""
        labels = [RULES_BY_KEY[k].label for k in self.keys if k in RULES_BY_KEY]
        return (f"{self.level_label} · −{self.penalty:.0f} điểm · "
                + " · ".join(labels))

    @property
    def has_critical(self) -> bool:
        """Có cờ hình sự / thao túng — mức không được phép đứng sau một nhãn tăng."""
        return any(f.is_critical for f in self.flags)

    def has(self, key: str) -> bool:
        return any(f.key == key for f in self.flags)

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol, "as_of": self.as_of,
            "window_days": self.window_days, "penalty": self.penalty,
            "penalty_raw": self.penalty_raw,
            "level": self.level, "n_scanned": self.n_scanned,
            "note": self.note, "n_judged": self.n_judged,
            "judged_by": list(self.judged_by),
            "flags": [f.to_dict() for f in self.flags],
            "dismissed": [f.to_dict() for f in self.dismissed],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RedFlags":
        raw = dict(data or {})
        flags = raw.pop("flags", None) or []
        dismissed = raw.pop("dismissed", None) or []
        known = set(cls.__dataclass_fields__)
        out = cls(**{k: v for k, v in raw.items() if k in known})

        def _flags(items):
            return [Flag(**{k: v for k, v in f.items()
                            if k in Flag.__dataclass_fields__})
                    for f in items if isinstance(f, dict)]

        out.flags = _flags(flags)
        out.dismissed = _flags(dismissed)
        return out


# ---------------------------------------------------------------------------
# chấm điểm
# ---------------------------------------------------------------------------
#: Độ cũ → hệ số. Khởi tố sáu tháng trước vẫn là khởi tố, nên đuôi không về 0;
#: nhưng một tin đồn của tháng Ba thì đã có hai quý để thị trường tiêu hoá.
DECAY = ((30.0, 1.0), (60.0, 0.9), (90.0, 0.8), (180.0, 0.65), (365.0, 0.5))


def decay_factor(age_days: int) -> float:
    if age_days <= DECAY[0][0]:
        return DECAY[0][1]
    for (x0, y0), (x1, y1) in zip(DECAY, DECAY[1:]):
        if age_days <= x1:
            span = x1 - x0
            return y0 if span == 0 else y0 + (y1 - y0) * (age_days - x0) / span
    return DECAY[-1][1]


#: Cờ thuộc nhóm nhạy chủ thể mà không tìm được chức danh nào của doanh nghiệp
#: trong bài. Giữ lại — người đọc vẫn cần biết là có — nhưng chỉ một phần tư
#: điểm, vì không chứng minh được bài đang nói về người của mã này.
WEAK_SUBJECT_FACTOR = 0.25


#: Chủ thể rõ tới đâu → nhân với trọng số của luật. Bốn nấc, và nấc nào cũng
#: **giữ cờ lại** — khác nhau ở điểm trừ, không ở chỗ có hiện hay không.
#:
#:   1,00  tiền tố mã của chính mình **và** có chức danh
#:         → *"DGC: Tổng giám đốc DGC Lưu Bách Đạt … sau khi bị khởi tố"*
#:   0,55  có chức danh nhưng bài không mang tiền tố mã
#:         → *"Bắt Giám đốc Mekolor…"* nằm trong feed của CTG: đúng là có một
#:           giám đốc bị bắt, nhưng không có gì nói đó là giám đốc của CTG
#:   0,50  có tiền tố mã nhưng chủ thể không phải lãnh đạo
#:         → *"MWG: Nhân viên Thế Giới Di Động chiếm đoạt 84 điện thoại"*
#:   0,25  không có cả hai
SUBJECT_FACTORS = {"role+prefix": 1.0, "role": 0.55, "prefix": 0.5, "none": 0.25}

#: Áp cho các luật **không** nhạy chủ thể khi bài không mang tiền tố mã.
#:
#: Đo trên kho: đây là nguồn nhiễu lớn nhất còn lại của nhóm "triển vọng xấu".
#: Feed của VIC chứa *"Việt An tăng đòn bẩy…"* và *"Thép Pomina vẫn kẹt…"*;
#: feed của DCM chứa *"Ngành phân bón phía Nam phân hoá mạnh"*. Cả ba là tin
#: thật, về doanh nghiệp khác, và ở hệ số 0,6 chúng trừ 10 điểm mỗi bài.
NO_PREFIX_FACTOR = 0.45

#: Chủ thể là người của công ty nhưng **không phải người điều hành**. Nhân
#: viên lấy trộm hàng là rủi ro vận hành, không phải rủi ro doanh nghiệp — và
#: −50 điểm cho *"Phanh phui nhóm tài xế rút ruột Xanh SM"* là sai bậc.
MINOR_SUBJECTS = ("nhan vien", "tai xe", "cong nhan", "shipper", "dai ly",
                  "nguoi dung", "khach hang", "moi gioi", "can bo")

#: Cụm hạ nhẹ: cơ quan quản lý mới **nhắc nhở**, chưa ra quyết định xử phạt.
#: Cùng cơ chế với ``NEGATIONS`` — nửa điểm, không phải bỏ cờ.
MINOR_MARKERS = ("nhac nho", "luu y nha dau tu", "canh bao som")


def confidence_for(tagged_count: int, is_disclosure: bool,
                   other_prefix: bool, subject_sensitive: bool = False,
                   has_role: bool = False) -> Tuple[float, List[str]]:
    """Bài này nói về **mã này** tới mức nào.

    Không phải phép đo mức độ nghiêm trọng — đó là ``weight``. Đây là câu hỏi
    khác, và nó có hai vế:

    1. *Bài có phải của riêng mã này không* — bài gắn 15 mã là điểm tin cả rổ,
       quy một vụ khởi tố trong đó cho riêng mã này là đọc nhiễu thành tín hiệu.
    2. *Chủ thể có phải người của doanh nghiệp không* — với nhóm nhạy chủ thể
       (hình sự, thao túng, điều tra, chế tài) thì đây là vế quyết định. Bản
       CBTT do chính doanh nghiệp công bố là bằng chứng mạnh nhất; sau đó là
       bài có nêu chức danh ("chủ tịch", "tổng giám đốc", "lãnh đạo"). Không có
       cả hai thì cờ vẫn hiện, nhưng chỉ tính ``WEAK_SUBJECT_FACTOR``.

    Vẫn giữ cờ trong mọi trường hợp: bỏ sót là lỗi không sửa được, còn một cờ
    vàng thừa thì người đọc bác trong mười giây.
    """
    notes: List[str] = []
    if is_disclosure or tagged_count <= 1:
        conf = 1.0
    elif tagged_count <= 3:
        conf = 0.85
        notes.append(f"bài gắn {tagged_count} mã")
    else:
        conf = 0.4
        notes.append(f"bài gắn {tagged_count} mã — nhiều khả năng là điểm tin "
                     f"cả rổ, không phải tin của riêng mã này")
    if other_prefix:
        conf *= OTHER_PREFIX_FACTOR
        notes.append("tiêu đề mang tiền tố của mã khác")
    if not subject_sensitive and not is_disclosure:
        # Ngay cả những luật không phụ thuộc chủ thể vẫn cần biết bài đang nói
        # về ai: *"Xây dựng Hoà Bình nợ ngắn hạn gấp 29 lần tiền mặt"* nằm
        # trong feed của MSB, *"SSI và nhiều công ty chứng khoán cắt margin
        # PNJ"* nằm trong feed của SSI. Cả hai đều là tin thật, về mã khác.
        conf *= NO_PREFIX_FACTOR
        notes.append("bài không mang tiền tố mã — có thể đang nói về doanh "
                     "nghiệp khác được nhắc trong cùng bài")
    if subject_sensitive:
        if has_role and is_disclosure:
            key = "role+prefix"
        elif has_role:
            key = "role"
            notes.append("có nêu chức danh nhưng bài không mang tiền tố mã — "
                         "chưa chắc chức danh đó là của doanh nghiệp này")
        elif is_disclosure:
            key = "prefix"
            notes.append("bài về đúng mã này nhưng chủ thể không phải lãnh đạo")
        else:
            key = "none"
            notes.append("không xác định được chủ thể là người của doanh nghiệp "
                         "này — cờ giữ lại để không bỏ sót, điểm trừ chỉ tính "
                         "một phần")
        conf *= SUBJECT_FACTORS[key]
    return conf, notes


def aggregate(flags: Sequence[Flag]) -> float:
    """Gộp nhiều cờ thành **một** điểm trừ, chặn ở ``MAX_PENALTY``.

    Không cộng thẳng: một vụ khởi tố thường kéo theo 8 bài trong hai tuần, và
    cộng tuyến tính biến một sự kiện thành bốn trăm điểm trừ. Cờ nặng nhất tính
    đủ, phần còn lại tính ``EXTRA_WEIGHT`` — đủ để hai sự kiện độc lập nặng hơn
    một, chưa tới mức mật độ đưa tin thay thế mức độ nghiêm trọng.
    """
    return aggregate_scores([f.score for f in flags])


def aggregate_scores(values: Sequence[float]) -> float:
    """Phần số học của ``aggregate``, tách ra để gộp được cả điểm chưa gắn cờ.

    ``rulings.apply`` cần gộp **hai** tập trên cùng một công thức: điểm sau khi
    đọc và điểm gốc của máy. Dựng lại một danh sách ``Flag`` giả chỉ để gọi
    ``aggregate`` là trả giá cho một lớp bọc không nói thêm gì.
    """
    scores = sorted((v for v in values if v), reverse=True)
    if not scores:
        return 0.0
    top = scores[0]
    # Phần đuôi bị chặn ở **một nửa** cờ nặng nhất. Không có chốt này thì mật
    # độ đưa tin thay thế mức độ nghiêm trọng: một án phạt thuế 25 điểm cộng
    # thêm mười đầu mục lặt vặt cũng chạm trần 50, đứng ngang một vụ khởi tố.
    # Mức cao nhất phải dành cho **một** sự kiện thật sự nặng.
    extra = min(EXTRA_CAP_RATIO * top, EXTRA_WEIGHT * sum(scores[1:]))
    return round(min(MAX_PENALTY, top + extra), 1)


def level_for(penalty: float) -> str:
    if penalty >= LEVEL_CRITICAL_MIN:
        return LEVEL_CRITICAL
    if penalty >= LEVEL_WARN_MIN:
        return LEVEL_WARN
    if penalty > 0:
        return LEVEL_NOTE
    return LEVEL_CLEAN


# ---------------------------------------------------------------------------
# quét
# ---------------------------------------------------------------------------
def _prefix_symbol(title: str) -> str:
    """``"PAT: Khởi tố…"`` → ``"PAT"``. Rỗng khi tiêu đề không có tiền tố mã.

    Dùng ``isalnum`` chứ không phải ``isalpha``: **PC1**, **SJ1**, **TV2** là mã
    thật và đều có chữ số. Cùng lỗi này đang nằm trong
    ``posts.DISCLOSURE_PREFIX`` (``^([A-Z]{3}):``) nên cột ``is_disclosure``
    trong kho luôn sai với nhóm mã đó — vì thế ở đây **không** đọc cột ấy mà
    tự tính lại tiền tố, và tính so với mã đang quét chứ không phải mã mà bài
    tình cờ được lưu dưới.
    """
    head = str(title or "")[:5]
    if len(head) >= 4 and head[3] == ":" and head[:3].isalnum():
        return head[:3].upper()
    return ""


def scan_rows(symbol: str, rows: Sequence[Dict[str, Any]],
              as_of_date: datetime, max_flags: int = 30) -> List[Flag]:
    """Các bản ghi ``posts`` → danh sách cờ, đã khử trùng lặp.

    Khử trùng lặp theo ``title_hash`` và **giữ bản sớm nhất**: báo Việt chép
    chéo nhau, một tin ra 8 bản (§9.4), và bản sớm nhất mới là ngày tin thật sự
    ra thị trường — thứ mà độ cũ của cờ dựa vào.
    """
    sym = symbol.strip().upper()
    best: Dict[str, Flag] = {}
    for row in rows:
        title = str(row.get("title") or "")
        desc = str(row.get("description") or "")
        blob = f"{title} . {desc}"
        folded = _fold(blob)
        matches = classify(blob)
        # Vai nạn nhân / nguyên đơn / đi cảnh báo thì loại đúng những luật mà
        # chủ thể quyết định nghĩa, chứ không loại cả bài: cùng một bài vẫn có
        # thể mang một cờ thuộc nhóm khác, và bỏ cả bài là bỏ luôn cờ đó.
        if any(_has(folded, p) for p in PR_VICTIM):
            matches = [(r, h) for r, h in matches
                       if r.key not in SUBJECT_SENSITIVE]
        if not matches:
            continue

        published = str(row.get("date") or "")
        day = published[:10]
        try:
            age = max(0, (as_of_date - datetime.strptime(day, "%Y-%m-%d")).days)
        except ValueError:
            age = 0

        tags = row.get("tagged_symbols") or []
        prefix = _prefix_symbol(title)
        rule, hit = matches[0]
        conf, notes = confidence_for(
            tagged_count=len(tags),
            is_disclosure=(prefix == sym),
            other_prefix=bool(prefix and prefix != sym),
            subject_sensitive=rule.key in SUBJECT_SENSITIVE,
            has_role=(any(_has(folded, r) for r in SUBJECT_ROLES)
                      and not any(_has(folded, m) for m in MINOR_SUBJECTS)),
        )
        if (rule.key in SUBJECT_SENSITIVE
                and any(_has(folded, m) for m in MINOR_SUBJECTS)):
            conf *= SUBJECT_FACTORS["none"] / SUBJECT_FACTORS["prefix"]
            notes.append("chủ thể là nhân viên/đối tác, không phải người điều "
                         "hành — rủi ro vận hành, không phải rủi ro doanh nghiệp")

        negated = (rule.key not in NEGATION_EXEMPT
                   and any(_has(folded, n) for n in NEGATIONS))
        minor = any(_has(folded, m) for m in MINOR_MARKERS)
        softened = negated or minor
        score = rule.weight * conf * decay_factor(age)
        if negated:
            score *= 0.5
            notes.append("tiêu đề có vế phủ định/bác bỏ — cờ giữ lại vì tin đã "
                         "ra thị trường, nhưng chỉ tính nửa điểm")
        if minor:
            score *= 0.5
            notes.append("mới ở mức nhắc nhở, chưa phải quyết định xử lý")
        if len(matches) > 1:
            notes.append("còn khớp: "
                         + ", ".join(r.label for r, _ in matches[1:4]))

        key = str(row.get("title_hash") or _fold(title))
        flag = Flag(
            key=rule.key, label=rule.label, title=title.strip(),
            published=published, session=day,
            source=str(row.get("source") or ""),
            url=str(row.get("source_url") or ""),
            post_id=row.get("post_id"), matched=hit,
            tagged_count=len(tags), age_days=age, weight=rule.weight,
            confidence=round(conf, 2), softened=softened,
            from_other_symbol=(str(row.get("symbol") or "").upper() != sym),
            score=round(score, 2), raw_score=round(score, 2),
            title_hash=key, notes=notes,
        )
        current = best.get(key)
        if current is None or flag.published < current.published:
            best[key] = flag

    ordered = sorted(best.values(), key=lambda f: (-f.score, f.published))
    return ordered[:max_flags]


def build(symbol: str, as_of: Optional[datetime] = None,
          window_days: int = WINDOW_DAYS, conn=None,
          db_path=None, max_flags: int = 30) -> RedFlags:
    """Quét cờ đỏ cho một mã. Đọc file, không chạm mạng.

    ``conn`` cho phép tầng gọi mở **một** kết nối rồi quét cả rổ — quét 79 mã
    mà mở 79 kết nối là trả giá cho không.
    """
    sym = symbol.strip().upper()
    end = as_of or datetime.now()
    since = (end - timedelta(days=max(1, window_days))).strftime("%Y-%m-%d")
    cutoff = end.strftime("%Y-%m-%d")

    out = RedFlags(symbol=sym, as_of=cutoff, window_days=window_days)

    def _scan(c) -> List[Dict[str, Any]]:
        return store_mod.load_posts_mentioning(
            c, sym, since=since, as_of=cutoff, limit=1500)

    if conn is not None:
        rows = _scan(conn)
    else:
        with store_mod.connect(db_path) as c:
            rows = _scan(c)

    out.n_scanned = len(rows)
    out.flags = scan_rows(sym, rows, end, max_flags=max_flags)
    out.penalty = aggregate(out.flags)
    out.level = level_for(out.penalty)
    if not rows:
        out.note = ("Không có bài nào trong cửa sổ — kho tin có thể chưa nạp tới "
                    "mốc này. Trống **không** đồng nghĩa với sạch cờ.")
    return out


def build_many(symbols: Sequence[str], as_of: Optional[datetime] = None,
               window_days: int = WINDOW_DAYS, db_path=None,
               max_flags: int = 30) -> Dict[str, RedFlags]:
    """Quét cả rổ trên **một** kết nối."""
    out: Dict[str, RedFlags] = {}
    with store_mod.connect(db_path) as conn:
        for sym in symbols:
            key = str(sym).strip().upper()
            try:
                out[key] = build(key, as_of=as_of, window_days=window_days,
                                 conn=conn, max_flags=max_flags)
            except Exception as exc:            # noqa: BLE001
                out[key] = RedFlags(
                    symbol=key,
                    as_of=(as_of or datetime.now()).strftime("%Y-%m-%d"),
                    window_days=window_days,
                    note=f"không quét được: {type(exc).__name__}: {exc}")
    return out
