import unittest
from datetime import datetime, timedelta
from typing import List, Optional, Sequence

from src.data.stock_data_loader import StockRecord
from src.ta.confluence import (
    CONFLICT, FULL, PARTIAL, Z1_EXTREME, Z2_BREAK, Z4_COUNTER, assess, assess_all,
    zones_for,
)
from src.ta.formations import DOUBLE_TOP, HEAD_SHOULDERS, find_formations


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
          volumes: Optional[Sequence[float]] = None) -> List[StockRecord]:
    records: List[StockRecord] = []
    i = 0
    for leg, (a, b) in enumerate(zip(legs, legs[1:])):
        vol = volumes[leg] if volumes else 1_000_000.0
        for step in range(bars_per_leg):
            p = a + (b - a) * step / bars_per_leg
            records.append(_bar(i, p, p + 0.4, p - 0.4, p, vol))
            i += 1
    records.append(_bar(i, legs[-1], legs[-1] + 0.4, legs[-1] - 0.4, legs[-1],
                        volumes[-1] if volumes else 1_000_000.0))
    return records


#: Rise, top, pull back, second top, break down through the neckline.
DOUBLE_TOP_LEGS = [70.0, 100.0, 88.0, 99.5, 80.0]
#: Left shoulder 100, head 112, right shoulder 100, break down.
HS_LEGS = [70.0, 100.0, 92.0, 112.0, 92.5, 100.0, 84.0]


def _only(records, kind=DOUBLE_TOP):
    f = next(f for f in find_formations(records) if f.kind == kind)
    return assess(records, f)


class ZoneTest(unittest.TestCase):
    def test_zones_cover_the_shoulder_the_break_and_the_aftermath(self):
        recs = _walk(DOUBLE_TOP_LEGS)
        f = next(f for f in find_formations(recs) if f.kind == DOUBLE_TOP)
        names = [z[0] for z in zones_for(f, len(recs))]
        self.assertIn(Z1_EXTREME, names)
        self.assertIn(Z2_BREAK, names)
        self.assertIn(Z4_COUNTER, names)

    def test_zones_stay_inside_the_series(self):
        recs = _walk(DOUBLE_TOP_LEGS)
        f = next(f for f in find_formations(recs) if f.kind == DOUBLE_TOP)
        for _, start, end in zones_for(f, len(recs)):
            self.assertLessEqual(0, start)
            self.assertLessEqual(start, end)
            self.assertLess(end, len(recs))

    def test_an_unbroken_formation_has_no_break_or_retest_zone(self):
        recs = _walk([70.0, 100.0, 88.0, 99.5, 92.0])
        f = next(f for f in find_formations(recs) if f.kind == DOUBLE_TOP)
        names = [z[0] for z in zones_for(f, len(recs))]
        self.assertNotIn(Z2_BREAK, names)


class TierTest(unittest.TestCase):
    def test_a_clean_walk_without_reversal_candles_is_only_partial(self):
        # Price glides in straight lines — the shape is there, the bars are not.
        ev = _only(_walk(DOUBLE_TOP_LEGS))
        self.assertEqual(ev.tier, PARTIAL)
        self.assertTrue(ev.missing)

    def test_missing_list_names_the_volume_gap(self):
        ev = _only(_walk(DOUBLE_TOP_LEGS))
        self.assertIn("volume chưa xác nhận", ev.missing)

    def test_forming_formation_says_it_has_not_broken_the_neckline(self):
        ev = _only(_walk([70.0, 100.0, 88.0, 99.5, 92.0]))
        self.assertTrue(any("neckline" in m for m in ev.missing))
        self.assertIn("Chưa xác nhận", ev.conclusion)

    def test_full_confluence_when_shape_candle_and_volume_all_agree(self):
        recs = _walk(DOUBLE_TOP_LEGS, volumes=[2e6, 2e6, 1e6, 1e6, 1e6])
        # A bearish engulfing on the second top, then a heavy break bar.
        f = next(f for f in find_formations(recs) if f.kind == DOUBLE_TOP)
        top = f.end_index
        recs[top] = _bar(top, 99.0, 99.4, 98.6, 99.3, 1e6)
        recs[top + 1] = _bar(top + 1, 99.6, 99.8, 95.0, 95.2, 1e6)
        brk = f.break_index
        recs[brk] = _bar(brk, 88.0, 88.2, 83.0, 83.2, 5e6)
        ev = _only(recs)
        self.assertEqual(ev.tier, FULL)
        self.assertEqual(ev.missing, [])
        self.assertIn("xác nhận trên cả ba yếu tố", ev.conclusion)
        self.assertIsNotNone(ev.strongest)

    def test_failed_formation_is_a_conflict_and_drops_the_level(self):
        recs = _walk([70.0, 100.0, 88.0, 99.5, 93.0, 108.0])
        ev = _only(recs)
        self.assertEqual(ev.tier, CONFLICT)
        self.assertIn("đã hỏng", ev.conclusion)

    def test_a_recent_counter_candle_downgrades_a_live_formation(self):
        recs = _walk(DOUBLE_TOP_LEGS, volumes=[2e6, 2e6, 1e6, 1e6, 1e6])
        # A strong bullish engulfing on the last two bars, pushing back.
        last = len(recs) - 1
        recs[last - 1] = _bar(last - 1, 82.0, 82.3, 78.0, 78.2, 1e6)
        recs[last] = _bar(last, 77.8, 84.5, 77.5, 84.0, 3e6)
        ev = _only(recs)
        self.assertEqual(ev.tier, CONFLICT)
        self.assertIn("đi ngược mô hình", ev.conclusion)


