import unittest
from datetime import datetime, timedelta
from typing import List, Optional, Sequence

from src.data.stock_data_loader import StockRecord
from src.ta.formations import (
    CONFIRMED, DOUBLE_BOTTOM, DOUBLE_TOP, FAILED, FORMING, HEAD_SHOULDERS,
    INVERSE_HEAD_SHOULDERS, TRIPLE_TOP, find_formations,
)


def _bar(i: int, price: float, volume: float = 1_000_000.0,
         pad: float = 0.4) -> StockRecord:
    return StockRecord(
        date=datetime(2026, 1, 1) + timedelta(days=i),
        symbol="TST",
        priceHigh=price + pad, priceLow=price - pad, priceOpen=price,
        priceAverage=price, priceClose=price, priceBasic=price,
        totalVolume=volume, dealVolume=volume, putthroughVolume=0.0,
        totalValue=0.0, putthroughValue=0.0,
        buyForeignQuantity=0.0, buyForeignValue=0.0,
        sellForeignQuantity=0.0, sellForeignValue=0.0,
        buyCount=0.0, buyQuantity=0.0, sellCount=0.0, sellQuantity=0.0,
        adjRatio=1.0, currentForeignRoom=0.0,
        propTradingNetDealValue=None, propTradingNetPTValue=None,
        propTradingNetValue=None, unit=1.0,
    )


def _walk(legs: Sequence[float], bars_per_leg: int = 7,
          volumes: Optional[Sequence[float]] = None) -> List[StockRecord]:
    """Price travelling in straight lines between the given turning points.

    ``volumes`` gives one volume per leg, so a test can make the second top
    trade lighter than the first the way the classic rule describes.
    """
    records: List[StockRecord] = []
    i = 0
    for leg, (a, b) in enumerate(zip(legs, legs[1:])):
        vol = volumes[leg] if volumes else 1_000_000.0
        for step in range(bars_per_leg):
            records.append(_bar(i, a + (b - a) * step / bars_per_leg, vol))
            i += 1
    records.append(_bar(i, legs[-1], volumes[-1] if volumes else 1_000_000.0))
    return records


def _kinds(records):
    return [f.kind for f in find_formations(records)]


def _first(records, kind):
    return next(f for f in find_formations(records) if f.kind == kind)


class DoubleTopTest(unittest.TestCase):
    #: Rise, top, pull back, top again at the same height, then break down.
    LEGS = [70.0, 100.0, 88.0, 99.5, 80.0]

    def test_detected_and_confirmed(self):
        f = _first(_walk(self.LEGS), DOUBLE_TOP)
        self.assertEqual(f.state, CONFIRMED)
        self.assertEqual(len(f.pivots), 3)

    def test_target_is_the_height_projected_down(self):
        f = _first(_walk(self.LEGS), DOUBLE_TOP)
        # Neckline sits at the middle trough, height is top minus neckline.
        self.assertAlmostEqual(f.height, f.peak - f.neckline_now, delta=0.6)
        self.assertLess(f.target, f.neckline_now)
        self.assertAlmostEqual(f.target, f.neckline_now - f.height, delta=0.6)

    def test_still_forming_before_the_neckline_gives_way(self):
        f = _first(_walk([70.0, 100.0, 88.0, 99.5, 92.0]), DOUBLE_TOP)
        self.assertEqual(f.state, FORMING)
        self.assertIsNone(f.target)

    def test_uneven_tops_are_not_a_double_top(self):
        # Second top 12 points under the first — that is a lower high, not a pair.
        self.assertNotIn(DOUBLE_TOP, _kinds(_walk([70.0, 100.0, 88.0, 88.5, 80.0])))

    def test_needs_a_prior_advance_to_reverse(self):
        # Same two tops, but price arrived sideways — nothing to turn over.
        self.assertNotIn(DOUBLE_TOP, _kinds(_walk([99.0, 100.0, 88.0, 99.5, 80.0])))

    def test_shallow_trough_between_the_tops_is_a_pause_not_a_pattern(self):
        self.assertNotIn(DOUBLE_TOP, _kinds(_walk([70.0, 100.0, 99.0, 99.5, 80.0])))

    def test_price_back_above_the_tops_kills_it(self):
        # The second top has to turn before it counts as a top at all, so price
        # dips to 93 — never reaching the neckline — and then runs clear.
        f = _first(_walk([70.0, 100.0, 88.0, 99.5, 93.0, 108.0]), DOUBLE_TOP)
        self.assertEqual(f.state, FAILED)
        self.assertIsNone(f.break_date)
        self.assertIn("bị xoá", f.label)

    def test_break_then_recovery_is_a_false_break(self):
        f = _first(_walk([70.0, 100.0, 88.0, 99.5, 84.0, 95.0]), DOUBLE_TOP)
        self.assertEqual(f.state, FAILED)
        self.assertIsNotNone(f.break_date)
        self.assertIn("phá vỡ giả", f.label)

    def test_lighter_second_top_shows_up_in_the_volume_ratio(self):
        heavy_then_light = _walk(self.LEGS, volumes=[2e6, 2e6, 1e6, 1e6, 1e6])
        f = _first(heavy_then_light, DOUBLE_TOP)
        self.assertIsNotNone(f.shoulder_volume_ratio)
        self.assertLess(f.shoulder_volume_ratio, 1.0)


