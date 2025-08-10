from typing import List, Optional
from src.math.indicatiors import IndicatorGroup1, IndicatorGroup4
from src.math.candle_pattern import BullishPatterns, BearishPatterns
from src.base.load_stock_data import StockRecord

def calculate_stock_score(records: List[StockRecord]) -> float:
    if len(records) < 30:
        return 0  # không đủ dữ liệu

    score = 0

    ### 1. Trung bình động
    sma = IndicatorGroup1.sma(records, period=14)
    ema = IndicatorGroup1.ema(records, period=14)
    vwma = IndicatorGroup1.vwma(records, period=14)

    close = records[-1].priceClose

    if sma[-1] and close > sma[-1]:
        score += 1
    else:
        score -= 1

    if ema[-1] and close > ema[-1]:
        score += 1
    else:
        score -= 1

    if vwma[-1] and close > vwma[-1]:
        score += 1
    else:
        score -= 1

    ### 2. Khối lượng
    obv = IndicatorGroup4.obv(records)
    if len(obv) >= 2 and obv[-1] > obv[-2]:
        score += 1
    else:
        score -= 1

    cmf = IndicatorGroup4.chaikin_money_flow(records, period=20)
    if cmf[-1] is not None:
        if cmf[-1] > 0.05:
            score += 1
        elif cmf[-1] < -0.05:
            score -= 1

    ### 3. Mô hình nến
    bullish_score = 0
    bearish_score = 0
    
    bullish_score += BullishPatterns.hammer(records[-5:])
    bullish_score += BullishPatterns.bullish_engulfing(records[-5:])
    bullish_score += BullishPatterns.three_white_soldiers(records[-5:])
    
    bearish_score += BearishPatterns.shooting_star(records[-5:])
    bearish_score += BearishPatterns.bearish_engulfing(records[-5:])
    bearish_score += BearishPatterns.three_black_crows(records[-5:])

    #return  IndicatorGroup4.vroc_score(records)[-1]
    score += bullish_score
    score -= bearish_score

    #print(f"Score breakdown: {score}, Bullish: {bullish_score}, Bearish: {bearish_score}")
    return score
