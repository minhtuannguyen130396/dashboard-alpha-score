import unittest
from datetime import datetime, timedelta
from typing import List, Sequence

from src.data.stock_data_loader import StockRecord
from src.ta.levels import (
    AT_PRICE, GAP, RESISTANCE, SUPPORT, SWING, VOLUME, build_profile, find_levels,
)


def _bar(i: int, o: float, h: float, l: float, c: float,
         volume: float = 1_000_000.0) -> StockRecord:
    return StockRecord(
        date=datetime(2026, 1, 1) + timedelta(days=i),
        symbol="TST",
        priceHigh=h, priceLow=l, priceOpen=o, priceAverage=(h + l) / 2,
        priceClose=c, priceBasic=c,
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
          volume: float = 1_000_000.0) -> List[StockRecord]:
    """A continuous series: each bar opens where the last one closed.

    Opening a bar at its own close makes every session gap by the full move,
    which would drown the level list in gap levels that are an artefact of the
    fixture rather than of the price.
    """
    prices = [legs[0]]
    for a, b in zip(legs, legs[1:]):
        prices += [a + (b - a) * step / bars_per_leg
                   for step in range(1, bars_per_leg + 1)]
    out: List[StockRecord] = []
    for i, p in enumerate(prices):
        o = prices[i - 1] if i else p
        out.append(_bar(i, o, max(o, p) + 0.4, min(o, p) - 0.4, p, volume))
    return out


class ProfileTest(unittest.TestCase):
    def test_poc_lands_where_price_spent_its_time(self):
        # Long stretch around 100, one brief excursion to 130.
        recs = [_bar(i, 100, 100.5, 99.5, 100) for i in range(60)]
        recs += [_bar(60 + i, 130, 130.5, 129.5, 130) for i in range(4)]
        profile = build_profile(recs)
        self.assertAlmostEqual(profile.poc, 100, delta=1.5)

    def test_value_area_brackets_the_poc(self):
        profile = build_profile(_walk([90, 110, 95, 108, 98]))
        self.assertLessEqual(profile.value_low, profile.poc)
        self.assertLessEqual(profile.poc, profile.value_high)

    def test_volume_is_spread_across_the_bar_not_dumped_on_the_close(self):
        # One very wide bar; its volume must not all land in a single bin.
        recs = [_bar(i, 100, 100.2, 99.8, 100) for i in range(30)]
        recs.append(_bar(30, 100, 140, 100, 101, 50_000_000))
        profile = build_profile(recs)
        busy = [v for v in profile.volumes if v > 0]
        self.assertGreater(len(busy), 5)

    def test_a_flat_series_has_no_profile(self):
        self.assertIsNone(build_profile([_bar(i, 100, 100, 100, 100)
                                         for i in range(30)]))

    def test_empty(self):
        self.assertIsNone(build_profile([]))


class ClusterTest(unittest.TestCase):
    def test_repeated_rejections_at_one_price_become_a_level(self):
        # Three tops at ~110, price now well below.
        levels, _ = find_levels(_walk([90, 110, 96, 110, 95, 110, 97]))
        near = [l for l in levels if abs(l.price - 110) < 2]
        self.assertTrue(near, [l.price for l in levels])
        self.assertEqual(near[0].kind, RESISTANCE)
        self.assertGreaterEqual(near[0].touches, 2)

    def test_a_level_below_price_is_labelled_support(self):
        # Kept inside max_distance_pct — a floor 20% under price is history,
        # not a level, and find_levels drops it on purpose.
        levels, _ = find_levels(_walk([110, 95, 104, 95, 105, 95, 108]))
        near = [l for l in levels if abs(l.price - 95) < 2]
        self.assertTrue(near)
        self.assertEqual(near[0].kind, SUPPORT)

    def test_a_single_visit_is_not_a_level(self):
        levels, _ = find_levels(_walk([90, 110, 96, 104, 98]), min_touches=3)
        self.assertTrue(all(l.touches >= 3 for l in levels if l.source == SWING))

    def test_a_level_beyond_the_distance_cap_is_dropped(self):
        levels, _ = find_levels(_walk([110, 90, 104, 90, 105, 90, 108]))
        self.assertFalse([l for l in levels if abs(l.price - 90) < 2])

    def test_levels_far_from_price_are_dropped(self):
        levels, _ = find_levels(_walk([90, 110, 96, 110, 95, 110, 97]),
                                max_distance_pct=5.0)
        self.assertTrue(all(abs(l.distance_pct) <= 5.0 for l in levels))

    def test_levels_do_not_stack_on_top_of_each_other(self):
        levels, _ = find_levels(_walk([90, 110, 96, 110, 95, 110, 97]))
        prices = sorted(l.price for l in levels)
        for a, b in zip(prices, prices[1:]):
            self.assertGreater(b - a, 0.0)

    def test_each_kept_level_is_numbered_and_described(self):
        levels, _ = find_levels(_walk([90, 110, 96, 110, 95, 110, 97]))
        self.assertEqual([l.id for l in levels], [f"L{i}" for i in range(1, len(levels) + 1)])
        for level in levels:
            self.assertTrue(level.label.startswith(level.id))
            self.assertIn("chạm", level.label)


