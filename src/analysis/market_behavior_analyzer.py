from typing import List

import pandas as pd

from src.data.stock_data_loader import StockRecord
from src.analysis.signal_scoring_v4 import SignalScoreV4
from src.analysis.score_config import DEFAULT_SCORE_CONFIG_V4
from src.analysis.technical_indicators import IndicatorGroup1, IndicatorGroup2, IndicatorGroup3, IndicatorGroup4


# Regimes in which a bearish score should NOT trigger an exit on its own.
# In a clearly bullish regime the trade simulator's ATR/trailing stop is
# the right exit mechanism — a single bearish bar should not cut a winner.
_BULL_REGIMES = {"bull_trend", "mild_bull"}

# Only these regimes allow a bullish entry. After tightening
# `bull_trend` to require EMA50>EMA100, `mild_bull` becomes the
# counter-trend bucket — excluding it removes most losers on basket
# tests. `bullish_reversal` is the labelled "first bullish bar after a
# confirmed bear_trend" state and is allowed.
_BUY_OK_REGIMES = {"bull_trend", "bullish_reversal"}


class MarketBehaviorSnapshot:
    """Container for derived market behavior signals and overlays."""

    def __init__(self):
        self.sale_point: List[bool] = []
        self.buy_point: List[bool] = []
        self.big_buyer: List[bool] = []
        self.fomo_retail: List[bool] = []
        self.total_volume: List[int] = []
        self.ema_volume: List[float] = []
        self.ema20: List[float] = []
        self.ema50: List[float] = []
        self.atr14: List[float] = []
        self.signal_scores: List[float] = []
        self.signal_labels: List[str] = []
        self.signal_reasons: List[str] = []
        # One payload per trading day — built once, consumed by the chart renderer.
        self.hover_payloads: List[dict] = []


def _build_hover_payloads(
    stock_records: List[StockRecord],
    signal_scores: List[SignalScoreV4],
    buy_point: List[bool],
    sale_point: List[bool],
    ema20: list,
    ema50: list,
) -> List[dict]:
    """Compute one hover payload per trading day.

    All indicators are calculated once on the full series here — the frontend
    never recomputes anything, it only reads from the pre-built dict.
    """
    ema100_s    = IndicatorGroup1.ema(stock_records, 100)
    atr14_s     = IndicatorGroup3.atr(stock_records, 14)
    rsi14_s     = IndicatorGroup2.rsi(stock_records, 14)
    macd_l, macd_sig, macd_h = IndicatorGroup2.macd(stock_records)
    adx14_s     = IndicatorGroup3.adx(stock_records, 14)
    mfi14_s     = IndicatorGroup4.mfi(stock_records, 14)
    obv_s       = IndicatorGroup4.obv(stock_records)

    def _v(series, i):
        if series and i < len(series) and series[i] is not None:
            return round(float(series[i]), 4)
        return None

    payloads: List[dict] = []
    for i, r in enumerate(stock_records):
        score = signal_scores[i] if i < len(signal_scores) else None

        past = stock_records[max(0, i - 20):i]
        avg_vol = (sum(rec.priceImpactVolume for rec in past) / len(past)) if past else r.priceImpactVolume
        rvol = round(r.priceImpactVolume / avg_vol, 2) if avg_vol else None

        obv_slope = None
        if i >= 5 and len(obv_s) > i:
            obv_slope = round((obv_s[i] - obv_s[i - 5]) / 5, 0)

        w10 = stock_records[max(0, i - 9):i + 1]
        w20 = stock_records[max(0, i - 19):i + 1]

        scores: dict = {}
        reasons: List[str] = []
        blockers: List[str] = []
        label = "none"
        regime = None

        if score is not None:
            label = getattr(score, "label", "none")
            reasons = list(getattr(score, "reasons", []))
            regime = getattr(score, "regime", None)
            scores = {
                "final":        round(getattr(score, "final_score", 0.0), 4),
                "setup":        round(getattr(score, "setup_score", 0.0), 4),
                "trigger":      round(getattr(score, "trigger_score", 0.0), 4),
                "candle":       round(getattr(score, "candle_score", 0.0), 4),
                "trend":        round(getattr(score, "trend_score", 0.0), 4),
                "momentum":     round(getattr(score, "momentum_score", 0.0), 4),
                "volume":       round(getattr(score, "volume_score", 0.0), 4),
                "vol_setup":    round(getattr(score, "volume_setup_score", 0.0), 4),
                "vol_trigger":  round(getattr(score, "volume_trigger_score", 0.0), 4),
                "structure":    round(getattr(score, "structure_score", 0.0), 4),
                "confirmation": round(getattr(score, "confirmation_score", 0.0), 4),
                "divergence":   round(getattr(score, "divergence_score", 0.0), 4),
                "regime_align": round(getattr(score, "regime_align_score", 0.0), 4),
            }
            blockers = list(getattr(score, "blockers_text", []))

        payloads.append({
            "date":   r.date.strftime("%Y-%m-%d"),
            "symbol": r.symbol,
            "price": {
                "open":   round(r.priceOpen, 2),
                "high":   round(r.priceHigh, 2),
                "low":    round(r.priceLow, 2),
                "close":  round(r.priceClose, 2),
                "avg":    round(r.priceAverage, 2),
                "volume": int(r.priceImpactVolume),
                "rvol":   rvol,
            },
            "indicators": {
                "ema20":      _v(ema20, i),
                "ema50":      _v(ema50, i),
                "ema100":     _v(ema100_s, i),
                "atr14":      _v(atr14_s, i),
                "rsi14":      _v(rsi14_s, i),
                "macd_line":  _v(macd_l, i),
                "macd_sig":   _v(macd_sig, i),
                "macd_hist":  _v(macd_h, i),
                "adx":        _v(adx14_s, i),
                "mfi":        _v(mfi14_s, i),
                "obv_slope":  obv_slope,
                "sw_hi10":    round(max(rec.priceHigh for rec in w10), 2),
                "sw_lo10":    round(min(rec.priceLow  for rec in w10), 2),
                "sw_hi20":    round(max(rec.priceHigh for rec in w20), 2),
                "sw_lo20":    round(min(rec.priceLow  for rec in w20), 2),
            },
            "scores":  scores,
            "signals": {
                "label":   label,
                "regime":  regime,
                "is_buy":  bool(buy_point[i]),
                "is_sale": bool(sale_point[i]),
            },
            "reasons":  reasons,
            "blockers": blockers,
        })

    return payloads


