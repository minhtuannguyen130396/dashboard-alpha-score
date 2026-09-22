"""Khung tuần: cùng một chuỗi giá, nhìn ở độ phân giải thô hơn.

Vì sao cần thêm một khung khi đã có nến ngày: EMA20 ngày là ý kiến về *hai
mươi phiên*, tức chưa đầy một tháng. Một mã nằm trên EMA20 ngày mà vẫn dưới
MA20 **tuần** đang ở giữa một nhịp hồi trong xu hướng giảm trung hạn — nến ngày
một mình không phân biệt được chuyện đó với một xu hướng tăng thật.

Hai quyết định thiết kế:

1. **Gộp bằng tuần ISO, không phải "mỗi 5 phiên".** Đếm 5 phiên một cục thì
   một tuần nghỉ lễ (Tết nghỉ 5–9 phiên) làm lệch pha toàn bộ chuỗi phía sau,
   và mọi cây nến tuần sau đó là một cửa sổ trượt không trùng với tuần nào có
   thật. ``date.isocalendar()[:2]`` cho đúng ranh giới thứ Hai–thứ Sáu.

2. **Cây nến tuần mang ngày của phiên CUỐI trong tuần.** Tuần đang chạy dở
   (hôm nay là thứ Tư) vẫn là một cây nến hợp lệ — chỉ là nó chưa đóng. Gắn
   ngày cuối tuần thật vào một tuần chưa xong là ghi ra một phiên chưa tồn
   tại, nên ``partial`` nói thẳng tuần cuối đã đóng hay chưa thay vì giấu.
"""
from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence

from src.analysis.technical_indicators import IndicatorGroup1, IndicatorGroup2, IndicatorGroup3
from src.data.stock_data_loader import StockRecord
from src.ta.loader import load_recent
from src.ta.swings import RANGE, TREND_NAMES, build_market_structure

#: Số ngày lịch cần nạp để EMA50 **tuần** có giá trị. 50 tuần ≈ 350 ngày, cộng
#: quãng mồi cho EMA ổn định và các tuần nghỉ lễ → 3 năm là mức an toàn mà vẫn
#: rẻ (loader cache theo năm, nên hai lượt gọi liền nhau gần như không tốn gì).
LOOKBACK_DAYS = 1100

#: Dưới ngưỡng này thì EMA50 tuần chưa ổn định — nói "chưa đủ tuần" chứ không
#: in ra một con số trông như đã đo.
MIN_WEEKS = 55


def to_weekly(records: Sequence[StockRecord]) -> List[StockRecord]:
    """Gộp nến ngày thành nến tuần ISO, giữ nguyên kiểu ``StockRecord``.

    Dùng ``replace`` trên bản ghi cuối của tuần thay vì dựng mới: mọi trường
    không liên quan tới OHLC (symbol, adjRatio, unit…) đi theo mà không phải
    liệt kê lại — và khi ``StockRecord`` thêm trường, hàm này không phải sửa.
    """
    if not records:
        return []

    out: List[StockRecord] = []
    bucket: List[StockRecord] = []
    key: Optional[tuple] = None

    def flush() -> None:
        if not bucket:
            return
        out.append(replace(
            bucket[-1],
            priceOpen=bucket[0].priceOpen,
            priceHigh=max(r.priceHigh for r in bucket),
            priceLow=min(r.priceLow for r in bucket),
            priceClose=bucket[-1].priceClose,
            # Giá tham chiếu của tuần là giá đóng cửa tuần TRƯỚC — đó là mốc
            # đúng để đọc % thay đổi của cả tuần.
            priceBasic=bucket[0].priceBasic,
            totalVolume=sum(r.totalVolume for r in bucket),
            dealVolume=sum(r.dealVolume for r in bucket),
            putthroughVolume=sum(r.putthroughVolume for r in bucket),
            totalValue=sum(r.totalValue for r in bucket),
            putthroughValue=sum(r.putthroughValue for r in bucket),
            buyForeignQuantity=sum(r.buyForeignQuantity for r in bucket),
            sellForeignQuantity=sum(r.sellForeignQuantity for r in bucket),
            buyForeignValue=sum(r.buyForeignValue for r in bucket),
            sellForeignValue=sum(r.sellForeignValue for r in bucket),
        ))

    for rec in records:
        k = rec.date.isocalendar()[:2]
        if k != key:
            flush()
            bucket, key = [], k
        bucket.append(rec)
    flush()
    return out


@dataclass
class WeeklyView:
    """Khung tuần nói gì — một khối nhỏ, đủ để trả lời "khung lớn có đồng thuận".

    ``side`` là kết luận đã rút gọn (``up`` / ``down`` / ``flat``) để tầng trên
    so với khung ngày mà không phải tự đọc lại bốn con số. ``comparable`` =
    False nghĩa là **chưa đủ tuần**, khác hẳn "đã đo và thấy đi ngang".
    """
    symbol: str
    as_of: str = ""
    weeks: int = 0
    comparable: bool = False
    partial: bool = False            # tuần cuối chưa đóng
    close: Optional[float] = None
    ema20: Optional[float] = None
    ema50: Optional[float] = None
    vs_ema20_pct: Optional[float] = None
    vs_ema50_pct: Optional[float] = None
    rsi14: Optional[float] = None
    change_4w: Optional[float] = None
    change_13w: Optional[float] = None
    side: str = "flat"
    label: str = ""
    structure_label: str = ""
    swings: List[str] = field(default_factory=list)
    note: str = ""

    def to_dict(self) -> dict:
        from dataclasses import asdict
        return asdict(self)


