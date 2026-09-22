"""Client FireAnt cho phần tin tức và sự kiện — mỏng, có rate limit, có retry.

Khác ``src/ta/update.py`` (chỉ lo giá) ở chỗ nó gọi các endpoint mà đặc tả
``/swagger/docs/v1`` mô tả nhưng repo chưa từng dùng. Hai endpoint dễ nhầm nhất,
ghi ở đây để khỏi phải tra lại:

* ``/symbols/{s}/transactions``        — giao dịch của **chính tổ chức** (cổ phiếu quỹ)
* ``/symbols/{s}/holder-transactions`` — giao dịch của **cổ đông lớn / người nội bộ**

Cái thứ hai mới là thứ tầng tin tức cần. Dò nhầm sang cái thứ nhất là lý do
lượt khảo sát đầu tiên tưởng rằng dữ liệu không có ``position`` và rằng đăng ký
với thực hiện nằm ở hai dòng khác nhau.
"""
import time
from typing import Any, Dict, List, Optional

import requests

from src.data.fireant_history_fetcher import build_headers

BASE_URL = "https://restv2.fireant.vn"

#: Nghỉ giữa hai request cùng host. FireAnt không công bố hạn mức, nên giữ
#: nhịp lịch sự thay vì dò xem chịu được tới đâu.
RATE_DELAY = 1.2

_MAX_ATTEMPTS = 3
_RETRY_STATUS = {429, 500, 502, 503, 504}

_last_call = 0.0


def _throttle() -> None:
    global _last_call
    gap = time.monotonic() - _last_call
    if gap < RATE_DELAY:
        time.sleep(RATE_DELAY - gap)
    _last_call = time.monotonic()


def get(path: str, params: Optional[Dict[str, Any]] = None,
        timeout: int = 25) -> Any:
    """GET một endpoint FireAnt, trả payload đã parse.

    Retry đúng những status FireAnt thật sự trả khi quá tải; 4xx (trừ 429) thì
    hỏng là hỏng, thử lại chỉ tốn thêm request.
    """
    url = f"{BASE_URL}{path}"
    headers = build_headers()
    last_error = None
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        _throttle()
        try:
            response = requests.get(url, headers=headers, params=params or {},
                                    timeout=timeout)
            if response.status_code in _RETRY_STATUS and attempt < _MAX_ATTEMPTS:
                time.sleep(1.5 * attempt)
                continue
            response.raise_for_status()
            return response.json()
        except (requests.Timeout, requests.ConnectionError) as exc:
            last_error = exc
            if attempt < _MAX_ATTEMPTS:
                time.sleep(1.5 * attempt)
                continue
            raise
    if last_error:
        raise last_error
    return None


def _as_list(payload: Any) -> List[dict]:
    return payload if isinstance(payload, list) else []


def holder_transactions(symbol: str, start_date: Optional[str] = None,
                        end_date: Optional[str] = None,
                        executed_only: bool = False,
                        offset: int = 0, limit: int = 100) -> List[dict]:
    """Giao dịch Mua/Bán của cổ đông lớn và người nội bộ.

    ``executed_only=True`` bỏ các đăng ký chưa thực hiện — hữu ích khi chỉ muốn
    giao dịch đã xảy ra, nhưng **mặc định để False**: đăng ký-rồi-không-làm tự
    nó là một tín hiệu, cắt đi là mất.
    """
    params = {"offset": offset, "limit": limit}
    if start_date:
        params["startDate"] = start_date
    if end_date:
        params["endDate"] = end_date
    if executed_only:
        params["executedOnly"] = "true"
    return _as_list(get(f"/symbols/{symbol}/holder-transactions", params))


def timescale_marks(symbol: str, start_date: str, end_date: str) -> List[dict]:
    """Mốc sự kiện theo thời gian (BCTC, cổ tức). Cả hai ngày đều bắt buộc."""
    return _as_list(get(f"/symbols/{symbol}/timescale-marks",
                        {"startDate": start_date, "endDate": end_date}))


def officers(symbol: str) -> List[dict]:
    """Ban lãnh đạo — từ điển tên người để khớp với ``holder_transactions``."""
    return _as_list(get(f"/symbols/{symbol}/officers"))


def holders(symbol: str) -> List[dict]:
    """Cơ cấu cổ đông lớn. Snapshot hôm nay, không phải chuỗi lịch sử."""
    return _as_list(get(f"/symbols/{symbol}/holders"))


def fundamental(symbol: str) -> Optional[dict]:
    """Chỉ số cơ bản. ``freeShares`` và ``avgVolume*`` là mẫu số bắt buộc để
    chuẩn hoá quy mô giao dịch nội bộ — số tuyệt đối một mình vô nghĩa."""
    payload = get(f"/symbols/{symbol}/fundamental")
    return payload if isinstance(payload, dict) else None


def posts(symbol: str, kind: int = 1, offset: int = 0,
          limit: int = 20) -> List[dict]:
    """Bài viết liên quan tới mã. ``kind``: 0 = mạng xã hội, 1 = tin tức.

    Response **không** mang toàn văn — phải gọi ``post_detail`` cho từng bài.
    """
    return _as_list(get(f"/symbols/{symbol}/posts",
                        {"type": kind, "offset": offset, "limit": limit}))


def post_detail(post_id: int) -> Optional[dict]:
    """Toàn văn một bài. Tốn một request riêng nên bắt buộc cache theo id."""
    payload = get(f"/posts/{post_id}")
    return payload if isinstance(payload, dict) else None
