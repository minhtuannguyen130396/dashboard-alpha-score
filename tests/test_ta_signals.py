import unittest
from datetime import datetime, timedelta
from typing import List, Optional, Sequence

from src.analysis.technical_indicators import IndicatorGroup3
from src.data.stock_data_loader import StockRecord
from src.ta.config import AdxConfig, RsiConfig
from src.ta.indicators_ext import adx_di
from src.ta.signals import (
    OVERBOUGHT_LOSS, OVERSOLD_RECLAIM, adx_state, detect_rsi_events, rsi_zone_state,
)


def _record(day_offset: int, close: float, high: Optional[float] = None,
            low: Optional[float] = None) -> StockRecord:
    """Minimal record — only the fields the signal code touches carry meaning."""
    return StockRecord(
        date=datetime(2026, 1, 1) + timedelta(days=day_offset),
        symbol="TST",
        priceHigh=high if high is not None else close + 1,
        priceLow=low if low is not None else close - 1,
        priceOpen=close,
        priceAverage=close,
        priceClose=close,
        priceBasic=close,
        totalVolume=1000.0,
        dealVolume=1000.0,
        putthroughVolume=0.0,
        totalValue=0.0,
        putthroughValue=0.0,
        buyForeignQuantity=0.0,
        buyForeignValue=0.0,
        sellForeignQuantity=0.0,
        sellForeignValue=0.0,
        buyCount=0.0,
        buyQuantity=0.0,
        sellCount=0.0,
        sellQuantity=0.0,
        adjRatio=1.0,
        currentForeignRoom=0.0,
        propTradingNetDealValue=None,
        propTradingNetPTValue=None,
        propTradingNetValue=None,
        unit=1.0,
    )


def _series(closes: Sequence[float]) -> List[StockRecord]:
    return [_record(i, c) for i, c in enumerate(closes)]


class RsiOversoldReclaimTest(unittest.TestCase):
    """The user's rule: dip below 30, turn, come back and touch 30 -> report."""

    def test_fires_on_the_bar_that_touches_the_threshold_back(self):
        rsi = [50, 40, 28, 22, 25, 31, 45]
        events = detect_rsi_events(_series([10] * len(rsi)), RsiConfig(), rsi)

        self.assertEqual(len(events), 1)
        event = events[0]
        self.assertEqual(event.kind, OVERSOLD_RECLAIM)
        self.assertEqual(event.index, 5)          # the bar where RSI reached 31
        self.assertEqual(event.extreme, 22)       # deepest point inside the zone
        self.assertEqual(event.bars_in_zone, 3)
        self.assertEqual(event.depth, 8.0)        # 30 - 22

    def test_silent_while_rsi_is_still_below_the_threshold(self):
        rsi = [50, 28, 22, 24, 26, 29]            # turned up, but never reached 30
        events = detect_rsi_events(_series([10] * len(rsi)), RsiConfig(), rsi)
        self.assertEqual(events, [])

    def test_touching_the_threshold_exactly_counts_as_a_reclaim(self):
        rsi = [50, 25, 24, 30]
        events = detect_rsi_events(_series([10] * len(rsi)), RsiConfig(), rsi)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].rsi, 30)

    def test_price_confirmation_follows_the_close(self):
        rsi = [50, 25, 24, 31]
        rising = detect_rsi_events(_series([10, 10, 10, 11]), RsiConfig(), rsi)[0]
        falling = detect_rsi_events(_series([10, 10, 10, 9]), RsiConfig(), rsi)[0]
        self.assertTrue(rising.price_confirms)
        self.assertFalse(falling.price_confirms)


class RsiOverboughtLossTest(unittest.TestCase):
    """Mirror rule: push above 70, turn, come back and touch 70 -> report."""

    def test_fires_when_rsi_returns_to_the_overbought_line(self):
        rsi = [50, 65, 74, 80, 76, 68, 55]
        events = detect_rsi_events(_series([10] * len(rsi)), RsiConfig(), rsi)

        self.assertEqual(len(events), 1)
        event = events[0]
        self.assertEqual(event.kind, OVERBOUGHT_LOSS)
        self.assertEqual(event.side, "bearish")
        self.assertEqual(event.index, 5)
        self.assertEqual(event.extreme, 80)
        self.assertEqual(event.bars_in_zone, 3)
        self.assertEqual(event.depth, 10.0)

    def test_silent_while_rsi_stays_above_the_threshold(self):
        rsi = [50, 74, 82, 78, 73]
        self.assertEqual(detect_rsi_events(_series([10] * 5), RsiConfig(), rsi), [])


