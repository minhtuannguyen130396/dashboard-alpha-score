"""Signal Score V4 — sole supported scoring engine.

Carries forward V3's dedicated candle scoring, rolling-rank momentum,
divergence detection, split volume_setup/volume_trigger, hard/soft
blockers and regime alignment. Tuning vs V3:

- Wider rolling-rank window (60 → 120) so trending names produce
  meaningful momentum scores instead of stuck-at-mid ranks.
- Looser entry gates (final 0.58 → 0.52, trigger 0.55 → 0.45) and
  lower hard blocker thresholds (ADX 15 → 10, RVOL 0.5 → 0.3) so
  decent setups actually trade.
- Smaller per-soft-blocker penalty (0.08 → 0.04) to avoid double
  punishment when several minor flags coexist.
- Dedicated sell thresholds in market_behavior_analyzer; the
  simulator's ATR stop/trailing already handles in-trend exits.
"""
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from src.data.stock_data_loader import StockRecord
from src.analysis.candle_patterns import BearishPatterns, BullishPatterns
from src.analysis.technical_indicators import (
    IndicatorGroup1, IndicatorGroup2, IndicatorGroup3, IndicatorGroup4,
)
from src.analysis.score_config import (
    ScoreConfigV4, DEFAULT_SCORE_CONFIG_V4,
)


# =============================================================================
# Data classes
# =============================================================================

@dataclass
class Blocker:
    tag: str
    severity: str  # "hard" | "soft"
    msg: str

    def as_dict(self) -> dict:
        return {"tag": self.tag, "severity": self.severity, "msg": self.msg}


@dataclass
class SignalScoreV4:
    label: str = "none"
    regime: str = "unknown"
    setup_score: float = 0.0
    trigger_score: float = 0.0
    final_score: float = 0.0
    candle_score: float = 0.0
    trend_score: float = 0.0
    momentum_score: float = 0.0
    volume_setup_score: float = 0.0
    volume_trigger_score: float = 0.0
    structure_score: float = 0.0
    confirmation_score: float = 0.0
    divergence_score: float = 0.0
    regime_align_score: float = 0.0
    prop_score: float = 0.0
    blockers: List[Blocker] = field(default_factory=list)
    reasons: List[str] = field(default_factory=list)

    @property
    def reason_text(self) -> str:
        return " | ".join(self.reasons)

    # Flat aliases consumed by hover/chart payloads.
    @property
    def volume_score(self) -> float:
        return round((self.volume_setup_score + self.volume_trigger_score) / 2, 4)

    @property
    def blockers_text(self) -> List[str]:
        return [f"[{b.severity}] {b.msg}" for b in self.blockers]


# =============================================================================
# Helpers
# =============================================================================

def _safe_last(series: list, fallback: float = 0.0) -> float:
    for v in reversed(series or []):
        if v is not None:
            return float(v)
    return fallback


def _percentile_rank(window: List[float], value: float) -> float:
    """Return 0..1 rank of ``value`` within ``window``."""
    clean = [x for x in window if x is not None]
    if not clean:
        return 0.5
    below = sum(1 for x in clean if x < value)
    return below / len(clean)


def _rolling_rank(series: List[Optional[float]], window: int) -> float:
    """Percentile rank of the latest value within the last ``window`` values."""
    if not series or series[-1] is None:
        return 0.5
    recent = [v for v in series[-window:] if v is not None]
    if not recent:
        return 0.5
    return _percentile_rank(recent, series[-1])


# =============================================================================
# Candle scoring V3 — dedicated
# =============================================================================

def _candle_quality(record: StockRecord, atr: float) -> dict:
    high, low, close, open_ = record.priceHigh, record.priceLow, record.priceClose, record.priceOpen
    rng = high - low if high > low else 1e-9
    body = abs(close - open_)
    upper_wick = high - max(close, open_)
    lower_wick = min(close, open_) - low
    return {
        "rng": rng,
        "body_ratio": body / rng,
        "upper_wick_ratio": upper_wick / rng,
        "lower_wick_ratio": lower_wick / rng,
        "close_pos": (close - low) / rng,
        "size_vs_atr": rng / atr if atr else 0.0,
        "is_green": close > open_,
    }


