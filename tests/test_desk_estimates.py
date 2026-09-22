"""Đóng băng định giá dựng sẵn — luật *không rơi về bản mới hơn*."""
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from src.desk import estimates

PAYLOAD = {
    "estimatedPriceDCF": 66212.7, "proportionDCF": 12.7,
    "estimatedPricePE": 71580.4, "proportionPE": 54.8,
    "estimatedPricePB": 39091.2, "proportionPB": 2.6,
    "estimatedPriceGraham1": 87907.0, "proportionGraham1": 6.0,
    "estimatedPriceGraham2": 77895.1, "proportionGraham2": 18.9,
    "estimatedPriceGraham3": 55215.0, "proportionGraham3": 4.9,
    "composedPrice": 71424.5,
}


class ParseTest(unittest.TestCase):
    def test_sau_mo_hinh_va_mot_gia_tong_hop(self):
        val = estimates.parse("FPT", PAYLOAD, "2026-09-19")
        self.assertEqual(len(val.models), 6)
        self.assertAlmostEqual(val.composed, 71424.5)
        self.assertEqual(val.models[0].name, "DCF")

    def test_do_trai_sau_mo_hinh_duoc_in_ra(self):
        """Một giá tổng hợp trông chính xác hơn thực tế đúng bằng độ trải này."""
        val = estimates.parse("FPT", PAYLOAD, "2026-09-19")
        self.assertGreater(val.spread_pct(), 60)

    def test_payload_rong_la_rong_chu_khong_phai_dinh_gia_bang_0(self):
        val = estimates.parse("FPT", None, "2026-09-19")
        self.assertTrue(val.is_empty)
        self.assertIsNone(val.composed)

    def test_upside_can_ca_hai_ve(self):
        val = estimates.parse("FPT", PAYLOAD, "2026-09-19")
        self.assertIsNone(val.upside_pct(None))
        self.assertAlmostEqual(val.upside_pct(60000.0), 19.0, places=0)

    def test_hai_nguon_hai_don_vi_phai_nhan_he_so(self):
        """`estimated-price` trả ĐỒNG, `data/` lưu NGHÌN ĐỒNG (`StockRecord.unit`
        = 1000). Thiếu hệ số là ra +99.516% — sai mà không ném lỗi."""
        val = estimates.parse("FPT", PAYLOAD, "2026-09-19")
        self.assertAlmostEqual(val.upside_pct(71.7, unit=1000.0), -0.4, places=1)
        self.assertGreater(val.upside_pct(71.7), 1000)      # quên hệ số = số vô lý

    def test_format_chan_ty_le_vo_ly_thay_vi_in_ra(self):
        from src.desk import format as desk_format
        val = estimates.parse("FPT", PAYLOAD, "2026-09-19")
        out = desk_format.format_valuation(val, "FPT", close=71.7)   # quên `unit`
        self.assertIn("lệch đơn vị", out)
        self.assertIn("không dùng được", out)
        self.assertNotIn("So với giá hiện tại: ", out)   # không in như một số thật


class FreezeTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        for day in ("2026-09-01", "2026-09-08", "2026-09-15"):
            estimates.freeze(estimates.parse("FPT", PAYLOAD, day), self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def test_doc_ban_moi_nhat_KHONG_muon_hon_moc(self):
        val = estimates.load("FPT", datetime(2026, 9, 10), self.root)
        self.assertEqual(val.snapshot_date, "2026-09-08")
        self.assertEqual(val.stale_days, 2)

    def test_khong_roi_ve_ban_moi_hon_khi_moc_qua_som(self):
        """Lấy bản tính sau mốc chính là cái nhìn trước mà `as_of` sinh ra để chặn."""
        self.assertIsNone(estimates.load("FPT", datetime(2026, 8, 20), self.root))

    def test_chua_dong_bang_ngay_nao_thi_tra_None(self):
        self.assertIsNone(estimates.load("HPG", datetime(2026, 9, 10), self.root))

    def test_chay_hai_lan_trong_ngay_khong_rai_file_trung(self):
        estimates.freeze(estimates.parse("FPT", PAYLOAD, "2026-09-15"), self.root)
        self.assertEqual(estimates.available_dates("FPT", self.root),
                         ["2026-09-01", "2026-09-08", "2026-09-15"])

    def test_coverage_dem_dung_so_ngay_da_giu_lai(self):
        cov = estimates.coverage(["FPT"], self.root)
        self.assertEqual(cov["sessions"], 3)
        self.assertEqual(cov["first"], "2026-09-01")
        self.assertEqual(cov["last"], "2026-09-15")


if __name__ == "__main__":                                     # pragma: no cover
    unittest.main()
