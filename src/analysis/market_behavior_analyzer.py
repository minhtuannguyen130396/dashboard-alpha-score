from typing import List

import pandas as pd

from src.data.stock_data_loader import StockRecord
from src.analysis.signal_scoring import SignalScore
from src.analysis.technical_indicators import IndicatorGroup1, IndicatorGroup3, IndicatorGroup4


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


def analyze_market_behavior(
    stock_records: List[StockRecord],
    signal_scores: List[SignalScore],
    sale_threshold: float = 0.7,
    buy_threshold: float = 0.7,
    period: int = 14,
) -> MarketBehaviorSnapshot:
    market_behavior = MarketBehaviorSnapshot()

    market_behavior.big_buyer = IndicatorGroup4.is_big_buyer(stock_records, period)
    market_behavior.fomo_retail = IndicatorGroup4.is_fomo_by_retail(stock_records, period)
    market_behavior.buy_point = [
        score.label == "bullish" and score.final_score >= buy_threshold
        for score in signal_scores
    ]
    market_behavior.sale_point = [
        score.label == "bearish" and score.final_score >= sale_threshold
        for score in signal_scores
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

    return market_behavior


MartketBehaviorDetector = MarketBehaviorSnapshot
detect_market_behavior = analyze_market_behavior