def _score_candle_v4(
    records: List[StockRecord], bullish: bool, cfg: ScoreConfigV4,
) -> Tuple[float, str]:
    if len(records) < 5:
        return 0.0, "Insufficient data"

    recent = records[-5:]
    atr = _safe_last(IndicatorGroup3.atr(records, cfg.periods.atr))
    q = _candle_quality(records[-1], atr)

    score = 0.0
    parts: List[str] = []

    if bullish:
        pattern_scores = [
            (0.60, "Hammer", BullishPatterns.hammer(recent) > 0),
            (0.75, "Bullish Engulfing", BullishPatterns.bullish_engulfing(recent) > 0),
            (0.85, "Morning Star", BullishPatterns.morning_star(recent) > 0),
            (0.65, "Piercing", BullishPatterns.piercing_pattern(recent) > 0),
            (0.85, "Three White Soldiers", BullishPatterns.three_white_soldiers(recent) > 0),
        ]
        best = max((s for s, _, m in pattern_scores if m), default=0.0)
        best_name = next((n for s, n, m in pattern_scores if m and s == best), "")
        score += best
        if best_name:
            parts.append(best_name)

        # Quality bonuses
        if q["is_green"] and q["body_ratio"] >= 0.6:
            score += 0.10
            parts.append("strong body")
        if q["close_pos"] >= 0.75:
            score += 0.10
            parts.append("close near high")
        if q["size_vs_atr"] >= 1.2:
            score += 0.05
            parts.append("wide range")
        # Lower wick bonus (buying rejection of lows)
        if q["lower_wick_ratio"] >= 0.4:
            score += 0.05
            parts.append("long lower wick")
    else:
        pattern_scores = [
            (0.60, "Shooting Star", BearishPatterns.shooting_star(recent) < 0),
            (0.75, "Bearish Engulfing", BearishPatterns.bearish_engulfing(recent) < 0),
            (0.85, "Evening Star", BearishPatterns.evening_star(recent) < 0),
            (0.70, "Dark Cloud", BearishPatterns.dark_cloud_cover(recent) < 0),
            (0.85, "Three Black Crows", BearishPatterns.three_black_crows(recent) < 0),
        ]
        best = max((s for s, _, m in pattern_scores if m), default=0.0)
        best_name = next((n for s, n, m in pattern_scores if m and s == best), "")
        score += best
        if best_name:
            parts.append(best_name)

        if (not q["is_green"]) and q["body_ratio"] >= 0.6:
            score += 0.10
            parts.append("strong body")
        if q["close_pos"] <= 0.25:
            score += 0.10
            parts.append("close near low")
        if q["size_vs_atr"] >= 1.2:
            score += 0.05
            parts.append("wide range")
        if q["upper_wick_ratio"] >= 0.4:
            score += 0.05
            parts.append("long upper wick")

    return min(1.0, score), ", ".join(parts)


# =============================================================================
# Trend scoring V3
# =============================================================================

