"""Chế độ hồi tưởng: giả định hôm nay là một phiên trong quá khứ.

Hai nhóm bài tách bạch. Nhóm *đọc ngày* chạy trên hằng số, không đụng đĩa. Nhóm
*cắt dữ liệu* chạy trên dữ liệu thật trong ``data/`` như các bài report/dossier
sẵn có, nhưng mọi thứ ghi ra đều bị đẩy vào thư mục tạm — một bài test không
được để lại file trong ``reports/`` hay sửa forecast đang sống.
"""
import json
import tempfile
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path
from unittest import mock

from src.ta import asof
from src.ta import dossier as dossier_mod
from src.ta import forecast as fc
from src.ta import ranking as ranking_mod
from src.ta import report as report_mod
from src.ta.format import asof_note, format_snapshot
from src.ta.scan import scan
from src.ta.snapshot import build_snapshot
from src.ta.structure import build_structure

MARK = "01/01/2025"
MARK_ISO = "2025-01-01"


class ParseTest(unittest.TestCase):
    def test_vietnamese_dates_are_day_first(self):
        """05/03 là mùng 5 tháng 3. Đoán theo giá trị thì 12/01 sẽ đọc sai."""
        self.assertEqual(asof.parse("5/3/2025").date(), date(2025, 3, 5))
        self.assertEqual(asof.parse("12/01/2025").date(), date(2025, 1, 12))
        self.assertEqual(asof.parse("01/01/2025").date(), date(2025, 1, 1))

    def test_iso_stays_iso(self):
        """Nhóm đầu 4 chữ số là năm — phân biệt bằng độ dài, không bằng giá trị."""
        self.assertEqual(asof.parse("2025-03-05").date(), date(2025, 3, 5))
        self.assertEqual(asof.parse("2025/03/05").date(), date(2025, 3, 5))
        self.assertEqual(asof.parse("20250305").date(), date(2025, 3, 5))
        self.assertEqual(asof.parse("2025-03-05T09:15:00").date(), date(2025, 3, 5))

    def test_accepts_the_words_around_the_date(self):
        self.assertEqual(asof.parse("ngày 01/01/2025").date(), date(2025, 1, 1))
        self.assertEqual(asof.parse("  01-01-2025  ").date(), date(2025, 1, 1))
        self.assertEqual(asof.parse("01/01/25").date(), date(2025, 1, 1))

    def test_no_mark_means_live(self):
        for value in ("", "   ", "hôm nay", "Hôm Nay", "hom nay", "today", "mới nhất", None):
            self.assertIsNone(asof.parse(value), value)

    def test_today_or_later_is_live_not_a_mark(self):
        """Giả định hôm nay là hôm nay — chính là chế độ thường."""
        self.assertIsNone(asof.parse(date.today().strftime("%d/%m/%Y")))
        self.assertIsNone(asof.parse(date.today() + timedelta(days=30)))

    def test_mark_reaches_the_end_of_its_own_day(self):
        """Bản ghi giá đóng dấu 00:00, nên mốc phải là cuối ngày mới lấy trọn phiên đó."""
        cut = asof.parse("01/01/2025")
        self.assertGreaterEqual(cut, datetime(2025, 1, 1, 23, 59))
        self.assertGreater(cut, datetime(2025, 1, 1))

    def test_rejects_what_it_cannot_mean(self):
        for bad in ("31/02/2025", "hôm kia", "2025-13-01", "abc"):
            with self.assertRaises(ValueError, msg=bad):
                asof.parse(bad)

    def test_rejects_dates_before_the_data_starts(self):
        with self.assertRaises(ValueError):
            asof.parse("01/01/2009")

    def test_label_and_before(self):
        cut = asof.parse(MARK)
        self.assertEqual(asof.label(cut), MARK_ISO)
        self.assertEqual(asof.label(None), "")
        self.assertTrue(asof.before(cut, "2024-12-31"))
        self.assertTrue(asof.before(cut, MARK_ISO))
        self.assertFalse(asof.before(cut, "2025-01-02"))
        self.assertTrue(asof.before(None, "2099-01-01"), "không mốc = thấy tất cả")


class OutputPathTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.base = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_retro_artefacts_never_land_in_todays_folder(self):
        cut = asof.parse(MARK)
        self.assertEqual(asof.out_root(self.base, cut).name, f"asof_{MARK_ISO}")
        self.assertEqual(asof.out_root(self.base, None).name,
                         datetime.now().strftime("%Y-%m-%d"))

    def test_retro_filenames_are_stable_across_runs(self):
        """Cùng mốc, cùng bộ mã thì ghi đè chính nó — giờ chạy không có ý nghĩa gì."""
        cut = asof.parse(MARK)
        self.assertEqual(asof.file_tag(cut), asof.file_tag(cut))
        self.assertEqual(asof.file_tag(cut), f"asof_{MARK_ISO}")
        self.assertNotEqual(asof.file_tag(None), asof.file_tag(cut))


