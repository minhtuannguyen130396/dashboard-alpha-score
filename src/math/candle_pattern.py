from typing import List, Optional
from datetime import datetime
from src.base.load_stock_data import StockRecord

def _extract(records: List[StockRecord], attr: str) -> List[float]:
    return [getattr(r, attr) for r in records]


def _candle_features(record: StockRecord):
    o = record.priceOpen
    h = record.priceHigh
    l = record.priceLow
    c = record.priceClose
    body = abs(c - o)
    total_range = h - l if h > l else 0.0
    upper_shadow = h - max(o, c)
    lower_shadow = min(o, c) - l
    return body, total_range, upper_shadow, lower_shadow


def _is_downtrend(records: List[StockRecord], lookback: int = 3) -> bool:
    closes = _extract(records, 'priceClose')
    if len(closes) < lookback + 1:
        return False
    for i in range(1, lookback + 1):
        if closes[-i] >= closes[-i-1]:
            return False
    return True


def _is_uptrend(records: List[StockRecord], lookback: int = 3) -> bool:
    closes = _extract(records, 'priceClose')
    if len(closes) < lookback + 1:
        return False
    for i in range(1, lookback + 1):
        if closes[-i] <= closes[-i-1]:
            return False
    return True


class BullishPatterns:
    @staticmethod
    def hammer(records: List[StockRecord]) -> int:
        if not _is_downtrend(records):
            return 0
        r = records[-1]
        body, total, up, low = _candle_features(r)
        if total == 0:
            return 0
        if body <= total * 0.3 and low >= body * 2 and up <= body:
            print("Hammer pattern detected (Bullish Reversal)")
            return 1
        return 0

    @staticmethod
    def inverted_hammer(records: List[StockRecord]) -> int:
        if not _is_downtrend(records):
            return 0
        r = records[-1]
        body, total, up, low = _candle_features(r)
        if total == 0:
            return 0
        if body <= total * 0.3 and up >= body * 2 and low <= body:
            print("Inverted Hammer pattern detected (Bullish Reversal)")
            return 1
        return 0

    @staticmethod
    def bullish_engulfing(records: List[StockRecord]) -> int:
        if len(records) < 2:
            return 0
        prev, curr = records[-2], records[-1]
        if prev.priceClose < prev.priceOpen and curr.priceClose > curr.priceOpen:
            if curr.priceOpen < prev.priceClose and curr.priceClose > prev.priceOpen:
                print("Bullish Engulfing pattern detected")
                return 1
        return 0

    @staticmethod
    def piercing_pattern(records: List[StockRecord]) -> int:
        if len(records) < 2:
            return 0
        prev, curr = records[-2], records[-1]
        if prev.priceClose < prev.priceOpen and curr.priceClose > curr.priceOpen:
            mid = prev.priceOpen - (prev.priceOpen - prev.priceClose) * 0.5
            if curr.priceClose > mid and curr.priceOpen < prev.priceClose:
                print("Piercing Pattern detected")
                return 1
        return 0

    @staticmethod
    # 65~80 %
    def morning_star(records: List[StockRecord]) -> int: 
        if len(records) < 3:
            return 0
        first, second, third = records[-3], records[-2], records[-1]
        if first.priceClose >= first.priceOpen:
            return 0
        sec_body = abs(second.priceClose - second.priceOpen)
        sec_range = second.priceHigh - second.priceLow if second.priceHigh > second.priceLow else 0
        if sec_range == 0 or sec_body > sec_range * 0.3:
            return 0
        if third.priceClose > third.priceOpen and third.priceClose > (first.priceOpen + first.priceClose) / 2:
            print("Morning Star pattern detected")
            return 1
        return 0

    @staticmethod
    def three_white_soldiers(records: List[StockRecord]) -> int:
        if len(records) < 3:
            return 0
        for i in range(-3, 0):
            r = records[i]
            if r.priceClose <= r.priceOpen:
                return 0
            body = abs(r.priceClose - r.priceOpen)
            total = r.priceHigh - r.priceLow if r.priceHigh > r.priceLow else 0
            if total == 0 or body < total * 0.6:
                return 0
        print("Three White Soldiers pattern detected (Very Strong Bullish)")
        return 1

    @staticmethod
    def doji_dragonfly(records: List[StockRecord]) -> int:
        r = records[-1]
        body = abs(r.priceClose - r.priceOpen)
        up = r.priceHigh - max(r.priceOpen, r.priceClose)
        low = min(r.priceOpen, r.priceClose) - r.priceLow
        if body <= (r.priceHigh - r.priceLow) * 0.1 and up <= body * 0.1 and low >= body * 2:
            print("Dragonfly Doji pattern detected (Bullish Reversal)")
            return 1
        return 0