def _score_trend_v4(
    records: List[StockRecord], bullish: bool, cfg: ScoreConfigV4,
) -> Tuple[float, str]:
    p = cfg.periods
    ema20 = _safe_last(IndicatorGroup1.ema(records, p.ema_fast))
    ema50 = _safe_last(IndicatorGroup1.ema(records, p.ema_mid))
    ema100 = _safe_last(IndicatorGroup1.ema(records, p.ema_slow))

    # EMA20 slope
    ema20_series = IndicatorGroup1.ema(records, p.ema_fast)
    ema20_prev = _safe_last(ema20_series[:-1]) if len(ema20_series) > 1 else ema20
    ema20_slope = (ema20 - ema20_prev) / ema20 if ema20 else 0.0

    adx_series = IndicatorGroup3.adx(records, p.adx)
    adx = _safe_last(adx_series)
    adx_rank = _rolling_rank(adx_series, p.zscore_window)

    close = records[-1].priceClose

    score = 0.0
    parts: List[str] = []

    if bullish:
        if ema20 and ema50 and close > ema20 > ema50:
            score += 0.40
            parts.append("Bullish EMA stack")
        elif ema20 and ema50 and close < ema20 < ema50:
            score += 0.20
            parts.append("Deep oversold context")
        elif ema20 and close > ema20:
            score += 0.25
        if ema50 and ema100 and ema50 > ema100:
            score += 0.10
            parts.append("EMA50>100")
        if ema20_slope > 0.002:
            score += 0.15
            parts.append(f"EMA20 slope +{ema20_slope*100:.2f}%")
    else:
        if ema20 and ema50 and close < ema20 < ema50:
            score += 0.40
            parts.append("Bearish EMA stack")
        elif ema20 and ema50 and close > ema20 > ema50:
            score += 0.20
            parts.append("Extreme overbought context")
        elif ema20 and close < ema20:
            score += 0.25
        if ema50 and ema100 and ema50 < ema100:
            score += 0.10
            parts.append("EMA50<100")
        if ema20_slope < -0.002:
            score += 0.15
            parts.append(f"EMA20 slope {ema20_slope*100:.2f}%")

    # ADX via rolling rank — adaptive to each symbol's volatility regime
    if adx_rank >= 0.75:
        score += 0.20
        parts.append(f"ADX{adx:.0f} top-quartile")
    elif adx_rank >= 0.5:
        score += 0.10

    return min(1.0, score), ", ".join(parts)


# =============================================================================
# Momentum V3 — rolling RSI rank + MACD + ROC
# =============================================================================

def _score_momentum_v4(
    records: List[StockRecord], bullish: bool, cfg: ScoreConfigV4,
) -> Tuple[float, str]:
    p = cfg.periods
    rsi_series = IndicatorGroup2.rsi(records, p.rsi)
    rsi = _safe_last(rsi_series, 50.0)
    rsi_rank = _rolling_rank(rsi_series, p.zscore_window)

    _, _, hist_series = IndicatorGroup2.macd(records, p.macd_fast, p.macd_slow, p.macd_signal)
    macd_hist = _safe_last(hist_series)
    macd_hist_prev = _safe_last(hist_series[:-1]) if len(hist_series) > 1 else 0.0
    macd_rising = macd_hist > macd_hist_prev

    roc = _safe_last(IndicatorGroup2.roc(records, p.roc))

    score = 0.0
    parts: List[str] = []

    if bullish:
        # Reversal zone: rank < 0.25 = oversold relative to symbol's own history
        if rsi_rank <= 0.2:
            score += 0.40
            parts.append(f"RSI{rsi:.0f} rank{rsi_rank:.2f}")
        elif rsi_rank <= 0.5:
            score += 0.20
        if macd_hist > 0 and macd_rising:
            score += 0.35
            parts.append("MACD hist>0 rising")
        elif macd_rising:
            score += 0.20
            parts.append("MACD hist improving")
        if roc > 0:
            score += 0.25
            parts.append(f"ROC+{roc:.1f}")
    else:
        if rsi_rank >= 0.8:
            score += 0.40
            parts.append(f"RSI{rsi:.0f} rank{rsi_rank:.2f}")
        elif rsi_rank >= 0.5:
            score += 0.20
        if macd_hist < 0 and not macd_rising:
            score += 0.35
            parts.append("MACD hist<0 falling")
        elif not macd_rising:
            score += 0.20
            parts.append("MACD hist declining")
        if roc < 0:
            score += 0.25
            parts.append(f"ROC{roc:.1f}")

    return min(1.0, score), ", ".join(parts)


# =============================================================================
# Volume — split into setup and trigger
# =============================================================================

