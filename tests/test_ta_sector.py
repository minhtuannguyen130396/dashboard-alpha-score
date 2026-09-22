"""Nhóm ngành và chỉ số cơ bản đóng băng theo ngày.

Bốn chỗ dễ sai, mỗi chỗ một bài:

* **nhãn quy mô không phải nhãn ngành** — ``stock_groups`` trộn ``vn30`` /
  ``large_cap`` với ``tai_chinh`` / ``bds``, và để lọt thì "cùng ngành với FPT"
  hoá ra là 30 mã VN30;
* **ngành 1–2 mã không được gộp im lặng** — trung vị của một quan sát là chính
  nó, nên "sức mạnh tương đối so với ngành" khi đó luôn bằng 0: một con số
  trông như đã đo mà không đo gì;
* **ảnh chụp chỉ số cơ bản muộn hơn mốc là nhìn trước** — FireAnt chỉ trả trạng
  thái hôm nay, nên đây là chỗ duy nhất chặn được;
* **chênh so với ngành phải quy về dấu "tốt hơn là dương"** — P/E ngược chiều
  ROE, và chỉ cần một tầng trên quên là cột định giá đảo dấu không báo.
"""
import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from src.news import insider
from src.news.models import PURCHASED, SOLD
from src.ta import fundamentals as fund_mod
from src.ta import sector
from src.ta.fundamentals import Fundamentals, Indicator


class _Row:
    """Đủ mặt những trường mà ``sector.build_view`` đọc tới, không hơn."""

    def __init__(self, symbol, score=0.0, side="flat", ch20=0.0, ch5=0.0):
        self.symbol = symbol
        self.trend = type("T", (), {"score": score, "side": side})()
        self.change_20d = ch20
        self.change_5d = ch5


class MembershipTest(unittest.TestCase):
    def test_nhan_quy_mo_khong_duoc_tinh_la_nganh(self):
        for tag in ("vn30", "large_cap", "mid_cap", "small_cap"):
            self.assertIn(tag, sector.SIZE_TAGS)
        self.assertNotIn("vn30", sector.sectors())
        self.assertNotIn("large_cap", sector.sectors())

    def test_ma_vn30_van_co_nganh_that(self):
        """FPT mang cả ``vn30`` lẫn ``cntt``; ngành của nó là ``cntt``."""
        self.assertEqual(sector.sector_of("FPT"), "cntt")
        self.assertNotIn("FPT", sector.peers("FPT"))

    def test_ma_la_khong_no(self):
        self.assertIsNone(sector.sector_of("KHONGCOMA"))
        self.assertEqual(sector.peers("KHONGCOMA"), [])
        self.assertEqual(sector.sector_label(None), "chưa phân ngành")


class SectorViewTest(unittest.TestCase):
    def test_nganh_qua_it_ma_thi_khong_so_duoc(self):
        rows = [_Row("AAA", 10.0, "up", 5.0), _Row("BBB", -10.0, "down", -5.0)]
        # Ép hai mã này vào cùng một ngành giả.
        original = sector._MEMBERSHIP
        sector._MEMBERSHIP = {"AAA": ["gia_dinh"], "BBB": ["gia_dinh"]}
        try:
            view = sector.build_view("AAA", rows)
        finally:
            sector._MEMBERSHIP = original
        self.assertFalse(view.comparable)
        self.assertIsNone(view.rs_vs_sector, "không đủ mã thì để trống, không trả 0")
        self.assertIn("trung vị", view.note)

    def test_du_ma_thi_do_duoc_do_rong_va_thu_hang(self):
        rows = [_Row("AAA", 50.0, "up", 12.0), _Row("BBB", 10.0, "up", 4.0),
                _Row("CCC", -30.0, "down", -6.0), _Row("DDD", 5.0, "flat", 1.0)]
        original = sector._MEMBERSHIP
        sector._MEMBERSHIP = {s: ["gia_dinh"] for s in ("AAA", "BBB", "CCC", "DDD")}
        try:
            view = sector.build_view("AAA", rows)
        finally:
            sector._MEMBERSHIP = original
        self.assertTrue(view.comparable)
        self.assertEqual(view.n_rows, 4)
        self.assertEqual(view.breadth_up, 50.0)
        self.assertEqual(view.leader, "AAA")
        self.assertEqual(view.laggard, "CCC")
        self.assertEqual(view.rank_in_sector, 1)
        self.assertEqual(view.median_change_20d, 2.5)
        self.assertEqual(view.rs_vs_sector, 9.5)

    def test_khong_co_nganh_thi_khong_dung_view(self):
        self.assertIsNone(sector.build_view("KHONGCOMA", [_Row("KHONGCOMA")]))


class RelativeStrengthTest(unittest.TestCase):
    def test_tang_8_khi_thi_truong_tang_12_la_tut_lai(self):
        rs = sector.relative_strength(8.0, 12.0, sessions=20, market=12.0)
        self.assertEqual(rs.vs_market, -4.0)
        self.assertEqual(rs.vs_sector, -4.0)

    def test_thieu_moc_thi_de_trong(self):
        rs = sector.relative_strength(8.0, None, sessions=20, market=None)
        self.assertIsNone(rs.vs_market)
        self.assertIsNone(rs.vs_sector)

    def test_round_trip_qua_dict(self):
        rs = sector.relative_strength(8.0, 3.0, sessions=20, market=5.0)
        again = sector.RelativeStrength.from_dict(rs.to_dict())
        self.assertEqual(again.vs_market, rs.vs_market)


