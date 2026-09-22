"""Sổ của bàn phân tích — mỗi test mang tên đúng cái bẫy nó chặn."""
import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from src.desk import ledger
from src.desk.ledger import Entry, LedgerConflict, LedgerError

# Lịch phiên giả: 30 phiên liên tiếp kể từ 01/09/2026, bỏ cuối tuần cho giống thật.
CALENDAR = [f"2026-09-{d:02d}" for d in range(1, 31) if d % 7 not in (0, 6)]


def _entry(root, **kw):
    base = dict(kind="stock", subject="FPT", session="2026-09-01",
                author="Claude Opus 5", stance="tang",
                headline="giữ trên cạnh hộp thì còn dư địa",
                trigger="đóng cửa > 24.8 với volume ≥ 1.5× TB20",
                invalidation="đóng cửa dưới 22.3", horizon_sessions=20,
                evidence_hash=ledger.hash_evidence("gói bằng chứng"))
    base.update(kw)
    return ledger.make_entry(**base)


class ValidationTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_khong_co_moc_huy_thi_khong_vao_so(self):
        """§7.7 — một câu không sai được thì không chấm điểm được."""
        with self.assertRaises(LedgerError) as ctx:
            _entry(self.root, invalidation="")
        self.assertIn("không bao giờ sai được", str(ctx.exception))

    def test_khong_co_han_thi_khong_vao_so(self):
        with self.assertRaises(LedgerError):
            _entry(self.root, horizon_sessions=0)

    def test_khong_biet_cua_ai_thi_khong_duyet_duoc(self):
        with self.assertRaises(LedgerError) as ctx:
            _entry(self.root, author="  ")
        self.assertIn("không duyệt được", str(ctx.exception))

    def test_phai_noi_ro_da_doc_goi_bang_chung_nao(self):
        with self.assertRaises(LedgerError):
            _entry(self.root, evidence_hash="")

    def test_session_la_phien_du_lieu_khong_phai_ngay_hom_nay(self):
        with self.assertRaises(LedgerError) as ctx:
            _entry(self.root, session="01/09/2026")
        self.assertIn("YYYY-MM-DD", str(ctx.exception))

    def test_tin_cay_la_NAC_khong_phai_phan_tram(self):
        """Trọng số do quy tắc tính; model chỉ được chọn nấc."""
        with self.assertRaises(LedgerError) as ctx:
            _entry(self.root, confidence="80")
        self.assertIn("trọng số do", str(ctx.exception))

    def test_hash_bang_chung_bo_qua_khac_biet_khoang_trang(self):
        self.assertEqual(ledger.hash_evidence("a  b\n c"), ledger.hash_evidence("a b c"))


class AppendOnlyTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_so_khong_co_ham_sua_va_khong_co_ham_xoa(self):
        """Luật quan trọng nhất, nên nó được kiểm bằng chính API công khai."""
        for forbidden in ("update", "delete", "edit", "remove"):
            self.assertFalse(hasattr(ledger, forbidden),
                             f"`ledger.{forbidden}` không được tồn tại")

    def test_ghi_lai_dung_ban_cu_la_no_op(self):
        e = _entry(self.root)
        p1 = ledger.append(e, self.root)
        p2 = ledger.append(e, self.root)
        self.assertEqual(p1, p2)
        self.assertEqual(len(ledger.all_entries(root=self.root)), 1)

    def test_trung_id_ma_khac_noi_dung_thi_dung_lai(self):
        e = _entry(self.root)
        path = ledger.append(e, self.root)
        data = json.loads(path.read_text(encoding="utf-8"))
        data["headline"] = "ai đó sửa tay"
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        with self.assertRaises(LedgerConflict):
            ledger.append(e, self.root)

    def test_doi_y_la_ghi_ban_moi_TRO_toi_ban_cu(self):
        old = _entry(self.root)
        ledger.append(old, self.root)
        new = _entry(self.root, session="2026-09-10", stance="trung_lap",
                     headline="mất cạnh hộp, hạ tư thế", supersedes=old.entry_id)
        ledger.append(new, self.root)

        rows = ledger.standings(as_of=datetime(2026, 9, 11), root=self.root,
                                calendar=CALENDAR)
        by_id = {s.entry.entry_id: s for s in rows}
        self.assertEqual(by_id[old.entry_id].status, ledger.SUPERSEDED)
        self.assertEqual(by_id[old.entry_id].replaced_by, new.entry_id)
        self.assertEqual(by_id[new.entry_id].status, ledger.OPEN)
        self.assertEqual([e.entry_id for e in ledger.chain_of(new.entry_id, self.root)],
                         [old.entry_id, new.entry_id])

    def test_khong_thay_duoc_mot_ban_khong_ton_tai(self):
        with self.assertRaises(LedgerError):
            ledger.append(_entry(self.root, supersedes="stock-FPT-2026-01-01-deadbeef"),
                          self.root)

    def test_khong_thay_duoc_quan_diem_ve_ma_khac(self):
        old = _entry(self.root)
        ledger.append(old, self.root)
        with self.assertRaises(LedgerError):
            ledger.append(_entry(self.root, subject="HPG", supersedes=old.entry_id),
                          self.root)

    def test_reindex_dung_lai_db_tu_file(self):
        ledger.append(_entry(self.root), self.root)
        (self.root / ledger.DB_NAME).unlink()
        self.assertEqual(ledger.reindex(self.root), 1)


class StandingTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_het_han_la_roi_khoi_so_ke_ca_khi_dang_lai(self):
        """§7.7 — không có cửa ra thì mọi vị thế thua đều 'vẫn đang chờ'."""
        e = _entry(self.root, horizon_sessions=3)
        ledger.append(e, self.root)
        rows = ledger.standings(as_of=datetime(2026, 9, 30), root=self.root,
                                calendar=CALENDAR)
        self.assertEqual(rows[0].status, ledger.EXPIRED)
        self.assertEqual(ledger.open_entries(as_of=datetime(2026, 9, 30),
                                             root=self.root, calendar=CALENDAR), [])

    def test_con_trong_han_thi_con_hieu_luc(self):
        ledger.append(_entry(self.root, horizon_sessions=20), self.root)
        rows = ledger.open_entries(as_of=datetime(2026, 9, 8), root=self.root,
                                   calendar=CALENDAR)
        self.assertEqual(len(rows), 1)

    def test_han_dem_bang_PHIEN_khong_phai_ngay_lich(self):
        # 01/09 → 09/09 là 8 ngày lịch nhưng chỉ 6 phiên trong lịch giả.
        self.assertEqual(ledger.sessions_since("2026-09-01",
                                               datetime(2026, 9, 9),
                                               calendar=CALENDAR), 6)

    def test_chua_doc_duoc_lich_phien_tra_None_chu_khong_tra_0(self):
        """*Chưa đo được* khác *bằng 0*: tuổi 0 thì không bao giờ hết hạn."""
        self.assertIsNone(ledger.sessions_since("2026-09-01",
                                                datetime(2026, 9, 9), calendar=[]))

    def test_ban_hoi_tuong_khong_thay_quan_diem_viet_sau_moc(self):
        ledger.append(_entry(self.root, session="2026-09-15"), self.root)
        rows = ledger.standings(as_of=datetime(2026, 9, 10), root=self.root,
                                calendar=CALENDAR)
        self.assertEqual(rows, [])


class StatsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_so_trong_la_so_trong_khong_phai_bang_diem_0(self):
        st = ledger.stats(root=self.root)
        self.assertEqual(st["n"], 0)
        self.assertIsNone(st["first_session"])

    def test_dem_theo_tung_cap_khong_gop_lai(self):
        ledger.append(_entry(self.root), self.root)
        ledger.append(_entry(self.root, kind="market", subject="VNINDEX",
                             stance="trung_lap"), self.root)
        st = ledger.stats(as_of=datetime(2026, 9, 3), root=self.root)
        self.assertEqual(set(st["by_kind"]), {"stock", "market"})


if __name__ == "__main__":                                     # pragma: no cover
    unittest.main()
