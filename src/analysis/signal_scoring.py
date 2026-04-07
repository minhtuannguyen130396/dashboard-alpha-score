from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from src.data.stock_data_loader import StockRecord
from src.analysis.candle_patterns import BearishPatterns, BullishPatterns
from src.analysis.technical_indicators import IndicatorGroup1, IndicatorGroup2, IndicatorGroup3, IndicatorGroup4
from src.analysis.score_config import ScoreConfigV2, DEFAULT_SCORE_CONFIG_V2


@dataclass
class SignalScore:
    label: str = "none"
    final_score: float = 0.0
    candle_score: float = 0.0
    volume_score: float = 0.0
    context_score: float = 0.0
    pivot_score: float = 0.0
    reasons: List[str] = field(default_factory=list)

    @property
    def reason_text(self) -> str:
        return " | ".join(self.reasons)


def _latest(values: List[float]) -> float:
    if not values:
        return 0.0
    value = values[-1]
    return float(value) if value is not None else 0.0


def _score_candle(records: List[StockRecord]) -> Tuple[float, str, float, str]:
    recent = records[-5:]

    bullish_candidates = [
        (0.70, "Hammer", BullishPatterns.hammer(recent) > 0),
        (0.90, "Bullish Engulfing", BullishPatterns.bullish_engulfing(recent) > 0),
        (1.00, "Morning Star", BullishPatterns.morning_star(recent) > 0),
        (0.75, "Piercing Pattern", BullishPatterns.piercing_pattern(recent) > 0),
        (1.00, "Three White Soldiers", BullishPatterns.three_white_soldiers(recent) > 0),
    ]
    bearish_candidates = [
        (0.70, "Shooting Star", BearishPatterns.shooting_star(recent) < 0),
        (0.90, "Bearish Engulfing", BearishPatterns.bearish_engulfing(recent) < 0),
        (1.00, "Evening Star", BearishPatterns.evening_star(recent) < 0),
        (0.80, "Dark Cloud Cover", BearishPatterns.dark_cloud_cover(recent) < 0),
        (1.00, "Three Black Crows", BearishPatterns.three_black_crows(recent) < 0),
    ]

    bullish_score, bullish_reason = 0.0, ""
    bearish_score, bearish_reason = 0.0, ""

    for score, reason, is_match in bullish_candidates:
        if is_match and score > bullish_score:
            bullish_score, bullish_reason = score, reason
    for score, reason, is_match in bearish_candidates:
        if is_match and score > bearish_score:
            bearish_score, bearish_reason = score, reason

    return bullish_score, bullish_reason, bearish_score, bearish_reason


def _score_volume(records: List[StockRecord]) -> Tuple[float, float, float]:
    volumes = [record.totalVolume for record in records]
    avg_volume = sum(volumes[-20:]) / min(20, len(volumes))
    rvol = records[-1].totalVolume / avg_volume if avg_volume else 0.0

    if rvol >= 1.5:
        score = 1.0
    elif rvol >= 1.2:
        score = 0.7
    else:
        score = 0.3

    atr14 = _latest(IndicatorGroup3.atr(records, 14))
    current_range = records[-1].priceHigh - records[-1].priceLow
    range_vs_atr = current_range / atr14 if atr14 else 0.0
    if range_vs_atr >= 1.2:
        score = min(1.0, score + 0.2)

    return score, rvol, atr14


def _score_context(records: List[StockRecord], bullish: bool, atr14: float) -> Tuple[float, str]:
    ema20 = _latest(IndicatorGroup1.ema(records, 20))
    ema50 = _latest(IndicatorGroup1.ema(records, 50))
    prev_ema20 = _latest(IndicatorGroup1.ema(records[:-1], 20)) if len(records) > 20 else ema20
    close = records[-1].priceClose

    uptrend = close > ema20 > ema50 and ema20 >= prev_ema20
    downtrend = close < ema20 < ema50 and ema20 <= prev_ema20

    score = 0.0
    reasons: List[str] = []
    if bullish:
        score += 0.5 if downtrend else 0.1
        if downtrend:
            reasons.append("Downtrend context")
        if atr14 and close <= ema20 - atr14:
            score += 0.3
            reasons.append("Close below EMA20 by ATR")
        elif close <= ema20:
            score += 0.15
            reasons.append("Close below EMA20")
    else:
        score += 0.5 if uptrend else 0.1
        if uptrend:
            reasons.append("Uptrend context")
        if atr14 and close >= ema20 + atr14:
            score += 0.3
            reasons.append("Close above EMA20 by ATR")
        elif close >= ema20:
            score += 0.15
            reasons.append("Close above EMA20")

    return min(1.0, score), ", ".join(reasons)


