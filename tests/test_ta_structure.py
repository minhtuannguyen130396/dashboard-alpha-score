import os
import tempfile
import unittest
from datetime import datetime, timedelta
from typing import List, Optional, Sequence

from src.data.stock_data_loader import StockRecord
from src.ta.boxes import (
    BREAKDOWN_CONFIRMED, BREAKOUT_UP_CONFIRMED, BREAKOUT_UP_WEAK, FALSE_BREAKOUT_UP,
    INSIDE, find_box,
)
from src.ta.patterns import (
    ASCENDING_TRIANGLE, DESCENDING_TRIANGLE, NONE, RECTANGLE, SYMMETRIC_TRIANGLE, classify,
)
from src.ta.pivots import HIGH, Pivot, find_pivots
from src.ta.render import render_structure_chart
from src.ta.structure import build_structure
from src.ta.trendlines import RESISTANCE, SUPPORT, TrendLine, find_trendlines


def _bar(i: int, high: float, low: float, close: Optional[float] = None,
         volume: float = 1_000_000.0) -> StockRecord:
    close = close if close is not None else (high + low) / 2
    return StockRecord(
        date=datetime(2026, 1, 1) + timedelta(days=i),
        symbol="TST",
        priceHigh=high, priceLow=low, priceOpen=close, priceAverage=close,
        priceClose=close, priceBasic=close,
        totalVolume=volume, dealVolume=volume, putthroughVolume=0.0,
        totalValue=0.0, putthroughValue=0.0,
        buyForeignQuantity=0.0, buyForeignValue=0.0,
        sellForeignQuantity=0.0, sellForeignValue=0.0,
        buyCount=0.0, buyQuantity=0.0, sellCount=0.0, sellQuantity=0.0,
        adjRatio=1.0, currentForeignRoom=0.0,
        propTradingNetDealValue=None, propTradingNetPTValue=None,
        propTradingNetValue=None, unit=1.0,
    )


def _zigzag(legs: Sequence[float], bars_per_leg: int = 6) -> List[StockRecord]:
    """Price walking linearly between the given turning points."""
    records: List[StockRecord] = []
    i = 0
    for a, b in zip(legs, legs[1:]):
        for step in range(bars_per_leg):
            mid = a + (b - a) * step / bars_per_leg
            records.append(_bar(i, mid + 0.2, mid - 0.2, mid))
            i += 1
    records.append(_bar(i, legs[-1] + 0.2, legs[-1] - 0.2, legs[-1]))
    return records


def _flat(bars: int, top: float, bottom: float, start: int = 0,
          volume: float = 1_000_000.0) -> List[StockRecord]:
    """A range that touches both edges without leaving them."""
    out = []
    for k in range(bars):
        if k % 4 == 0:
            hi, lo = top, top - 0.4
        elif k % 4 == 2:
            hi, lo = bottom + 0.4, bottom
        else:
            mid = (top + bottom) / 2
            hi, lo = mid + 0.2, mid - 0.2
        out.append(_bar(start + k, hi, lo, (hi + lo) / 2, volume))
    return out


class PivotTest(unittest.TestCase):
    def test_alternating_highs_and_lows(self):
        records = _zigzag([10, 16, 11, 18, 12, 20])
        pivots = find_pivots(records, fractal=2, min_swing_atr=0.5)
        kinds = [p.kind for p in pivots]
        self.assertGreaterEqual(len(pivots), 3)
        for a, b in zip(kinds, kinds[1:]):
            self.assertNotEqual(a, b, "pivots must alternate high/low")

    def test_shallow_wiggles_are_filtered_out(self):
        deep = find_pivots(_zigzag([10, 16, 11, 18]), fractal=2, min_swing_atr=0.5)
        shallow = find_pivots(_zigzag([10, 10.2, 10.05, 10.25]), fractal=2, min_swing_atr=3.0)
        self.assertGreater(len(deep), len(shallow))

    def test_too_few_bars_returns_nothing(self):
        self.assertEqual(find_pivots(_zigzag([10, 12], bars_per_leg=1), fractal=3), [])


