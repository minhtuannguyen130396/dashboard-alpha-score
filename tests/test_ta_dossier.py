import re
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from src.ta import dossier as dossier_mod
from src.ta import forecast as fc
from src.ta.dossier import _md_to_html, build_dossier


class MarkdownTest(unittest.TestCase):
    """The converter only has to cover what format.py emits — and escape first."""

    def test_table_keeps_alignment_and_cells(self):
        html = _md_to_html("| Mã | Giá |\n|----|----:|\n| FPT | 70.7 |")
        self.assertIn("<th>Mã</th>", html)
        self.assertIn("<th class=\"num\">Giá</th>", html)
        self.assertIn("<td class=\"num\">70.7</td>", html)
        self.assertNotIn("----", html)

    def test_headings_are_collected_for_the_nav(self):
        headings = []
        html = _md_to_html("## Cấu trúc\n\n### Xu hướng", headings)
        self.assertEqual([(a, t, lv) for a, t, lv in headings],
                         [("muc-1", "Cấu trúc", 2), ("muc-2", "Xu hướng", 3)])
        self.assertIn('<h2 id="muc-1">', html)
        self.assertIn('<h3 id="muc-2">', html)

    def test_bold_and_code_survive_but_html_does_not(self):
        html = _md_to_html("- **đỉnh** `73.3` <script>alert(1)</script>")
        self.assertIn("<strong>đỉnh</strong>", html)
        self.assertIn("<code>73.3</code>", html)
        self.assertNotIn("<script>", html)
        self.assertIn("&lt;script&gt;", html)

    def test_continuation_line_stays_inside_its_bullet(self):
        html = _md_to_html("- **FPT** — chờ kích hoạt\n  giá đã vượt, chờ volume")
        self.assertEqual(html.count("<li>"), 1)
        self.assertIn('<div class="sub">giá đã vượt, chờ volume</div></li>', html)


class DossierTest(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self._patches = [
            mock.patch.object(fc, "FORECAST_DIR", self.tmp / "forecasts"),
            mock.patch.object(dossier_mod, "DOSSIER_DIR", self.tmp / "reports"),
        ]
        for p in self._patches:
            p.start()
        self.dossier = build_dossier("ACB", lookback_days=180)
        self.html = Path(self.dossier.path).read_text(encoding="utf-8")

    def tearDown(self):
        for p in self._patches:
            p.stop()
        self._tmp.cleanup()

    def test_file_lands_under_the_dossier_dir(self):
        self.assertTrue(Path(self.dossier.path).is_file())
        self.assertIn(str(self.tmp / "reports"), self.dossier.path)
        self.assertIn("ACB", Path(self.dossier.path).name)

    def test_chart_is_live_data_not_a_picture(self):
        self.assertIn("const CANDLE_DATA", self.html)
        self.assertIn("const OVERLAY_DATA", self.html)
        self.assertIn('id="price-chart"', self.html)
        self.assertNotIn("data:image/png;base64,", self.html)

    def test_structure_overlays_reach_the_chart(self):
        payload = re.search(r"const OVERLAY_DATA\s*=\s*(\{.*\});", self.html)
        self.assertIsNotNone(payload, "overlay payload must be injected")
        self.assertIn('"lines"', payload.group(1))
        self.assertIn('"boxes"', payload.group(1))

    def test_nothing_is_fetched_from_the_network(self):
        # The library, its CSS and its JS are inlined — a dossier has to open
        # offline and after being emailed.
        self.assertFalse(re.search(r'(src|href)="https?://', self.html))
        self.assertIn("LightweightCharts", self.html)

    def test_the_deep_dive_text_is_in_the_file(self):
        for heading in ("Xu hướng", "Động lượng", "Thanh khoản", "Diễn giải"):
            self.assertIn(heading, self.html)
        self.assertIn("ACB", self.dossier.markdown)

    def test_prose_from_the_data_is_escaped(self):
        # Only the prose — the injected data and the chart JS live outside it.
        body = self.html.split('<div class="sections">', 1)[1] \
                        .split('<div class="foot">', 1)[0]
        self.assertNotIn("<script", body.lower())

    def test_unknown_symbol_returns_none(self):
        self.assertIsNone(build_dossier("KHONGCOMA"))


if __name__ == "__main__":
    unittest.main()
