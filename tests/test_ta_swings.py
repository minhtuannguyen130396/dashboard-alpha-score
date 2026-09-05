import unittest
from datetime import datetime, timedelta
from typing import List, Sequence

from src.data.stock_data_loader import StockRecord
from src.ta.swings import (
    BOS, CHOCH, DOWNTREND, HH, HL, LH, LL, RANGE, UPTREND, build_market_structure,
    label_swings,
)
from src.ta.pivots import HIGH, LOW, Pivot


def _bar(i: int, price: float, pad: float = 0.4) -> StockRecord:
    return StockRecord(
        date=datetime(2026, 1, 1) + timedelta(days=i),
        symbol="TST",
        priceHigh=price + pad, priceLow=price - pad, priceOpen=price,
        priceAverage=price, priceClose=price, priceBasic=price,
        totalVolume=1e6, dealVolume=1e6, putthroughVolume=0.0,
        totalValue=0.0, putthroughValue=0.0,
        buyForeignQuantity=0.0, buyForeignValue=0.0,
        sellForeignQuantity=0.0, sellForeignValue=0.0,
        buyCount=0.0, buyQuantity=0.0, sellCount=0.0, sellQuantity=0.0,
        adjRatio=1.0, currentForeignRoom=0.0,
        propTradingNetDealValue=None, propTradingNetPTValue=None,
        propTradingNetValue=None, unit=1.0,
    )


def _walk(legs: Sequence[float], bars_per_leg: int = 7) -> List[StockRecord]:
    out: List[StockRecord] = []
    i = 0
    for a, b in zip(legs, legs[1:]):
        for step in range(bars_per_leg):
            out.append(_bar(i, a + (b - a) * step / bars_per_leg))
            i += 1
    out.append(_bar(i, legs[-1]))
    return out


def _pivot(i, price, kind):
    return Pivot(index=i, date=f"2026-01-{i + 1:02d}", price=price, kind=kind)


class LabelTest(unittest.TestCase):
    def test_rising_sequence_is_hh_and_hl(self):
        pivots = [_pivot(0, 90, LOW), _pivot(5, 100, HIGH), _pivot(10, 95, LOW),
                  _pivot(15, 110, HIGH), _pivot(20, 104, LOW)]
        labels = [s.label for s in label_swings(pivots)]
        self.assertEqual(labels, [HL, HH, HL])

    def test_falling_sequence_is_lh_and_ll(self):
        pivots = [_pivot(0, 110, HIGH), _pivot(5, 100, LOW), _pivot(10, 105, HIGH),
                  _pivot(15, 92, LOW), _pivot(20, 99, HIGH)]
        labels = [s.label for s in label_swings(pivots)]
        self.assertEqual(labels, [LH, LL, LH])

    def test_the_first_pivot_on_each_side_has_nothing_to_compare_against(self):
        pivots = [_pivot(0, 100, HIGH), _pivot(5, 90, LOW)]
        self.assertEqual(label_swings(pivots), [])

    def test_label_records_what_it_was_measured_against(self):
        pivots = [_pivot(0, 100, HIGH), _pivot(5, 90, LOW), _pivot(10, 112, HIGH)]
        swing = label_swings(pivots)[0]
        self.assertEqual(swing.label, HH)
        self.assertEqual(swing.versus, 100.0)


class TrendTest(unittest.TestCase):
    def test_staircase_up_reads_as_an_uptrend(self):
        ms = build_market_structure(_walk([60, 80, 72, 96, 88, 112]))
        self.assertEqual(ms.trend, UPTREND)
        self.assertIn("tăng", ms.label)

    def test_staircase_down_reads_as_a_downtrend(self):
        ms = build_market_structure(_walk([112, 88, 96, 72, 80, 60]))
        self.assertEqual(ms.trend, DOWNTREND)

    def test_a_flat_range_is_not_a_trend(self):
        ms = build_market_structure(_walk([100, 108, 100, 108, 100, 108]))
        self.assertEqual(ms.trend, RANGE)

    def test_empty_input(self):
        ms = build_market_structure([])
        self.assertEqual(ms.trend, RANGE)
        self.assertEqual(ms.swings, [])


class EventTest(unittest.TestCase):
    def test_continuing_up_produces_bos_not_choch(self):
        ms = build_market_structure(_walk([60, 80, 72, 96, 88, 112]))
        ups = [e for e in ms.events if e.direction == "up"]
        self.assertTrue(ups)
        self.assertTrue(all(e.kind == BOS for e in ups[1:]),
                        [f"{e.kind}/{e.direction}" for e in ms.events])

    def test_first_break_against_an_uptrend_is_a_choch(self):
        # Up, up, then price loses the most recent higher low.
        ms = build_market_structure(_walk([60, 80, 72, 96, 88, 100, 70]))
        downs = [e for e in ms.events if e.direction == "down"]
        self.assertTrue(downs)
        self.assertEqual(downs[0].kind, CHOCH)

    def test_a_level_fires_once_and_is_then_consumed(self):
        ms = build_market_structure(_walk([60, 80, 72, 96, 88, 112]))
        levels = [(e.direction, e.level) for e in ms.events]
        self.assertEqual(len(levels), len(set(levels)),
                         f"a swing level fired twice: {levels}")

    def test_events_carry_a_sentence(self):
        ms = build_market_structure(_walk([60, 80, 72, 96, 88, 112]))
        for event in ms.events:
            self.assertTrue(event.label)
            self.assertIn(event.date, event.label)

    def test_pivots_are_not_read_before_they_could_be_known(self):
        # With a lag of 3 no event may reference a pivot fewer than 3 bars old.
        recs = _walk([60, 80, 72, 96, 88, 112])
        ms = build_market_structure(recs, confirm_lag=3)
        for event in ms.events:
            matching = [s for s in ms.swings if abs(s.price - event.level) < 1e-6]
            for swing in matching:
                self.assertGreaterEqual(event.index - swing.index, 3)


class SerialiseTest(unittest.TestCase):
    def test_to_dict(self):
        ms = build_market_structure(_walk([60, 80, 72, 96, 88, 112]))
        data = ms.to_dict()
        self.assertEqual(data["trend"], UPTREND)
        self.assertEqual(len(data["swings"]), len(ms.swings))
        self.assertIn("trend_name", data)
        self.assertTrue(data["label"])


if __name__ == "__main__":
    unittest.main()