def _score_pivot(records: List[StockRecord], bullish: bool) -> Tuple[float, str]:
    lookback = min(5, len(records))
    recent = records[-lookback:]

    if bullish:
        lows = [record.priceLow for record in recent]
        current_value = recent[-1].priceLow
        ordered = sorted(lows)
        if current_value == ordered[0]:
            return 1.0, "Pivot low"
        if len(ordered) > 1 and current_value == ordered[1]:
            return 0.5, "Near pivot low"
    else:
        highs = [record.priceHigh for record in recent]
        current_value = recent[-1].priceHigh
        ordered = sorted(highs, reverse=True)
        if current_value == ordered[0]:
            return 1.0, "Pivot high"
        if len(ordered) > 1 and current_value == ordered[1]:
            return 0.5, "Near pivot high"

    return 0.0, ""


def _build_signal_score(
    label: str,
    candle_score: float,
    candle_reason: str,
    volume_score: float,
    context_score: float,
    context_reason: str,
    pivot_score: float,
    pivot_reason: str,
    rvol: float,
) -> SignalScore:
    final_score = (
        0.4 * candle_score
        + 0.3 * volume_score
        + 0.2 * context_score
        + 0.1 * pivot_score
    )

    reasons = []
    if candle_reason:
        reasons.append(candle_reason)
    reasons.append(f"RVOL {rvol:.2f}")
    if context_reason:
        reasons.append(context_reason)
    if pivot_reason:
        reasons.append(pivot_reason)

    return SignalScore(
        label=label,
        final_score=round(final_score, 4),
        candle_score=round(candle_score, 4),
        volume_score=round(volume_score, 4),
        context_score=round(context_score, 4),
        pivot_score=round(pivot_score, 4),
        reasons=reasons,
    )


def calculate_signal_score(records: List[StockRecord], trigger_threshold: float = 0.7) -> SignalScore:
    if len(records) < 50:
        return SignalScore(reasons=["Warm-up"])

    bullish_candle, bullish_reason, bearish_candle, bearish_reason = _score_candle(records)
    if bullish_candle == 0 and bearish_candle == 0:
        return SignalScore(reasons=["No reversal pattern"])

    volume_score, rvol, atr14 = _score_volume(records)
    bullish_context, bullish_context_reason = _score_context(records, bullish=True, atr14=atr14)
    bearish_context, bearish_context_reason = _score_context(records, bullish=False, atr14=atr14)
    bullish_pivot, bullish_pivot_reason = _score_pivot(records, bullish=True)
    bearish_pivot, bearish_pivot_reason = _score_pivot(records, bullish=False)

    bullish_signal = _build_signal_score(
        "bullish",
        bullish_candle,
        bullish_reason,
        volume_score,
        bullish_context,
        bullish_context_reason,
        bullish_pivot,
        bullish_pivot_reason,
        rvol,
    )
    bearish_signal = _build_signal_score(
        "bearish",
        bearish_candle,
        bearish_reason,
        volume_score,
        bearish_context,
        bearish_context_reason,
        bearish_pivot,
        bearish_pivot_reason,
        rvol,
    )

    candidate = bullish_signal if bullish_signal.final_score >= bearish_signal.final_score else bearish_signal
    if candidate.final_score < trigger_threshold or candidate.candle_score == 0:
        return SignalScore(
            final_score=candidate.final_score,
            candle_score=candidate.candle_score,
            volume_score=candidate.volume_score,
            context_score=candidate.context_score,
            pivot_score=candidate.pivot_score,
            reasons=candidate.reasons + [f"Below threshold {trigger_threshold:.2f}"],
        )

    return candidate


calculate_stock_score = calculate_signal_score


# ===========================================================================
# Score V2
# ===========================================================================

