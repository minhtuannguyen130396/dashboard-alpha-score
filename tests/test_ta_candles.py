import unittest
from datetime import datetime, timedelta
from typing import List, Optional, Sequence, Tuple

from src.data.stock_data_loader import StockRecord
from src.ta.candles import (
    BEARISH_ENGULFING, BULLISH_ENGULFING, CEILING, DARK_CLOUD, DOJI, EVENING_STAR,
    FLOOR, HAMMER, INSIDE_BAR, LIMIT_DOWN, LIMIT_UP, MORNING_STAR, NORMAL, PIERCING,
    GAP_DOWN, GAP_UP, SHOOTING_STAR, SPINNING_TOP, THREE_BLACK_CROWS,
    THREE_WHITE_SOLDIERS, TOUCHED_CEILING, TOUCHED_FLOOR, detect, limit_state,
    scan, shapes,
)


def _bar(i: int, o: float, h: float, l: float, c: float,
         basic: Optional[float] = None, volume: float = 1_000_000.0) -> StockRecord:
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


#: Filler carries the same typical range as the test bars, so ATR lands near 6
#: and ``spread_atr`` stays around 1 — the shape rules are what gets tested,
#: not the width bonus.
def _frame(tail: Sequence[Tuple[float, float, float, float]],
           filler: int = 16) -> List[StockRecord]:
    records = [_bar(i, 100.0, 103.0, 97.0, 100.5) for i in range(filler)]
    for k, (o, h, l, c) in enumerate(tail):
        records.append(_bar(filler + k, o, h, l, c))
    return records


def _kinds(records: List[StockRecord]) -> List[str]:
    return [s.kind for s in detect(records, -1)]


class ShapeTest(unittest.TestCase):
    def test_anatomy(self):
        recs = _frame([(100.0, 106.0, 96.0, 104.0)])
        s = shapes(recs)[-1]
        self.assertAlmostEqual(s.body, 4.0)
        self.assertAlmostEqual(s.bar_range, 10.0)
        self.assertAlmostEqual(s.upper_wick, 2.0)
        self.assertAlmostEqual(s.lower_wick, 4.0)
        self.assertAlmostEqual(s.body_pct, 0.4)
        self.assertAlmostEqual(s.close_pos, 0.8)
        self.assertEqual(s.direction, "up")

    def test_zero_range_bar_has_no_ratios(self):
        recs = _frame([(100.0, 100.0, 100.0, 100.0)])
        s = shapes(recs)[-1]
        self.assertIsNone(s.body_pct)
        self.assertIsNone(s.close_pos)
        self.assertEqual(s.direction, "flat")
        self.assertEqual(detect(recs, -1), [])


class LimitStateTest(unittest.TestCase):
    def test_ceiling_needs_the_close_pinned_to_the_high(self):
        self.assertEqual(limit_state(_bar(0, 105, 107, 104, 107, basic=100)), CEILING)
        # Same size move, but it gave the high back — not a ceiling close.
        self.assertEqual(limit_state(_bar(0, 105, 107, 104, 105, basic=100)),
                         TOUCHED_CEILING)

    def test_floor(self):
        self.assertEqual(limit_state(_bar(0, 95, 96, 93, 93, basic=100)), FLOOR)
        self.assertEqual(limit_state(_bar(0, 95, 96, 93, 95, basic=100)), TOUCHED_FLOOR)

    def test_ordinary_session(self):
        self.assertEqual(limit_state(_bar(0, 100, 103, 97, 100.5, basic=100)), NORMAL)

    def test_missing_reference_price_is_not_a_limit(self):
        self.assertEqual(limit_state(_bar(0, 100, 103, 97, 107, basic=0)), NORMAL)


class SingleBarTest(unittest.TestCase):
    def test_hammer(self):
        recs = _frame([(104.0, 104.5, 98.0, 104.2)])
        self.assertIn(HAMMER, _kinds(recs))

    def test_shooting_star(self):
        recs = _frame([(100.8, 107.0, 100.5, 101.0)])
        self.assertIn(SHOOTING_STAR, _kinds(recs))

    def test_doji_without_a_long_wick_is_only_a_doji(self):
        recs = _frame([(100.0, 103.0, 97.0, 100.1)])
        kinds = _kinds(recs)
        self.assertIn(DOJI, kinds)
        self.assertNotIn(HAMMER, kinds)
        self.assertNotIn(SHOOTING_STAR, kinds)

    def test_spinning_top(self):
        recs = _frame([(100.0, 103.0, 97.0, 101.0)])
        self.assertIn(SPINNING_TOP, _kinds(recs))

    def test_narrow_bar_is_not_a_doji(self):
        # Same silhouette, but the bar barely moved — a dead session, not a standoff.
        recs = _frame([(100.0, 100.6, 99.4, 100.02)])
        self.assertNotIn(DOJI, _kinds(recs))


