"""Consolidation boxes — the rectangle a trader draws around a sideways range.

A box is a stretch where the whole high-low range stays inside a few ATRs.
The interesting part is what happens at the edge: a close outside the box
*with* volume behind it is the breakout worth acting on, the same move on thin
volume is the one that fails. Both are reported, and named differently.
"""
from dataclasses import asdict, dataclass
from typing import List, Optional, Sequence

import pandas as pd

from src.analysis.technical_indicators import IndicatorGroup3
from src.data.stock_data_loader import StockRecord
from src.ta.retest import Retest, find_retest

INSIDE = "inside"
BREAKOUT_UP_CONFIRMED = "breakout_up_confirmed"
BREAKOUT_UP_WEAK = "breakout_up_weak"
BREAKDOWN_CONFIRMED = "breakdown_confirmed"
BREAKDOWN_WEAK = "breakdown_weak"
FALSE_BREAKOUT_UP = "false_breakout_up"
FALSE_BREAKDOWN = "false_breakdown"

STATE_LABELS = {
    INSIDE: "còn trong hộp",
    BREAKOUT_UP_CONFIRMED: "vượt hộp có volume xác nhận",
    BREAKOUT_UP_WEAK: "vượt hộp nhưng volume yếu",
    BREAKDOWN_CONFIRMED: "thủng đáy hộp có volume xác nhận",
    BREAKDOWN_WEAK: "thủng đáy hộp nhưng volume yếu",
    FALSE_BREAKOUT_UP: "vượt hộp rồi tụt lại vào trong (phá vỡ giả)",
    FALSE_BREAKDOWN: "thủng hộp rồi bật lại vào trong (phá vỡ giả)",
}


@dataclass
class Box:
    top: float
    bottom: float
    start_index: int
    start_date: str
    end_index: int
    end_date: str
    bars: int
    height: float
    height_pct: float
    state: str
    position_pct: Optional[float]       # where close sits in the box, 0 = bottom
    breakout_index: Optional[int] = None
    breakout_date: Optional[str] = None
    breakout_close: Optional[float] = None
    breakout_volume_x: Optional[float] = None
    bars_since_breakout: Optional[int] = None
    retest: Optional[Retest] = None
    target: Optional[float] = None      # measured move from the box height
    target_hit: bool = False
    invalidation: Optional[float] = None
    label: str = ""
    id: str = ""                        # "#1" — handle for asking about this box

    def to_dict(self) -> dict:
        return asdict(self)


def _atr_at(atr: Sequence[Optional[float]], index: int, fallback: float) -> float:
    for i in range(min(index, len(atr) - 1), -1, -1):
        if atr[i] is not None:
            return float(atr[i])
    return fallback