@dataclass
class SignalScoreV2:
    label: str = "none"
    regime: str = "unknown"
    setup_score: float = 0.0
    trigger_score: float = 0.0
    final_score: float = 0.0
    candle_score: float = 0.0
    trend_score: float = 0.0
    momentum_score: float = 0.0
    volume_score: float = 0.0
    structure_score: float = 0.0
    confirmation_score: float = 0.0
    blockers: List[str] = field(default_factory=list)
    reasons: List[str] = field(default_factory=list)

    @property
    def reason_text(self) -> str:
        return " | ".join(self.reasons)


def _safe_last(series: list, fallback: float = 0.0) -> float:
    """Return the last non-None value from a series, or fallback."""
    for v in reversed(series):
        if v is not None:
            return float(v)
    return fallback


def _score_trend_v2(
    records: List[StockRecord], bullish: bool, cfg: ScoreConfigV2,
) -> Tuple[float, str]:
    p = cfg.periods
    ema20 = _safe_last(IndicatorGroup1.ema(records, p.ema_fast))
    ema50 = _safe_last(IndicatorGroup1.ema(records, p.ema_mid))
    ema100 = _safe_last(IndicatorGroup1.ema(records, p.ema_slow))
    ema20_prev = _safe_last(IndicatorGroup1.ema(records[:-1], p.ema_fast)) if len(records) > p.ema_fast else ema20
    adx = _safe_last(IndicatorGroup3.adx(records, p.adx))
    close = records[-1].priceClose

    score = 0.0
    parts: List[str] = []

    if bullish:
        if ema20 and ema50 and close > ema20 > ema50:
            score += 0.40
            parts.append("Bullish EMA stack")
        elif ema20 and ema50 and close < ema20 < ema50:
            score += 0.25  # downtrend = good reversal context
            parts.append("Downtrend reversal context")
        elif ema20 and close > ema20:
            score += 0.20
        if ema50 and ema100 and ema50 > ema100:
            score += 0.10
            parts.append("EMA50>EMA100")
        if ema20 and ema20_prev and ema20 > ema20_prev:
            score += 0.15
            parts.append("EMA20 rising")
    else:
        if ema20 and ema50 and close < ema20 < ema50:
            score += 0.40
            parts.append("Bearish EMA stack")
        elif ema20 and ema50 and close > ema20 > ema50:
            score += 0.25  # uptrend = good reversal context
            parts.append("Uptrend reversal context")
        elif ema20 and close < ema20:
            score += 0.20
        if ema50 and ema100 and ema50 < ema100:
            score += 0.10
            parts.append("EMA50<EMA100")
        if ema20 and ema20_prev and ema20 < ema20_prev:
            score += 0.15
            parts.append("EMA20 falling")

    if adx >= 25:
        score += 0.20
        parts.append(f"ADX={adx:.1f} strong")
    elif adx >= 20:
        score += 0.10
        parts.append(f"ADX={adx:.1f}")
    else:
        parts.append(f"ADX={adx:.1f} weak")

    return min(1.0, score), ", ".join(parts)


def _score_momentum_v2(
    records: List[StockRecord], bullish: bool, cfg: ScoreConfigV2,
) -> Tuple[float, str]:
    p = cfg.periods
    rsi = _safe_last(IndicatorGroup2.rsi(records, p.rsi), 50.0)
    _, _, hist_series = IndicatorGroup2.macd(records, p.macd_fast, p.macd_slow, p.macd_signal)
    macd_hist = _safe_last(hist_series)
    macd_hist_prev = _safe_last(hist_series[:-1]) if len(hist_series) > 1 else 0.0
    roc = _safe_last(IndicatorGroup2.roc(records, p.roc))

    score = 0.0
    parts: List[str] = []

    if bullish:
        if rsi < 30:
            score += 0.40
            parts.append(f"RSI oversold {rsi:.1f}")
        elif rsi < 50:
            score += 0.25
            parts.append(f"RSI {rsi:.1f}")
        elif rsi < 70:
            score += 0.15
        else:
            score += 0.05

        if macd_hist > 0 and macd_hist > macd_hist_prev:
            score += 0.35
            parts.append("MACD hist rising above 0")
        elif macd_hist > macd_hist_prev:
            score += 0.20
            parts.append("MACD hist improving")

        if roc > 0:
            score += 0.25
            parts.append(f"ROC+ {roc:.2f}")
        elif roc > -2:
            score += 0.10
    else:
        if rsi > 70:
            score += 0.40
            parts.append(f"RSI overbought {rsi:.1f}")
        elif rsi > 50:
            score += 0.25
            parts.append(f"RSI {rsi:.1f}")
        elif rsi > 30:
            score += 0.15
        else:
            score += 0.05

        if macd_hist < 0 and macd_hist < macd_hist_prev:
            score += 0.35
            parts.append("MACD hist falling below 0")
        elif macd_hist < macd_hist_prev:
            score += 0.20
            parts.append("MACD hist declining")

        if roc < 0:
            score += 0.25
            parts.append(f"ROC- {roc:.2f}")
        elif roc < 2:
            score += 0.10

    return min(1.0, score), ", ".join(parts)