class TwoBarTest(unittest.TestCase):
    def test_bearish_engulfing(self):
        recs = _frame([(100.0, 104.5, 99.5, 104.0), (105.0, 105.5, 98.5, 99.0)])
        self.assertIn(BEARISH_ENGULFING, _kinds(recs))

    def test_bullish_engulfing(self):
        recs = _frame([(104.0, 104.5, 99.5, 100.0), (99.0, 105.5, 98.5, 105.0)])
        self.assertIn(BULLISH_ENGULFING, _kinds(recs))

    def test_engulfing_a_doji_does_not_count(self):
        # Nothing was engulfed — the previous session had no body to take back.
        recs = _frame([(100.0, 103.0, 97.0, 100.1), (101.0, 101.5, 95.5, 96.0)])
        self.assertNotIn(BEARISH_ENGULFING, _kinds(recs))

    def test_dark_cloud(self):
        recs = _frame([(100.0, 104.5, 99.5, 104.0), (105.0, 105.5, 100.5, 101.0)])
        self.assertIn(DARK_CLOUD, _kinds(recs))

    def test_piercing(self):
        recs = _frame([(104.0, 104.5, 99.5, 100.0), (99.0, 103.5, 98.5, 103.0)])
        self.assertIn(PIERCING, _kinds(recs))

    def test_dark_cloud_that_goes_all_the_way_is_engulfing_instead(self):
        recs = _frame([(100.0, 104.5, 99.5, 104.0), (105.0, 105.5, 98.5, 99.0)])
        kinds = _kinds(recs)
        self.assertIn(BEARISH_ENGULFING, kinds)
        self.assertNotIn(DARK_CLOUD, kinds)

    def test_inside_bar(self):
        recs = _frame([(100.0, 106.0, 96.0, 101.0), (101.0, 104.0, 99.0, 102.0)])
        self.assertIn(INSIDE_BAR, _kinds(recs))

    def test_tighter_inside_bar_scores_higher(self):
        wide = _frame([(100.0, 106.0, 96.0, 101.0), (101.0, 105.5, 96.5, 102.0)])
        tight = _frame([(100.0, 106.0, 96.0, 101.0), (101.0, 102.0, 100.0, 101.5)])

        def _score(recs):
            return next(s.strength for s in detect(recs, -1) if s.kind == INSIDE_BAR)

        self.assertGreater(_score(tight), _score(wide))


class ThreeBarTest(unittest.TestCase):
    def test_evening_star(self):
        recs = _frame([(100.0, 106.5, 99.5, 106.0),
                       (107.0, 108.0, 106.5, 107.5),
                       (106.0, 106.5, 100.5, 101.0)])
        self.assertIn(EVENING_STAR, _kinds(recs))

    def test_morning_star(self):
        recs = _frame([(106.0, 106.5, 99.5, 100.0),
                       (99.0, 99.5, 98.0, 98.5),
                       (100.0, 105.5, 99.5, 105.0)])
        self.assertIn(MORNING_STAR, _kinds(recs))

    def test_star_needs_an_indecisive_middle_bar(self):
        # Middle bar has a full body of its own, so this is just a swing, not a star.
        recs = _frame([(100.0, 106.5, 99.5, 106.0),
                       (106.5, 111.0, 106.0, 110.5),
                       (106.0, 106.5, 100.5, 101.0)])
        self.assertNotIn(EVENING_STAR, _kinds(recs))

    def test_three_black_crows(self):
        recs = _frame([(110.0, 110.5, 105.5, 106.0),
                       (108.0, 108.5, 102.5, 103.0),
                       (105.0, 105.5, 99.5, 100.0)])
        self.assertIn(THREE_BLACK_CROWS, _kinds(recs))

    def test_three_white_soldiers(self):
        recs = _frame([(100.0, 104.5, 99.5, 104.0),
                       (102.0, 107.5, 101.5, 107.0),
                       (105.0, 110.5, 104.5, 110.0)])
        self.assertIn(THREE_WHITE_SOLDIERS, _kinds(recs))

    def test_crows_must_open_inside_the_previous_body(self):
        # Each session gaps clear of the last — a slide, not the orderly
        # distribution the pattern is meant to describe.
        recs = _frame([(110.0, 110.5, 105.5, 106.0),
                       (104.0, 104.5, 98.5, 99.0),
                       (97.0, 97.5, 91.5, 92.0)])
        self.assertNotIn(THREE_BLACK_CROWS, _kinds(recs))


