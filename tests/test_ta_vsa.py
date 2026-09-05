import unittest
from datetime import datetime, timedelta
from typing import List, Optional, Sequence, Tuple

from src.data.stock_data_loader import StockRecord
from src.ta.vsa import (
    BUYING_CLIMAX, CHURN, DRY_UP, NO_DEMAND, NO_SUPPLY, SELLING_CLIMAX, detect,
    scan, volume_multiples,
)


def _bar(i: int, o: float, h: float, l: float, c: float,
         volume: float = 1_000_000.0, basic: Optional[float] = None) -> StockRecord:
    return StockRecord(
        date=datetime(2026, 1, 1) + timedelta(days=i),
        symbol="TST",
        priceHigh=h, priceLow=l, priceOpen=o, priceAverage=(h + l) / 2,
        priceClose=c, priceBasic=basic if basic is not None else c,
        totalVolume=volume, dealVolume=volume, putthroughVolume=0.0,
        totalValue=0.0, putthroughValue=0.0,
        buyForeignQuantity=0.0, buyForeignValue=0.0,
        sellForeignQuantity=0.0, sellForeignValue=0.0,
        buyCount=0.0, buyQuantity=0.0, sellCount=0.0, sellQuantity=0.0,
        adjRatio=1.0, currentForeignRoom=0.0,
        propTradingNetDealValue=None, propTradingNetPTValue=None,
        propTradingNetValue=None, unit=1.0,
    )


#: 30 ordinary bars — range 6, volume 1m — so ATR lands near 6 and the volume
#: EMA near 1m. The bar under test is appended last.
def _frame(tail: Sequence[Tuple], filler: int = 30) -> List[StockRecord]:
    out = [_bar(i, 100.0, 103.0, 97.0, 100.5) for i in range(filler)]
    for k, spec in enumerate(tail):
        o, h, l, c, vol = spec
        out.append(_bar(filler + k, o, h, l, c, vol))
    return out


def _kinds(records):
    return [s.kind for s in detect(records, -1)]


class ClimaxTest(unittest.TestCase):
    def test_buying_climax_needs_the_close_given_back(self):
        # Wide up bar, 3× volume, closes in the lower third.
        self.assertIn(BUYING_CLIMAX,
                      _kinds(_frame([(100.0, 110.0, 99.0, 102.0, 3e6)])))

    def test_a_wide_up_bar_that_holds_its_close_is_not_a_climax(self):
        self.assertNotIn(BUYING_CLIMAX,
                         _kinds(_frame([(100.0, 110.0, 99.0, 109.5, 3e6)])))

    def test_selling_climax(self):
        self.assertIn(SELLING_CLIMAX,
                      _kinds(_frame([(110.0, 111.0, 100.0, 108.0, 3e6)])))

    def test_a_wide_bar_on_ordinary_volume_is_just_a_wide_bar(self):
        self.assertEqual(_kinds(_frame([(100.0, 110.0, 99.0, 102.0, 1e6)])), [])


class ChurnTest(unittest.TestCase):
    def test_heavy_volume_going_nowhere(self):
        self.assertIn(CHURN, _kinds(_frame([(100.0, 101.5, 99.5, 100.4, 4e6)])))

    def test_heavy_volume_that_did_move_price_is_not_churn(self):
        self.assertNotIn(CHURN, _kinds(_frame([(100.0, 110.0, 99.0, 109.0, 4e6)])))


class ParticipationTest(unittest.TestCase):
    def test_no_demand_is_an_up_bar_nobody_joined(self):
        self.assertIn(NO_DEMAND, _kinds(_frame([(100.0, 101.5, 99.8, 101.2, 4e5)])))

    def test_no_supply_is_a_down_bar_nobody_joined(self):
        self.assertIn(NO_SUPPLY, _kinds(_frame([(101.2, 101.5, 99.8, 100.0, 4e5)])))

    def test_direction_decides_which_of_the_two_fires(self):
        kinds = _kinds(_frame([(100.0, 101.5, 99.8, 101.2, 4e5)]))
        self.assertNotIn(NO_SUPPLY, kinds)


class DryUpTest(unittest.TestCase):
    def test_volume_contracting_to_a_multi_week_low(self):
        # Volume steps down for a month, range narrowing with it.
        tail = [(100.0, 100.0 + 3 - k * 0.08, 100.0 - 3 + k * 0.08, 100.2,
                 1e6 * (1 - k * 0.03)) for k in range(24)]
        self.assertIn(DRY_UP, _kinds(_frame(tail)))

    def test_a_quiet_bar_in_an_otherwise_busy_stretch_is_not_a_dry_up(self):
        self.assertNotIn(DRY_UP, _kinds(_frame([(100.0, 103.0, 97.0, 100.5, 9e5)])))


class LimitTest(unittest.TestCase):
    def test_a_ceiling_session_reports_nothing(self):
        recs = _frame([])
        recs.append(_bar(90, 105.0, 107.0, 104.0, 107.0, 5e6, basic=100.0))
        self.assertEqual(detect(recs, -1), [])


class MechanicsTest(unittest.TestCase):
    def test_volume_multiples_track_the_ema(self):
        recs = _frame([(100.0, 103.0, 97.0, 100.5, 3e6)])
        vols = volume_multiples(recs)
        self.assertGreater(vols[-1], 2.0)
        self.assertAlmostEqual(vols[0], 1.0, places=6)

    def test_scan_window_is_inclusive_and_ordered(self):
        recs = _frame([(100.0, 110.0, 99.0, 102.0, 3e6),
                       (100.0, 101.5, 99.5, 100.4, 4e6)])
        last = len(recs) - 1
        found = scan(recs, last - 1, last)
        self.assertTrue(found)
        self.assertTrue(all(last - 1 <= s.index <= last for s in found))
        self.assertEqual([s.index for s in found], sorted(s.index for s in found))

    def test_out_of_range_and_empty(self):
        self.assertEqual(detect(_frame([]), 999), [])
        self.assertEqual(detect([], 0), [])
        self.assertEqual(scan([]), [])

    def test_every_signal_carries_a_sentence_and_serialises(self):
        for signal in detect(_frame([(100.0, 110.0, 99.0, 102.0, 3e6)]), -1):
            self.assertTrue(signal.label.startswith("**"))
            self.assertIn("volume", signal.label)
            self.assertIn("kind", signal.to_dict())


if __name__ == "__main__":
    unittest.main()
