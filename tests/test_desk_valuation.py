"""Định giá lịch sử — BCTC, ngày công bố, và chuỗi P/E không nhìn trước."""
import unittest
from datetime import datetime
from types import SimpleNamespace

from src.desk import financials as fin_mod
from src.desk import valuation as val_mod
from src.desk.financials import Financials, Quarter


def _row(name, values, level=1, rid=1):
    return {"id": rid, "level": level, "name": name,
            "values": [{"year": y, "quarter": q, "value": v} for y, q, v in values]}


def _quarters(n=8, npat=1_000_000_000.0, shares=1_000_000.0, equity=None):
    out = []
    year, quarter = 2024, 1
    for i in range(n):
        out.append(Quarter(year=year, quarter=quarter, npat=npat, shares=shares,
                           equity=equity,
                           published=f"{year}-{quarter * 3:02d}-28",
                           published_source="mark"))
        quarter += 1
        if quarter == 5:
            year, quarter = year + 1, 1
    return out


class ParseTest(unittest.TestCase):
    def test_khop_dong_loi_nhuan_theo_TEN_khong_theo_id(self):
        """Ngân hàng dùng mẫu KQKD khác: VCB không có dòng 'cổ đông công ty mẹ'."""
        doanh_nghiep = [_row("19. Lợi nhuận sau thuế thu nhập doanh nghiệp",
                             [(2026, 2, 100.0)], rid=19),
                        _row("21. Lợi nhuận sau thuế của cổ đông của công ty mẹ",
                             [(2026, 2, 90.0)], rid=21)]
        ngan_hang = [_row("Lợi nhuận sau thuế thu nhập doanh nghiệp",
                          [(2026, 2, 140.0)], rid=13)]
        qs, _ = fin_mod.parse_statements(doanh_nghiep, [])
        self.assertEqual(qs[0].npat, 90.0)       # ưu tiên cổ đông công ty mẹ
        qs2, _ = fin_mod.parse_statements(ngan_hang, [])
        self.assertEqual(qs2[0].npat, 140.0)     # lùi về dòng của ngân hàng

    def test_khong_lay_dong_co_dong_thieu_so(self):
        rows = [_row("20. Lợi nhuận sau thuế của cổ đông không kiểm soát",
                     [(2026, 2, 5.0)], rid=20)]
        qs, notes = fin_mod.parse_statements(rows, [])
        self.assertTrue(all(q.npat is None for q in qs) or not qs)
        self.assertTrue(any("lợi nhuận" in n for n in notes))

    def test_so_co_phieu_suy_tu_VON_GOP_theo_dung_thu_tu_uu_tien(self):
        """SSI có cả 'vốn góp' (đúng) lẫn 'vốn đầu tư' (đã gồm thặng dư)."""
        balance = [_row("1. Vốn đầu tư của chủ sở hữu", [(2026, 2, 30_396e9)]),
                   _row("1.1. Vốn góp của chủ sở hữu", [(2026, 2, 25_030e9)])]
        qs, _ = fin_mod.parse_statements([], balance)
        self.assertAlmostEqual(qs[0].shares, 25_030e9 / 10_000)

    def test_ngan_hang_goi_von_chu_so_huu_la_von_va_cac_quy(self):
        balance = [_row("VIII. Vốn và các quỹ", [(2026, 2, 248_491e9)], level=2),
                   _row("- Vốn điều lệ", [(2026, 2, 83_556e9)], level=4)]
        qs, notes = fin_mod.parse_statements([], balance)
        self.assertAlmostEqual(qs[0].equity, 248_491e9)
        self.assertFalse(any("vốn chủ sở hữu" in n for n in notes))

    def test_thieu_thi_None_chu_khong_phai_0(self):
        qs, _ = fin_mod.parse_statements([], [_row("1. Vốn góp của chủ sở hữu",
                                                   [(2026, 2, 10_000e9)])])
        self.assertIsNone(qs[0].npat)

    def test_ky_khong_co_moc_dung_moc_thay_the_VA_TU_KHAI(self):
        qs = [Quarter(year=2026, quarter=1), Quarter(year=2026, quarter=2)]
        out = fin_mod.attach_publish_dates(qs, {(2026, 1): "2026-04-20"})
        self.assertEqual(out[0].published_source, "mark")
        self.assertEqual(out[0].published, "2026-04-20")
        self.assertEqual(out[1].published_source, "lag")
        self.assertEqual(out[1].published, "2026-08-14")     # 30/06 + 45 ngày


