import json
import tempfile
import unittest
from pathlib import Path

from src.ta import thesis as thesis_mod
from src.ta.thesis import (
    SECTIONS, STANCES, NewsRead, Thesis, format_thesis, parse_submission,
)


def _payload(**over) -> dict:
    base = {
        "stance": "tang_cho",
        "headline": "Giá đã vượt cạnh hộp nhưng volume chưa xác nhận",
        "trigger": "đóng cửa > 74.80 kèm volume ≥ 1.5× TB20",
        "invalidation": "đóng cửa dưới 70.70",
        "target": "78.90 — chiều cao hộp chiếu ra",
        "confidence": "trung bình",
        "reasons": {key: f"kết luận mục {key}" for key, _ in SECTIONS},
        "news": {"ket_luan": "tin nghiêng về tích cực",
                 "ly_do": ["phiên 2026-09-03 có tin trúng thầu"],
                 "dien_giai": "hai phiên có tin đều chạy trước thị trường",
                 "da_vao_gia": "phần lớn đã vào giá"},
        "risks": ["ngành đang phân hoá"],
    }
    base.update(over)
    return base


class ParseTest(unittest.TestCase):
    def test_accepts_a_plain_json_object(self):
        t = parse_submission(json.dumps(_payload(), ensure_ascii=False),
                             "FPT", "2026-09-10", source="Test Model")
        self.assertEqual(t.symbol, "FPT")
        self.assertEqual(t.stance_label, STANCES["tang_cho"])
        self.assertEqual(t.source, "Test Model")
        self.assertTrue(t.written_at)
        self.assertEqual(len(t.reasons), len(SECTIONS))

    def test_accepts_json_inside_a_fenced_block(self):
        raw = "Đây là nhận định:\n```json\n" + json.dumps(_payload()) + "\n```\n"
        self.assertEqual(parse_submission(raw, "FPT", "2026-09-10").stance, "tang_cho")

    def test_unknown_stance_is_refused_rather_than_defaulted(self):
        """Rơi về 'trung lập' khi model gõ sai là bịa ra một nhận định."""
        with self.assertRaises(ValueError) as caught:
            parse_submission(json.dumps(_payload(stance="mua manh")),
                             "FPT", "2026-09-10")
        self.assertIn("stance", str(caught.exception))

    def test_missing_headline_is_refused(self):
        with self.assertRaises(ValueError):
            parse_submission(json.dumps(_payload(headline="  ")), "FPT", "2026-09-10")

    def test_a_missing_section_says_so_instead_of_disappearing(self):
        """Mục thiếu phải hiện ra là 'chưa đo được', không im lặng biến mất."""
        payload = _payload()
        payload["reasons"].pop("nganh")
        t = parse_submission(json.dumps(payload, ensure_ascii=False),
                             "FPT", "2026-09-10")
        self.assertIn("Chưa đo được", t.reasons["nganh"])
        self.assertTrue(any("thiếu mục" in r for r in t.risks))

    def test_empty_news_stays_none_rather_than_an_empty_verdict(self):
        t = parse_submission(json.dumps(_payload(news={})), "FPT", "2026-09-10")
        self.assertIsNone(t.news)

    def test_unknown_confidence_falls_back_to_the_cautious_end(self):
        t = parse_submission(json.dumps(_payload(confidence="tuyệt đối")),
                             "FPT", "2026-09-10")
        self.assertEqual(t.confidence, "thấp")

    def test_garbage_input_raises(self):
        with self.assertRaises(Exception):
            parse_submission("không phải json", "FPT", "2026-09-10")


