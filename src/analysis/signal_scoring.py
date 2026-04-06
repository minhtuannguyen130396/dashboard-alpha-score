from dataclasses import dataclass, field
from typing import List, Tuple

from src.data.stock_data_loader import StockRecord
from src.analysis.candle_patterns import BearishPatterns, BullishPatterns
from src.analysis.technical_indicators import IndicatorGroup1, IndicatorGroup3


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