class TrailingTest(unittest.TestCase):
    def test_bon_quy_phai_lien_tiep(self):
        qs = _quarters(8)
        del qs[4]                       # thủng một kỳ ở giữa
        eps, _, _, _ = val_mod.trailing(qs[:5])
        self.assertIsNone(eps)

    def test_eps_la_tong_bon_quy_chia_so_co_phieu(self):
        eps, bvps, shares, label = val_mod.trailing(
            _quarters(6, npat=1_000_000_000.0, shares=1_000_000.0,
                      equity=20_000_000_000.0))
        self.assertAlmostEqual(eps, 4000.0)
        self.assertAlmostEqual(bvps, 20000.0)
        self.assertEqual(label, "Q2/2025")

    def test_chua_du_bon_quy_thi_khong_tra_eps(self):
        eps, _, _, _ = val_mod.trailing(_quarters(3))
        self.assertIsNone(eps)


class SeriesTest(unittest.TestCase):
    def _fin(self):
        return Financials(symbol="AAA", quarters=_quarters(
            8, npat=1_000_000_000.0, shares=1_000_000.0, equity=20_000_000_000.0))

    def test_chi_dung_quy_DA_CONG_BO_tai_moi_phien(self):
        fin = self._fin()
        self.assertEqual(len(fin.known_at("2024-06-30")), 2)
        self.assertEqual(len(fin.known_at("2020-01-01")), 0)

    def test_duoi_12_ky_thi_khong_so_sanh_duoc(self):
        series = val_mod.ValuationSeries(symbol="AAA", quarters_known=6)
        self.assertFalse(series.comparable)

    def test_band_doc_ra_cau_re_hay_dat_so_voi_CHINH_MA(self):
        band = val_mod.Band(metric="P/E", now=7.0, pct={5: 12.0}, med={5: 14.0},
                            n={5: 900})
        text = band.read(5)
        self.assertIn("phân vị 12", text)
        self.assertIn("thấp hơn trung vị", text)

    def test_chua_du_du_lieu_thi_band_noi_thang(self):
        band = val_mod.Band(metric="P/E", now=7.0)
        self.assertIn("chưa đủ dữ liệu", band.read(5))

    def test_lo_bon_quy_thi_PE_khong_dinh_nghia_duoc(self):
        """P/E âm không có nghĩa 'rẻ', nên nó phải là None chứ không phải số âm."""
        fin = Financials(symbol="AAA", quarters=_quarters(
            8, npat=-1_000_000_000.0, shares=1_000_000.0))
        series = val_mod.build("AAA", fin=fin, allow_fetch=False,
                               as_of=datetime(2026, 1, 1))
        for p in series.points:
            self.assertIsNone(p.pe)


class LookaheadTest(unittest.TestCase):
    def test_phan_vi_tinh_tai_t_khong_dung_tuong_lai(self):
        from src.desk.calibrate_valuation import expanding_ranks
        ranks = expanding_ranks([1.0] * 5 + [9.0], min_history=3)
        self.assertIsNone(ranks[0])
        self.assertIsNone(ranks[2])
        self.assertIsNotNone(ranks[3])
        self.assertEqual(ranks[-1], 1.0)          # cao nhất trong quá khứ của nó

    def test_khong_du_lich_su_thi_bo_han_chu_khong_doan(self):
        from src.desk.calibrate_valuation import expanding_ranks
        self.assertEqual(expanding_ranks([1.0, 2.0], min_history=250), [None, None])


if __name__ == "__main__":                                     # pragma: no cover
    unittest.main()
