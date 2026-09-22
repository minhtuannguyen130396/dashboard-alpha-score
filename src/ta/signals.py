"""RSI reversal detection and ADX momentum regime.

The RSI rule implemented here is the one the user specified, in three parts:

  1. RSI14 pushes into an extreme zone (below oversold / above overbought)
  2. it turns around inside that zone (a trough or peak forms)
  3. it travels back and touches the threshold again  ->  report

Step 3 is the event. Step 2 alone is reported separately as a *watch* state,
so a name can be picked up while the reversal is still forming.
"""
from dataclasses import asdict, dataclass, field
from typing import List, Optional, Sequence

from src.analysis.technical_indicators import IndicatorGroup2
from src.data.stock_data_loader import StockRecord
from src.ta.config import AdxConfig, RsiConfig
from src.ta.indicators_ext import adx_di

OVERSOLD_RECLAIM = "oversold_reclaim"
OVERBOUGHT_LOSS = "overbought_loss"

#: |ADX slope| at or below this is treated as flat, not a strengthening trend.
_ADX_FLAT_BAND = 0.1


# ---------------------------------------------------------------------------
# RSI
# ---------------------------------------------------------------------------
@dataclass
class RsiEvent:
    """One completed round-trip through an extreme zone."""
    symbol: str
    date: str
    index: int
    kind: str                 # OVERSOLD_RECLAIM | OVERBOUGHT_LOSS
    side: str                 # "bullish" | "bearish"
    rsi: float                # RSI on the bar that touched the threshold back
    threshold: float
    extreme: float            # deepest RSI reached inside the zone
    extreme_date: str
    depth: float              # how far past the threshold it dug, in RSI points
    bars_in_zone: int
    bars_since_extreme: int   # how long the turn took
    close: float
    change_pct: float         # close change on the trigger bar
    price_confirms: bool      # price moved the same way as the signal
    divergence: bool          # price made a new extreme, RSI did not
    quality: str              # "strong" | "normal" | "weak"
    reasons: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class RsiZoneState:
    """Where RSI stands right now - used for the watchlist, not the event log."""
    rsi: Optional[float]
    state: str                # neutral | in_oversold | turning_up | in_overbought | turning_down
    extreme: Optional[float] = None
    bars_in_zone: int = 0
    recovered: Optional[float] = None          # RSI points off the extreme
    distance_to_threshold: Optional[float] = None
    label: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def _pct(new: float, old: float) -> float:
    return round((new / old - 1.0) * 100, 2) if old else 0.0


def _grade(depth: float, bars_in_zone: int, divergence: bool,
           price_confirms: bool, cfg: RsiConfig):
    """Grade an event and explain the grade in Vietnamese."""
    reasons: List[str] = []
    weak = False
    if bars_in_zone < cfg.min_bars_in_zone:
        weak = True
        reasons.append(f"chỉ {bars_in_zone} phiên trong vùng (cần ≥ {cfg.min_bars_in_zone})")
    if depth < cfg.min_depth:
        weak = True
        reasons.append(f"lún {depth:.1f} điểm RSI (cần ≥ {cfg.min_depth:.0f})")
    if divergence:
        reasons.append("có phân kỳ RSI")
    reasons.append("giá xác nhận cùng chiều" if price_confirms else "giá chưa xác nhận")

    if weak:
        return "weak", reasons
    if divergence or (bars_in_zone >= 4 and depth >= 6.0):
        reasons.append(f"{bars_in_zone} phiên trong vùng, lún {depth:.1f} điểm")
        return "strong", reasons
    return "normal", reasons


