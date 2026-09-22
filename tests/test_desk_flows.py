"""Dòng tiền — fixture tĩnh, không mạng, không đĩa."""
import unittest
from datetime import date, datetime, timedelta
from types import SimpleNamespace

from src.desk import flows
from src.desk.flows import build_points, build_symbol_flow, etf_review_window


def _bar(day, close=10.0, total_bn=100.0, pt_bn=0.0, buy_bn=0.0, sell_bn=0.0,
         prop_bn=None, room=None, deal_vol=1_000_000.0):
    """Một phiên giả. Đơn vị vào là **tỷ**, đổi sang đồng như dữ liệu thật."""
    return SimpleNamespace(
        date=day if isinstance(day, datetime) else datetime.strptime(day, "%Y-%m-%d"),
        priceClose=close,
        totalValue=total_bn * 1e9,
        putthroughValue=pt_bn * 1e9,
        dealVolume=deal_vol,
        buyForeignValue=buy_bn * 1e9,
        sellForeignValue=sell_bn * 1e9,
        propTradingNetDealValue=(prop_bn * 1e9 if prop_bn is not None else None),
        currentForeignRoom=room,
    )


def _series(n=40, **kw):
    start = datetime(2026, 5, 4)          # thứ Hai, tránh tuần ETF của tháng 3/6/9/12
    return [_bar(start + timedelta(days=i), **kw) for i in range(n)]


class MeasureTest(unittest.TestCase):
    def test_gia_tri_khop_lenh_da_tru_thoa_thuan(self):
        """Cùng quy ước `priceImpactVolume = dealVolume` của mọi chỉ báo."""
        pts = build_points([_bar("2026-05-04", total_bn=100, pt_bn=30)])
        self.assertAlmostEqual(pts[0].value_bn, 70.0)
        self.assertAlmostEqual(pts[0].pt_share_pct, 30.0)

    def test_chuan_hoa_theo_CHINH_MA_chu_khong_so_tuyet_doi(self):
        """300 tỷ ở một mã lớn là chuyện thường, ở mã nhỏ là chuyện lớn."""
        big = _series(30, total_bn=1000.0) + [_bar("2026-06-15", total_bn=1000,
                                                   buy_bn=300)]
        small = _series(30, total_bn=50.0) + [_bar("2026-06-15", total_bn=50,
                                                  buy_bn=300)]
        b = build_points(big)[-1]
        s = build_points(small)[-1]
        self.assertAlmostEqual(b.foreign_net_bn, s.foreign_net_bn)
        self.assertLess(b.foreign_net_pct, s.foreign_net_pct)
        self.assertAlmostEqual(b.foreign_net_pct, 30.0)

    def test_chua_du_phien_thi_cot_phan_tram_de_TRONG(self):
        """*Chưa đo được* khác *bằng 0*."""
        pts = build_points(_series(5, total_bn=100))
        self.assertIsNone(pts[-1].foreign_net_pct)
        flow = build_symbol_flow("AAA", bars=_series(5, total_bn=100))
        self.assertIsNone(flow.foreign_net_pct)
        self.assertTrue(any("chưa đủ" in n for n in flow.notes))

    def test_mau_so_khong_gom_chinh_phien_dang_do(self):
        """Một phiên đột biến không được tự nâng mẫu số của chính nó."""
        bars = _series(25, total_bn=100) + [_bar("2026-06-15", total_bn=1000,
                                                 buy_bn=100)]
        self.assertAlmostEqual(build_points(bars)[-1].foreign_net_pct, 100.0)

    def test_chuoi_cung_dau_moi_la_hanh_vi(self):
        bars = (_series(25, total_bn=100)
                + [_bar(f"2026-06-{d:02d}", total_bn=100, buy_bn=5) for d in range(1, 4)])
        self.assertEqual(build_symbol_flow("AAA", bars=bars).foreign_streak, 3)

    def test_chuoi_dut_khi_doi_dau(self):
        bars = (_series(25, total_bn=100)
                + [_bar("2026-06-01", total_bn=100, buy_bn=5),
                   _bar("2026-06-02", total_bn=100, sell_bn=5)])
        self.assertEqual(build_symbol_flow("AAA", bars=bars).foreign_streak, -1)