class DoubleBottomTest(unittest.TestCase):
    def test_detected(self):
        f = _first(_walk([130.0, 100.0, 112.0, 100.5, 120.0]), DOUBLE_BOTTOM)
        self.assertEqual(f.state, CONFIRMED)
        self.assertGreater(f.target, f.neckline_now)


class HeadShouldersTest(unittest.TestCase):
    #: Left shoulder 100, head 112, right shoulder 100 — necklline near 92.
    LEGS = [70.0, 100.0, 92.0, 112.0, 92.5, 100.0, 84.0]

    def test_detected_and_confirmed(self):
        f = _first(_walk(self.LEGS), HEAD_SHOULDERS)
        self.assertEqual(f.state, CONFIRMED)
        self.assertEqual(len(f.pivots), 5)

    def test_head_defines_the_height_but_the_shoulder_defines_the_stop(self):
        f = _first(_walk(self.LEGS), HEAD_SHOULDERS)
        self.assertAlmostEqual(f.peak, 112.0, delta=0.6)
        # Invalidation is the right shoulder, well below the head.
        self.assertLess(f.invalidation, f.peak)
        self.assertAlmostEqual(f.invalidation, 100.0, delta=1.0)

    def test_sloping_neckline_is_measured(self):
        f = _first(_walk(self.LEGS), HEAD_SHOULDERS)
        self.assertGreater(f.neckline_slope, 0.0)

    def test_a_flat_head_is_a_triple_top_instead(self):
        kinds = _kinds(_walk([70.0, 100.0, 92.0, 100.3, 92.5, 100.0, 84.0]))
        self.assertIn(TRIPLE_TOP, kinds)
        self.assertNotIn(HEAD_SHOULDERS, kinds)

    def test_uneven_shoulders_are_rejected(self):
        # Right shoulder 12 points under the left — not a shoulder pair.
        self.assertNotIn(HEAD_SHOULDERS,
                         _kinds(_walk([70.0, 100.0, 92.0, 112.0, 92.5, 88.0, 84.0])))

    def test_a_trough_above_the_shoulders_is_rejected(self):
        self.assertNotIn(HEAD_SHOULDERS,
                         _kinds(_walk([70.0, 100.0, 99.0, 112.0, 99.2, 100.0, 84.0])))

    def test_inverse(self):
        f = _first(_walk([130.0, 100.0, 108.0, 88.0, 107.5, 100.0, 116.0]),
                   INVERSE_HEAD_SHOULDERS)
        self.assertEqual(f.state, CONFIRMED)
        self.assertGreater(f.target, f.neckline_now)


class OverlapTest(unittest.TestCase):
    def test_a_head_and_shoulders_does_not_also_report_its_inner_double_top(self):
        found = find_formations(_walk(HeadShouldersTest.LEGS))
        self.assertEqual(found[0].kind, HEAD_SHOULDERS)
        spans = [(f.start_index, f.end_index) for f in found]
        for i, a in enumerate(spans):
            for b in spans[i + 1:]:
                self.assertFalse(a[0] <= b[1] and b[0] <= a[1],
                                 f"overlapping formations reported: {spans}")

    def test_confirmed_outranks_forming(self):
        found = find_formations(_walk(HeadShouldersTest.LEGS))
        self.assertTrue(found)
        self.assertEqual(found[0].state, CONFIRMED)


class EdgeTest(unittest.TestCase):
    def test_short_series_is_empty(self):
        self.assertEqual(find_formations([_bar(i, 100.0) for i in range(8)]), [])

    def test_flat_series_has_no_formations(self):
        self.assertEqual(find_formations([_bar(i, 100.0) for i in range(120)]), [])

    def test_every_formation_carries_a_sentence_and_serialises(self):
        for f in find_formations(_walk(HeadShouldersTest.LEGS)):
            self.assertIn("**", f.label)
            data = f.to_dict()
            self.assertEqual(len(data["pivots"]), len(f.pivots))
            self.assertEqual(len(data["roles"]), len(f.pivots))


if __name__ == "__main__":
    unittest.main()