class TrendLineTest(unittest.TestCase):
    def test_descending_resistance_through_two_highs(self):
        # Highs sit 1.5 below the line except at bars 5 and 40, which define it.
        def level(i):
            return 30 - i * 0.1
        records = [_bar(i, level(i) - 1.5, level(i) - 2.5, level(i) - 2.0)
                   for i in range(60)]
        for i in (5, 40):
            records[i] = _bar(i, level(i), level(i) - 1.0, level(i) - 0.8)
        pivots = [Pivot(5, "2026-01-06", records[5].priceHigh, HIGH),
                  Pivot(40, "2026-02-10", records[40].priceHigh, HIGH)]
        lines = find_trendlines(records, pivots, kinds=(RESISTANCE,))
        self.assertEqual(len(lines), 1)
        line = lines[0]
        self.assertEqual(line.kind, RESISTANCE)
        self.assertLess(line.slope, 0)
        self.assertEqual(line.touches, 2)
        self.assertFalse(line.broken)

    def test_line_cut_through_between_anchors_is_rejected(self):
        records = [_bar(i, 20.0, 19.0) for i in range(40)]
        records[20] = _bar(20, 26.0, 19.0)          # a spike straight through the line
        pivots = [Pivot(5, "d1", 20.0, HIGH), Pivot(35, "d2", 20.0, HIGH)]
        self.assertEqual(find_trendlines(records, pivots, kinds=(RESISTANCE,)), [])

    def test_touches_count_episodes_not_consecutive_bars(self):
        # Flat resistance at 20: bars 5-15 all hug it, then bars 30-35 do again.
        records = [_bar(i, 18.0, 17.0) for i in range(45)]
        for i in list(range(5, 16)) + list(range(30, 36)):
            records[i] = _bar(i, 20.0, 19.0)
        pivots = [Pivot(5, "d1", 20.0, HIGH), Pivot(35, "d2", 20.0, HIGH)]
        lines = find_trendlines(records, pivots, kinds=(RESISTANCE,))
        self.assertEqual(len(lines), 1)
        self.assertEqual(lines[0].touches, 2, "two runs against the line = two touches")

    def test_break_is_detected_and_dated(self):
        records = [_bar(i, 18.5, 17.5, 18.0) for i in range(45)]
        for i in (5, 30):
            records[i] = _bar(i, 20.0, 19.0, 19.5)   # the two anchors
        for i in range(38, 45):
            records[i] = _bar(i, 24.0, 22.0, 23.0)   # closes well above the line
        pivots = [Pivot(5, "d1", 20.0, HIGH), Pivot(30, "d2", 20.0, HIGH)]
        lines = find_trendlines(records, pivots, kinds=(RESISTANCE,))
        self.assertTrue(lines[0].broken)
        self.assertEqual(lines[0].break_index, 38)

    def test_line_far_from_price_is_dropped(self):
        records = [_bar(i, 20.0, 19.0, 19.5) for i in range(60)]
        for i in range(40, 60):
            records[i] = _bar(i, 12.0, 11.0, 11.5)   # price collapses far below
        pivots = [Pivot(5, "d1", 20.0, HIGH), Pivot(30, "d2", 20.0, HIGH)]
        self.assertEqual(find_trendlines(records, pivots, kinds=(RESISTANCE,)), [])


class BoxTest(unittest.TestCase):
    def test_range_still_inside_the_box(self):
        box = find_box(_flat(20, 22.0, 20.0), min_bars=8)
        self.assertIsNotNone(box)
        self.assertEqual(box.state, INSIDE)
        self.assertAlmostEqual(box.top, 22.0, places=2)
        self.assertAlmostEqual(box.bottom, 20.0, places=2)
        self.assertIsNotNone(box.position_pct)

    def test_breakout_on_heavy_volume_is_confirmed_with_a_measured_target(self):
        records = _flat(20, 22.0, 20.0)
        records += [_bar(20 + k, 24.0, 23.0, 23.5, volume=4_000_000.0) for k in range(3)]
        box = find_box(records, min_bars=8)
        self.assertEqual(box.state, BREAKOUT_UP_CONFIRMED)
        self.assertGreaterEqual(box.breakout_volume_x, 1.5)
        self.assertAlmostEqual(box.target, 24.0, places=2)     # top + height
        self.assertAlmostEqual(box.invalidation, 20.0, places=2)

    def test_breakout_on_thin_volume_is_flagged_weak(self):
        records = _flat(20, 22.0, 20.0)
        records += [_bar(20 + k, 24.0, 23.0, 23.5, volume=700_000.0) for k in range(3)]
        box = find_box(records, min_bars=8)
        self.assertEqual(box.state, BREAKOUT_UP_WEAK)
        self.assertLess(box.breakout_volume_x, 1.5)

    def test_breakdown_is_detected(self):
        records = _flat(20, 22.0, 20.0)
        records += [_bar(20 + k, 19.0, 18.0, 18.2, volume=4_000_000.0) for k in range(3)]
        box = find_box(records, min_bars=8)
        self.assertEqual(box.state, BREAKDOWN_CONFIRMED)
        self.assertLess(box.target, box.bottom)

    def test_breakout_that_falls_back_inside_is_called_false(self):
        records = _flat(20, 22.0, 20.0)
        records.append(_bar(20, 24.0, 23.0, 23.5, volume=4_000_000.0))
        records += [_bar(21 + k, 21.5, 20.5, 21.0) for k in range(3)]
        box = find_box(records, min_bars=8)
        self.assertEqual(box.state, FALSE_BREAKOUT_UP)

    def test_too_short_a_series_has_no_box(self):
        self.assertIsNone(find_box(_flat(5, 22.0, 20.0), min_bars=8))