class RsiQualityGradingTest(unittest.TestCase):
    def test_single_bar_wick_is_weak(self):
        rsi = [50, 29, 45]                       # 1 bar in zone, only 1 point deep
        event = detect_rsi_events(_series([10] * 3), RsiConfig(), rsi)[0]
        self.assertEqual(event.quality, "weak")
        self.assertEqual(event.bars_in_zone, 1)

    def test_deep_sustained_dip_is_strong(self):
        rsi = [50, 28, 24, 20, 22, 26, 31]       # 5 bars in zone, 10 points deep
        event = detect_rsi_events(_series([10] * 7), RsiConfig(), rsi)[0]
        self.assertEqual(event.quality, "strong")

    def test_bullish_divergence_when_price_makes_a_lower_low_and_rsi_does_not(self):
        rsi = [50, 20, 35, 50, 25, 40]
        # bar 4 (RSI 25) is a higher RSI low, on a lower price low than bar 1
        closes = [30, 20, 25, 28, 18, 24]
        records = [_record(i, c, high=c + 1, low=c - 1) for i, c in enumerate(closes)]
        events = detect_rsi_events(records, RsiConfig(), rsi)
        self.assertEqual(len(events), 2)
        self.assertFalse(events[0].divergence)
        self.assertTrue(events[1].divergence)

    def test_consecutive_zones_do_not_leak_state(self):
        rsi = [50, 25, 35, 24, 22, 33]
        events = detect_rsi_events(_series([10] * 6), RsiConfig(), rsi)
        self.assertEqual([e.bars_in_zone for e in events], [1, 2])


class RsiZoneStateTest(unittest.TestCase):
    def test_turning_up_while_still_inside_the_oversold_zone(self):
        rsi = [50, 22, 20, 24, 27]               # 7 points off the trough, still < 30
        state = rsi_zone_state(_series([10] * 5), RsiConfig(), rsi)
        self.assertEqual(state.state, "turning_up")
        self.assertEqual(state.extreme, 20)
        self.assertEqual(state.recovered, 7.0)
        self.assertEqual(state.distance_to_threshold, 3.0)

    def test_still_falling_inside_the_zone_is_not_turning(self):
        rsi = [50, 28, 24, 21]
        state = rsi_zone_state(_series([10] * 4), RsiConfig(), rsi)
        self.assertEqual(state.state, "in_oversold")

    def test_turning_down_while_still_inside_the_overbought_zone(self):
        rsi = [50, 78, 82, 77, 74]
        state = rsi_zone_state(_series([10] * 5), RsiConfig(), rsi)
        self.assertEqual(state.state, "turning_down")
        self.assertEqual(state.extreme, 82)

    def test_neutral_between_the_thresholds(self):
        state = rsi_zone_state(_series([10] * 3), RsiConfig(), [45, 50, 55])
        self.assertEqual(state.state, "neutral")


class ThresholdConfigTest(unittest.TestCase):
    def test_custom_thresholds_shift_the_zones(self):
        cfg = RsiConfig(oversold=25.0, overbought=75.0)
        rsi = [50, 28, 26, 31]                   # never below 25
        self.assertEqual(detect_rsi_events(_series([10] * 4), cfg, rsi), [])

        rsi2 = [50, 24, 22, 26]                  # dips below 25 and reclaims it
        events = detect_rsi_events(_series([10] * 4), cfg, rsi2)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].threshold, 25.0)


class AdxTest(unittest.TestCase):
    """+DI / -DI are new; ADX itself must stay identical to the existing one."""

    def setUp(self):
        closes = [10 + (i % 7) - (i % 3) + i * 0.05 for i in range(80)]
        self.records = [
            _record(i, c, high=c + 0.6, low=c - 0.6) for i, c in enumerate(closes)
        ]

    def test_adx_matches_the_existing_implementation(self):
        original = IndicatorGroup3.adx(self.records, 14)
        adx, _, _ = adx_di(self.records, 14)
        for a, b in zip(original, adx):
            if a is None or b is None:
                self.assertIs(a, b)
            else:
                self.assertAlmostEqual(a, b, places=9)

    def test_di_series_align_with_records(self):
        adx, pdi, mdi = adx_di(self.records, 14)
        self.assertEqual(len(adx), len(self.records))
        self.assertEqual(len(pdi), len(self.records))
        self.assertIsNone(pdi[13])
        self.assertIsNotNone(pdi[14])            # +DI is available from index period
        self.assertIsNotNone(adx[27])            # ADX from index 2*period - 1

    def test_short_history_yields_no_values(self):
        adx, pdi, mdi = adx_di(self.records[:20], 14)
        self.assertTrue(all(v is None for v in adx))
        self.assertTrue(all(v is None for v in pdi))

    def test_regime_bands(self):
        state = adx_state(self.records, AdxConfig())
        self.assertIn(state.regime, ("no_trend", "emerging", "strong"))
        self.assertEqual(state.has_momentum, state.adx >= 20.0)
        self.assertIn(state.direction, ("up", "down", "flat"))

    def test_regime_threshold_is_configurable(self):
        state = adx_state(self.records, AdxConfig(trend_threshold=99.0))
        self.assertFalse(state.has_momentum)

    def test_missing_data_is_reported_not_crashed(self):
        state = adx_state(self.records[:5], AdxConfig())
        self.assertEqual(state.regime, "no_data")
        self.assertFalse(state.has_momentum)


class EmptyInputTest(unittest.TestCase):
    def test_no_records_is_safe(self):
        self.assertEqual(detect_rsi_events([], RsiConfig()), [])
        self.assertEqual(rsi_zone_state([], RsiConfig()).state, "neutral")


if __name__ == "__main__":
    unittest.main()
