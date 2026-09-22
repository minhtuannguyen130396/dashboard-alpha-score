"""Hiệu chuẩn dòng tiền — chặn đúng hai kiểu tự lừa mình.

Không test trên dữ liệu thật: kết quả thật là *kết luận*, và một test khẳng
định trước kết luận sẽ hỏng ngay khi dữ liệu nói khác. Cái test được phép
khẳng định là **cơ chế**.
"""
import random
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from src.desk import calibrate_flows as cal
from src.desk.calibrate_flows import FlowCalibration, Observation, build_hypothesis
from src.desk.flows import FlowPoint


def _obs(n, seed=7, edge=0.0, special_every=0):
    """n quan sát; ``edge`` gắn thêm lợi suất cho nhóm dòng tiền cao nhất.

    ``pct_rank`` tính bằng chính hàm thật, vì việc chia nhóm chạy trên phân vị
    trong từng mã chứ không trên giá trị tuyệt đối.
    """
    rng = random.Random(seed)
    out = []
    for i in range(n):
        value = rng.uniform(-100, 100)
        rel = rng.gauss(0, 0.05) + (edge if value > 60 else 0.0)
        out.append(Observation(date=f"2020-01-{i % 28 + 1:02d}", value=value, rel=rel,
                               special=bool(special_every and i % special_every == 0),
                               symbol="AAA"))
    for obs, rank in zip(out, cal._percentile_ranks([o.value for o in out])):
        obs.pct_rank = rank
    return out


