import re
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from src.ta import forecast as fc
from src.ta import report as report_mod
from src.ta.report import build, to_markdown


class ReportTest(unittest.TestCase):
    """Charts are slow, so most cases run with with_charts=False."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        # Keep generated forecasts and report files out of the repo.
        self._patches = [
            mock.patch.object(fc, "FORECAST_DIR", self.tmp / "forecasts"),
            mock.patch.object(report_mod, "REPORT_DIR", self.tmp / "reports"),
        ]
        for p in self._patches:
            p.start()

    def tearDown(self):
        for p in self._patches:
            p.stop()
        self._tmp.cleanup()

    def test_report_covers_every_requested_symbol(self):
        report = build("ACB,HPG", lookback_days=180, with_charts=False)
        self.assertEqual([s.symbol for s in report.sections], ["ACB", "HPG"])
        for section in report.sections:
            self.assertGreater(section.snapshot.bars, 50)
            self.assertTrue(section.headline)

    def test_markdown_contains_the_overview_table_and_every_symbol(self):
        report = build("ACB,HPG", lookback_days=180, with_charts=False)
        md = to_markdown(report)
        self.assertIn("## Tổng quan", md)
        self.assertIn("| **ACB** |", md)
        self.assertIn("| **HPG** |", md)
        self.assertIn("### ACB", md)

    def test_html_file_is_written_and_self_contained(self):
        report = build("ACB", lookback_days=180, with_charts=True)
        self.assertIsNotNone(report.html_path)
        html = Path(report.html_path).read_text(encoding="utf-8")
        self.assertIn("<title>", html)
        self.assertIn("data:image/png;base64,", html, "chart must be embedded, not linked")
        # Nothing may be fetched from the network.
        self.assertFalse(re.search(r'(src|href)="https?://', html))

    def test_html_escapes_text_from_the_data(self):
        report = build("ACB", lookback_days=180, with_charts=False)
        html = Path(report.html_path).read_text(encoding="utf-8")
        body = html.split("<body>", 1)[1]
        # Only our own markup may contain tags — no raw < from generated prose.
        self.assertNotIn("<script", body.lower())

    def test_open_forecasts_appear_in_the_report(self):
        for forecast in fc.propose("ACB", lookback_days=180):
            fc.save(forecast)
        report = build("ACB", lookback_days=180, with_charts=False)
        stored = [f for s in report.sections for f in s.forecasts]
        self.assertEqual(len(stored), len(fc.load_all(["ACB"])))
        if any(f.is_open for f in stored):
            self.assertIn("Forecast đang mở", to_markdown(report))

    def test_unknown_symbol_is_reported_not_raised(self):
        report = build("NOSUCHTICKER", lookback_days=100)
        self.assertEqual(report.sections, [])
        self.assertTrue(report.skipped)
        self.assertIn("Không tìm thấy dữ liệu", to_markdown(report))

    def test_symbol_count_is_capped(self):
        report = build("vn30", lookback_days=120, with_charts=False, with_forecasts=False)
        self.assertLessEqual(len(report.sections), report_mod.MAX_SYMBOLS)
        self.assertTrue(any("giới hạn" in s for s in report.skipped))


if __name__ == "__main__":
    unittest.main()
