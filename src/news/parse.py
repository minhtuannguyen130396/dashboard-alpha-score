"""Chuyển payload thô của FireAnt thành dataclass, và parse chuỗi ``title``.

Ranh giới cố ý: module này **không gọi mạng** và **không đọc đĩa**. Cho nó một
dict, nó trả một dataclass. Nhờ vậy test chạy được trên fixture nằm sẵn trên đĩa
mà không cần mock HTTP.

Phần dễ gãy nhất ở đây là ``parse_mark_title``. ``timescale-marks`` trả về chuỗi
viết cho người đọc chứ không phải dữ liệu — format đổi là regex gãy. Nên hàm này
trả về dict *rỗng* khi không khớp thay vì ném lỗi, và bản gốc luôn được giữ ở
``raw_title``: mất phần parse thì vẫn còn đọc được bằng mắt, mất bản gốc thì mất hẳn.
"""
import re
from typing import Any, Dict, List, Optional

from src.news.models import SRC_SWAGGER, HolderTransaction, TimescaleMark

# "Ngày KHQ: 28/05/2026"
_RE_KHQ = re.compile(r"Ngày\s+KHQ\s*:\s*(\d{1,2}/\d{1,2}/\d{4})", re.IGNORECASE)
# "tỷ lệ 1.000đ/CP"  |  "tỷ lệ 15%"
_RE_TY_LE_TIEN = re.compile(r"tỷ\s*lệ\s*([\d.,]+)\s*đ\s*/\s*CP", re.IGNORECASE)
_RE_TY_LE_PCT = re.compile(r"tỷ\s*lệ\s*([\d.,]+)\s*%")
# "DT: 20.225,5 tỷ, +14,9% (vs. Q4/24)"
_RE_DT = re.compile(r"DT:\s*([\d.,]+)\s*tỷ,\s*([+-][\d.,]+)%")
_RE_LN = re.compile(r"LN:\s*([\d.,]+)\s*tỷ,\s*([+-][\d.,]+)%")
# "BCTC quý 4/2025" | "BCTC năm 2025"
_RE_KY_QUY = re.compile(r"BCTC\s+quý\s+(\d)\s*/\s*(\d{4})", re.IGNORECASE)
_RE_KY_NAM = re.compile(r"BCTC\s+năm\s+(\d{4})", re.IGNORECASE)


def _num(text: str) -> Optional[float]:
    """Đọc số kiểu Việt Nam: '20.225,5' -> 20225.5, '+14,9' -> 14.9."""
    if text is None:
        return None
    cleaned = text.strip().replace(".", "").replace(",", ".")
    try:
        return float(cleaned)
    except ValueError:
        return None


def parse_mark_title(title: str) -> Dict[str, Any]:
    """Rút số từ chuỗi ``title`` của một mốc. Không khớp thì trả dict rỗng."""
    if not title:
        return {}
    out: Dict[str, Any] = {}

    m = _RE_KY_QUY.search(title)
    if m:
        out["quarter"], out["year"] = int(m.group(1)), int(m.group(2))
    else:
        m = _RE_KY_NAM.search(title)
        if m:
            out["quarter"], out["year"] = 0, int(m.group(1))

    m = _RE_DT.search(title)
    if m:
        out["doanh_thu_ty"] = _num(m.group(1))
        out["doanh_thu_yoy_pct"] = _num(m.group(2))
    m = _RE_LN.search(title)
    if m:
        out["loi_nhuan_ty"] = _num(m.group(1))
        out["loi_nhuan_yoy_pct"] = _num(m.group(2))

    m = _RE_KHQ.search(title)
    if m:
        out["ngay_gdkhq"] = m.group(1)
    m = _RE_TY_LE_TIEN.search(title)
    if m:
        out["co_tuc_tien_dong"] = _num(m.group(1))
    m = _RE_TY_LE_PCT.search(title)
    if m:
        out["co_tuc_ty_le_pct"] = _num(m.group(1))

    return out


def parse_holder_transaction(row: dict, symbol: str) -> Optional[HolderTransaction]:
    """Một dòng ``MajorHolderTransaction`` -> dataclass.

    ``direction`` lấy thẳng field ``type`` vì đặc tả API định nghĩa enum này
    tường minh — nên ``direction_source`` là ``swagger_enum``, không phải suy đoán.
    Dòng thiếu ``type`` bị bỏ: không biết chiều thì bản ghi vô dụng cho mọi
    thống kê sau này, giữ lại chỉ tổ lẫn vào số liệu.
    """
    if row is None or row.get("type") is None:
        return None
    tid = row.get("transactionID")
    if tid is None:
        return None
    return HolderTransaction(
        transaction_id=int(tid),
        symbol=row.get("symbol") or symbol,
        name=row.get("name") or "",
        position=row.get("position"),
        direction=int(row["type"]),
        direction_source=SRC_SWAGGER,
        registered_volume=row.get("registeredVolume"),
        execution_volume=row.get("executionVolume"),
        start_date=row.get("startDate"),
        end_date=row.get("endDate"),
        execution_date=row.get("executionDate"),
        major_holder_id=row.get("majorHolderID"),
        individual_holder_id=row.get("individualHolderID"),
        institution_holder_id=row.get("institutionHolderID"),
        is_organization=row.get("isOrganization"),
    )


def parse_timescale_mark(row: dict, symbol: str) -> Optional[TimescaleMark]:
    if row is None or not row.get("id"):
        return None
    title = row.get("title") or ""
    return TimescaleMark(
        mark_id=str(row["id"]),
        symbol=symbol,
        label=row.get("label") or "",
        date=row.get("date") or "",
        raw_title=title,
        parsed=parse_mark_title(title),
    )


def parse_holder_transactions(rows: List[dict], symbol: str) -> List[HolderTransaction]:
    out = [parse_holder_transaction(r, symbol) for r in rows or []]
    return [x for x in out if x is not None]


def parse_timescale_marks(rows: List[dict], symbol: str) -> List[TimescaleMark]:
    out = [parse_timescale_mark(r, symbol) for r in rows or []]
    return [x for x in out if x is not None]
