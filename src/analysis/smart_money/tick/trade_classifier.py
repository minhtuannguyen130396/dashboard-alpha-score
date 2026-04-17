"""Trade classification (tick rule, Lee-Ready, BVC).

VN tick feeds rarely include a side flag, so primitives have to infer
buy/sell direction from price + (optional) bid/ask.
"""
import math
from statistics import mean, pstdev
from typing import List

from src.data.flow_records import IntradayFlowRecord, RawTick


def tick_rule_classify(ticks: List[RawTick]) -> List[RawTick]:
    """Mark each tick +1/-1/0 based on price change vs previous tick.

    Equal price → carry the previous side ("zero-uptick"/"zero-downtick").
    Accuracy ~70% on TAQ-style data per Lee & Ready (1991).
    """
    if not ticks:
        return ticks
    prev_price = ticks[0].price
    prev_side = 0
    for t in ticks:
        if t.price > prev_price:
            t.side = 1
        elif t.price < prev_price:
            t.side = -1
        else:
            t.side = prev_side
        prev_price = t.price
        prev_side = t.side
    return ticks


def lee_ready_classify(ticks: List[RawTick]) -> List[RawTick]:
    """Quote-rule + tick-rule fallback (Lee-Ready 1991). Needs bid/ask."""
    if not ticks:
        return ticks
    prev_price = ticks[0].price
    prev_side = 0
    for t in ticks:
        if t.bid is not None and t.ask is not None and t.ask > t.bid:
            mid = (t.bid + t.ask) / 2
            if t.price > mid:
                t.side = 1
            elif t.price < mid:
                t.side = -1
            else:
                # Mid-quote tie-breaker: tick rule
                if t.price > prev_price:
                    t.side = 1
                elif t.price < prev_price:
                    t.side = -1
                else:
                    t.side = prev_side
        else:
            # Missing quotes → fall back to tick rule
            if t.price > prev_price:
                t.side = 1
            elif t.price < prev_price:
                t.side = -1
            else:
                t.side = prev_side
        prev_price = t.price
        prev_side = t.side
    return ticks


def _normal_cdf(z: float) -> float:
    return 0.5 * (1 + math.erf(z / math.sqrt(2)))


def bvc_classify(bars: List[IntradayFlowRecord]) -> List[IntradayFlowRecord]:
    """Bulk Volume Classification — splits each bar's volume into buy/sell.

    Doesn't need bid/ask; uses the bar's close-vs-open displacement scaled
    by recent return volatility. Mutates each bar's ``buy_volume`` /
    ``sell_volume`` and returns the same list.
    """
    if not bars:
        return bars

    returns: List[float] = []
    prev_close = bars[0].close
    for b in bars[1:]:
        if prev_close > 0:
            returns.append((b.close - prev_close) / prev_close)
        prev_close = b.close

    if len(returns) >= 5:
        sigma = pstdev(returns) or 1e-9
    else:
        sigma = 0.01  # 1% fallback when not enough history

    for b in bars:
        if b.open <= 0 or sigma <= 0:
            buy_frac = 0.5
        else:
            z = (b.close - b.open) / (b.open * sigma)
            buy_frac = _normal_cdf(z)
        b.buy_volume = b.volume * buy_frac
        b.sell_volume = b.volume * (1 - buy_frac)
    return bars


class TradeClassifier:
    """Front-end that picks the right method based on data + config."""

    def __init__(self, method: str = "auto"):
        self.method = method

    def classify_ticks(self, ticks: List[RawTick]) -> List[RawTick]:
        method = self._resolve_for_ticks(ticks) if self.method == "auto" else self.method
        if method == "lee_ready":
            return lee_ready_classify(ticks)
        if method == "tick_rule":
            return tick_rule_classify(ticks)
        # BVC operates on bars, not ticks; fall back to tick rule for raw ticks
        return tick_rule_classify(ticks)

    def classify_bars(
        self, bars: List[IntradayFlowRecord],
    ) -> List[IntradayFlowRecord]:
        method = self._resolve_for_bars(bars) if self.method == "auto" else self.method
        if method == "bvc":
            return bvc_classify(bars)
        # tick_rule / lee_ready don't help if all you have is OHLCV bars
        return bvc_classify(bars)

    @staticmethod
    def _resolve_for_ticks(ticks: List[RawTick]) -> str:
        if not ticks:
            return "tick_rule"
        has_quotes = sum(
            1 for t in ticks[: min(50, len(ticks))]
            if t.bid is not None and t.ask is not None
        )
        if has_quotes >= 5:
            return "lee_ready"
        return "tick_rule"

    @staticmethod
    def _resolve_for_bars(bars: List[IntradayFlowRecord]) -> str:
        return "bvc"
