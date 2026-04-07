from typing import List, Union

import pandas as pd

from src.data.stock_data_loader import StockRecord
from src.analysis.signal_scoring import SignalScore, SignalScoreV2
from src.analysis.technical_indicators import IndicatorGroup1, IndicatorGroup2, IndicatorGroup3, IndicatorGroup4


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
    signal_scores: List[Union[SignalScore, SignalScoreV2]],
    buy_point: List[bool],
    sale_point: List[bool],
    ema20: list,
    ema50: list,
) -> List[dict]:
    """Compute one hover payload per trading day.

    All indicators are calculated once on the full series here — the frontend
    never recomputes anything, it only reads from the pre-built dict.
    """
    # Full-series indicator pass (O(N) each, done once)
    ema100_s    = IndicatorGroup1.ema(stock_records, 100)
    atr14_s     = IndicatorGroup3.atr(stock_records, 14)
    rsi14_s     = IndicatorGroup2.rsi(stock_records, 14)
    macd_l, macd_sig, macd_h = IndicatorGroup2.macd(stock_records)
    adx14_s     = IndicatorGroup3.adx(stock_records, 14)
    mfi14_s     = IndicatorGroup4.mfi(stock_records, 14)
    obv_s       = IndicatorGroup4.obv(stock_records)   # length == N

    def _v(series, i):
        """Safe float lookup — returns None when value is missing."""
        if series and i < len(series) and series[i] is not None:
            return round(float(series[i]), 4)
        return None

    payloads: List[dict] = []
    for i, r in enumerate(stock_records):
        score = signal_scores[i] if i < len(signal_scores) else None

        # RVOL: today / avg(last 20 sessions, excluding today — no look-ahead)
        past = stock_records[max(0, i - 20):i]
        avg_vol = (sum(rec.totalVolume for rec in past) / len(past)) if past else r.totalVolume
        rvol = round(r.totalVolume / avg_vol, 2) if avg_vol else None

        # OBV slope over last 5 sessions
        obv_slope = None
        if i >= 5 and len(obv_s) > i:
            obv_slope = round((obv_s[i] - obv_s[i - 5]) / 5, 0)

        # Swing levels with true lookback (no future data)
        w10 = stock_records[max(0, i - 9):i + 1]
        w20 = stock_records[max(0, i - 19):i + 1]

        # Score decomposition — works for both v1 and v2
        scores: dict = {}
        reasons: List[str] = []
        blockers: List[str] = []
        label = "none"
        regime = None

        if score is not None:
            label = score.label
            reasons = list(score.reasons)
            if isinstance(score, SignalScoreV2):
                regime = score.regime
                scores = {
                    "final":        round(score.final_score, 4),
                    "setup":        round(score.setup_score, 4),
                    "trigger":      round(score.trigger_score, 4),
                    "candle":       round(score.candle_score, 4),
                    "trend":        round(score.trend_score, 4),
                    "momentum":     round(score.momentum_score, 4),
                    "volume":       round(score.volume_score, 4),
                    "structure":    round(score.structure_score, 4),
                    "confirmation": round(score.confirmation_score, 4),
                }
                blockers = list(score.blockers)
            else:
                scores = {
                    "final":   round(score.final_score, 4),
                    "candle":  round(score.candle_score, 4),
                    "volume":  round(score.volume_score, 4),
                    "context": round(score.context_score, 4),
                    "pivot":   round(score.pivot_score, 4),
                }

        payloads.append({
            "date":   r.date.strftime("%Y-%m-%d"),
            "symbol": r.symbol,
            "price": {
                "open":   round(r.priceOpen, 2),
                "high":   round(r.priceHigh, 2),
                "low":    round(r.priceLow, 2),
                "close":  round(r.priceClose, 2),
                "avg":    round(r.priceAverage, 2),
                "volume": int(r.totalVolume),
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


def _is_buy_signal(score: Union[SignalScore, SignalScoreV2], threshold: float) -> bool:
    """Return True if the score represents a valid buy signal above threshold."""
    if isinstance(score, SignalScoreV2):
        # For v2, also require trigger_score above threshold and no critical blockers
        return (
            score.label == "bullish"
            and score.final_score >= threshold
            and score.trigger_score >= threshold
            and len(score.blockers) == 0
        )
    return score.label == "bullish" and score.final_score >= threshold


def _is_sale_signal(score: Union[SignalScore, SignalScoreV2], threshold: float) -> bool:
    """Return True if the score represents a valid sell signal above threshold."""
    if isinstance(score, SignalScoreV2):
        return (
            score.label == "bearish"
            and score.final_score >= threshold
            and score.trigger_score >= threshold
            and len(score.blockers) == 0
        )
    return score.label == "bearish" and score.final_score >= threshold


def analyze_market_behavior(
    stock_records: List[StockRecord],
    signal_scores: List[Union[SignalScore, SignalScoreV2]],
    sale_threshold: float = 0.7,
    buy_threshold: float = 0.7,
    period: int = 14,
) -> MarketBehaviorSnapshot:
    market_behavior = MarketBehaviorSnapshot()

    market_behavior.big_buyer = IndicatorGroup4.is_big_buyer(stock_records, period)
    market_behavior.fomo_retail = IndicatorGroup4.is_fomo_by_retail(stock_records, period)
    market_behavior.buy_point = [
        _is_buy_signal(score, buy_threshold) for score in signal_scores
    ]
    market_behavior.sale_point = [
        _is_sale_signal(score, sale_threshold) for score in signal_scores
    ]

    volume_series = [record.totalVolume for record in stock_records]
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
