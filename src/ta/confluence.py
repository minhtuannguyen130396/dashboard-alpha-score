"""Where a formation, a candle and volume have to agree before anything is said.

The naive way to combine the two families is to detect candles across the whole
series and report the ones that land on the same day as a formation. That is a
cross-join of two noisy signals, and it produces noise squared: a bearish
engulfing in the middle of a sideways drift means nothing, and pairing it with
a double top that broke six weeks ago means less.

The constraint that makes it work is *location*. A formation marks out a small
number of bars where a candle actually carries information — the last shoulder,
the bar that breaks the neckline, the retest after it — and candles are only
read inside those windows. Everywhere else they are ignored.

What comes out is deliberately not a score. It is a tier plus a list of what is
missing, because "confirmed on two of three, still waiting on volume" is the
sentence a reader can act on, and a number between 0 and 1 is not.
"""
from dataclasses import asdict, dataclass, field
from typing import List, Optional, Sequence

from src.data.stock_data_loader import StockRecord
from src.ta import candles
from src.ta.candles import CandleShape, CandleSignal
from src.ta.formations import (
    BEARISH, BULLISH, CONFIRMED, FAILED, FORMING, Formation,
)

Z1_EXTREME = "z1_extreme"
Z2_BREAK = "z2_break"
Z3_RETEST = "z3_retest"
Z4_COUNTER = "z4_counter"

ZONE_LABELS = {
    Z1_EXTREME: "tại đỉnh/đáy cuối của mô hình",
    Z2_BREAK: "tại phiên phá neckline",
    Z3_RETEST: "khi retest neckline",
    Z4_COUNTER: "tín hiệu ngược chiều gần đây",
}

#: Confluence tiers, strongest first.
FULL = "full"
PARTIAL = "partial"
CONFLICT = "conflict"

TIER_LABELS = {
    FULL: "hợp lưu đủ 3 yếu tố",
    PARTIAL: "thiếu yếu tố xác nhận",
    CONFLICT: "có yếu tố mâu thuẫn",
}

TIER_MARKS = {FULL: "🔴", PARTIAL: "⚠️", CONFLICT: "⚪"}
TIER_MARKS_BULL = {FULL: "🟢", PARTIAL: "⚠️", CONFLICT: "⚪"}

#: A shape weaker than this is not evidence of anything.
MIN_CONFIRM = 0.50
#: Pushing back against a live formation is a bigger claim, so it costs more.
MIN_COUNTER = 0.60
#: Same convention the boxes and forecasts already use.
CONFIRM_VOLUME_X = 1.5
#: Bars either side of the defining pivot that still count as "at" it.
Z1_WINDOW = 3
#: How long after a break a return to the neckline is still a retest.
Z3_BARS = 10
#: How far back a counter-signal is still current news.
Z4_BARS = 10


@dataclass
class ZoneHit:
    zone: str
    label: str
    start_date: str
    end_date: str
    signals: List[CandleSignal] = field(default_factory=list)

    def to_dict(self) -> dict:
        data = asdict(self)
        data["signals"] = [s.to_dict() for s in self.signals]
        return data


@dataclass
class Evidence:
    """One formation, everything found around it, and the reading that follows."""
    formation: Formation
    tier: str
    mark: str
    zones: List[ZoneHit] = field(default_factory=list)
    shape_note: str = ""
    candle_note: str = ""
    volume_note: str = ""
    missing: List[str] = field(default_factory=list)
    conclusion: str = ""

    @property
    def strongest(self) -> Optional[CandleSignal]:
        found = [s for z in self.zones if z.zone != Z4_COUNTER for s in z.signals]
        return max(found, key=lambda s: s.strength) if found else None

    def to_dict(self) -> dict:
        return {
            "formation": self.formation.to_dict(),
            "tier": self.tier,
            "mark": self.mark,
            "zones": [z.to_dict() for z in self.zones],
            "shape_note": self.shape_note,
            "candle_note": self.candle_note,
            "volume_note": self.volume_note,
            "missing": self.missing,
            "conclusion": self.conclusion,
        }


def zones_for(formation: Formation, bars: int) -> List[ZoneHit]:
    """The bar windows where a candle would mean something, as (start, end) pairs.

    Returned without signals attached — ``assess`` fills those in.
    """
    last = bars - 1
    out: List[tuple] = [
        (Z1_EXTREME,
         max(0, formation.end_index - Z1_WINDOW),
         min(last, formation.end_index + Z1_WINDOW)),
    ]
    if formation.break_index is not None:
        b = formation.break_index
        out.append((Z2_BREAK, b, b))
        if b + 1 <= last:
            out.append((Z3_RETEST, b + 1, min(last, b + Z3_BARS)))
    counter_start = max(formation.end_index + 1, last - Z4_BARS + 1)
    if counter_start <= last:
        out.append((Z4_COUNTER, counter_start, last))
    return out


def _volume_reading(f: Formation) -> tuple:
    """``(ok, sentence)`` — what volume says about this formation right now."""
    if f.state == CONFIRMED and f.break_volume_x is not None:
        if f.break_volume_x >= CONFIRM_VOLUME_X:
            return True, (f"phiên phá neckline có volume {f.break_volume_x:g}× "
                          f"trung bình 20 phiên")
        return False, (f"phiên phá neckline chỉ có volume {f.break_volume_x:g}× "
                       f"(< {CONFIRM_VOLUME_X:g}×) — thiếu lực")
    ratio = f.shoulder_volume_ratio
    if ratio is None:
        return False, "không đo được volume hai đầu mô hình"
    side = "vai phải/vai trái" if "shoulder" in f.kind else "đỉnh sau/đỉnh đầu" \
        if f.bias == BEARISH else "đáy sau/đáy đầu"
    if ratio < 1.0:
        return True, (f"volume {side} {ratio:g}× — "
                      f"{'cầu' if f.bias == BEARISH else 'cung'} yếu dần qua từng nhịp")
    return False, (f"volume {side} {ratio:g}× — chưa thấy dấu "
                   f"{'phân phối' if f.bias == BEARISH else 'hấp thụ'}")