def _score_volume_setup_v4(
    records: List[StockRecord], bullish: bool, cfg: ScoreConfigV4,
) -> Tuple[float, str]:
    """Slow-moving accumulation/distribution view."""
    p = cfg.periods
    obv = IndicatorGroup4.obv(records)
    n = max(p.obv_slope, 1)
    obv_slope = (obv[-1] - obv[-n - 1]) / n if len(obv) >= n + 1 else 0.0

    mfi = _safe_last(IndicatorGroup4.mfi(records, p.mfi), 50.0)

    score = 0.0
    parts: List[str] = []
    if bullish:
        if obv_slope > 0:
            score += 0.50
            parts.append("OBV accumulating")
        if mfi > 55:
            score += 0.40
            parts.append(f"MFI{mfi:.0f}")
        elif mfi > 45:
            score += 0.20
    else:
        if obv_slope < 0:
            score += 0.50
            parts.append("OBV distributing")
        if mfi < 45:
            score += 0.40
            parts.append(f"MFI{mfi:.0f}")
        elif mfi < 55:
            score += 0.20
    return min(1.0, score), ", ".join(parts)


def _score_volume_trigger_v4(
    records: List[StockRecord], bullish: bool, cfg: ScoreConfigV4,
) -> Tuple[float, str]:
    """Intraday-only trigger: RVOL, wide range, close position."""
    p = cfg.periods
    vols = [r.priceImpactVolume for r in records]
    avg_vol = sum(vols[-p.rvol:]) / min(p.rvol, len(vols)) if vols else 1.0
    rvol = records[-1].priceImpactVolume / avg_vol if avg_vol else 0.0

    atr = _safe_last(IndicatorGroup3.atr(records, p.atr))
    rng = records[-1].priceHigh - records[-1].priceLow
    range_atr = rng / atr if atr else 0.0

    score = 0.0
    parts: List[str] = []
    if rvol >= 2.0:
        score += 0.60
        parts.append(f"Explosive RVOL{rvol:.2f}")
    elif rvol >= 1.5:
        score += 0.45
        parts.append(f"High RVOL{rvol:.2f}")
    elif rvol >= 1.2:
        score += 0.25
        parts.append(f"RVOL{rvol:.2f}")
    elif rvol >= 0.8:
        score += 0.10

    if range_atr >= 1.5:
        score += 0.35
        parts.append(f"range {range_atr:.2f}xATR")
    elif range_atr >= 1.0:
        score += 0.15

    return min(1.0, score), ", ".join(parts)


# =============================================================================
# Structure — swing S/R with ATR-normalized distance
# =============================================================================

def _score_structure_v4(
    records: List[StockRecord], bullish: bool, cfg: ScoreConfigV4,
) -> Tuple[float, str]:
    p = cfg.periods
    n_short = min(p.swing_short, len(records))
    n_long = min(p.swing_long, len(records))
    close = records[-1].priceClose
    atr = _safe_last(IndicatorGroup3.atr(records, p.atr)) or close * 0.02

    low_s = min(r.priceLow for r in records[-n_short:])
    high_s = max(r.priceHigh for r in records[-n_short:])
    low_l = min(r.priceLow for r in records[-n_long:])
    high_l = max(r.priceHigh for r in records[-n_long:])

    score = 0.0
    parts: List[str] = []

    if bullish:
        d_low = (close - low_s) / atr
        if d_low <= 0.5:
            score += 0.55
            parts.append("at 10d support")
        elif d_low <= 1.5:
            score += 0.30
        if (close - low_l) / atr <= 1.5:
            score += 0.25
            parts.append("near 20d support")
        if (high_s - close) / atr < 0.5:
            score -= 0.25
            parts.append("capped by resistance")
    else:
        d_high = (high_s - close) / atr
        if d_high <= 0.5:
            score += 0.55
            parts.append("at 10d resistance")
        elif d_high <= 1.5:
            score += 0.30
        if (high_l - close) / atr <= 1.5:
            score += 0.25
            parts.append("near 20d resistance")
        if (close - low_s) / atr < 0.5:
            score -= 0.25
            parts.append("supported")

    return max(0.0, min(1.0, score)), ", ".join(parts)


# =============================================================================
# Confirmation — breakout today
# =============================================================================

