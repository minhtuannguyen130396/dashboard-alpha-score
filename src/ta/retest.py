"""Did price come back to the level it broke, and did the level hold?

A breakout tells you a level gave way. The retest tells you whether it changed
sides — whether the resistance that was just cleared now acts as support. That
second event is where the structure actually becomes tradable, and until now
nothing in this engine looked for it: the box knew "vượt hộp có volume xác
nhận" and stopped there.

The test is deliberately two-part, because a single bar cannot answer it. Price
has to *reach* the level again (an intraday touch is enough — that is what a
retest is), and then it has to *close* away from it. A touch that closes back
through is not a retest that failed; it is the breakout failing, which the
callers already model separately.

The level is passed as a callable so the same code serves a flat box edge, a
sloping trendline and a tilted neckline.
"""
from dataclasses import asdict, dataclass
from typing import Callable, Optional, Sequence

from src.data.stock_data_loader import StockRecord

UP = "up"        # broke upward — the level should now hold as support
DOWN = "down"    # broke downward — the level should now cap as resistance

#: How close price must come before it counts as having returned to the level.
TOUCH_ATR = 0.35
#: How long after the break a return still reads as a retest of that break.
WINDOW = 15
#: Bars allowed for the close to recover after the touch.
RECOVER_BARS = 3


@dataclass
class Retest:
    index: int
    date: str
    level: float
    close: float
    reach_atr: float          # how far past the level it dipped, in ATR
    held: bool
    bars_after_break: int
    label: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def find_retest(
    records: Sequence[StockRecord],
    break_index: int,
    level_at: Callable[[int], float],
    direction: str,
    atr: float,
    touch_atr: float = TOUCH_ATR,
    window: int = WINDOW,
    recover_bars: int = RECOVER_BARS,
) -> Optional[Retest]:
    """The first return to a broken level, or ``None`` if price never came back.

    ``held`` is the answer that matters: the level was reached and price closed
    back on the breakout side, either that bar or within ``recover_bars``.
    """
    n = len(records)
    if not 0 <= break_index < n or atr <= 0:
        return None
    up = direction == UP
    tol = touch_atr * atr

    for i in range(break_index + 1, min(n, break_index + 1 + window)):
        level = level_at(i)
        bar = records[i]
        reached = (bar.priceLow <= level + tol) if up else (bar.priceHigh >= level - tol)
        if not reached:
            continue

        reach = ((level - bar.priceLow) if up else (bar.priceHigh - level)) / atr
        held = False
        for j in range(i, min(n, i + recover_bars + 1)):
            close = records[j].priceClose
            if (close > level_at(j)) if up else (close < level_at(j)):
                held = True
                break
        retest = Retest(
            index=i,
            date=bar.date.strftime("%Y-%m-%d"),
            level=round(level, 2),
            close=round(bar.priceClose, 2),
            reach_atr=round(reach, 2),
            held=held,
            bars_after_break=i - break_index,
        )
        retest.label = describe_retest(retest, up)
        return retest
    return None


def describe_retest(r: Retest, up: bool) -> str:
    side = "hỗ trợ" if up else "kháng cự"
    when = f"ngày {r.date} ({r.bars_after_break} phiên sau khi phá)"
    if r.held:
        return (f"Đã retest {r.level} {when} và giữ được — mốc này đã đổi vai "
                f"thành {side}.")
    return (f"Đã quay lại {r.level} {when} nhưng chưa đóng cửa lại được phía "
            f"{'trên' if up else 'dưới'} — mốc chưa đổi vai.")