class LimitSessionTest(unittest.TestCase):
    def test_ceiling_close_reports_only_itself(self):
        recs = _frame([(100.0, 103.0, 97.0, 100.5)])
        recs.append(_bar(99, 105.0, 107.0, 104.0, 107.0, basic=100.0))
        signals = detect(recs, -1)
        self.assertEqual([s.kind for s in signals], [LIMIT_UP])

    def test_floor_close_reports_only_itself(self):
        recs = _frame([(100.0, 103.0, 97.0, 100.5)])
        recs.append(_bar(99, 95.0, 96.0, 93.0, 93.0, basic=100.0))
        self.assertEqual([s.kind for s in detect(recs, -1)], [LIMIT_DOWN])

    def test_a_ceiling_bar_poisons_the_pattern_that_spans_it(self):
        # The engulfing shape is there, but the bar it engulfs was never traded
        # out — it was locked at the ceiling.
        recs = _frame([])
        recs.append(_bar(90, 105.0, 107.0, 104.0, 107.0, basic=100.0))
        recs.append(_bar(91, 108.0, 108.5, 103.5, 104.0, basic=107.0))
        self.assertNotIn(BEARISH_ENGULFING, _kinds(recs))

    def test_touching_the_ceiling_still_reads_as_a_shape(self):
        recs = _frame([])
        recs.append(_bar(90, 100.8, 107.0, 100.5, 101.0, basic=100.0))
        signals = detect(recs, -1)
        self.assertIn(SHOOTING_STAR, [s.kind for s in signals])
        self.assertIn("chạm trần", next(s.label for s in signals
                                        if s.kind == SHOOTING_STAR))


class GapTest(unittest.TestCase):
    def test_an_unfilled_gap_up_is_reported(self):
        # Yesterday closed 100.5; today opens 105 and never trades back down.
        recs = _frame([(104.0, 107.0, 103.5, 106.5)])
        self.assertIn(GAP_UP, _kinds(recs))

    def test_a_gap_the_session_closes_is_not_a_gap(self):
        # Opens away but trades back through yesterday's close within the day.
        recs = _frame([(104.0, 107.0, 99.0, 106.5)])
        self.assertNotIn(GAP_UP, _kinds(recs))

    def test_gap_down(self):
        recs = _frame([(97.0, 97.5, 93.0, 93.5)])
        self.assertIn(GAP_DOWN, _kinds(recs))

    def test_a_small_open_drift_is_not_a_gap(self):
        recs = _frame([(101.0, 103.5, 100.8, 103.0)])
        self.assertNotIn(GAP_UP, _kinds(recs))

    def test_shape_records_the_gap_size_and_whether_it_filled(self):
        recs = _frame([(104.0, 107.0, 99.0, 106.5)])
        s = shapes(recs)[-1]
        self.assertGreater(s.gap_atr, 0)
        self.assertTrue(s.gap_filled)

    def test_the_first_bar_has_no_previous_close_to_gap_from(self):
        self.assertIsNone(shapes(_frame([]))[0].gap_atr)


class ScanTest(unittest.TestCase):
    def test_scan_window_is_inclusive_and_ordered(self):
        recs = _frame([(100.0, 104.5, 99.5, 104.0), (105.0, 105.5, 98.5, 99.0)])
        last = len(recs) - 1
        found = scan(recs, last - 1, last)
        self.assertTrue(found)
        self.assertTrue(all(last - 1 <= s.index <= last for s in found))
        self.assertEqual([s.index for s in found], sorted(s.index for s in found))

    def test_scan_respects_min_strength(self):
        recs = _frame([(100.0, 104.5, 99.5, 104.0), (105.0, 105.5, 98.5, 99.0)])
        self.assertEqual(scan(recs, min_strength=1.01), [])

    def test_scan_outside_the_series_is_empty(self):
        recs = _frame([(100.0, 104.5, 99.5, 104.0)])
        self.assertEqual(detect(recs, 999), [])
        self.assertEqual(detect([], 0), [])

    def test_detect_returns_strongest_first(self):
        recs = _frame([(104.0, 104.5, 98.0, 104.2)])
        strengths = [s.strength for s in detect(recs, -1)]
        self.assertEqual(strengths, sorted(strengths, reverse=True))


class LabelTest(unittest.TestCase):
    def test_every_signal_carries_a_sentence(self):
        recs = _frame([(100.0, 104.5, 99.5, 104.0), (105.0, 105.5, 98.5, 99.0)])
        for signal in detect(recs, -1):
            self.assertTrue(signal.label.startswith("**"))
            self.assertTrue(signal.label.endswith("."))
            self.assertIn("—", signal.label)


if __name__ == "__main__":
    unittest.main()