class StoreTest(unittest.TestCase):
    def test_round_trip_keeps_every_field(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            t = parse_submission(json.dumps(_payload(), ensure_ascii=False),
                                 "FPT", "2026-09-10", source="Test Model")
            thesis_mod.save_thesis(t, root=root)
            back = thesis_mod.load_thesis("FPT", "2026-09-10", root=root)
            self.assertEqual(back.headline, t.headline)
            self.assertEqual(back.stance, t.stance)
            self.assertEqual(back.reasons, t.reasons)
            self.assertEqual(back.news.ly_do, t.news.ly_do)
            self.assertEqual(back.source, "Test Model")

    def test_another_session_does_not_inherit_this_one(self):
        """Nhận định của phiên trước nói về một cây nến khác — không dùng lại."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            t = parse_submission(json.dumps(_payload()), "FPT", "2026-09-10")
            thesis_mod.save_thesis(t, root=root)
            self.assertIsNone(thesis_mod.load_thesis("FPT", "2026-09-11", root=root))

    def test_missing_file_is_none_not_an_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(
                thesis_mod.load_thesis("FPT", "2026-09-10", root=Path(tmp)))

    def test_corrupt_file_is_none_not_a_crash(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = thesis_mod.thesis_path("FPT", "2026-09-10", root)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("{ broken", encoding="utf-8")
            self.assertIsNone(thesis_mod.load_thesis("FPT", "2026-09-10", root=root))


class FormatTest(unittest.TestCase):
    def test_absent_thesis_says_nobody_wrote_one(self):
        """Chỗ trống phải nói là trống — một câu trung tính viết sẵn ở đây
        trông y hệt một kết luận đã có người đọc."""
        md = format_thesis(None, symbol="FPT", as_of="2026-09-10")
        self.assertIn("chưa có", md)
        self.assertIn("submit_thesis", md)
        self.assertIn("FPT", md)

    def test_conclusion_comes_before_the_reasons(self):
        t = parse_submission(json.dumps(_payload(), ensure_ascii=False),
                             "FPT", "2026-09-10", source="Test Model")
        md = format_thesis(t)
        self.assertLess(md.index("KẾT LUẬN"), md.index("LÝ DO"))
        self.assertIn(STANCES["tang_cho"], md)

    def test_all_five_sections_are_printed_in_order(self):
        t = parse_submission(json.dumps(_payload(), ensure_ascii=False),
                             "FPT", "2026-09-10")
        md = format_thesis(t)
        positions = [md.index(label) for _, label in SECTIONS]
        self.assertEqual(positions, sorted(positions))

    def test_news_block_keeps_conclusion_reason_explanation_order(self):
        t = parse_submission(json.dumps(_payload(), ensure_ascii=False),
                             "FPT", "2026-09-10")
        md = format_thesis(t)
        self.assertLess(md.index("tin nghiêng về tích cực"), md.index("**Lý do:**"))
        self.assertLess(md.index("**Lý do:**"), md.index("**Diễn giải:**"))

    def test_the_writer_is_named(self):
        t = parse_submission(json.dumps(_payload(), ensure_ascii=False),
                             "FPT", "2026-09-10", source="Test Model")
        self.assertIn("Test Model", format_thesis(t))

    def test_summary_line_carries_stance_and_levels(self):
        t = parse_submission(json.dumps(_payload(), ensure_ascii=False),
                             "FPT", "2026-09-10")
        line = thesis_mod.summary_line(t)
        self.assertIn(STANCES["tang_cho"], line)
        self.assertIn("74.80", line)
        self.assertEqual(thesis_mod.summary_line(None), "")


class BriefTest(unittest.TestCase):
    """Gói bằng chứng phải mang đủ năm mục và giữ nguyên ranh giới untrusted."""

    @classmethod
    def setUpClass(cls):
        cls.brief = thesis_mod.format_brief(thesis_mod.build_evidence("FPT"))

    def test_untrusted_boundary_survives(self):
        self.assertIn("<untrusted", self.brief)
        self.assertIn("</untrusted>", self.brief)
        self.assertIn("DỮ LIỆU", self.brief)

    def test_every_section_of_the_checklist_is_covered(self):
        for needle in ("Bối cảnh thị trường", "Khung tuần", "Khung ngày",
                       "ngành", "tin"):
            self.assertIn(needle.lower(), self.brief.lower(), needle)

    def test_the_submit_step_is_explained_inside_the_tool_output(self):
        """Hướng dẫn phải nằm trong chuỗi tool trả về, không phải trong
        .claude/commands/ — tool này dùng được từ mọi MCP client."""
        self.assertIn("submit_thesis", self.brief)
        self.assertIn("session", self.brief)
        for key, _ in SECTIONS:
            self.assertIn(key, self.brief)

    def test_it_says_which_session_to_submit_against(self):
        self.assertIn("`session` = **", self.brief)


if __name__ == "__main__":
    unittest.main()