class NoteTest(unittest.TestCase):
    def test_volume_note_reads_the_break_bar_when_confirmed(self):
        recs = _walk(DOUBLE_TOP_LEGS)
        f = next(f for f in find_formations(recs) if f.kind == DOUBLE_TOP)
        recs[f.break_index] = _bar(f.break_index, 88.0, 88.2, 83.0, 83.2, 9e6)
        ev = _only(recs)
        self.assertIn("phá neckline", ev.volume_note)

    def test_volume_note_reads_the_two_tops_when_still_forming(self):
        ev = _only(_walk([70.0, 100.0, 88.0, 99.5, 92.0],
                         volumes=[2e6, 2e6, 1e6, 1e6, 1e6]))
        self.assertIn("×", ev.volume_note)
        self.assertNotIn("phá neckline", ev.volume_note)

    def test_candle_note_says_so_when_nothing_fired(self):
        ev = _only(_walk(DOUBLE_TOP_LEGS))
        self.assertIn("không có nến", ev.candle_note)

    def test_conclusion_never_gives_an_instruction(self):
        for legs in (DOUBLE_TOP_LEGS, [70.0, 100.0, 88.0, 99.5, 92.0], HS_LEGS):
            kind = HEAD_SHOULDERS if legs is HS_LEGS else DOUBLE_TOP
            ev = _only(_walk(legs), kind)
            for banned in ("nên mua", "nên bán", "khuyến nghị", "mua vào", "bán ra"):
                self.assertNotIn(banned, ev.conclusion.lower())


class HeadShouldersConfluenceTest(unittest.TestCase):
    def test_zones_anchor_on_the_right_shoulder(self):
        recs = _walk(HS_LEGS)
        f = next(f for f in find_formations(recs) if f.kind == HEAD_SHOULDERS)
        z1 = next(z for z in zones_for(f, len(recs)) if z[0] == Z1_EXTREME)
        self.assertLessEqual(z1[1], f.pivots[-1].index)
        self.assertGreaterEqual(z1[2], f.pivots[-1].index)


class AssessAllTest(unittest.TestCase):
    def test_shares_one_pass_and_keeps_order(self):
        recs = _walk(HS_LEGS)
        found = find_formations(recs)
        out = assess_all(recs, found)
        self.assertEqual(len(out), len(found))
        self.assertEqual([e.formation.kind for e in out], [f.kind for f in found])

    def test_empty_input(self):
        self.assertEqual(assess_all(_walk(HS_LEGS), []), [])

    def test_serialises(self):
        recs = _walk(HS_LEGS)
        for ev in assess_all(recs, find_formations(recs)):
            data = ev.to_dict()
            self.assertIn("conclusion", data)
            self.assertIn("formation", data)
            self.assertIsInstance(data["missing"], list)


if __name__ == "__main__":
    unittest.main()