def _score_confirmation_v4(
    records: List[StockRecord], bullish: bool, cfg: ScoreConfigV4,
) -> Tuple[float, str]:
    if len(records) < 4:
        return 0.0, ""
    p = cfg.periods
    r = records[-1]
    rng = r.priceHigh - r.priceLow if r.priceHigh > r.priceLow else 1e-9
    body_pos = (r.priceClose - r.priceLow) / rng

    prev3_hi = max(x.priceHigh for x in records[-4:-1])
    prev3_lo = min(x.priceLow for x in records[-4:-1])

    vols = [x.priceImpactVolume for x in records]
    avg_vol = sum(vols[-p.rvol:]) / min(p.rvol, len(vols)) if vols else 1.0
    rvol = r.priceImpactVolume / avg_vol if avg_vol else 0.0

    score = 0.0
    parts: List[str] = []
    if bullish:
        if r.priceClose > prev3_hi:
            score += 0.55
            parts.append("Close>3d hi")
        elif r.priceClose > records[-2].priceHigh:
            score += 0.30
        if rvol >= 1.5:
            score += 0.25
            parts.append(f"breakout vol {rvol:.2f}")
        elif rvol >= 1.2:
            score += 0.15
        if body_pos >= 0.75:
            score += 0.25
            parts.append("close@high")
    else:
        if r.priceClose < prev3_lo:
            score += 0.55
            parts.append("Close<3d lo")
        elif r.priceClose < records[-2].priceLow:
            score += 0.30
        if rvol >= 1.5:
            score += 0.25
            parts.append(f"breakdown vol {rvol:.2f}")
        elif rvol >= 1.2:
            score += 0.15
        if body_pos <= 0.25:
            score += 0.25
            parts.append("close@low")

    return min(1.0, score), ", ".join(parts)


# =============================================================================
# Divergence — price vs RSI / MACD / OBV
# =============================================================================

def _detect_divergence(
    price_series: List[float], indicator_series: List[Optional[float]],
    lookback: int, bullish: bool,
) -> bool:
    """True if price makes new low/high but indicator doesn't confirm."""
    if len(price_series) < lookback + 2:
        return False
    recent_prices = price_series[-lookback:]
    recent_ind = [v for v in indicator_series[-lookback:] if v is not None]
    if len(recent_ind) < lookback // 2:
        return False

    if bullish:
        # price lower low, indicator higher low
        p_now, p_prev = price_series[-1], min(price_series[-lookback:-2]) if lookback > 2 else price_series[-2]
        i_now = indicator_series[-1]
        # Find prior pivot: lowest indicator value in the lookback window
        prior_idx_vals = [(j, v) for j, v in enumerate(indicator_series[-lookback:-2]) if v is not None]
        if not prior_idx_vals or i_now is None:
            return False
        prior_low = min(v for _, v in prior_idx_vals)
        return p_now < p_prev and i_now > prior_low
    else:
        p_now = price_series[-1]
        p_prev = max(price_series[-lookback:-2]) if lookback > 2 else price_series[-2]
        i_now = indicator_series[-1]
        prior_idx_vals = [(j, v) for j, v in enumerate(indicator_series[-lookback:-2]) if v is not None]
        if not prior_idx_vals or i_now is None:
            return False
        prior_high = max(v for _, v in prior_idx_vals)
        return p_now > p_prev and i_now < prior_high


def _score_divergence_v4(
    records: List[StockRecord], bullish: bool, cfg: ScoreConfigV4,
) -> Tuple[float, str]:
    p = cfg.periods
    lookback = p.divergence_lookback
    closes = [r.priceClose for r in records]

    rsi = IndicatorGroup2.rsi(records, p.rsi)
    _, _, hist = IndicatorGroup2.macd(records, p.macd_fast, p.macd_slow, p.macd_signal)
    obv = IndicatorGroup4.obv(records)
    obv_padded: List[Optional[float]] = [None] + [float(x) for x in obv]

    hits = 0
    parts: List[str] = []
    if _detect_divergence(closes, rsi, lookback, bullish):
        hits += 1
        parts.append("RSI div")
    if _detect_divergence(closes, hist, lookback, bullish):
        hits += 1
        parts.append("MACD div")
    if _detect_divergence(closes, obv_padded, lookback, bullish):
        hits += 1
        parts.append("OBV div")

    score = min(1.0, hits / 2.0)  # two+ confirmations = 1.0
    return score, ", ".join(parts)