def detect_rsi_events(
    records: List[StockRecord],
    cfg: RsiConfig = RsiConfig(),
    rsi_series: Optional[Sequence[Optional[float]]] = None,
) -> List[RsiEvent]:
    """Scan the whole series and return every zone round-trip, oldest first."""
    if not records:
        return []
    rsi = list(rsi_series) if rsi_series is not None else IndicatorGroup2.rsi(records, cfg.period)
    symbol = records[-1].symbol
    events: List[RsiEvent] = []

    # Previous zone extremes, for divergence: (index, price, rsi)
    prior_lows: List[tuple] = []
    prior_highs: List[tuple] = []

    state = "neutral"
    extreme: Optional[float] = None
    extreme_idx = 0
    bars_in_zone = 0

    def _divergence(idx: int, rsi_extreme: float, bullish: bool) -> bool:
        history = prior_lows if bullish else prior_highs
        for p_idx, p_price, p_rsi in reversed(history):
            if idx - p_idx > cfg.divergence_lookback:
                break
            if bullish:
                if records[idx].priceLow < p_price and rsi_extreme > p_rsi:
                    return True
            elif records[idx].priceHigh > p_price and rsi_extreme < p_rsi:
                return True
        return False

    def _emit(i: int, bullish: bool) -> None:
        threshold = cfg.oversold if bullish else cfg.overbought
        depth = round(abs(threshold - extreme), 2)
        prev_close = records[i - 1].priceClose if i > 0 else records[i].priceClose
        change = _pct(records[i].priceClose, prev_close)
        confirms = change > 0 if bullish else change < 0
        div = _divergence(extreme_idx, extreme, bullish)
        quality, reasons = _grade(depth, bars_in_zone, div, confirms, cfg)
        events.append(RsiEvent(
            symbol=symbol,
            date=records[i].date.strftime("%Y-%m-%d"),
            index=i,
            kind=OVERSOLD_RECLAIM if bullish else OVERBOUGHT_LOSS,
            side="bullish" if bullish else "bearish",
            rsi=round(float(rsi[i]), 2),
            threshold=threshold,
            extreme=round(extreme, 2),
            extreme_date=records[extreme_idx].date.strftime("%Y-%m-%d"),
            depth=depth,
            bars_in_zone=bars_in_zone,
            bars_since_extreme=i - extreme_idx,
            close=round(records[i].priceClose, 2),
            change_pct=change,
            price_confirms=confirms,
            divergence=div,
            quality=quality,
            reasons=reasons,
        ))
        (prior_lows if bullish else prior_highs).append((
            extreme_idx,
            records[extreme_idx].priceLow if bullish else records[extreme_idx].priceHigh,
            extreme,
        ))

    for i, value in enumerate(rsi):
        if value is None:
            continue
        v = float(value)

        if state == "below":
            if v < cfg.oversold:
                bars_in_zone += 1
                if extreme is None or v < extreme:
                    extreme, extreme_idx = v, i
                continue
            _emit(i, bullish=True)          # RSI came back and touched oversold
            state, extreme, bars_in_zone = "neutral", None, 0

        elif state == "above":
            if v > cfg.overbought:
                bars_in_zone += 1
                if extreme is None or v > extreme:
                    extreme, extreme_idx = v, i
                continue
            _emit(i, bullish=False)         # RSI came back and touched overbought
            state, extreme, bars_in_zone = "neutral", None, 0

        # Re-check the same bar: it may open a new zone right after closing one.
        if state == "neutral":
            if v < cfg.oversold:
                state, extreme, extreme_idx, bars_in_zone = "below", v, i, 1
            elif v > cfg.overbought:
                state, extreme, extreme_idx, bars_in_zone = "above", v, i, 1

    return events