def _score_volume_v2(
    records: List[StockRecord], bullish: bool, cfg: ScoreConfigV2,
) -> Tuple[float, str]:
    p = cfg.periods
    vols = [r.totalVolume for r in records]
    avg_vol = sum(vols[-p.rvol:]) / min(p.rvol, len(vols)) if vols else 1.0
    rvol = records[-1].totalVolume / avg_vol if avg_vol else 0.0

    atr = _safe_last(IndicatorGroup3.atr(records, p.atr))
    current_range = records[-1].priceHigh - records[-1].priceLow
    range_atr = current_range / atr if atr else 0.0

    obv = IndicatorGroup4.obv(records)
    n = p.obv_slope
    obv_slope = (obv[-1] - obv[-n - 1]) / n if len(obv) >= n + 1 else 0.0

    mfi = _safe_last(IndicatorGroup4.mfi(records, p.mfi), 50.0)

    score = 0.0
    parts: List[str] = []

    if rvol >= 1.5:
        score += 0.35
        parts.append(f"High RVOL {rvol:.2f}")
    elif rvol >= 1.2:
        score += 0.25
        parts.append(f"RVOL {rvol:.2f}")
    elif rvol >= 0.8:
        score += 0.10
    else:
        parts.append(f"Weak RVOL {rvol:.2f}")

    if range_atr >= 1.2:
        score += 0.20
        parts.append(f"Wide range {range_atr:.2f}x ATR")
    elif range_atr >= 0.8:
        score += 0.10

    if bullish and obv_slope > 0:
        score += 0.25
        parts.append("OBV rising")
    elif not bullish and obv_slope < 0:
        score += 0.25
        parts.append("OBV falling")
    elif bullish and obv_slope < 0:
        parts.append("OBV bearish divergence")
    elif not bullish and obv_slope > 0:
        parts.append("OBV bullish divergence")

    if bullish and mfi > 60:
        score += 0.20
        parts.append(f"MFI bullish {mfi:.1f}")
    elif bullish and mfi > 40:
        score += 0.10
    elif not bullish and mfi < 40:
        score += 0.20
        parts.append(f"MFI bearish {mfi:.1f}")
    elif not bullish and mfi < 60:
        score += 0.10

    return min(1.0, score), ", ".join(parts)


def _score_structure_v2(
    records: List[StockRecord], bullish: bool, cfg: ScoreConfigV2,
) -> Tuple[float, str]:
    p = cfg.periods
    n_short = min(p.swing_short, len(records))
    n_long = min(p.swing_long, len(records))
    close = records[-1].priceClose
    atr = _safe_last(IndicatorGroup3.atr(records, p.atr)) or close * 0.02

    swing_low_s = min(r.priceLow for r in records[-n_short:])
    swing_high_s = max(r.priceHigh for r in records[-n_short:])
    swing_low_l = min(r.priceLow for r in records[-n_long:])
    swing_high_l = max(r.priceHigh for r in records[-n_long:])

    score = 0.0
    parts: List[str] = []

    if bullish:
        dist_low_s = (close - swing_low_s) / atr
        dist_low_l = (close - swing_low_l) / atr
        if dist_low_s <= 0.5:
            score += 0.50
            parts.append("At 10d swing low support")
        elif dist_low_s <= 1.5:
            score += 0.30
            parts.append("Near 10d swing low")
        if dist_low_l <= 1.0:
            score += 0.25
            parts.append("At 20d swing low")
        elif dist_low_l <= 2.0:
            score += 0.15
        # Penalise if close to resistance
        if (swing_high_s - close) / atr < 0.5:
            score -= 0.20
            parts.append("Near resistance")
    else:
        dist_high_s = (swing_high_s - close) / atr
        dist_high_l = (swing_high_l - close) / atr
        if dist_high_s <= 0.5:
            score += 0.50
            parts.append("At 10d swing high resistance")
        elif dist_high_s <= 1.5:
            score += 0.30
            parts.append("Near 10d swing high")
        if dist_high_l <= 1.0:
            score += 0.25
            parts.append("At 20d swing high")
        elif dist_high_l <= 2.0:
            score += 0.15
        # Penalise if close to support
        if (close - swing_low_s) / atr < 0.5:
            score -= 0.20
            parts.append("Near support")

    return max(0.0, min(1.0, score)), ", ".join(parts)