# =============================================================================
# Proprietary trading (tự doanh) flow
# =============================================================================

def _score_prop_trading_v4(
    records: List[StockRecord], bullish: bool, cfg: ScoreConfigV4,
) -> Tuple[float, str]:
    """Score domestic proprietary trading (tự doanh) net flow.

    Positive ``propTradingNetValue`` means prop desks are net buyers (accumulating);
    negative means net sellers (distributing). Bullish setups benefit from recent
    accumulation, bearish setups from distribution.
    """
    p = cfg.periods
    short_n = min(p.prop_short, len(records))
    long_n = min(p.prop_long, len(records))
    if short_n <= 0:
        return 0.0, ""

    short_window = records[-short_n:]
    long_window = records[-long_n:]

    def _net(r: StockRecord) -> float:
        v = r.propTradingNetValue
        return float(v) if v is not None else 0.0

    short_sum = sum(_net(r) for r in short_window)
    long_sum = sum(_net(r) for r in long_window)
    today = _net(records[-1])

    # Normalise today against recent absolute magnitudes so large/small caps
    # get comparable scores. Use average abs of prop flow over the long window.
    abs_vals = [abs(_net(r)) for r in long_window if _net(r) != 0.0]
    avg_abs = sum(abs_vals) / len(abs_vals) if abs_vals else 0.0
    today_ratio = (today / avg_abs) if avg_abs > 0 else 0.0

    score = 0.0
    parts: List[str] = []

    if bullish:
        if short_sum > 0:
            score += 0.40
            parts.append("prop accumulating 10d")
        if long_sum > 0:
            score += 0.20
            parts.append("prop accumulating 20d")
        if today > 0:
            score += 0.20
            parts.append("prop buying today")
        if today_ratio >= 1.5:
            score += 0.20
            parts.append(f"prop surge {today_ratio:.1f}x")
        elif today_ratio >= 0.8:
            score += 0.10
    else:
        if short_sum < 0:
            score += 0.40
            parts.append("prop distributing 10d")
        if long_sum < 0:
            score += 0.20
            parts.append("prop distributing 20d")
        if today < 0:
            score += 0.20
            parts.append("prop selling today")
        if today_ratio <= -1.5:
            score += 0.20
            parts.append(f"prop dump {today_ratio:.1f}x")
        elif today_ratio <= -0.8:
            score += 0.10

    return min(1.0, score), ", ".join(parts)


# =============================================================================
# Regime alignment
# =============================================================================

def _score_regime_align_v4(
    records: List[StockRecord], bullish: bool, cfg: ScoreConfigV4,
) -> Tuple[float, str, str]:
    p = cfg.periods
    close = records[-1].priceClose
    ema20 = _safe_last(IndicatorGroup1.ema(records, p.ema_fast))
    ema50 = _safe_last(IndicatorGroup1.ema(records, p.ema_mid))
    ema100 = _safe_last(IndicatorGroup1.ema(records, p.ema_slow))

    # bull_trend now requires the long-term stack EMA50 > EMA100 too —
    # otherwise a counter-trend bounce that pushes close > ema20 > ema50
    # falsely registers as a major uptrend and produces losing entries.
    if ema20 and ema50 and ema100 and close > ema20 > ema50 > ema100:
        regime = "bull_trend"
    elif ema20 and ema50 and ema100 and close < ema20 < ema50 < ema100:
        regime = "bear_trend"
    elif ema20 and ema50 and close > ema20 > ema50:
        regime = "mild_bull"
    elif ema20 and ema50 and close < ema20 < ema50:
        regime = "mild_bear"
    elif ema20 and close > ema20:
        regime = "mild_bull"
    elif ema20 and close < ema20:
        regime = "mild_bear"
    else:
        regime = "sideway"

    # Alignment: bullish signal gets boost only if regime is bull or reversal-from-bear
    if bullish:
        if regime in ("bull_trend", "mild_bull"):
            return 1.0, "aligned bull", regime
        if regime == "bear_trend":
            return 0.5, "bullish reversal attempt", "bullish_reversal"
        return 0.6, "", regime
    else:
        if regime in ("bear_trend", "mild_bear"):
            return 1.0, "aligned bear", regime
        if regime == "bull_trend":
            return 0.5, "bearish reversal attempt", "bearish_reversal"
        return 0.6, "", regime