class SourceTest(unittest.TestCase):
    def test_the_volume_point_of_control_is_offered_as_a_level(self):
        levels, profile = find_levels(_walk([90, 110, 96, 110, 95, 110, 100]))
        self.assertIsNotNone(profile)
        sources = {l.source for l in levels}
        self.assertTrue({SWING, VOLUME} & sources)

    def test_an_unfilled_gap_becomes_a_level(self):
        recs = _walk([100, 104, 100, 104, 100], bars_per_leg=8)
        # Jump away and never come back through the hole.
        base = len(recs)
        for k in range(6):
            p = 118 + k
            recs.append(_bar(base + k, p, p + 0.4, p - 0.4, p))
        levels, _ = find_levels(recs, max_distance_pct=40.0)
        self.assertIn(GAP, {l.source for l in levels}, [l.label for l in levels])

    def test_a_gap_price_has_traded_back_into_is_not_a_level(self):
        """Filling only needs price back at the far edge, not one bar spanning it.

        Requiring a single bar to cover the whole hole leaves gaps "unfilled"
        after price has nibbled through them from both sides for weeks.
        """
        recs = _walk([100, 104, 100, 104, 100], bars_per_leg=8)
        base = len(recs)
        for k in range(4):                       # jump away, leaving a hole
            p = 118 + k
            recs.append(_bar(base + k, p, p + 0.4, p - 0.4, p))
        # Walk back down continuously — each bar opens where the last closed —
        # so the descent adds no gaps of its own and only the original hole is
        # under test.
        base = len(recs)
        prev = recs[-1].priceClose
        for k in range(24):
            p = prev - 1.5
            recs.append(_bar(base + k, prev, max(prev, p) + 0.4, min(prev, p) - 0.4, p))
            prev = p
        gaps = [l for l in find_levels(recs, max_distance_pct=60.0)[0]
                if l.source == GAP]
        self.assertEqual(gaps, [], [l.label for l in gaps])

    def test_both_sides_are_represented_when_both_exist(self):
        """Scoring leans on proximity, so one side can sweep every slot.

        A list that is all resistance says nothing about where the floor is.
        """
        # Ranked purely by score the top two here are both resistance (7.83
        # and 5.77); the support at 95.60 scores 5.05 and would be cut.
        recs = _walk([104, 96, 104, 95, 104, 96, 104, 100])
        levels, _ = find_levels(recs, limit=2, max_distance_pct=30.0)
        kinds = {l.kind for l in levels}
        self.assertIn(RESISTANCE, kinds, [l.label for l in levels])
        self.assertIn(SUPPORT, kinds, [l.label for l in levels])

    def test_a_price_inside_the_zone_is_neither_support_nor_resistance(self):
        recs = _walk([90, 110, 96, 110, 95, 110])
        levels, _ = find_levels(recs)
        for level in levels:
            if level.low <= recs[-1].priceClose <= level.high:
                self.assertEqual(level.kind, AT_PRICE)


class EdgeTest(unittest.TestCase):
    def test_short_series(self):
        levels, profile = find_levels(_walk([100, 102], bars_per_leg=4))
        self.assertEqual(levels, [])
        self.assertIsNone(profile)

    def test_serialises(self):
        levels, profile = find_levels(_walk([90, 110, 96, 110, 95, 110, 97]))
        for level in levels:
            self.assertIn("price", level.to_dict())
        if profile is not None:
            self.assertIn("poc", profile.to_dict())


if __name__ == "__main__":
    unittest.main()
