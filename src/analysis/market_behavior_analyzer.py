from typing import List

import pandas as pd

from src.data.stock_data_loader import StockRecord
from src.analysis.technical_indicators import IndicatorGroup1, IndicatorGroup2, IndicatorGroup3, IndicatorGroup4


class MarketBehaviorSnapshot:
    """Container for derived market behavior overlays consumed by the chart."""

    def __init__(self):
        self.big_buyer: List[bool] = []
        self.fomo_retail: List[bool] = []
        self.total_volume: List[int] = []
        self.ema_volume: List[float] = []
        self.ema20: List[float] = []
        self.ema50: List[float] = []
        self.atr14: List[float] = []
        # One payload per trading day — built once, consumed by the chart renderer.
        self.hover_payloads: List[dict] = []


def _build_hover_payloads(
    stock_records: List[StockRecord],
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
        past = stock_records[max(0, i - 20):i]
        avg_vol = (sum(rec.priceImpactVolume for rec in past) / len(past)) if past else r.priceImpactVolume
        rvol = round(r.priceImpactVolume / avg_vol, 2) if avg_vol else None

        obv_slope = None
        if i >= 5 and len(obv_s) > i:
            obv_slope = round((obv_s[i] - obv_s[i - 5]) / 5, 0)

        w10 = stock_records[max(0, i - 9):i + 1]
        w20 = stock_records[max(0, i - 19):i + 1]

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
        })

    return payloads


def analyze_market_behavior(
    stock_records: List[StockRecord],
    period: int = 14,
) -> MarketBehaviorSnapshot:
    market_behavior = MarketBehaviorSnapshot()

    market_behavior.big_buyer = IndicatorGroup4.is_big_buyer(stock_records, period)
    market_behavior.fomo_retail = IndicatorGroup4.is_fomo_by_retail(stock_records, period)

    volume_series = [record.priceImpactVolume for record in stock_records]
    market_behavior.total_volume = volume_series
    market_behavior.ema_volume = (
        pd.Series(volume_series).ewm(span=period, adjust=False).mean().tolist()
    )
    market_behavior.ema20 = IndicatorGroup1.ema(stock_records, 20)
    market_behavior.ema50 = IndicatorGroup1.ema(stock_records, 50)
    market_behavior.atr14 = IndicatorGroup3.atr(stock_records, 14)

    market_behavior.hover_payloads = _build_hover_payloads(
        stock_records, market_behavior.ema20, market_behavior.ema50,
    )

    return market_behavior


MartketBehaviorDetector = MarketBehaviorSnapshot
detect_market_behavior = analyze_market_behavior