class CutTest(unittest.TestCase):
    """Dữ liệu thật, cắt tại mốc — không phiên nào sau mốc được lọt vào."""

    def test_snapshot_stops_at_the_mark_and_remembers_it(self):
        snap = build_snapshot("ACB", as_of=asof.parse(MARK), lookback_days=400)
        self.assertGreater(snap.bars, 100)
        self.assertLessEqual(snap.as_of, MARK_ISO)
        self.assertEqual(snap.as_of_requested, MARK_ISO)

    def test_structure_stops_at_the_mark_and_remembers_it(self):
        st = build_structure("ACB", lookback_days=180, as_of=asof.parse(MARK))
        self.assertLessEqual(st.as_of, MARK_ISO)
        self.assertEqual(st.as_of_requested, MARK_ISO)
        self.assertTrue(all(r.date.date() <= date(2025, 1, 1) for r in st.records))
        self.assertEqual(st.to_dict()["as_of_requested"], MARK_ISO)

    def test_live_run_carries_no_mark(self):
        snap = build_snapshot("ACB", lookback_days=200)
        self.assertEqual(snap.as_of_requested, "")
        self.assertGreater(snap.as_of, MARK_ISO, "chạy thật phải mới hơn mốc thử")

    def test_scan_carries_the_mark(self):
        result = scan(universe="ACB,HPG", rules=["adx_momentum"],
                      as_of=asof.parse(MARK), recent_bars=5)
        self.assertEqual(result.as_of_requested, MARK_ISO)
        self.assertLessEqual(result.as_of, MARK_ISO)

    def test_the_same_mark_gives_the_same_answer_twice(self):
        """Bản hồi tưởng phải tái lập được — đó là lý do tồn tại của nó."""
        first = build_snapshot("ACB", as_of=asof.parse(MARK), lookback_days=300)
        second = build_snapshot("ACB", as_of=asof.parse(MARK_ISO), lookback_days=300)
        self.assertEqual(first.as_of, second.as_of)
        self.assertEqual(first.price, second.price)


class BannerTest(unittest.TestCase):
    def test_banner_names_both_dates_when_they_differ(self):
        """Mốc rơi vào ngày nghỉ: giấu chỗ lệch đi là để người đọc tự suy ra sai."""
        note = asof_note(MARK_ISO, "2024-12-31")
        self.assertIn(MARK_ISO, note)
        self.assertIn("2024-12-31", note)

    def test_banner_is_silent_on_a_live_run(self):
        self.assertEqual(asof_note("", "2026-08-25"), "")

    def test_snapshot_markdown_carries_the_banner(self):
        retro = format_snapshot(build_snapshot("ACB", as_of=asof.parse(MARK)))
        live = format_snapshot(build_snapshot("ACB", lookback_days=200))
        self.assertIn("Hồi tưởng", retro)
        self.assertIn(MARK_ISO, retro)
        self.assertNotIn("Hồi tưởng", live)


class ForecastAsOfTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self._patch = mock.patch.object(fc, "FORECAST_DIR", self.tmp / "forecasts")
        self._patch.start()

    def tearDown(self):
        self._patch.stop()
        self._tmp.cleanup()

    def _save(self, created: str, forecast_id: str) -> fc.Forecast:
        forecast = fc.Forecast(
            id=forecast_id, symbol="ACB", created=created,
            basis="box_breakout", direction="up",
            trigger_type=fc.CLOSE_ABOVE, trigger_level=1.0,
            target=1_000_000.0, invalidation=0.0,
            deadline_bars=500, created_close=1.0,
        )
        fc.save(forecast)
        return forecast

    def test_a_forecast_created_after_the_mark_is_invisible(self):
        self._save("2024-06-01", "old")
        self._save("2026-06-01", "new")
        ids = {f.id for f in fc.load_all(["ACB"], as_of=asof.parse(MARK))}
        self.assertEqual(ids, {"old"}, "kỳ vọng đặt sau mốc không thuộc về bản hồi tưởng")
        self.assertEqual(len(fc.load_all(["ACB"])), 2)

    def test_a_retro_check_never_writes_over_live_state(self):
        self._save("2024-06-01", "old")
        path = fc.path_for("old")
        before = path.read_text(encoding="utf-8")
        fc.check_all(["ACB"], as_of=asof.parse(MARK))
        self.assertEqual(path.read_text(encoding="utf-8"), before,
                         "file forecast là trạng thái hôm nay, không được tua ngược")

    def test_a_retro_check_only_replays_up_to_the_mark(self):
        self._save("2024-06-01", "old")
        retro = fc.check_all(["ACB"], as_of=asof.parse(MARK))
        live = fc.check_all(["ACB"])
        self.assertEqual(retro.as_of_requested, MARK_ISO)
        self.assertEqual(live.as_of_requested, "")
        self.assertGreater(live.forecasts[0].bars_elapsed,
                           retro.forecasts[0].bars_elapsed,
                           "bản hồi tưởng phải thấy ít phiên hơn bản chạy thật")

    def test_what_resolved_before_the_mark_is_still_reported(self):
        """`open_only` lọc *danh sách đang mở*, không được nuốt luôn chuyện đã xảy ra.

        Mức huỷ đặt cao hơn mọi giá nên phiên đầu tiên sau ngày tạo đã phủ định
        kỳ vọng — chuyện đó xong từ giữa 2024, tức là trước mốc.
        """
        dead = fc.Forecast(
            id="doomed", symbol="ACB", created="2024-06-03",
            basis="box_breakout", direction="up",
            trigger_type=fc.CLOSE_ABOVE, trigger_level=1e9,
            target=1e9, invalidation=1e9,
            deadline_bars=500, created_close=1.0,
        )
        fc.save(dead)
        result = fc.check_all(["ACB"], open_only=True, as_of=asof.parse(MARK))
        self.assertEqual([c["to"] for c in result.changes], [fc.INVALIDATED])
        self.assertEqual(result.forecasts, [], "đã đóng tính tới mốc thì không còn 'đang mở'")


class RankingAsOfTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.latest = self.tmp / "xep_hang_moi_nhat.json"
        self._patches = [
            mock.patch.object(ranking_mod, "REPORT_DIR", self.tmp),
            mock.patch.object(ranking_mod, "LATEST_JSON", self.latest),
        ]
        for p in self._patches:
            p.start()

    def tearDown(self):
        for p in self._patches:
            p.stop()
        self._tmp.cleanup()

    def test_a_retro_board_does_not_replace_the_live_one(self):
        live = ranking_mod.build(universe="ACB,HPG", lookback_days=180, with_html=False)
        self.assertTrue(self.latest.is_file())
        stamp = self.latest.read_text(encoding="utf-8")

        retro = ranking_mod.build(universe="ACB,HPG", lookback_days=180,
                                  with_html=False, as_of=asof.parse(MARK))
        self.assertEqual(retro.as_of_requested, MARK_ISO)
        self.assertEqual(self.latest.read_text(encoding="utf-8"), stamp,
                         "nhịp dùng hàng ngày đọc con trỏ này — thử hồi tưởng không được đụng vào")
        self.assertIn(f"asof_{MARK_ISO}", retro.json_path)
        self.assertGreater(live.as_of, retro.as_of)

    def test_the_retro_board_can_be_found_again_by_its_mark(self):
        ranking_mod.build(universe="ACB,HPG", lookback_days=180,
                          with_html=False, as_of=asof.parse(MARK))
        board = ranking_mod.load_ranking(as_of=asof.parse(MARK))
        self.assertEqual(board.as_of_requested, MARK_ISO)
        self.assertTrue(board.rows)

    def test_asking_for_a_board_never_built_says_so(self):
        with self.assertRaises(FileNotFoundError):
            ranking_mod.load_ranking(as_of=asof.parse("02/01/2025"))

    def test_the_mark_survives_the_json_round_trip(self):
        built = ranking_mod.build(universe="ACB", lookback_days=180,
                                  with_html=False, as_of=asof.parse(MARK))
        data = json.loads(Path(built.json_path).read_text(encoding="utf-8"))
        self.assertEqual(data["as_of_requested"], MARK_ISO)
        self.assertEqual(ranking_mod.Ranking.from_dict(data).as_of_requested, MARK_ISO)


class ReportFilesAsOfTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self._patches = [
            mock.patch.object(fc, "FORECAST_DIR", self.tmp / "forecasts"),
            mock.patch.object(report_mod, "REPORT_DIR", self.tmp / "reports"),
            mock.patch.object(dossier_mod, "DOSSIER_DIR", self.tmp / "reports"),
        ]
        for p in self._patches:
            p.start()

    def tearDown(self):
        for p in self._patches:
            p.stop()
        self._tmp.cleanup()

    def test_report_html_files_itself_under_the_mark_and_says_so(self):
        rep = report_mod.build("ACB", lookback_days=180, with_charts=False,
                               as_of=asof.parse(MARK))
        self.assertEqual(rep.as_of_requested, MARK_ISO)
        path = Path(rep.html_path)
        self.assertEqual(path.parent.name, f"asof_{MARK_ISO}")
        html = path.read_text(encoding="utf-8")
        self.assertIn("Hồi tưởng", html)
        self.assertIn(MARK_ISO, html)
        self.assertIn("Hồi tưởng", report_mod.to_markdown(rep, detail=False))

    def test_a_live_report_carries_no_banner(self):
        rep = report_mod.build("ACB", lookback_days=180, with_charts=False)
        self.assertNotIn("Hồi tưởng", Path(rep.html_path).read_text(encoding="utf-8"))
        self.assertNotIn("Hồi tưởng", report_mod.to_markdown(rep, detail=False))

    def test_dossier_html_files_itself_under_the_mark_and_says_so(self):
        d = dossier_mod.build_dossier("ACB", lookback_days=200, as_of=asof.parse(MARK))
        self.assertEqual(d.as_of_requested, MARK_ISO)
        path = Path(d.path)
        self.assertEqual(path.parent.name, f"asof_{MARK_ISO}")
        html = path.read_text(encoding="utf-8")
        self.assertIn("Hồi tưởng", html)
        self.assertEqual(html.count("Hồi tưởng"), 1, "một dải cảnh báo, không lặp lại")
        self.assertIn("Hồi tưởng", d.markdown, "terminal vẫn phải thấy nhãn")


if __name__ == "__main__":
    unittest.main()
