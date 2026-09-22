import json
import re
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock

from src.reporting.chart_renderer_v2 import _basis_points
from src.ta import dossier as dossier_mod
from src.ta import forecast as fc
from src.ta import thesis as thesis_mod
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

    def test_basis_pane_shares_the_candle_timeline(self):
        # Các pane khớp nhau bằng chỉ số cây nến, không bằng ngày: thiếu một
        # phiên là cả chồng biểu đồ lệch dần khi kéo về quá khứ.
        candles = json.loads(
            re.search(r"const CANDLE_DATA\s*=\s*(\[.*?\]);", self.html, re.S).group(1))
        basis = json.loads(
            re.search(r"const BASIS_DATA\s*=\s*(\[.*?\]);", self.html, re.S).group(1))
        self.assertEqual(len(basis), len(candles))
        self.assertEqual([p["time"] for p in basis], [c["time"] for c in candles])
        self.assertTrue(any("value" in p for p in basis),
                        "phải có ít nhất một phiên có basis khi đã nạp VN30/VN30F1M")

    def test_basis_pane_sits_under_adx(self):
        order = [m for m in re.findall(r'id="(\w+)-chart"', self.html)]
        self.assertEqual(order[-2:], ["adx", "basis"])


class BasisPointsTest(unittest.TestCase):
    """Phiên nào phái sinh không có vẫn phải chiếm chỗ, dưới dạng điểm trắng."""

    class _Rec:
        def __init__(self, day):
            self.date = datetime.strptime(day, "%Y-%m-%d")

    def _points(self, days, basis):
        return _basis_points([self._Rec(d) for d in days], basis)

    def test_missing_session_becomes_whitespace_not_a_gap(self):
        pts = self._points(
            ["2025-01-02", "2025-01-03", "2025-01-06"],
            {"2025-01-02": {"pct": -0.4, "sessions": 8, "expiry": False},
             "2025-01-06": {"pct": 0.2, "sessions": 6, "expiry": True}},
        )
        self.assertEqual([p["time"] for p in pts],
                         ["2025-01-02", "2025-01-03", "2025-01-06"])
        self.assertNotIn("value", pts[1])
        self.assertEqual(pts[0]["value"], -0.4)
        self.assertTrue(pts[2]["expiry"])

    def test_no_futures_data_means_no_pane_at_all(self):
        self.assertEqual(self._points(["2025-01-02"], {}), [])
        self.assertEqual(self._points(["2025-01-02"], None), [])


if __name__ == "__main__":
    unittest.main()


class VerdictLayerTest(unittest.TestCase):
    """Hồ sơ có hai tầng: kết luận ở trên, số đo gốc ở dưới và gập lại.

    Thứ tự đó là cả điểm của thiết kế — người đọc duyệt một kết luận đã có
    chứ không tự dựng lấy một cái, nhưng vẫn bác được nó bằng số liệu nằm
    cùng file.
    """

    PAYLOAD = {
        "stance": "tang_cho",
        "headline": "Đã vượt cạnh hộp, còn thiếu volume xác nhận",
        "trigger": "đóng cửa > 25.40 kèm volume ≥ 1.5× TB20",
        "invalidation": "đóng cửa dưới 23.10",
        "target": "27.70 — chiều cao hộp chiếu ra",
        "confidence": "trung bình",
        "reasons": {k: f"kết luận {k}" for k, _ in thesis_mod.SECTIONS},
        "news": {"ket_luan": "tin nghiêng tích cực", "ly_do": ["một bằng chứng"],
                 "dien_giai": "vì sao", "da_vao_gia": "một phần"},
        "risks": ["độ rộng thị trường đang co lại"],
    }

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self._patches = [
            mock.patch.object(fc, "FORECAST_DIR", self.tmp / "forecasts"),
            mock.patch.object(dossier_mod, "DOSSIER_DIR", self.tmp / "reports"),
            mock.patch.object(thesis_mod, "THESIS_DIR", self.tmp / "nhan_dinh"),
        ]
        for p in self._patches:
            p.start()

    def tearDown(self):
        for p in self._patches:
            p.stop()
        self._tmp.cleanup()

    def _write_thesis(self, session):
        parsed = thesis_mod.parse_submission(
            json.dumps(self.PAYLOAD, ensure_ascii=False), "ACB", session,
            source="Test Model")
        thesis_mod.save_thesis(parsed)
        return parsed

    def test_without_a_thesis_the_gap_is_stated_and_evidence_comes_back(self):
        d = build_dossier("ACB", lookback_days=180)
        self.assertTrue(d.needs_thesis)
        self.assertIn("submit_thesis", d.brief)
        html = Path(d.path).read_text(encoding="utf-8")
        self.assertIn("KẾT LUẬN — chưa có", html)
        # Số đo vẫn ra đủ — thiếu kết luận không được làm hỏng phần đo được.
        self.assertIn("Động lượng", html)

    def test_with_a_thesis_the_conclusion_sits_above_the_numbers(self):
        session = build_dossier("ACB", lookback_days=180, with_brief=False).as_of
        self._write_thesis(session)
        d = build_dossier("ACB", lookback_days=180, with_brief=False)
        self.assertFalse(d.needs_thesis)
        html = Path(d.path).read_text(encoding="utf-8")
        self.assertNotIn("KẾT LUẬN — chưa có", html)
        self.assertLess(html.index("verdict-layer"), html.index("detail-layer"))
        self.assertIn(thesis_mod.STANCES["tang_cho"], html)
        self.assertIn("Test Model", html)

    def test_the_raw_numbers_are_collapsed_but_still_there(self):
        session = build_dossier("ACB", lookback_days=180, with_brief=False).as_of
        self._write_thesis(session)
        html = Path(build_dossier("ACB", lookback_days=180,
                                  with_brief=False).path).read_text(encoding="utf-8")
        self.assertIn('<details class="detail-layer"', html)
        self.assertNotIn('<details class="detail-layer" open', html)
        self.assertIn("Vùng giá tham chiếu", html)

    def test_the_card_under_the_chart_carries_the_verdict_not_the_note_list(self):
        session = build_dossier("ACB", lookback_days=180, with_brief=False).as_of
        parsed = self._write_thesis(session)
        html = Path(build_dossier("ACB", lookback_days=180,
                                  with_brief=False).path).read_text(encoding="utf-8")
        self.assertIn('"stance_label"', html)
        self.assertIn(parsed.headline, html)

    def test_a_thesis_from_another_session_is_not_reused(self):
        """Kết luận viết cho phiên khác nói về một cây nến khác và một mốc khác."""
        self._write_thesis("1999-01-04")
        d = build_dossier("ACB", lookback_days=180, with_brief=False)
        self.assertTrue(d.needs_thesis)

    def test_broken_evidence_does_not_kill_the_report(self):
        with mock.patch.object(thesis_mod, "build_evidence",
                               side_effect=RuntimeError("kho tin hỏng")):
            d = build_dossier("ACB", lookback_days=180)
        self.assertTrue(Path(d.path).is_file())
        self.assertIn("kho tin hỏng", d.brief)