def _score_confirmation_v2(
    records: List[StockRecord], bullish: bool, cfg: ScoreConfigV2,
) -> Tuple[float, str]:
    p = cfg.periods
    if len(records) < 4:
        return 0.0, "Insufficient data"

    close = records[-1].priceClose
    high = records[-1].priceHigh
    low = records[-1].priceLow
    body_pos = (close - low) / (high - low) if high != low else 0.5

    prev3_highs = [r.priceHigh for r in records[-4:-1]]
    prev3_lows = [r.priceLow for r in records[-4:-1]]

    vols = [r.totalVolume for r in records]
    avg_vol = sum(vols[-p.rvol:]) / min(p.rvol, len(vols)) if vols else 1.0
    rvol = records[-1].totalVolume / avg_vol if avg_vol else 0.0

    score = 0.0
    parts: List[str] = []

    if bullish:
        if close > max(prev3_highs):
            score += 0.50
            parts.append("Close > 3-bar high")
        elif close > records[-2].priceHigh:
            score += 0.30
            parts.append("Close > prev high")
        if rvol >= 1.5:
            score += 0.25
            parts.append(f"Breakout vol RVOL={rvol:.2f}")
        elif rvol >= 1.2:
            score += 0.15
        if body_pos >= 0.7:
            score += 0.25
            parts.append("Close near high")
        elif body_pos >= 0.5:
            score += 0.10
    else:
        if close < min(prev3_lows):
            score += 0.50
            parts.append("Close < 3-bar low")
        elif close < records[-2].priceLow:
            score += 0.30
            parts.append("Close < prev low")
        if rvol >= 1.5:
            score += 0.25
            parts.append(f"Breakdown vol RVOL={rvol:.2f}")
        elif rvol >= 1.2:
            score += 0.15
        if body_pos <= 0.3:
            score += 0.25
            parts.append("Close near low")
        elif body_pos <= 0.5:
            score += 0.10

    return min(1.0, score), ", ".join(parts)


def _detect_blockers_v2(
    records: List[StockRecord],
    bullish: bool,
    adx: float,
    rvol: float,
    rsi: float,
    macd_hist: float,
    macd_hist_prev: float,
    close: float,
    swing_high: float,
    swing_low: float,
    atr: float,
    cfg: ScoreConfigV2,
) -> List[str]:
    t = cfg.thresholds
    blockers: List[str] = []

    if adx < t.adx_min:
        blockers.append(f"ADX={adx:.1f} too low, possible sideway")
    if rvol < t.rvol_min:
        blockers.append(f"Weak volume RVOL={rvol:.2f}")

    if bullish:
        if rsi > t.rsi_overbought:
            blockers.append(f"RSI overbought {rsi:.1f}")
        if atr and (swing_high - close) < 0.5 * atr:
            blockers.append("Close near resistance")
        if macd_hist < 0 and macd_hist < macd_hist_prev:
            blockers.append("MACD declining (bearish)")
    else:
        if rsi < t.rsi_oversold:
            blockers.append(f"RSI oversold {rsi:.1f}")
        if atr and (close - swing_low) < 0.5 * atr:
            blockers.append("Close near support")
        if macd_hist > 0 and macd_hist > macd_hist_prev:
            blockers.append("MACD rising (bullish)")

    return blockers


