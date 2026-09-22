import unittest
from datetime import datetime, timedelta

from src.data.stock_data_loader import StockRecord
from src.ta import weekly as weekly_mod
from src.ta.weekly import agreement, to_weekly


def _rec(date: datetime, o=10.0, h=11.0, lo=9.0, c=10.5, vol=1000.0) -> StockRecord:
    return StockRecord(
        date=date, symbol="TEST", priceHigh=h, priceLow=lo, priceOpen=o,
        priceAverage=(h + lo) / 2, priceClose=c, priceBasic=o, totalVolume=vol,
        dealVolume=vol, putthroughVolume=0.0, totalValue=vol * c,
        putthroughValue=0.0, buyForeignQuantity=0.0, buyForeignValue=0.0,
        sellForeignQuantity=0.0, sellForeignValue=0.0, buyCount=0.0,
        buyQuantity=0.0, sellCount=0.0, sellQuantity=0.0, adjRatio=1.0,
        currentForeignRoom=0.0, propTradingNetDealValue=None,
        propTradingNetPTValue=None, propTradingNetValue=None, unit=1.0,
    )


class ResampleTest(unittest.TestCase):
    """Gộp tuần phải bám ranh giới tuần ISO, không phải đếm 5 phiên một cục."""

    def test_one_full_week_becomes_one_bar_with_extremes(self):
        # Thứ Hai 2025-01-06 → thứ Sáu 2025-01-10.
        monday = datetime(2025, 1, 6)
        days = [
            _rec(monday, o=10.0, h=11.0, lo=9.5, c=10.2, vol=100),
            _rec(monday + timedelta(days=1), o=10.2, h=12.5, lo=10.0, c=12.0, vol=200),
            _rec(monday + timedelta(days=2), o=12.0, h=12.2, lo=8.8, c=9.0, vol=300),
            _rec(monday + timedelta(days=3), o=9.0, h=9.9, lo=8.9, c=9.7, vol=400),
            _rec(monday + timedelta(days=4), o=9.7, h=10.4, lo=9.6, c=10.3, vol=500),
        ]
        bars = to_weekly(days)
        self.assertEqual(len(bars), 1)
        bar = bars[0]
        self.assertEqual(bar.priceOpen, 10.0)        # mở cửa phiên đầu tuần
        self.assertEqual(bar.priceClose, 10.3)       # đóng cửa phiên cuối tuần
        self.assertEqual(bar.priceHigh, 12.5)        # đỉnh cao nhất trong tuần
        self.assertEqual(bar.priceLow, 8.8)          # đáy thấp nhất trong tuần
        self.assertEqual(bar.dealVolume, 1500)       # volume cộng dồn
        self.assertEqual(bar.date, days[-1].date)    # mang ngày phiên CUỐI

    def test_a_holiday_week_does_not_shift_the_following_weeks(self):
        """Đây là lý do gộp theo tuần ISO chứ không theo 'mỗi 5 phiên'.

        Tuần giữa chỉ có 2 phiên (nghỉ lễ). Đếm 5 phiên một cục thì mọi cây
        nến sau đó lệch pha; gộp theo tuần ISO thì mỗi tuần vẫn là một cây.
        """
        days = []
        for offset in (0, 1, 2, 3, 4):              # tuần 1 — đủ 5 phiên
            days.append(_rec(datetime(2025, 1, 6) + timedelta(days=offset)))
        for offset in (0, 1):                        # tuần 2 — nghỉ lễ, 2 phiên
            days.append(_rec(datetime(2025, 1, 13) + timedelta(days=offset)))
        for offset in (0, 1, 2, 3, 4):              # tuần 3 — đủ 5 phiên
            days.append(_rec(datetime(2025, 1, 20) + timedelta(days=offset)))

        bars = to_weekly(days)
        self.assertEqual(len(bars), 3)
        self.assertEqual([b.date.isocalendar()[1] for b in bars], [2, 3, 4])

    def test_year_boundary_does_not_merge_two_different_weeks(self):
        """Số tuần lặp lại mỗi năm — khoá phải mang cả năm, nếu không tuần 1
        của 2025 sẽ dính vào tuần 1 của 2024."""
        days = [_rec(datetime(2024, 1, 2)), _rec(datetime(2025, 1, 2))]
        self.assertEqual(len(to_weekly(days)), 2)

    def test_empty_input_gives_empty_output(self):
        self.assertEqual(to_weekly([]), [])


class ViewTest(unittest.TestCase):
    def test_too_few_weeks_reports_not_measured_rather_than_a_number(self):
        """Chưa đủ tuần khác 'đã đo và thấy đi ngang' — đúng quy ước của dự án."""
        days = [_rec(datetime(2025, 1, 6) + timedelta(days=i)) for i in range(60)]
        view = weekly_mod.build_view("TEST", records=days)
        self.assertFalse(view.comparable)
        self.assertIsNone(view.ema50)
        self.assertIn("tuần", view.note)

    def test_no_data_is_reported_not_swallowed(self):
        view = weekly_mod.build_view("TEST", records=[])
        self.assertEqual(view.weeks, 0)
        self.assertFalse(view.comparable)
        self.assertTrue(view.note)

    def test_real_symbol_builds_a_comparable_view(self):
        view = weekly_mod.build_view("FPT")
        self.assertTrue(view.comparable, view.note)
        self.assertGreaterEqual(view.weeks, weekly_mod.MIN_WEEKS)
        self.assertIsNotNone(view.ema20)
        self.assertIsNotNone(view.ema50)
        self.assertIn(view.side, ("up", "down", "flat"))
        self.assertTrue(view.label)


class AgreementTest(unittest.TestCase):
    """Hai khung lệch nhau thì phải nói ra chỗ lệch, không làm phẳng thành một nhãn."""

    def test_opposite_sides_are_flagged_loudly(self):
        note = agreement("down", "up")
        self.assertIn("ngược nhau", note)
        self.assertIn("⚠️", note)

    def test_same_side_says_the_big_frame_does_not_block(self):
        self.assertIn("cùng chiều", agreement("up", "up"))

    def test_one_side_flat_is_neither_agreement_nor_conflict(self):
        note = agreement("flat", "up")
        self.assertNotIn("ngược nhau", note)
        self.assertNotIn("cùng chiều", note)

    def test_missing_side_gives_no_sentence(self):
        self.assertEqual(agreement("", "up"), "")


if __name__ == "__main__":
    unittest.main()