def _round(value: Optional[float], digits: int = 2) -> Optional[float]:
    return round(float(value), digits) if value is not None else None


def _last(series: Sequence[Optional[float]]) -> Optional[float]:
    for value in reversed(series or []):
        if value is not None:
            return value
    return None


def _pct(new: Optional[float], old: Optional[float]) -> Optional[float]:
    if new is None or not old:
        return None
    return round((new / old - 1.0) * 100, 2)


def build_view(symbol: str, as_of: Optional[datetime] = None,
               records: Optional[Sequence[StockRecord]] = None) -> WeeklyView:
    """Khung tuần của một mã. ``records`` truyền sẵn = chuỗi **ngày** đã nạp."""
    daily = records if records is not None else load_recent(symbol, LOOKBACK_DAYS, as_of)
    weekly = to_weekly(daily)
    if not weekly:
        return WeeklyView(symbol=symbol, note=f"Không có dữ liệu tuần cho {symbol}")

    last = weekly[-1]
    view = WeeklyView(
        symbol=symbol,
        as_of=last.date.strftime("%Y-%m-%d"),
        weeks=len(weekly),
        # Tuần cuối đã đóng khi phiên cuối rơi vào thứ Sáu (isoweekday 5) trở đi.
        partial=last.date.isoweekday() < 5,
        close=_round(last.priceClose),
    )
    if len(weekly) < MIN_WEEKS:
        view.note = (f"Mới {len(weekly)} tuần — cần ≥ {MIN_WEEKS} tuần để MA50 tuần "
                     f"có nghĩa, nên khung tuần để trống thay vì trả một con số chưa ổn định.")
        return view

    view.comparable = True
    ema20 = IndicatorGroup1.ema(weekly, 20)
    ema50 = IndicatorGroup1.ema(weekly, 50)
    rsi = IndicatorGroup2.rsi(weekly, 14)
    atr = IndicatorGroup3.atr(weekly, 14)

    close = last.priceClose
    e20, e50 = _last(ema20), _last(ema50)
    view.ema20, view.ema50 = _round(e20), _round(e50)
    view.vs_ema20_pct = _pct(close, e20)
    view.vs_ema50_pct = _pct(close, e50)
    view.rsi14 = _round(_last(rsi))
    view.change_4w = _pct(close, weekly[-5].priceClose) if len(weekly) > 4 else None
    view.change_13w = _pct(close, weekly[-14].priceClose) if len(weekly) > 13 else None

    market = build_market_structure(weekly, atr=atr)
    view.structure_label = market.label
    view.swings = [s.short for s in market.swings[-6:]]

    if e20 is not None and e50 is not None:
        if close > e20 > e50:
            view.side, view.label = "up", "Trên MA20 tuần, MA20 trên MA50 — khung lớn thuận"
        elif close < e20 < e50:
            view.side, view.label = "down", "Dưới MA20 tuần, MA20 dưới MA50 — khung lớn nghịch"
        elif close > e50:
            view.side, view.label = ("flat",
                                     "Trên MA50 tuần nhưng chưa vượt MA20 tuần — "
                                     "khung lớn chưa xác nhận")
        else:
            view.side, view.label = "down", "Dưới MA50 tuần — khung lớn còn yếu"
    if market.trend != RANGE:
        # TREND_NAMES đã mang sẵn chữ "theo cấu trúc" — chỉ thêm "tuần" để nói
        # rõ chuỗi swing này đếm trên nến tuần, không phải nến ngày.
        view.label += f" · {TREND_NAMES[market.trend].lower()} tuần"
    return view


def agreement(weekly_side: str, daily_side: str) -> str:
    """Một câu về chỗ hai khung gặp hay lệch nhau.

    Không gộp hai bên thành một nhãn: đúng lý do ``CLAUDE.md`` đã dùng cho
    EMA và chuỗi swing — khi hai cách đọc lệch nhau thì **chính chỗ lệch** là
    thông tin, không phải thứ cần làm phẳng đi.
    """
    if not weekly_side or not daily_side:
        return ""
    if weekly_side == daily_side:
        return ("Hai khung cùng chiều — khung tuần không cản tín hiệu khung ngày."
                if weekly_side != "flat" else
                "Cả hai khung đều chưa rõ chiều.")
    if weekly_side == "flat" or daily_side == "flat":
        return ("Một khung đã có chiều, khung kia chưa — tín hiệu còn sống nhưng "
                "chưa có khung lớn đẩy sau lưng.")
    return ("⚠️ Hai khung **ngược nhau** — tín hiệu khung ngày đang đi ngược khung "
            "tuần, tức là đánh vào một nhịp hồi chứ không phải xu hướng chính.")