class GateTest(unittest.TestCase):
    def test_chua_du_quan_sat_la_CHUA_DO_DUOC_khong_phai_da_do_va_thay_phang(self):
        hyp = build_hypothesis(_obs(40), "foreign", 20, False, draws=50)
        self.assertFalse(hyp.passed)
        self.assertIn("chưa đo được", hyp.note)
        self.assertEqual(hyp.buckets, [])

    def test_nhieu_thuan_tuy_khong_qua_duoc_nguong_Bonferroni(self):
        hyp = build_hypothesis(_obs(1200), "foreign", 20, False, draws=200)
        self.assertFalse(hyp.passed)
        self.assertIn("Bonferroni", hyp.note)

    def test_tin_hieu_that_thi_nhom_cao_nhat_tach_khoi_nen(self):
        hyp = build_hypothesis(_obs(1500, edge=0.12), "foreign", 20, False, draws=300)
        self.assertTrue(hyp.passed)
        self.assertGreater(hyp.buckets[-1].edge, 0)

    def test_so_sanh_voi_NEN_PLACEBO_chu_khong_voi_0(self):
        hyp = build_hypothesis(_obs(1500, edge=0.12), "foreign", 20, False, draws=300)
        for b in hyp.buckets:
            if b.median_rel is not None:
                self.assertIsNotNone(b.placebo_median)
                self.assertAlmostEqual(b.edge, round(b.median_rel - b.placebo_median, 3),
                                       places=2)

    def test_ban_sach_loai_phien_dac_biet_khoi_mau(self):
        obs = _obs(1200, special_every=2)
        full = build_hypothesis(obs, "foreign", 20, False, draws=50)
        clean = build_hypothesis(obs, "foreign", 20, True, draws=50)
        self.assertLess(clean.pool_n, full.pool_n)
        self.assertIn("đã loại", clean.question)

    def test_moc_chia_nhom_lay_tu_phan_vi_cua_chinh_mau(self):
        edges = cal._bucket_edges([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], 5)
        self.assertEqual(len(edges), 4)
        self.assertEqual(cal._bucket_index(0.5, edges), 0)
        self.assertEqual(cal._bucket_index(99, edges), 4)

    def test_moc_trung_nhau_bi_GOP_chu_khong_de_lai_nhom_rong(self):
        """Lượt chạy đầu của D2: 8% số phiên có dòng tiền đúng bằng 0 nên hai mốc
        phân vị bằng nhau, để nguyên là sinh ra một nhóm rỗng **trông như đã đo**."""
        values = [0.0] * 60 + [float(i) for i in range(1, 41)]
        ranks = cal._percentile_ranks(values)
        rows = [Observation(date="2020-01-02", value=v, rel=0.0, symbol="AAA",
                            pct_rank=r) for v, r in zip(values, ranks)]
        groups = cal.split_buckets(rows)
        self.assertTrue(all(g for g in groups))
        self.assertLess(len(groups), cal.BUCKETS)       # nói ra là tách được ít nhóm hơn
        self.assertEqual(sum(len(g) for g in groups), len(values))

    def test_tach_duoc_it_nhom_hon_thi_NOI_RA(self):
        values = [0.0] * 600 + [float(i) for i in range(1, 401)]
        ranks = cal._percentile_ranks(values)
        rows = [Observation(date="2020-01-02", value=v, rel=0.001 * i, symbol="AAA",
                            pct_rank=r)
                for i, (v, r) in enumerate(zip(values, ranks))]
        hyp = build_hypothesis(rows, "foreign", 20, False, draws=50)
        self.assertIn("thay vì 5", hyp.note)

    def test_chia_nhom_theo_phan_vi_TRONG_TUNG_MA(self):
        """Nếu chia theo giá trị gộp cả rổ thì nhóm đuôi chỉ toàn mã biến động
        mạnh, và cái đo được là *nhóm gồm mã nào* chứ không phải dòng tiền."""
        rows = []
        for sym, scale in (("BIG", 1.0), ("SMALL", 100.0)):
            vals = [scale * v for v in range(-10, 10)]
            ranks = cal._percentile_ranks(vals)
            for v, r in zip(vals, ranks):
                rows.append(Observation(date="2020-01-02", value=v, rel=0.0,
                                        symbol=sym, pct_rank=r))
        edges = cal._bucket_edges([o.pct_rank for o in rows], 5)
        groups = [[] for _ in range(len(edges) + 1)]
        for o in rows:
            groups[cal._bucket_index(o.pct_rank, edges)].append(o.symbol)
        for g in groups:
            self.assertEqual(sorted(set(g)), ["BIG", "SMALL"], g)

    def test_gia_tri_bang_nhau_thi_phan_vi_bang_nhau(self):
        ranks = cal._percentile_ranks([5.0, 5.0, 1.0, 9.0])
        self.assertEqual(ranks[0], ranks[1])
        self.assertLess(ranks[2], ranks[0])
        self.assertGreater(ranks[3], ranks[0])

    def test_ten_nhom_mang_luon_khoang_gia_tri_that(self):
        hyp = build_hypothesis(_obs(1200), "foreign", 20, False, draws=50)
        self.assertIn("→", hyp.buckets[-1].name)

    def test_chi_so_dong_tien_khong_biet_thi_ném_loi(self):
        point = FlowPoint(date="2026-01-02", value_bn=1.0, foreign_net_bn=0.0)
        with self.assertRaises(ValueError):
            cal._feature_value(point, "khong_ton_tai")


class NoteTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_chua_chay_khac_da_chay_va_khong_dat(self):
        note, ok = cal.calibration_note(self.root)
        self.assertFalse(ok)
        self.assertIn("chưa hiệu chuẩn", note)

        flat = FlowCalibration(generated="2026-09-19 10:00", universe="all",
                               n_symbols=80,
                               hypotheses=[build_hypothesis(_obs(1200), "foreign",
                                                            20, False, draws=50)])
        cal.save(flat, self.root)
        note2, ok2 = cal.calibration_note(self.root)
        self.assertFalse(ok2)
        self.assertIn("kết luận của dữ liệu", note2)
        self.assertNotIn("chưa hiệu chuẩn", note2)

    def test_ket_qua_di_tron_vong_JSON(self):
        c = FlowCalibration(generated="2026-09-19 10:00", universe="all", n_symbols=80,
                            hypotheses=[build_hypothesis(_obs(1500, edge=0.12),
                                                         "foreign", 20, False, draws=100)])
        cal.save(c, self.root)
        back = cal.load(self.root)
        self.assertEqual(back.n_symbols, 80)
        self.assertTrue(back.any_passed)
        self.assertEqual(len(back.hypotheses[0].buckets), cal.BUCKETS)


if __name__ == "__main__":                                     # pragma: no cover
    unittest.main()