def _has_hard_blocker(score: SignalScoreV4) -> bool:
    return any(b.severity == "hard" for b in score.blockers)


def _is_buy_signal(score: SignalScoreV4) -> bool:
    """Buy when setup is solid, both gates clear and no hard blocker.

    Three-stage filter:
    1. Regime gate — buy only in bull_trend / mild_bull / bullish_reversal.
       Anywhere else (sideway, mild_bear, bear_trend) the win-rate
       collapses on basket tests.
    2. Setup gate — require setup_score >= setup_good. Setup represents
       *context*, so a weak setup (below 0.65) means we are entering on
       a confirmation/breakout without underlying support.
    3. Trigger + final gate — the today-action confirmation.
    """
    t = DEFAULT_SCORE_CONFIG_V4.thresholds
    if score.label != "bullish":
        return False
    if score.regime not in _BUY_OK_REGIMES:
        return False
    if score.setup_score < t.setup_good:
        return False
    return (
        score.final_score >= t.final_signal
        and score.trigger_score >= t.trigger
        and not _has_hard_blocker(score)
    )


def _is_sale_signal(score: SignalScoreV4) -> bool:
    """Asymmetric sell: looser thresholds, but suppressed in bull regimes.

    Rationale: when we're in a clearly bullish regime, the trade
    simulator's ATR / trailing stop should manage the exit. Letting a
    single bearish bar fire a sell signal cuts winners prematurely.
    Sells are only meaningful when the regime has flipped (or is
    drifting bearish), or as a counter-trend warning during reversals.
    """
    t = DEFAULT_SCORE_CONFIG_V4.thresholds
    if score.label != "bearish":
        return False
    if score.regime in _BULL_REGIMES:
        return False
    return (
        score.final_score >= t.sell_final
        and score.trigger_score >= t.sell_trigger
        and not _has_hard_blocker(score)
    )


def analyze_market_behavior(
    stock_records: List[StockRecord],
    signal_scores: List[SignalScoreV4],
    period: int = 14,
) -> MarketBehaviorSnapshot:
    market_behavior = MarketBehaviorSnapshot()

    market_behavior.big_buyer = IndicatorGroup4.is_big_buyer(stock_records, period)
    market_behavior.fomo_retail = IndicatorGroup4.is_fomo_by_retail(stock_records, period)
    market_behavior.buy_point = [_is_buy_signal(score) for score in signal_scores]
    market_behavior.sale_point = [_is_sale_signal(score) for score in signal_scores]

    volume_series = [record.priceImpactVolume for record in stock_records]
    market_behavior.total_volume = volume_series
    market_behavior.ema_volume = (
        pd.Series(volume_series).ewm(span=period, adjust=False).mean().tolist()
    )
    market_behavior.ema20 = IndicatorGroup1.ema(stock_records, 20)
    market_behavior.ema50 = IndicatorGroup1.ema(stock_records, 50)
    market_behavior.atr14 = IndicatorGroup3.atr(stock_records, 14)
    market_behavior.signal_scores = [score.final_score for score in signal_scores]
    market_behavior.signal_labels = [score.label for score in signal_scores]
    market_behavior.signal_reasons = [score.reason_text for score in signal_scores]

    market_behavior.hover_payloads = _build_hover_payloads(
        stock_records, signal_scores,
        market_behavior.buy_point, market_behavior.sale_point,
        market_behavior.ema20, market_behavior.ema50,
    )

    return market_behavior


MartketBehaviorDetector = MarketBehaviorSnapshot
detect_market_behavior = analyze_market_behavior