def assess(
    records: Sequence[StockRecord],
    formation: Formation,
    measured: Optional[List[CandleShape]] = None,
    atr: Optional[Sequence[Optional[float]]] = None,
) -> Evidence:
    """Read one formation together with the candles and volume around it."""
    n = len(records)
    sh = measured if measured is not None else candles.shapes(records, atr)
    counter_bias = BULLISH if formation.bias == BEARISH else BEARISH

    hits: List[ZoneHit] = []
    for zone, start, end in zones_for(formation, n):
        want = counter_bias if zone == Z4_COUNTER else formation.bias
        floor = MIN_COUNTER if zone == Z4_COUNTER else MIN_CONFIRM
        found = [s for s in candles.scan(records, start, end, atr=atr, measured=sh)
                 if s.bias == want and s.strength >= floor]
        # Keep the best shape per bar; a dragonfly doji reported twice adds nothing.
        best = {}
        for s in found:
            if s.index not in best or s.strength > best[s.index].strength:
                best[s.index] = s
        if best:
            hits.append(ZoneHit(
                zone=zone, label=ZONE_LABELS[zone],
                start_date=sh[start].date, end_date=sh[end].date,
                signals=[best[k] for k in sorted(best)],
            ))

    confirming = [z for z in hits if z.zone != Z4_COUNTER]
    countering = next((z for z in hits if z.zone == Z4_COUNTER), None)
    volume_ok, volume_note = _volume_reading(formation)

    missing: List[str] = []
    if formation.state == FORMING:
        side = "dưới" if formation.bias == BEARISH else "trên"
        missing.append(f"chưa đóng cửa {side} neckline {formation.neckline_now}")
    if not confirming:
        missing.append("chưa có nến xác nhận tại vùng quyết định")
    if not volume_ok:
        missing.append("volume chưa xác nhận")

    if formation.state == FAILED:
        tier = CONFLICT
    elif countering is not None:
        tier = CONFLICT
    elif not missing:
        tier = FULL
    else:
        tier = PARTIAL

    marks = TIER_MARKS if formation.bias == BEARISH else TIER_MARKS_BULL
    evidence = Evidence(
        formation=formation,
        tier=tier,
        mark=marks[tier],
        zones=hits,
        shape_note=formation.label,
        candle_note=_candle_note(confirming),
        volume_note=volume_note,
        missing=missing,
    )
    evidence.conclusion = _conclude(evidence, countering)
    return evidence


def _candle_note(zones: List[ZoneHit]) -> str:
    if not zones:
        return "không có nến đảo chiều nào tại các vùng quyết định"
    parts = []
    for z in zones:
        best = max(z.signals, key=lambda s: s.strength)
        parts.append(f"{ZONE_LABELS[z.zone]}: {best.name} ngày {best.date}")
    return "; ".join(parts)


def _conclude(ev: Evidence, countering: Optional[ZoneHit]) -> str:
    """The sentence the report prints — a technical state, never a recommendation."""
    f = ev.formation
    direction = "giảm" if f.bias == BEARISH else "tăng"
    over = "trên" if f.bias == BEARISH else "dưới"
    under = "dưới" if f.bias == BEARISH else "trên"

    if f.state == FAILED:
        return f"Mô hình đã hỏng — không còn dùng {f.neckline_now} làm mốc."

    if countering is not None:
        best = max(countering.signals, key=lambda s: s.strength)
        return (f"Cấu trúc vẫn còn nhưng {best.name} ngày {best.date} đi ngược mô hình — "
                f"độ tin cậy giảm. Mô hình chỉ hỏng hẳn khi đóng cửa {over} "
                f"{f.invalidation}.")

    if ev.tier == FULL:
        hit = " — đã chạm mục tiêu" if f.target_hit else ""
        return (f"Đảo chiều {direction} xác nhận trên cả ba yếu tố. "
                f"Mục tiêu đo được {f.target}{hit}; mô hình bị phủ định nếu đóng cửa "
                f"{over} {f.invalidation}.")

    if f.state == CONFIRMED:
        return (f"Đã phá neckline nhưng {', '.join(ev.missing)} — "
                f"khả năng quay lại retest {f.neckline_now} còn cao. "
                f"Mục tiêu nếu đúng {f.target}, phủ định tại {f.invalidation}.")

    need = f"đóng cửa {under} {f.neckline_now} kèm volume ≥ {CONFIRM_VOLUME_X:g}×"
    return (f"Chưa xác nhận — {', '.join(ev.missing)}. "
            f"Cần {need} thì mục tiêu đo được là "
            f"{round(f.neckline_now - f.height if f.bias == BEARISH else f.neckline_now + f.height, 2)}; "
            f"mô hình huỷ nếu đóng cửa {over} {f.invalidation}.")


def assess_all(
    records: Sequence[StockRecord],
    formations: Sequence[Formation],
    atr: Optional[Sequence[Optional[float]]] = None,
) -> List[Evidence]:
    """Assess every formation against one shared pass over the candles."""
    if not formations:
        return []
    sh = candles.shapes(records, atr)
    return [assess(records, f, measured=sh, atr=atr) for f in formations]