class IndicatorGapTest(unittest.TestCase):
    def test_pe_thap_hon_nganh_ra_dau_duong(self):
        cheap = Indicator(key="P/E", name="P/E", group=1, value=10.0, industry=20.0)
        self.assertGreater(cheap.gap_pct, 0)

    def test_roe_thap_hon_nganh_ra_dau_am(self):
        weak = Indicator(key="ROE", name="ROE", group=4, value=10.0, industry=20.0)
        self.assertLess(weak.gap_pct, 0)

    def test_chi_so_khong_biet_chieu_thi_khong_phat_bieu(self):
        odd = Indicator(key="Lạ", name="Lạ", group=9, value=10.0, industry=20.0)
        self.assertIsNone(odd.gap_pct)

    def test_thieu_moc_nganh_thi_khong_phat_bieu(self):
        lone = Indicator(key="P/E", name="P/E", group=1, value=10.0, industry=None)
        self.assertIsNone(lone.gap_pct)


class SnapshotTest(unittest.TestCase):
    @staticmethod
    def _fund(date: str) -> Fundamentals:
        return Fundamentals(
            symbol="AAA", snapshot_date=date, pe=12.0, free_shares=1e9,
            indicators={"P/E": Indicator(key="P/E", name="P/E", group=1,
                                         value=12.0, industry=15.0)},
        )

    def test_ghi_ra_roi_doc_lai_khong_mat_gi(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fund_mod.freeze(self._fund("2026-09-10"), root)
            back = fund_mod.load("AAA", datetime(2026, 9, 10), root)
        self.assertEqual(back.pe, 12.0)
        self.assertEqual(back.gap("P/E"), 20.0)
        self.assertEqual(back.stale_days, 0)

    def test_khong_bao_gio_doc_anh_chup_muon_hon_moc(self):
        """Dùng P/E hôm nay để giải thích tin năm ngoái là nhìn trước."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fund_mod.freeze(self._fund("2026-09-10"), root)
            self.assertIsNone(fund_mod.load("AAA", datetime(2025, 1, 1), root))

    def test_lay_ban_gan_nhat_khong_muon_hon_moc(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fund_mod.freeze(self._fund("2026-01-01"), root)
            fund_mod.freeze(self._fund("2026-06-01"), root)
            fund_mod.freeze(self._fund("2026-09-10"), root)
            got = fund_mod.load("AAA", datetime(2026, 7, 1), root)
        self.assertEqual(got.snapshot_date, "2026-06-01")
        self.assertEqual(got.stale_days, 30)

    def test_chua_co_anh_chup_nao_thi_tra_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(fund_mod.load("AAA", None, Path(tmp)))

    def test_ghi_hai_lan_trong_ngay_khong_rai_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fund_mod.freeze(self._fund("2026-09-10"), root)
            fund_mod.freeze(self._fund("2026-09-10"), root)
            self.assertEqual(fund_mod.available_dates("AAA", root), ["2026-09-10"])


class InsiderFlowTest(unittest.TestCase):
    @staticmethod
    def _tx(direction, registered=None, executed=None, name="Người A"):
        return {"direction": direction, "registered_volume": registered,
                "execution_volume": executed, "name": name}

    def test_chuan_hoa_theo_co_phieu_tu_do(self):
        """1 triệu cổ của mã 100 triệu cổ khác hẳn 1 triệu của mã 4 tỷ cổ."""
        rows = [self._tx(PURCHASED, executed=1e6)]
        small = insider.summarise("AAA", rows, free_shares=1e8)
        large = insider.summarise("BBB", rows, free_shares=4e9)
        self.assertGreater(small.net_ratio_pct, large.net_ratio_pct)

    def test_dang_ky_va_da_thuc_hien_khong_bi_gop(self):
        planned = insider.summarise("AAA", [self._tx(PURCHASED, registered=1e6)],
                                    free_shares=1e8)
        done = insider.summarise("AAA", [self._tx(PURCHASED, executed=1e6)],
                                 free_shares=1e8)
        self.assertTrue(planned.registered_only)
        self.assertFalse(done.registered_only)
        self.assertIn("đăng ký", planned.label)

    def test_mua_va_ban_bu_tru_dung_chieu(self):
        rows = [self._tx(PURCHASED, executed=2e6), self._tx(SOLD, executed=5e5)]
        flow = insider.summarise("AAA", rows, free_shares=1e8)
        self.assertAlmostEqual(flow.executed_net, 1.5e6)
        self.assertGreater(flow.net_ratio_pct, 0)

    def test_thieu_mau_so_thi_de_trong_chu_khong_tra_0(self):
        flow = insider.summarise("AAA", [self._tx(PURCHASED, executed=1e6)])
        self.assertIsNone(flow.net_ratio_pct)
        self.assertIn("chuẩn hoá", flow.label)

    def test_khong_co_giao_dich_thi_noi_thang(self):
        flow = insider.summarise("AAA", [], free_shares=1e8)
        self.assertTrue(flow.is_empty)
        self.assertIn("không có", flow.label)

    def test_round_trip_qua_dict(self):
        flow = insider.summarise("AAA", [self._tx(PURCHASED, executed=1e6)],
                                 free_shares=1e8)
        again = insider.InsiderFlow.from_dict(flow.to_dict())
        self.assertEqual(again.net_ratio_pct, flow.net_ratio_pct)


if __name__ == "__main__":
    unittest.main()
