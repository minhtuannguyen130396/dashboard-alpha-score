"""Chế độ hồi tưởng — giả định "hôm nay" là một phiên trong quá khứ.

Cắt chuỗi giá tại một ngày là việc ``loader.load_recent`` đã làm được. Ba thứ
mà riêng phép cắt đó không cho, module này giữ:

* **Đọc ngày người dùng gõ.** Người Việt viết ``01/01/2025``, không phải
  ``2025-01-01``. Ngày đứng trước tháng, nên ``05/03/2025`` là mùng 5 tháng 3,
  không bao giờ là 3 tháng 5. Dạng ISO vẫn là ISO — phân biệt bằng số chữ số
  của nhóm đầu, không đoán theo giá trị.
* **Dán nhãn.** Mở một file HTML hồi tưởng ra, nó trông y hệt báo cáo thật.
  Mọi artefact phải nói rõ *giả định hôm nay là ngày nào* và *dữ liệu thật sự
  dừng ở phiên nào* — hai con số này lệch nhau mỗi khi mốc rơi vào ngày nghỉ
  (chọn 01/01/2025 thì phiên cuối là 31/12/2024).
* **Chỗ để file.** Bản hồi tưởng đi vào ``reports/asof_<ngày>/`` chứ không phải
  ``reports/<hôm nay>/``: chạy lại cùng một mốc ở hai ngày khác nhau vẫn ra
  cùng một chỗ, và không bao giờ đè lên báo cáo của phiên thật.

Cắt giá là điều kiện cần nhưng chưa đủ để replay trung thực. Forecast nằm trên
đĩa được tạo *sau* mốc hồi tưởng và trạng thái của chúng tính từ những phiên mà
bản replay lẽ ra không được biết. Nên phía gọi phải lọc theo ``created <= as_of``
rồi đánh giá lại **mà không ghi xuống đĩa** — một lần kiểm tra hồi tưởng không
được phép tua ngược trạng thái forecast đang sống.

Mốc rơi vào hôm nay hoặc tương lai được coi là *không có mốc*: "giả định hôm nay
là hôm nay" chính là chế độ thường, và trả ``None`` ở đây giúp mọi tầng trên chỉ
phải kiểm tra đúng một điều kiện (``as_of is None`` = chạy thật).
"""
import re
import unicodedata
from datetime import date, datetime, time
from pathlib import Path
from typing import Optional, Union

#: Chữ người dùng gõ khi họ *không* muốn mốc nào cả.
LIVE_WORDS = {
    "", "-", "none", "null",
    "hom nay", "today", "now", "live", "moi nhat", "hien tai", "gan nhat",
}

#: Năm sớm nhất thư mục ``data/`` có thể trả lời.
FIRST_YEAR = 2010

_ISO = re.compile(r"^(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})$")
_DMY = re.compile(r"^(\d{1,2})[-/.](\d{1,2})[-/.](\d{2}|\d{4})$")
_COMPACT = re.compile(r"^(\d{4})(\d{2})(\d{2})$")
_PREFIX = re.compile(r"^(ngay|phien|tinh den|den|as of|asof)\s+", re.IGNORECASE)


def _fold(text: str) -> str:
    """Bỏ dấu và hạ chữ thường — để ``Hôm Nay`` và ``hom nay`` là một."""
    stripped = "".join(
        c for c in unicodedata.normalize("NFD", text)
        if unicodedata.category(c) != "Mn"
    )
    return " ".join(stripped.replace("đ", "d").replace("Đ", "D").lower().split())


def parse(value: Union[str, datetime, date, None]) -> Optional[datetime]:
    """Mốc hồi tưởng từ thứ người dùng gõ, hoặc ``None`` nếu chạy thật.

    Trả về mốc đã đẩy tới **cuối ngày**: bản ghi giá đóng dấu 00:00 nên mốc
    23:59:59 mới lấy trọn phiên của chính ngày đó vào.
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        return _finish(value.year, value.month, value.day)
    if isinstance(value, date):
        return _finish(value.year, value.month, value.day)

    raw = str(value).strip()
    folded = _fold(raw)
    if folded in LIVE_WORDS:
        return None
    folded = _PREFIX.sub("", folded).strip()
    if folded in LIVE_WORDS:
        return None

    text = folded.split()[0] if folded else ""      # bỏ phần giờ nếu có
    head = text.split("t", 1)[0]                    # 2025-01-01T09:00 → 2025-01-01
    if _ISO.match(head):
        text = head

    m = _ISO.match(text)
    if m:
        year, month, day = (int(g) for g in m.groups())
    else:
        m = _DMY.match(text)
        if m:
            day, month, year = (int(g) for g in m.groups())
            if year < 100:
                year += 2000
        else:
            m = _COMPACT.match(text)
            if not m:
                raise ValueError(
                    f"Không đọc được mốc thời gian {raw!r}. "
                    "Dùng 01/01/2025 (ngày/tháng/năm) hoặc 2025-01-01."
                )
            year, month, day = (int(g) for g in m.groups())

    try:
        parsed = date(year, month, day)
    except ValueError as exc:
        raise ValueError(f"Ngày không tồn tại: {raw!r} ({exc})") from exc
    if parsed.year < FIRST_YEAR:
        raise ValueError(
            f"Mốc {label(parsed)} nằm trước {FIRST_YEAR} — dữ liệu giá bắt đầu từ {FIRST_YEAR}."
        )
    return _finish(parsed.year, parsed.month, parsed.day)


def _finish(year: int, month: int, day: int) -> Optional[datetime]:
    """Cuối ngày, hoặc ``None`` khi mốc là hôm nay trở đi (= chạy thật)."""
    if date(year, month, day) >= date.today():
        return None
    return datetime.combine(date(year, month, day), time(23, 59, 59))


def label(value: Union[datetime, date, None]) -> str:
    """``2025-01-01`` — dạng ngày dùng thống nhất trong mọi nhãn và tên file."""
    if value is None:
        return ""
    return value.strftime("%Y-%m-%d")


def out_root(base: Path, as_of: Optional[datetime] = None,
             out_dir: Optional[str] = None) -> Path:
    """Thư mục ghi artefact: ``asof_<ngày>`` khi hồi tưởng, ``<hôm nay>`` khi chạy thật."""
    if out_dir:
        root = Path(out_dir)
    elif as_of is not None:
        root = base / f"asof_{label(as_of)}"
    else:
        root = base / datetime.now().strftime("%Y-%m-%d")
    root.mkdir(parents=True, exist_ok=True)
    return root


def file_tag(as_of: Optional[datetime] = None) -> str:
    """Đuôi tên file. Chạy thật lấy giờ; hồi tưởng lấy chính mốc đó.

    Cố ý *không* lấy giờ cho bản hồi tưởng: cùng một mốc, cùng một bộ mã thì ra
    đúng cùng một file — chạy lại là ghi đè chứ không rải thêm bản trùng nội dung.
    """
    if as_of is not None:
        return f"asof_{label(as_of)}"
    return datetime.now().strftime("%H%M")


def before(as_of: Optional[datetime], day: Optional[str]) -> bool:
    """``day`` (chuỗi ``YYYY-MM-DD``) có nằm trong tầm nhìn của mốc không."""
    if as_of is None or not day:
        return True
    return day[:10] <= label(as_of)
