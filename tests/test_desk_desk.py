"""Đồng thuận CTCK, lịch xúc tác, sổ mô phỏng, kiểm tra chéo, bảng điểm."""
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from src.desk import book as book_mod
from src.desk import calendar as calendar_mod
from src.desk import consensus as cons_mod
from src.desk import consistency as consistency_mod
from src.desk import ledger as ledger_mod
from src.desk import scorecard as scorecard_mod
from src.desk.consensus import Report

CALENDAR = [f"2026-09-{d:02d}" for d in range(1, 31) if d % 7 not in (0, 6)]


def _report(title="", abstract="", symbol="AAA", date="2026-09-10", rid=1,
            source="BSC"):
    return Report(report_id=rid, date=date, symbol=symbol, source_name=source,
                  category_id=1, title=title, abstract=abstract)


# ---------------------------------------------------------------------------
class RatingTest(unittest.TestCase):
    def test_mot_am_tiet_khong_duoc_bat_tu_van_xuoi(self):
        """"FPT - MUA" từng bị đọc thành BÁN vì tóm tắt có "doanh thu bán hàng"."""
        rep = _report(title="FPT - MUA: Chủ động thích nghi",
                      abstract="Doanh thu bán hàng quý 2 tăng 12% so với cùng kỳ.")
        rating = cons_mod.extract_rating(rep)
        self.assertIsNotNone(rating)
        self.assertEqual(rating.word, "MUA")

    def test_phu_dinh_lam_mat_hieu_luc_chu_khong_dao_chieu(self):
        rep = _report(title="DCL - Q1/2026: Tình hình kinh doanh không khả quan")
        self.assertIsNone(cons_mod.extract_rating(rep))

    def test_tu_thuong_gap_can_cum_bao_hieu(self):
        prose = _report(title="PNJ - nhu cầu trang sức duy trì tích cực")
        self.assertIsNone(cons_mod.extract_rating(prose))
        real = _report(title="PNJ - cập nhật",
                       abstract="Chúng tôi khuyến nghị TÍCH CỰC với giá mục tiêu 120.000đ.")
        self.assertEqual(cons_mod.extract_rating(real).word, "TÍCH CỰC")

    def test_tu_khuyen_nghi_luon_mang_NGUYEN_VAN_cau_chua_no(self):
        rep = _report(title="ABC - cập nhật",
                      abstract="Duy trì KHẢ QUAN cho cổ phiếu này. Rủi ro còn đó.")
        rating = cons_mod.extract_rating(rep)
        self.assertIn("KHẢ QUAN", rating.quote)

    def test_khong_co_tu_nao_thi_None_nghia_la_KHONG_NOI(self):
        self.assertIsNone(cons_mod.extract_rating(
            _report(title="XYZ - Báo cáo phân tích kỹ thuật")))


class BurstTest(unittest.TestCase):
    def test_cum_phat_hanh_la_mot_su_kien(self):
        rows = [_report(rid=i, date=f"2026-09-{d:02d}", source=f"S{i}")
                for i, d in enumerate((1, 3, 6), start=1)]
        bursts = cons_mod.find_bursts(rows, min_n=3, window_days=14)
        self.assertEqual(len(bursts), 1)
        self.assertEqual(bursts[0].n, 3)

    def test_rai_rac_thi_khong_thanh_cum(self):
        rows = [_report(rid=i, date=d) for i, d in
                enumerate(("2026-01-05", "2026-04-05", "2026-08-05"), start=1)]
        self.assertEqual(cons_mod.find_bursts(rows), [])


# ---------------------------------------------------------------------------
class CalendarTest(unittest.TestCase):
    def test_uoc_luong_va_su_that_lich_khong_tron_vao_nhau(self):
        cal = calendar_mod.Calendar(start="2026-09-20", end="2026-10-20", events=[
            calendar_mod.Event(date="2026-10-15", kind="dao_han", subject="VN30F1M",
                               title="đáo hạn", certain=True),
            calendar_mod.Event(date="2026-10-30", kind="bctc", subject="FPT",
                               title="ước lượng", certain=False)])
        self.assertEqual(len(cal.certain), 1)
        self.assertEqual(len(cal.estimated), 1)

    def test_phien_dao_han_la_thu_Nam_tuan_thu_ba(self):
        from datetime import date
        events = calendar_mod.futures_events(date(2026, 10, 1), date(2026, 10, 31))
        self.assertEqual(len(events), 1)
        day = datetime.strptime(events[0].date, "%Y-%m-%d").date()
        self.assertEqual(day.weekday(), 3)
        self.assertIn(day.day, range(15, 22))


# ---------------------------------------------------------------------------
def _entry(root, symbol="FPT", stance="tang", confidence="cao", session="2026-09-01",
           **kw):
    base = dict(kind="stock", subject=symbol, session=session,
                author="test", stance=stance, confidence=confidence,
                headline="giữ trên cạnh hộp", trigger="đóng cửa > 24.8",
                invalidation="đóng cửa dưới 22.3", horizon_sessions=20,
                evidence_hash=ledger_mod.hash_evidence("gói"))
    base.update(kw)
    entry = ledger_mod.make_entry(**base)
    ledger_mod.append(entry, root)
    return entry


class BookTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def _standings(self, as_of=datetime(2026, 9, 3)):
        rows = ledger_mod.all_entries(kind="stock", root=self.root)
        return [s for s in ledger_mod.standings(rows, as_of, self.root, CALENDAR)
                if s.status == ledger_mod.OPEN]

    def test_trong_so_theo_NAC_tin_cay_chu_khong_do_model_dat(self):
        _entry(self.root, "AAA", confidence="cao")
        _entry(self.root, "BBB", confidence="thap")
        book = book_mod.build(as_of=datetime(2026, 9, 3),
                              standings=self._standings())
        weights = {p.symbol: p.weight_pct for p in book.positions}
        self.assertGreater(weights["AAA"], weights["BBB"])

    def test_tu_the_cho_kich_hoat_an_nua_trong_so(self):
        _entry(self.root, "AAA", stance="tang")
        _entry(self.root, "BBB", stance="tang_cho")
        book = book_mod.build(as_of=datetime(2026, 9, 3),
                              standings=self._standings())
        w = {p.symbol: p.weight_pct for p in book.positions}
        self.assertAlmostEqual(w["AAA"], w["BBB"] * 2, delta=0.2)

    def test_tu_the_giam_va_dung_ngoai_khong_duoc_cap_von(self):
        _entry(self.root, "AAA", stance="giam")
        _entry(self.root, "BBB", stance="dung_ngoai")
        book = book_mod.build(as_of=datetime(2026, 9, 3),
                              standings=self._standings())
        self.assertEqual(book.positions, [])
        self.assertEqual(book.cash_pct, 100.0)

    def test_tien_mat_luon_la_phan_con_lai_va_tong_bang_100(self):
        for sym in ("AAA", "BBB", "CCC"):
            _entry(self.root, sym)
        book = book_mod.build(as_of=datetime(2026, 9, 3),
                              standings=self._standings())
        self.assertAlmostEqual(book.invested_pct + book.cash_pct, 100.0, places=1)

    def test_tran_moi_ma_duoc_ton_trong(self):
        _entry(self.root, "AAA", confidence="cao")
        book = book_mod.build(as_of=datetime(2026, 9, 3),
                              standings=self._standings())
        for p in book.positions:
            self.assertLessEqual(p.weight_pct, book_mod.MAX_PER_NAME + 0.01)

    def test_so_trong_noi_ro_la_CHUA_AI_VIET(self):
        book = book_mod.build(as_of=datetime(2026, 9, 3), standings=[])
        self.assertEqual(book.cash_pct, 100.0)
        self.assertTrue(any("chưa ai viết" in n for n in book.notes))


class ConsistencyTest(unittest.TestCase):
    def test_tong_ty_trong_sai_thi_LOAI(self):
        book = book_mod.Book(as_of="2026-09-18", cash_pct=50.0, positions=[
            book_mod.Position(symbol="AAA", stance="tang", confidence="cao",
                              weight_pct=10.0)])
        rep = consistency_mod.check(book, with_redflags=False)
        self.assertFalse(rep.publishable)
        self.assertTrue(any(c.code == "tong_ty_trong" for c in rep.blocks))

    def test_co_do_do_tin_cay_thap_la_CANH_BAO_chu_khong_chan(self):
        """Một validator quá tay còn tệ hơn không có: người dùng sẽ tắt nó.

        Đo thật 20/09/2026: FPT bị gắn cờ hình sự vì bài *"Vụ khởi tố bị can
        Nguyễn Thành Nam…"* (trùng tên, độ tin cậy 0,25). Chặn theo *sự có mặt
        của từ khoá* là chặn gần như mọi mã lớn.
        """
        from src.news.redflag import LEVEL_CRITICAL, LEVEL_WARN
        book = book_mod.Book(as_of="2026-09-18", cash_pct=90.0, positions=[
            book_mod.Position(symbol="AAA", stance="tang", confidence="cao",
                              weight_pct=10.0)])
        orig = consistency_mod.redflag_state
        try:
            consistency_mod.redflag_state = lambda s, a: (LEVEL_WARN,
                                                          ['Hình sự: "trùng tên"'])
            rep = consistency_mod.check(book)
            self.assertTrue(rep.publishable)
            self.assertTrue(any(c.code == "co_do_nhe" for c in rep.warns))
            self.assertIn("trùng tên", rep.warns[0].message)

            consistency_mod.redflag_state = lambda s, a: (LEVEL_CRITICAL,
                                                          ['Hình sự: "khởi tố chủ tịch"'])
            rep2 = consistency_mod.check(book)
            self.assertFalse(rep2.publishable)
        finally:
            consistency_mod.redflag_state = orig

    def test_khong_mau_thuan_thi_noi_ro_la_DA_KIEM(self):
        from src.desk import format as desk_format
        rep = consistency_mod.Report(as_of="2026-09-18", n_positions=3)
        text = desk_format.format_consistency(rep)
        self.assertIn("không mâu thuẫn", text)
        self.assertIn("đã kiểm", text)


class ScorecardTest(unittest.TestCase):
    def test_tu_the_trung_lap_khong_vao_ty_le_dung(self):
        self.assertIsNone(scorecard_mod.STANCE_DIRECTION["trung_lap"])
        self.assertEqual(scorecard_mod.STANCE_DIRECTION["giam"], -1)

    def test_so_trong_la_chua_co_gi_de_cham(self):
        card = scorecard_mod.build(standings=[])
        self.assertEqual(card.n_complete, 0)
        self.assertIn("chưa có gì để chấm", card.note)

    def test_duoi_nguong_quan_sat_thi_khong_phat_bieu(self):
        card = scorecard_mod.Scorecard(as_of="2026-09-18", n_complete=7)
        self.assertFalse(card.enough)
        self.assertLess(card.n_complete, scorecard_mod.MIN_INDEPENDENT)

    def test_chi_phi_vong_duoc_tru_va_in_rieng(self):
        self.assertGreater(scorecard_mod.ROUND_TRIP_COST_PCT, 0)


if __name__ == "__main__":                                     # pragma: no cover
    unittest.main()