def _build_score_v2(
    records: List[StockRecord],
    bullish: bool,
    candle_score: float,
    candle_reason: str,
    cfg: ScoreConfigV2,
) -> SignalScoreV2:
    w = cfg.weights
    p = cfg.periods
    t = cfg.toggles

    trend_score, trend_r = _score_trend_v2(records, bullish, cfg) if t.use_trend else (0.5, "disabled")
    momentum_score, momentum_r = _score_momentum_v2(records, bullish, cfg) if t.use_momentum else (0.5, "disabled")
    volume_score, volume_r = _score_volume_v2(records, bullish, cfg) if t.use_volume else (0.5, "disabled")
    structure_score, structure_r = _score_structure_v2(records, bullish, cfg) if t.use_structure else (0.5, "disabled")
    confirmation_score, confirmation_r = _score_confirmation_v2(records, bullish, cfg) if t.use_confirmation else (0.5, "disabled")

    setup_score = (
        w.setup_candle * candle_score
        + w.setup_trend * trend_score
        + w.setup_momentum * momentum_score
        + w.setup_volume * volume_score
        + w.setup_structure * structure_score
    )
    trigger_score = (
        w.trigger_confirmation * confirmation_score
        + w.trigger_volume * volume_score
        + w.trigger_candle * candle_score
        + w.trigger_momentum * momentum_score
        + w.trigger_structure * structure_score
    )
    final_score = w.final_setup * setup_score + w.final_trigger * trigger_score

    # Regime
    close = records[-1].priceClose
    ema20 = _safe_last(IndicatorGroup1.ema(records, p.ema_fast))
    ema50 = _safe_last(IndicatorGroup1.ema(records, p.ema_mid))
    if bullish:
        regime = "bullish_continuation" if (ema20 and ema50 and close > ema20 > ema50) else "bullish_reversal"
    else:
        regime = "bearish_continuation" if (ema20 and ema50 and close < ema20 < ema50) else "bearish_reversal"

    # Collect values for blockers
    adx = _safe_last(IndicatorGroup3.adx(records, p.adx))
    vols = [r.totalVolume for r in records]
    avg_vol = sum(vols[-p.rvol:]) / min(p.rvol, len(vols)) if vols else 1.0
    rvol = records[-1].totalVolume / avg_vol if avg_vol else 0.0
    rsi = _safe_last(IndicatorGroup2.rsi(records, p.rsi), 50.0)
    _, _, hist_s = IndicatorGroup2.macd(records, p.macd_fast, p.macd_slow, p.macd_signal)
    macd_hist = _safe_last(hist_s)
    macd_hist_prev = _safe_last(hist_s[:-1]) if len(hist_s) > 1 else 0.0
    atr = _safe_last(IndicatorGroup3.atr(records, p.atr))
    n = min(p.swing_short, len(records))
    swing_high = max(r.priceHigh for r in records[-n:])
    swing_low = min(r.priceLow for r in records[-n:])

    blockers = _detect_blockers_v2(
        records, bullish, adx, rvol, rsi,
        macd_hist, macd_hist_prev, close,
        swing_high, swing_low, atr, cfg,
    )

    reasons: List[str] = [r for r in [candle_reason, trend_r, momentum_r, volume_r, structure_r, confirmation_r] if r]

    return SignalScoreV2(
        label="bullish" if bullish else "bearish",
        regime=regime,
        setup_score=round(setup_score, 4),
        trigger_score=round(trigger_score, 4),
        final_score=round(final_score, 4),
        candle_score=round(candle_score, 4),
        trend_score=round(trend_score, 4),
        momentum_score=round(momentum_score, 4),
        volume_score=round(volume_score, 4),
        structure_score=round(structure_score, 4),
        confirmation_score=round(confirmation_score, 4),
        blockers=blockers,
        reasons=reasons,
    )


def calculate_signal_score_v2(
    records: List[StockRecord],
    cfg: Optional[ScoreConfigV2] = None,
) -> SignalScoreV2:
    if cfg is None:
        cfg = DEFAULT_SCORE_CONFIG_V2

    if len(records) < 50:
        return SignalScoreV2(reasons=["Warm-up: need at least 50 records"])

    t = cfg.toggles
    if t.use_candle:
        bullish_candle, bullish_reason, bearish_candle, bearish_reason = _score_candle(records)
    else:
        bullish_candle, bullish_reason = 0.5, ""
        bearish_candle, bearish_reason = 0.5, ""

    bull = _build_score_v2(records, True, bullish_candle, bullish_reason, cfg)
    bear = _build_score_v2(records, False, bearish_candle, bearish_reason, cfg)

    return bull if bull.final_score >= bear.final_score else bear