# =============================================================================
# Blockers
# =============================================================================

def _detect_blockers_v4(
    records: List[StockRecord],
    bullish: bool,
    adx: float, rvol: float, rsi: float,
    macd_hist: float, macd_hist_prev: float,
    close: float, swing_high: float, swing_low: float, atr: float,
    cfg: ScoreConfigV4,
) -> List[Blocker]:
    t = cfg.thresholds
    out: List[Blocker] = []

    # Hard blockers — unconditional rejection
    if adx < t.hard_adx_min:
        out.append(Blocker("adx_dead", "hard", f"ADX={adx:.1f} dead flat"))
    if rvol < t.hard_rvol_min:
        out.append(Blocker("vol_dead", "hard", f"RVOL={rvol:.2f} no participation"))

    # Soft blockers — apply penalty, don't reject outright
    if t.hard_adx_min <= adx < t.soft_adx_min:
        out.append(Blocker("adx_low", "soft", f"ADX={adx:.1f} weak trend"))
    if t.hard_rvol_min <= rvol < t.soft_rvol_min:
        out.append(Blocker("vol_low", "soft", f"RVOL={rvol:.2f} below avg"))

    if bullish:
        if rsi > t.rsi_overbought:
            out.append(Blocker("rsi_ob", "soft", f"RSI={rsi:.1f} overbought"))
        if atr and (swing_high - close) < 0.3 * atr:
            out.append(Blocker("near_res", "soft", "close glued to resistance"))
        if macd_hist < 0 and macd_hist < macd_hist_prev:
            out.append(Blocker("macd_falling", "soft", "MACD still falling"))
    else:
        if rsi < t.rsi_oversold:
            out.append(Blocker("rsi_os", "soft", f"RSI={rsi:.1f} oversold"))
        if atr and (close - swing_low) < 0.3 * atr:
            out.append(Blocker("near_sup", "soft", "close glued to support"))
        if macd_hist > 0 and macd_hist > macd_hist_prev:
            out.append(Blocker("macd_rising", "soft", "MACD still rising"))

    return out


# =============================================================================
# Main build
# =============================================================================