class BearishPatterns:
    @staticmethod
    def shooting_star(records: List[StockRecord]) -> int:
        if not _is_uptrend(records):
            return 0
        r = records[-1]
        body, total, up, low = _candle_features(r)
        if total == 0:
            return 0
        if body <= total * 0.3 and up >= body * 2 and low <= body:
            print("Shooting Star pattern detected (Bearish Reversal)")
            return -1
        return 0

    @staticmethod
    def hanging_man(records: List[StockRecord]) -> int:
        if not _is_uptrend(records):
            return 0
        r = records[-1]
        body, total, up, low = _candle_features(r)
        if total == 0:
            return 0
        if body <= total * 0.3 and low >= body * 2 and up <= body:
            print("Hanging Man pattern detected (Bearish Reversal)")
            return -1
        return 0

    @staticmethod
    def bearish_engulfing(records: List[StockRecord]) -> int:
        if len(records) < 2:
            return 0
        prev, curr = records[-2], records[-1]
        if prev.priceClose > prev.priceOpen and curr.priceClose < curr.priceOpen:
            if curr.priceOpen > prev.priceClose and curr.priceClose < prev.priceOpen:
                print("Bearish Engulfing pattern detected")
                return -1
        return 0

    @staticmethod
    def dark_cloud_cover(records: List[StockRecord]) -> int:
        if len(records) < 2:
            return 0
        prev, curr = records[-2], records[-1]
        if prev.priceClose > prev.priceOpen and curr.priceClose < curr.priceOpen:
            mid = prev.priceClose - (prev.priceClose - prev.priceOpen) * 0.5
            if curr.priceClose < mid and curr.priceOpen > prev.priceClose:
                print("Dark Cloud Cover pattern detected")
                return -1
        return 0

    @staticmethod
    def evening_star(records: List[StockRecord]) -> int:
        if len(records) < 3:
            return 0
        first, second, third = records[-3], records[-2], records[-1]
        if first.priceClose <= first.priceOpen:
            return 0
        sec_body = abs(second.priceClose - second.priceOpen)
        sec_range = second.priceHigh - second.priceLow if second.priceHigh > second.priceLow else 0
        if sec_range == 0 or sec_body > sec_range * 0.3:
            return 0
        if third.priceClose < third.priceOpen and third.priceClose < (first.priceOpen + first.priceClose) / 2:
            print("Evening Star pattern detected")
            return -1
        return 0

    @staticmethod
    def three_black_crows(records: List[StockRecord]) -> int:
        if len(records) < 3:
            return 0
        for i in range(-3, 0):
            r = records[i]
            if r.priceClose >= r.priceOpen:
                return 0
            body = abs(r.priceClose - r.priceOpen)
            total = r.priceHigh - r.priceLow if r.priceHigh > r.priceLow else 0
            if total == 0 or body < total * 0.6:
                return 0
        print("Three Black Crows pattern detected (Very Strong Bearish)")
        return -1

    @staticmethod
    def doji_gravestone(records: List[StockRecord]) -> int:
        r = records[-1]
        body = abs(r.priceClose - r.priceOpen)
        up = r.priceHigh - max(r.priceOpen, r.priceClose)
        low = min(r.priceOpen, r.priceClose) - r.priceLow
        if body <= (r.priceHigh - r.priceLow) * 0.1 and low <= body * 0.1 and up >= body * 2:
            print("Gravestone Doji pattern detected (Bearish Reversal)")
            return -1
        return 0


class NeutralPatterns:
    @staticmethod
    def doji(records: List[StockRecord]) -> int:
        r = records[-1]
        body = abs(r.priceClose - r.priceOpen)
        total = r.priceHigh - r.priceLow if r.priceHigh > r.priceLow else 0
        if total > 0 and body <= total * 0.1:
            print("Doji detected (Neutral)")
        return 0

    @staticmethod
    def spinning_top(records: List[StockRecord]) -> int:
        r = records[-1]
        body = abs(r.priceClose - r.priceOpen)
        up = r.priceHigh - max(r.priceOpen, r.priceClose)
        low = min(r.priceOpen, r.priceClose) - r.priceLow
        total = r.priceHigh - r.priceLow if r.priceHigh > r.priceLow else 0
        if total > 0 and body <= total * 0.3 and up > body and low > body:
            print("Spinning Top detected (Neutral)")
        return 0

    @staticmethod
    def rising_three_methods(records: List[StockRecord]) -> int:
        if len(records) < 5:
            return 0
        print("Rising/Falling Three Methods detected (Neutral/Continuation)")
        return 0