class SpecialSessionTest(unittest.TestCase):
    def test_ma_kin_room_mang_co_vi_ban_rong_la_co_che(self):
        """§7.3 — room hết thì lệnh mua không vào được, đó không phải quan điểm."""
        bars = _series(25, total_bn=100, deal_vol=1_000_000, room=10_000_000)
        bars.append(_bar("2026-06-15", total_bn=100, sell_bn=20, room=100.0,
                         deal_vol=1_000_000))
        flow = build_symbol_flow("AAA", bars=bars)
        self.assertTrue(flow.room_capped)
        self.assertTrue(any("cơ chế" in n for n in flow.notes))

    def test_room_con_rong_thi_khong_gan_co(self):
        bars = _series(26, total_bn=100, room=500_000_000.0)
        self.assertFalse(build_symbol_flow("AAA", bars=bars).room_capped)

    def test_tuan_ETF_co_cau_duoc_danh_dau(self):
        third_friday = flows._third_friday(2026, 3)
        self.assertEqual(third_friday.weekday(), 4)
        self.assertIn(third_friday.day, range(15, 22))
        self.assertTrue(etf_review_window(third_friday))
        self.assertTrue(etf_review_window(third_friday - timedelta(days=3)))
        self.assertFalse(etf_review_window(third_friday + timedelta(days=1)))
        self.assertFalse(etf_review_window(date(2026, 2, 20)))   # tháng không cơ cấu


class PropTest(unittest.TestCase):
    def test_chua_co_so_tu_doanh_khac_tu_doanh_bang_0(self):
        flow = build_symbol_flow("AAA", bars=_series(26, total_bn=100))
        self.assertFalse(flow.prop_available)
        self.assertIsNone(flow.prop_net_bn)
        self.assertIsNone(flow.prop_net_5d_bn)
        self.assertTrue(any("chưa có số tự doanh" in n for n in flow.notes))

    def test_co_so_tu_doanh_thi_chuan_hoa_cung_mau_so(self):
        bars = _series(25, total_bn=100, prop_bn=0.0)
        bars.append(_bar("2026-06-15", total_bn=100, prop_bn=25.0))
        pt = build_points(bars)[-1]
        self.assertAlmostEqual(pt.prop_net_pct, 25.0)


class BoardTest(unittest.TestCase):
    def test_ma_thieu_du_lieu_khong_giet_ca_bang(self):
        flow = build_symbol_flow("AAA", bars=[])
        self.assertTrue(flow.is_empty)
        self.assertIn("chưa đọc được giá", flow.notes)

    def test_as_of_cat_moi_phien_sau_moc(self):
        bars = _series(30, total_bn=100)
        flow = build_symbol_flow("AAA", as_of=datetime(2026, 5, 10), bars=bars)
        self.assertEqual(flow.as_of, "2026-05-10")

    def test_thoa_thuan_cao_duoc_noi_ra_chu_khong_am_tham(self):
        bars = _series(25, total_bn=100)
        bars.append(_bar("2026-06-15", total_bn=100, pt_bn=60, buy_bn=10))
        flow = build_symbol_flow("AAA", bars=bars)
        self.assertTrue(any("sang tay" in n for n in flow.notes))


class SectorFlowTest(unittest.TestCase):
    def test_nganh_duoi_3_ma_bi_danh_dau_mong(self):
        thin = flows.SectorFlow(code="20", n_members=1, n_total=33,
                                foreign_net_bn=5.0, value_bn=50.0)
        thick = flows.SectorFlow(code="30", n_members=27, n_total=120,
                                 foreign_net_bn=5.0, value_bn=50.0)
        self.assertTrue(thin.thin)
        self.assertFalse(thick.thin)
        self.assertEqual(thin.coverage_pct, 3)

    def test_phan_tram_tinh_theo_thanh_khoan_nganh(self):
        sec = flows.SectorFlow(code="30", n_members=5, foreign_net_bn=10.0,
                               value_bn=200.0)
        self.assertAlmostEqual(sec.foreign_net_pct, 5.0)


if __name__ == "__main__":                                     # pragma: no cover
    unittest.main()