def _build_score_v4(
    records: List[StockRecord],
    bullish: bool,
    cfg: ScoreConfigV4,
) -> SignalScoreV4:
    w = cfg.weights
    p = cfg.periods
    t = cfg.toggles

    candle_score, candle_r = _score_candle_v4(records, bullish, cfg) if t.use_candle else (0.5, "")
    trend_score, trend_r = _score_trend_v4(records, bullish, cfg) if t.use_trend else (0.5, "")
    momentum_score, momentum_r = _score_momentum_v4(records, bullish, cfg) if t.use_momentum else (0.5, "")
    vol_setup, vs_r = _score_volume_setup_v4(records, bullish, cfg) if t.use_volume else (0.5, "")
    vol_trig, vt_r = _score_volume_trigger_v4(records, bullish, cfg) if t.use_volume else (0.5, "")
    structure_score, structure_r = _score_structure_v4(records, bullish, cfg) if t.use_structure else (0.5, "")
    confirmation_score, conf_r = _score_confirmation_v4(records, bullish, cfg) if t.use_confirmation else (0.5, "")
    divergence_score, div_r = _score_divergence_v4(records, bullish, cfg) if t.use_divergence else (0.0, "")
    regime_align, reg_r, regime = _score_regime_align_v4(records, bullish, cfg) if t.use_regime_align else (0.5, "", "unknown")
    prop_score, prop_r = _score_prop_trading_v4(records, bullish, cfg) if t.use_prop else (0.5, "")

    setup_score = (
        w.setup_candle    * candle_score
        + w.setup_trend     * trend_score
        + w.setup_momentum  * momentum_score
        + w.setup_volume    * vol_setup
        + w.setup_structure * structure_score
        + w.setup_regime    * regime_align
        + w.setup_prop      * prop_score
    )
    trigger_score = (
        w.trigger_confirmation * confirmation_score
        + w.trigger_volume       * vol_trig
        + w.trigger_candle       * candle_score
        + w.trigger_momentum     * momentum_score
        + w.trigger_divergence   * divergence_score
    )
    final_score = w.final_setup * setup_score + w.final_trigger * trigger_score

    # Blockers
    close = records[-1].priceClose
    adx = _safe_last(IndicatorGroup3.adx(records, p.adx))
    vols = [r.priceImpactVolume for r in records]
    avg_vol = sum(vols[-p.rvol:]) / min(p.rvol, len(vols)) if vols else 1.0
    rvol = records[-1].priceImpactVolume / avg_vol if avg_vol else 0.0
    rsi = _safe_last(IndicatorGroup2.rsi(records, p.rsi), 50.0)
    _, _, hist_s = IndicatorGroup2.macd(records, p.macd_fast, p.macd_slow, p.macd_signal)
    macd_hist = _safe_last(hist_s)
    macd_hist_prev = _safe_last(hist_s[:-1]) if len(hist_s) > 1 else 0.0
    atr = _safe_last(IndicatorGroup3.atr(records, p.atr))
    n = min(p.swing_short, len(records))
    swing_high = max(r.priceHigh for r in records[-n:])
    swing_low = min(r.priceLow for r in records[-n:])

    blockers = _detect_blockers_v4(
        records, bullish, adx, rvol, rsi,
        macd_hist, macd_hist_prev, close,
        swing_high, swing_low, atr, cfg,
    )

    # Apply soft penalty
    soft_count = sum(1 for b in blockers if b.severity == "soft")
    final_score = max(0.0, final_score - soft_count * cfg.thresholds.soft_penalty)

    reasons = [r for r in [candle_r, trend_r, momentum_r, vs_r, vt_r, structure_r, conf_r, div_r, reg_r, prop_r] if r]

    return SignalScoreV4(
        label="bullish" if bullish else "bearish",
        regime=regime,
        setup_score=round(setup_score, 4),
        trigger_score=round(trigger_score, 4),
        final_score=round(final_score, 4),
        candle_score=round(candle_score, 4),
        trend_score=round(trend_score, 4),
        momentum_score=round(momentum_score, 4),
        volume_setup_score=round(vol_setup, 4),
        volume_trigger_score=round(vol_trig, 4),
        structure_score=round(structure_score, 4),
        confirmation_score=round(confirmation_score, 4),
        divergence_score=round(divergence_score, 4),
        regime_align_score=round(regime_align, 4),
        prop_score=round(prop_score, 4),
        blockers=blockers,
        reasons=reasons,
    )


def calculate_signal_score_v4(
    records: List[StockRecord],
    cfg: Optional[ScoreConfigV4] = None,
) -> SignalScoreV4:
    if cfg is None:
        cfg = DEFAULT_SCORE_CONFIG_V4

    # Soft warm-up: under 30 bars return neutral, 30-60 return half-strength,
    # 60+ return full score.
    if len(records) < 30:
        return SignalScoreV4(reasons=["Warm-up<30"])

    bull = _build_score_v4(records, True, cfg)
    bear = _build_score_v4(records, False, cfg)

    winner = bull if bull.final_score >= bear.final_score else bear
    if len(records) < 60:
        winner.final_score = round(winner.final_score * 0.6, 4)
        winner.reasons.append("half-warmup")
    return winner