def find_box(
    records: List[StockRecord],
    min_bars: int = 8,
    max_bars: int = 60,
    range_atr: float = 3.0,
    search_window: int = 30,
    confirm_atr: float = 0.25,
    volume_x: float = 1.5,
    atr: Optional[Sequence[Optional[float]]] = None,
) -> Optional[Box]:
    """The most relevant recent consolidation box, or ``None``.

    ``search_window`` lets the box end before the last bar, which is what
    happens once price has already broken out of it.
    """
    n = len(records)
    if n < min_bars + 2:
        return None

    atr_s = list(atr) if atr is not None else IndicatorGroup3.atr(records, 14)
    typical = sum(r.priceHigh - r.priceLow for r in records) / n or 1e-9
    highs = [r.priceHigh for r in records]
    lows = [r.priceLow for r in records]

    best = None                          # (score, start, end, top, bottom)
    earliest_end = max(min_bars - 1, n - 1 - search_window)
    for end in range(n - 1, earliest_end - 1, -1):
        limit = range_atr * _atr_at(atr_s, end, typical)
        top, bottom = highs[end], lows[end]
        found_start = None
        found_top = found_bottom = None
        for start in range(end, max(-1, end - max_bars), -1):
            top = max(top, highs[start])
            bottom = min(bottom, lows[start])
            if top - bottom > limit:
                break
            if end - start + 1 >= min_bars:
                found_start, found_top, found_bottom = start, top, bottom
        if found_start is None:
            continue
        bars = end - found_start + 1
        score = bars - 0.5 * (n - 1 - end)
        if best is None or score > best[0]:
            best = (score, found_start, end, found_top, found_bottom)

    if best is None:
        return None

    _, start, end, top, bottom = best
    height = top - bottom
    if height <= 0:
        return None

    volumes = [r.priceImpactVolume for r in records]
    vol_ema = pd.Series(volumes).ewm(span=20, adjust=False).mean().tolist()

    state = INSIDE
    b_index = b_date = b_close = b_vol_x = None
    for i in range(end + 1, n):
        atr_i = _atr_at(atr_s, i, typical)
        close = records[i].priceClose
        if close > top + confirm_atr * atr_i:
            b_index, direction = i, "up"
        elif close < bottom - confirm_atr * atr_i:
            b_index, direction = i, "down"
        else:
            continue
        base = vol_ema[i] or 1e-9
        b_vol_x = round(volumes[i] / base, 2)
        b_date = records[i].date.strftime("%Y-%m-%d")
        b_close = round(close, 2)
        strong = b_vol_x >= volume_x
        if direction == "up":
            state = BREAKOUT_UP_CONFIRMED if strong else BREAKOUT_UP_WEAK
        else:
            state = BREAKDOWN_CONFIRMED if strong else BREAKDOWN_WEAK
        break

    close = records[-1].priceClose
    # A breakout that gave the ground back is a failed breakout, not a breakout.
    if state in (BREAKOUT_UP_CONFIRMED, BREAKOUT_UP_WEAK) and close < top:
        state = FALSE_BREAKOUT_UP
    elif state in (BREAKDOWN_CONFIRMED, BREAKDOWN_WEAK) and close > bottom:
        state = FALSE_BREAKDOWN

    if state in (BREAKOUT_UP_CONFIRMED, BREAKOUT_UP_WEAK):
        target, invalidation = top + height, bottom
    elif state in (BREAKDOWN_CONFIRMED, BREAKDOWN_WEAK):
        target, invalidation = bottom - height, top
    else:
        target, invalidation = None, None

    box = Box(
        top=round(top, 2), bottom=round(bottom, 2),
        start_index=start, start_date=records[start].date.strftime("%Y-%m-%d"),
        end_index=end, end_date=records[end].date.strftime("%Y-%m-%d"),
        bars=end - start + 1,
        height=round(height, 2),
        height_pct=round(height / bottom * 100, 2) if bottom else 0.0,
        state=state,
        position_pct=round((close - bottom) / height * 100, 1) if state == INSIDE else None,
        breakout_index=b_index, breakout_date=b_date, breakout_close=b_close,
        breakout_volume_x=b_vol_x,
        bars_since_breakout=(n - 1 - b_index) if b_index is not None else None,
        target=round(target, 2) if target else None,
        target_hit=bool(
            target and (close >= target if "up" in state else close <= target)
        ),
        invalidation=round(invalidation, 2) if invalidation else None,
    )
    if b_index is not None and state not in (FALSE_BREAKOUT_UP, FALSE_BREAKDOWN):
        edge = top if "up" in state else bottom
        box.retest = find_retest(
            records, b_index, lambda _i, level=edge: level,
            "up" if "up" in state else "down",
            _atr_at(atr_s, b_index, typical),
        )
    box.label = describe_box(box, volume_x)
    return box


def describe_box(box: Box, volume_x: float = 1.5) -> str:
    head = (f"Hộp tích luỹ {box.bottom}–{box.top} "
            f"(biên độ {box.height_pct:.1f}%, {box.bars} phiên, "
            f"{box.start_date} → {box.end_date})")
    state = STATE_LABELS.get(box.state, box.state)

    if box.state == INSIDE:
        return (f"{head} — giá đang ở {box.position_pct:.0f}% chiều cao hộp. "
                f"Đóng cửa vượt {box.top} kèm volume ≥ {volume_x:g}× trung bình 20 phiên "
                f"là breakout đáng mua; thủng {box.bottom} là mất cấu trúc.")

    when = f"ngày {box.breakout_date} ({box.bars_since_breakout} phiên trước)"
    vol = f"volume {box.breakout_volume_x:g}× trung bình" if box.breakout_volume_x else ""

    reached = " — đã chạm mục tiêu" if box.target_hit else ""
    retest = f" {box.retest.label}" if box.retest is not None else ""

    if box.state == BREAKOUT_UP_CONFIRMED:
        return (f"{head} — {state} {when}, {vol}. Mục tiêu đo được {box.target} "
                f"(chiều cao hộp chiếu lên){reached}, "
                f"mất hiệu lực nếu đóng cửa dưới {box.invalidation}.{retest}")
    if box.state == BREAKOUT_UP_WEAK:
        return (f"{head} — {state} {when}, {vol} (< {volume_x:g}×). "
                f"Cần volume xác nhận trước khi tin; mục tiêu nếu đúng {box.target}.{retest}")
    if box.state == BREAKDOWN_CONFIRMED:
        return (f"{head} — {state} {when}, {vol}. Mục tiêu giảm {box.target}{reached}, "
                f"cấu trúc phục hồi nếu lấy lại {box.invalidation}.{retest}")
    if box.state == BREAKDOWN_WEAK:
        return f"{head} — {state} {when}, {vol} (< {volume_x:g}×)."
    return f"{head} — {state} {when}."