class PatternTest(unittest.TestCase):
    """Slopes drive the classification, so feed the classifier explicit lines."""

    @staticmethod
    def _line(kind, start_price, end_price, n):
        slope = (end_price - start_price) / n
        return TrendLine(
            kind=kind,
            p1_index=0, p1_date="a", p1_price=start_price,
            p2_index=n, p2_date="b", p2_price=end_price,
            slope=slope, intercept=start_price,
            touches=3, span=n, score=1.0,
            value_now=end_price, distance_pct=0.0,
            slope_pct_per_bar=slope / start_price * 100,
        )

    def _lines(self, records, res_from, res_to, sup_from, sup_to):
        n = len(records) - 1
        return [self._line(RESISTANCE, res_from, res_to, n),
                self._line(SUPPORT, sup_from, sup_to, n)]

    @staticmethod
    def _atr(records):
        """A calm ATR — these bars are drawn edge-to-edge, not realistically."""
        return [0.4] * len(records)

    def test_flat_resistance_with_rising_support_is_an_ascending_triangle(self):
        records = [_bar(i, 20.0, 10.0 + i * 0.1) for i in range(50)]
        lines = self._lines(records, 20.0, 20.0, 10.0, 14.9)
        self.assertEqual(classify(records, lines, self._atr(records)).kind, ASCENDING_TRIANGLE)

    def test_falling_resistance_with_flat_support_is_a_descending_triangle(self):
        records = [_bar(i, 25.0 - i * 0.1, 10.0) for i in range(50)]
        lines = self._lines(records, 25.0, 20.1, 10.0, 10.0)
        self.assertEqual(classify(records, lines, self._atr(records)).kind, DESCENDING_TRIANGLE)

    def test_converging_from_both_sides_is_a_symmetric_triangle(self):
        records = [_bar(i, 25.0 - i * 0.1, 10.0 + i * 0.1) for i in range(50)]
        lines = self._lines(records, 25.0, 20.1, 10.0, 14.9)
        pattern = classify(records, lines, self._atr(records))
        self.assertEqual(pattern.kind, SYMMETRIC_TRIANGLE)
        self.assertIsNotNone(pattern.apex_bars)

    def test_two_flat_edges_are_a_rectangle(self):
        records = [_bar(i, 20.0, 10.0) for i in range(50)]
        lines = self._lines(records, 20.0, 20.0, 10.0, 10.0)
        self.assertEqual(classify(records, lines, self._atr(records)).kind, RECTANGLE)

    def test_one_sided_lines_cannot_be_classified(self):
        records = [_bar(i, 20.0, 10.0) for i in range(50)]
        pattern = classify(records, [])
        self.assertEqual(pattern.kind, NONE)
        self.assertIn("Chưa đủ", pattern.label)


class StructureAndRenderTest(unittest.TestCase):
    def test_structure_on_real_data_is_coherent(self):
        structure = build_structure("ACB", lookback_days=200)
        self.assertGreater(structure.bars, 50)
        self.assertGreater(structure.close, 0)
        self.assertTrue(structure.brief, "brief must explain something")
        for line in structure.trendlines:
            self.assertIn(line.kind, (RESISTANCE, SUPPORT))
            self.assertGreaterEqual(line.touches, 2)

    def test_empty_symbol_degrades_gracefully(self):
        structure = build_structure("NOSUCHTICKER", lookback_days=100)
        self.assertEqual(structure.bars, 0)
        self.assertTrue(structure.warnings)
        self.assertIsNone(render_structure_chart(structure))

    def test_chart_is_written_to_disk(self):
        structure = build_structure("ACB", lookback_days=200)
        with tempfile.TemporaryDirectory() as tmp:
            path = render_structure_chart(structure, out_dir=tmp)
            self.assertTrue(os.path.isfile(path))
            self.assertGreater(os.path.getsize(path), 10_000)


if __name__ == "__main__":
    unittest.main()