def rsi_zone_state(
    records: List[StockRecord],
    cfg: RsiConfig = RsiConfig(),
    rsi_series: Optional[Sequence[Optional[float]]] = None,
) -> RsiZoneState:
    """Current position of RSI relative to the extreme zones.

    ``turning_up`` / ``turning_down`` is the "dấu hiệu quay đầu" state: still
    inside the zone, but already moving back toward the threshold.
    """
    if not records:
        return RsiZoneState(rsi=None, state="neutral", label="không có dữ liệu")
    rsi = list(rsi_series) if rsi_series is not None else IndicatorGroup2.rsi(records, cfg.period)
    last = rsi[-1] if rsi else None
    if last is None:
        return RsiZoneState(rsi=None, state="neutral", label="chưa đủ dữ liệu RSI")
    last = float(last)

    if cfg.oversold <= last <= cfg.overbought:
        return RsiZoneState(rsi=round(last, 2), state="neutral",
                            label=f"RSI {last:.1f} — vùng trung tính")

    bullish = last < cfg.oversold
    threshold = cfg.oversold if bullish else cfg.overbought

    bars = 0
    extreme = last
    for value in reversed(rsi):
        if value is None:
            break
        v = float(value)
        if (bullish and v < cfg.oversold) or (not bullish and v > cfg.overbought):
            bars += 1
            extreme = min(extreme, v) if bullish else max(extreme, v)
        else:
            break

    recovered = round(abs(last - extreme), 2)
    turning = recovered >= cfg.turn_min_move and bars > cfg.turn_min_bars
    gap = abs(threshold - last)
    if bullish:
        state = "turning_up" if turning else "in_oversold"
        label = (
            f"RSI {last:.1f} — đã bật {recovered:.1f} điểm khỏi đáy {extreme:.1f}, "
            f"còn {gap:.1f} điểm nữa chạm {threshold:.0f}"
            if turning else
            f"RSI {last:.1f} — đang trong vùng quá bán ({bars} phiên), chưa quay đầu"
        )
    else:
        state = "turning_down" if turning else "in_overbought"
        label = (
            f"RSI {last:.1f} — đã lùi {recovered:.1f} điểm khỏi đỉnh {extreme:.1f}, "
            f"còn {gap:.1f} điểm nữa chạm {threshold:.0f}"
            if turning else
            f"RSI {last:.1f} — đang trong vùng quá mua ({bars} phiên), chưa quay đầu"
        )

    return RsiZoneState(
        rsi=round(last, 2), state=state, extreme=round(extreme, 2),
        bars_in_zone=bars, recovered=recovered,
        distance_to_threshold=round(gap, 2), label=label,
    )


# ---------------------------------------------------------------------------
# ADX
# ---------------------------------------------------------------------------
@dataclass
class AdxState:
    adx: Optional[float]
    plus_di: Optional[float]
    minus_di: Optional[float]
    regime: str               # no_data | no_trend | emerging | strong
    direction: str            # up | down | flat
    slope: Optional[float]    # change over cfg.slope_bars
    rising: Optional[bool]
    has_momentum: bool        # ADX above the user's threshold (default 20)
    label: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def adx_state(
    records: List[StockRecord],
    cfg: AdxConfig = AdxConfig(),
    index: int = -1,
) -> AdxState:
    """ADX regime at one bar, with direction taken from +DI vs -DI."""
    adx_s, pdi_s, mdi_s = adx_di(records, cfg.period)
    no_data = AdxState(None, None, None, "no_data", "flat", None, None, False,
                       f"cần ≥ {2 * cfg.period} phiên để tính ADX")
    if not adx_s:
        return no_data
    i = index if index >= 0 else len(adx_s) + index
    if not 0 <= i < len(adx_s) or adx_s[i] is None:
        return no_data

    value = float(adx_s[i])
    pdi, mdi = pdi_s[i], mdi_s[i]
    j = i - cfg.slope_bars
    slope = round(value - adx_s[j], 2) if j >= 0 and adx_s[j] is not None else None

    if value >= cfg.strong_threshold:
        regime = "strong"
    elif value >= cfg.trend_threshold:
        regime = "emerging"
    else:
        regime = "no_trend"

    if pdi is None or mdi is None or pdi == mdi:
        direction = "flat"
    else:
        direction = "up" if pdi > mdi else "down"

    trend_word = {"up": "tăng", "down": "giảm", "flat": "đi ngang"}[direction]
    if regime == "no_trend":
        label = f"ADX {value:.1f} < {cfg.trend_threshold:.0f} — chưa có động lực, giá đi ngang/nhiễu"
    elif regime == "emerging":
        label = f"ADX {value:.1f} — động lực chớm hình thành, hướng {trend_word}"
    else:
        label = f"ADX {value:.1f} — xu hướng {trend_word} mạnh"
    # A slope inside the flat band is noise, not a strengthening trend.
    rising = None if slope is None else slope > _ADX_FLAT_BAND
    if slope is not None:
        if abs(slope) <= _ADX_FLAT_BAND:
            moving = "đi ngang"
        else:
            moving = "đang mạnh lên" if slope > 0 else "đang yếu đi"
        label += f" ({moving}, {slope:+.1f} sau {cfg.slope_bars} phiên)"

    return AdxState(
        adx=round(value, 2),
        plus_di=round(pdi, 2) if pdi is not None else None,
        minus_di=round(mdi, 2) if mdi is not None else None,
        regime=regime, direction=direction, slope=slope,
        rising=rising,
        has_momentum=value >= cfg.trend_threshold,
        label=label,
    )