class RedFlagLayerTest(unittest.TestCase):
    """Cờ đỏ phải đọc được **trước** biểu đồ và trước kết luận.

    Một vụ khởi tố lãnh đạo làm mọi con số phía dưới đổi nghĩa. Đặt nó sau
    phần nhận định là mặc định rằng người đọc sẽ cuộn xuống cuối — mà người
    đọc một báo cáo có kết luận sẵn thì thường không cuộn.
    """

    @staticmethod
    def _flags(penalty=50.0, key="hinh_su"):
        from src.news import redflag as rf

        out = rf.RedFlags(symbol="ACB", as_of="2026-09-10", penalty=penalty,
                          level=rf.level_for(penalty), n_scanned=90)
        out.flags = [rf.Flag(key=key, label="Hình sự",
                             title="ACB: Chủ tịch HĐQT bị khởi tố",
                             published="2026-08-01", age_days=40,
                             score=penalty, matched="khoi to")]
        return out

    def _html(self, redflags, thesis=None):
        from src.ta.snapshot import build_snapshot
        from src.ta.structure import build_structure

        snap = build_snapshot("ACB", lookback_days=200)
        structure = build_structure("ACB", lookback_days=200)
        return dossier_mod.render_dossier(snap, structure, redflags=redflags,
                                          thesis=thesis)

    def test_dai_co_do_nam_tren_ca_ten_ma(self):
        html = self._html(self._flags())
        self.assertIn('<div class="redflag-banner', html)
        self.assertLess(html.index('<div class="redflag-banner'),
                        html.index('<div id="header"'))
        self.assertIn("ACB: Chủ tịch HĐQT bị khởi tố", html)

    def test_khoi_co_do_dung_tren_ket_luan(self):
        html = self._html(self._flags())
        self.assertLess(html.index("Cờ đỏ — sự kiện pháp lý"),
                        html.index("KẾT LUẬN"))

    def test_sach_co_thi_khong_co_dai_bao_dong_nhung_van_noi_da_quet(self):
        from src.news import redflag as rf

        html = self._html(rf.RedFlags(symbol="ACB", as_of="2026-09-10",
                                      n_scanned=90))
        self.assertNotIn('<div class="redflag-banner', html)
        self.assertIn("Không có cờ nào", html)

    def test_chua_quet_duoc_khong_duoc_doc_thanh_sach_co(self):
        html = self._html(None)
        self.assertIn("Chưa quét được cờ đỏ", html)

    def test_ket_luan_tang_ma_co_hinh_su_thi_bi_chi_ra_cho_lech(self):
        parsed = thesis_mod.parse_submission(
            json.dumps(VerdictLayerTest.PAYLOAD, ensure_ascii=False),
            "ACB", "2026-09-10", source="Test Model")
        html = self._html(self._flags(), thesis=parsed)
        self.assertIn("Hai tầng của trang đang nói khác nhau", html)

    def test_ket_luan_co_nhac_toi_co_thi_khong_canh_bao_nua(self):
        payload = dict(VerdictLayerTest.PAYLOAD)
        payload["risks"] = ["chủ tịch bị khởi tố ngày 01/08, chưa có người thay"]
        parsed = thesis_mod.parse_submission(
            json.dumps(payload, ensure_ascii=False), "ACB", "2026-09-10",
            source="Test Model")
        self.assertEqual(
            thesis_mod.redflag_conflict(parsed, self._flags()), "")
