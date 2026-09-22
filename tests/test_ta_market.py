import unittest
from datetime import datetime, timedelta
from types import SimpleNamespace

from src.ta import market as market_mod
from src.ta.market import Breadth, build_breadth, distribution_days


def _row(symbol="AAA", close=10.0, vs20=1.0, vs50=1.0, side="up"):
    return SimpleNamespace(symbol=symbol, close=close, vs_ema20=vs20,
                           vs_ema50=vs50, trend=SimpleNamespace(side=side))


def _board(rows, as_of="2026-09-10"):
    return SimpleNamespace(as_of=as_of, rows=rows)


def _bar(date, close, volume):
    return SimpleNamespace(date=date, priceClose=close, priceImpactVolume=volume)


class BreadthTest(unittest.TestCase):
    def test_counts_each_axis_separately(self):
        rows = [_row("A", vs20=2.0, vs50=1.0, side="up"),
                _row("B", vs20=-1.0, vs50=1.0, side="up"),
                _row("C", vs20=-2.0, vs50=-3.0, side="down"),
                _row("D", vs20=1.0, vs50=-1.0, side="flat")]
        b = build_breadth(_board(rows), ref_date="2026-09-10")
        self.assertEqual(b.n, 4)
        self.assertEqual(b.above_ema20, 2)
        self.assertEqual(b.above_ema50, 2)
        self.assertEqual(b.trend_up, 2)
        self.assertEqual(b.trend_down, 1)
        self.assertEqual(b.pct_above_ema20, 50.0)

    def test_no_board_is_none_not_a_neutral_reading(self):
        """Chưa có bảng là *chưa đo được*, không phải 'độ rộng trung tính'."""
        self.assertIsNone(build_breadth(None))
        self.assertIsNone(build_breadth(_board([])))

    def test_a_stale_board_says_how_stale_and_why_it_matters(self):
        b = build_breadth(_board([_row()], as_of="2026-08-01"),
                          ref_date="2026-09-10")
        self.assertGreaterEqual(b.stale_days, market_mod.BREADTH_STALE_DAYS)
        self.assertIn("2026-08-01", b.note)
        self.assertIn("build_ranking", b.note)

    def test_a_fresh_board_notes_its_date_without_alarm(self):
        b = build_breadth(_board([_row()], as_of="2026-09-09"),
                          ref_date="2026-09-10")
        self.assertLess(b.stale_days, market_mod.BREADTH_STALE_DAYS)
        self.assertNotIn("Chạy", b.note)

    def test_label_changes_with_the_reading(self):
        wide = Breadth(source_as_of="x", n=10, above_ema20=8)
        thin = Breadth(source_as_of="x", n=10, above_ema20=2)
        self.assertIn("lan rộng", wide.label)
        self.assertIn("suy kiệt", thin.label)

    def test_label_on_an_empty_basket_does_not_divide_by_zero(self):
        self.assertIn("chưa đo được", Breadth(source_as_of="x", n=0).label)


class DistributionTest(unittest.TestCase):
    """Phiên phân phối = chỉ số giảm KÈM volume tăng. Hai vế, không phải một."""

    def setUp(self):
        self.day = datetime(2026, 9, 1)

    def _series(self, spec):
        out, price = [], 100.0
        for i, (change, vol) in enumerate(spec):
            price = price * (1 + change / 100)
            out.append(_bar(self.day + timedelta(days=i), round(price, 2), vol))
        return out

    def test_a_drop_on_rising_volume_counts(self):
        bars = self._series([(0.0, 1000), (-1.0, 1500)])
        self.assertEqual(len(distribution_days(bars)), 1)

    def test_a_drop_on_falling_volume_does_not(self):
        """Giảm mà volume cạn là không ai muốn mua, khác hẳn có người bán ra."""
        bars = self._series([(0.0, 1000), (-1.0, 600)])
        self.assertEqual(distribution_days(bars), [])

    def test_a_rise_on_rising_volume_does_not(self):
        bars = self._series([(0.0, 1000), (+1.2, 2000)])
        self.assertEqual(distribution_days(bars), [])

    def test_rounding_noise_is_below_the_threshold(self):
        bars = self._series([(0.0, 1000), (-0.1, 2000)])
        self.assertEqual(distribution_days(bars), [])

    def test_the_window_cuts_off_older_sessions(self):
        spec = [(0.0, 1000)] + [(-1.0, 1000 + 10 * i) for i in range(1, 31)]
        bars = self._series(spec)
        self.assertLessEqual(len(distribution_days(bars, window=5)), 5)

    def test_empty_input_is_empty_output(self):
        self.assertEqual(distribution_days([]), [])


class RegimeTest(unittest.TestCase):
    def test_real_index_builds_a_regime_with_a_headline(self):
        r = market_mod.build_regime()
        self.assertFalse(r.is_empty, r.notes)
        self.assertEqual(r.symbol, "VNINDEX")
        self.assertIn(r.side, ("up", "down", "flat"))
        self.assertTrue(r.headline)
        self.assertIsNotNone(r.distribution_days)

    def test_a_missing_index_is_reported_not_guessed(self):
        """Không nạp được VNINDEX thì nói ra, đừng trả về một nền 'trung tính'."""
        from unittest import mock
        with mock.patch.object(market_mod, "build_snapshot") as fake:
            fake.return_value = SimpleNamespace(bars=0)
            r = market_mod.build_regime()
        self.assertTrue(r.is_empty)
        self.assertTrue(r.notes)
        self.assertIn("update", r.notes[0])
        self.assertIn("Chưa đọc được", r.headline)


if __name__ == "__main__":
    unittest.main()
