"""Danh sách triển vọng cao: từng thành phần điểm, và các cửa chặn.

Sáu chỗ dễ sai nhất của tầng này, mỗi chỗ một bài test:

* **RSI phải là đường cong, không phải cửa sổ** — 40–60 đủ điểm, 65 vẫn còn
  hơn nửa, 75 về 0, trên đó là điểm âm. Cắt phựt ở 60 là loại đúng những mã
  mà tiêu chí mẫu hình + breakout vừa chọn ra;
* **breakout phải phân biệt được "xác nhận bằng volume" với "phá suông"** — và
  một breakout hỏng (phá lên rồi tụt lại) không được ăn điểm nào;
* **thanh khoản là cửa, không phải điểm** — mã dưới ngưỡng phải biến khỏi danh
  sách chứ không phải tụt xuống cuối;
* **định giá so với ngành phải đúng chiều** — P/E thấp hơn ngành là *tốt*, ROE
  thấp hơn ngành là *xấu*; sai dấu ở đây thì cả cột đảo ngược im lặng;
* **điểm tin không được trộn vào điểm đo được** — hai vế phải tách ra được sau
  khi ghi ra JSON rồi đọc lại;
* **"chưa chấm tin" khác "chấm tin ra 0"** — một mã chưa ai đọc tin không được
  hiện ra như một mã đã đọc và thấy trung tính.
"""
import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from src.news import verdict as verdict_mod
from src.ta import prospect
from src.ta.fundamentals import Fundamentals, Indicator
from src.ta.prospect import (
    BoxFacts, Component, MAX_NEWS, NewsVerdict, ProspectBoard, ProspectRow,
    breakout_points, insider_points, pattern_points, rsi_points, rs_points,
    valuation_points,
)
from src.ta.ranking import PatternRank, SymbolRank, TrendRank
from src.ta.sector import RelativeStrength, SectorView


def _pattern(bias="bullish", state="confirmed", confidence=80.0,
             name="vượt hộp", **kw):
    return PatternRank(source="box", name=name, bias=bias, state=state,
                       confidence=confidence, **kw)


def _trend(score=40.0, side="up", conflict=False):
    return TrendRank(side=side, score=score, ema_side=side, ema_label="tăng",
                     structure_side=side, structure_label="uptrend",
                     conflict=conflict, adx=25.0, adx_direction=side,
                     adx_regime="có xu hướng")


def _row(symbol="AAA", rsi=50.0, rvol=1.5, close=20.0, avg_value_bn=100.0,
         pattern=None, box_state="", vol_x=None, change_20d=5.0):
    return SymbolRank(
        symbol=symbol, as_of="2026-09-10", bars=300, close=close,
        change_pct=1.0, change_5d=2.0, change_20d=change_20d, rsi=rsi,
        rsi_state="neutral", rvol=rvol, atr_pct=2.0, vs_ema20=3.0, vs_ema50=5.0,
        box_position=90.0, box_top=21.0, box_bottom=18.0,
        trend=_trend(), pattern=pattern or _pattern(),
        box_state=box_state, box_breakout_volume_x=vol_x,
        avg_value_bn=avg_value_bn,
    )


class RsiCurveTest(unittest.TestCase):
    """Yêu cầu là "lý tưởng 40–60", nhưng cắt cứng ở đó thì tự mâu thuẫn."""

    def test_vung_ly_tuong_duoc_du_diem(self):
        for rsi in (40.0, 50.0, 60.0):
            self.assertEqual(rsi_points(rsi).points, prospect.MAX_RSI,
                             f"RSI {rsi} phải đủ điểm")

    def test_qua_mua_bi_tru_diem_that_su(self):
        """"Trừ điểm đi" nghĩa là điểm âm, không phải bằng 0."""
        self.assertLess(rsi_points(85.0).points, 0.0)
        self.assertLess(rsi_points(95.0).points, rsi_points(85.0).points)

    def test_giam_dan_chu_khong_cat_phut(self):
        """Một mã breakout thường có RSI 62–72; nó phải còn điểm, chỉ ít hơn."""
        self.assertGreater(rsi_points(65.0).points, 0.0)
        self.assertGreater(rsi_points(70.0).points, 0.0)
        self.assertGreater(rsi_points(60.0).points, rsi_points(65.0).points)
        self.assertGreater(rsi_points(65.0).points, rsi_points(70.0).points)

    def test_duoi_vung_ly_tuong_cung_it_diem_hon(self):
        self.assertLess(rsi_points(32.0).points, prospect.MAX_RSI)
        self.assertLessEqual(rsi_points(20.0).points, 0.0)

    def test_thieu_rsi_khong_bia_ra_diem(self):
        c = rsi_points(None)
        self.assertEqual(c.points, 0.0)
        self.assertIn("không tính được", c.note)


class PatternPointsTest(unittest.TestCase):
    def test_mau_hinh_giam_khong_duoc_diem_nao(self):
        c = pattern_points(_pattern(bias="bearish", confidence=90.0))
        self.assertEqual(c.points, 0.0)
        self.assertIn("giảm", c.note)

    def test_trang_thai_xep_truoc_diem_so(self):
        """"đã xác nhận 70" phải hơn "chưa xác nhận 95" — quy ước của CLAUDE.md."""
        confirmed = pattern_points(_pattern(state="confirmed", confidence=70.0))
        pending = pattern_points(_pattern(state="pending", confidence=95.0))
        self.assertGreater(confirmed.points, pending.points)

    def test_mau_hinh_hong_bang_khong(self):
        self.assertEqual(pattern_points(_pattern(state="failed", confidence=60.0)).points,
                         0.0)


class BreakoutPointsTest(unittest.TestCase):
    def test_volume_xac_nhan_an_diem_hon_pha_suong(self):
        strong = breakout_points(
            BoxFacts(state="breakout_up_confirmed", breakout_volume_x=2.5),
            _pattern(), 2.5)
        weak = breakout_points(BoxFacts(state="breakout_up_weak"), _pattern(), 1.0)
        self.assertGreater(strong.points, weak.points)
        self.assertIn("volume", strong.note)

    def test_breakout_hong_khong_duoc_diem(self):
        c = breakout_points(BoxFacts(state="false_breakout_up"), _pattern(), 3.0)
        self.assertEqual(c.points, 0.0)
        self.assertIn("hỏng", c.note)

    def test_cu_pha_cu_bi_tru_diem(self):
        fresh = breakout_points(
            BoxFacts(state="breakout_up_confirmed", breakout_volume_x=2.0,
                     bars_since_breakout=2), _pattern(), 2.0)
        stale = breakout_points(
            BoxFacts(state="breakout_up_confirmed", breakout_volume_x=2.0,
                     bars_since_breakout=30), _pattern(), 2.0)
        self.assertGreater(fresh.points, stale.points)

    def test_retest_giu_duoc_cong_them(self):
        plain = breakout_points(
            BoxFacts(state="breakout_up_confirmed", breakout_volume_x=1.5),
            _pattern(), 1.5)
        held = breakout_points(
            BoxFacts(state="breakout_up_confirmed", breakout_volume_x=1.5,
                     retest_held=True), _pattern(), 1.5)
        self.assertGreater(held.points, plain.points)

    def test_mo_hinh_dao_chieu_cung_tinh_la_cu_pha(self):
        """Không có hộp không có nghĩa là không có cú phá — vai đầu vai ngược
        đã xác nhận cũng phá một mốc thật."""
        c = breakout_points(BoxFacts(), _pattern(name="Vai đầu vai ngược",
                                                 bars_since_break=3), 2.0)
        self.assertGreater(c.points, 0.0)
        self.assertIn("số thay thế", c.note)

    def test_con_trong_hop_thi_gan_nhu_khong_co_diem(self):
        inside = breakout_points(BoxFacts(state="inside", position_pct=40.0),
                                 _pattern(state="pending"), 1.0)
        self.assertEqual(inside.points, 0.0)
        near = breakout_points(BoxFacts(state="inside", position_pct=92.0),
                               _pattern(state="pending"), 1.0)
        self.assertGreater(near.points, 0.0)
        self.assertLess(near.points, 10.0)

    def test_khong_bao_gio_vuot_tran(self):
        c = breakout_points(
            BoxFacts(state="breakout_up_confirmed", breakout_volume_x=9.0,
                     bars_since_breakout=1, retest_held=True), _pattern(), 9.0)
        self.assertLessEqual(c.points, prospect.MAX_BREAKOUT)


class ValuationDirectionTest(unittest.TestCase):
    """Sai dấu ở đây làm cả cột đảo ngược mà không có gì báo."""

    @staticmethod
    def _fund(**pairs) -> Fundamentals:
        inds = {}
        for key, (value, industry) in pairs.items():
            key = {"pe": "P/E", "pb": "P/B", "roe": "ROE",
                   "margin": "%Lãi ròng"}[key]
            inds[key] = Indicator(key=key, name=key, group=1, value=value,
                                  industry=industry)
        return Fundamentals(symbol="AAA", snapshot_date="2026-09-10",
                            indicators=inds)

    def test_pe_thap_hon_nganh_la_diem_cong(self):
        cheap = self._fund(pe=(10.0, 20.0))
        rich = self._fund(pe=(30.0, 20.0))
        self.assertGreater(valuation_points(cheap).points, 0.0)
        self.assertLess(valuation_points(rich).points, 0.0)

    def test_roe_cao_hon_nganh_la_diem_cong(self):
        good = self._fund(roe=(30.0, 20.0))
        bad = self._fund(roe=(10.0, 20.0))
        self.assertGreater(valuation_points(good).points, 0.0)
        self.assertLess(valuation_points(bad).points, 0.0)

    def test_chua_co_anh_chup_thi_khong_phai_trung_tinh(self):
        c = valuation_points(None)
        self.assertEqual(c.points, 0.0)
        self.assertIn("chưa có ảnh chụp", c.note)


class InsiderPointsTest(unittest.TestCase):
    class _Flow:
        def __init__(self, ratio, empty=False, registered_only=False):
            self.net_ratio_pct = ratio
            self.is_empty = empty
            self.registered_only = registered_only
            self.label = "thử"

    def test_mua_rong_cong_ban_rong_tru(self):
        self.assertGreater(insider_points(self._Flow(0.4)).points, 0.0)
        self.assertLess(insider_points(self._Flow(-0.4)).points, 0.0)

    def test_dang_ky_chi_an_nua_trong_so(self):
        """Đăng ký là ý định, chưa phải sự thật."""
        done = insider_points(self._Flow(0.5)).points
        planned = insider_points(self._Flow(0.5, registered_only=True)).points
        self.assertAlmostEqual(planned, done / 2, places=5)

    def test_thieu_mau_so_thi_khong_cham(self):
        c = insider_points(self._Flow(None))
        self.assertEqual(c.points, 0.0)
        self.assertIn("chuẩn hoá", c.note)


class RelativeStrengthPointsTest(unittest.TestCase):
    def test_khoe_hon_thi_truong_va_nganh_deu_cong_diem(self):
        strong = rs_points(RelativeStrength(sessions=20, vs_market=10.0, vs_sector=10.0))
        weak = rs_points(RelativeStrength(sessions=20, vs_market=-10.0, vs_sector=-10.0))
        self.assertGreater(strong.points, 0.0)
        self.assertLess(weak.points, 0.0)

    def test_thieu_moc_thi_de_trong_chu_khong_cho_0_diem_am(self):
        c = rs_points(RelativeStrength(sessions=20))
        self.assertEqual(c.points, 0.0)
        self.assertIn("chưa so được", c.note)


class GatesTest(unittest.TestCase):
    def test_thanh_khoan_thap_bi_loai_khoi_danh_sach(self):
        thin = prospect.score_row(_row(avg_value_bn=5.0), min_liquidity_bn=20.0)
        self.assertEqual(thin.excluded, prospect.EX_LIQUIDITY)
        self.assertIn("5", thin.excluded_note)

    def test_thanh_khoan_du_thi_khong_bi_loai(self):
        ok = prospect.score_row(_row(avg_value_bn=100.0), min_liquidity_bn=20.0)
        self.assertEqual(ok.excluded, "")

    def test_mau_hinh_giam_da_xac_nhan_bi_loai(self):
        bear = prospect.score_row(
            _row(pattern=_pattern(bias="bearish", state="confirmed")))
        self.assertEqual(bear.excluded, prospect.EX_BEARISH)

    def test_khong_do_duoc_thanh_khoan_thi_khong_phai_dat_nguong(self):
        """Để lọt qua cửa là biến một khoảng trống dữ liệu thành lời xác nhận."""
        blind = prospect.score_row(_row(avg_value_bn=None), min_liquidity_bn=20.0)
        self.assertEqual(blind.excluded, prospect.EX_NO_DATA)

    def test_mau_hinh_giam_chua_xac_nhan_thi_chua_loai(self):
        """Bằng chứng chưa đủ thì chưa phải một kết luận."""
        row = prospect.score_row(
            _row(pattern=_pattern(bias="bearish", state="pending")))
        self.assertEqual(row.excluded, "")


class ScoreCompositionTest(unittest.TestCase):
    def test_tong_bang_dung_tong_cac_thanh_phan(self):
        row = prospect.score_row(_row())
        self.assertAlmostEqual(row.base_score,
                               sum(c.points for c in row.components), places=5)

    def test_tran_tong_dung_100(self):
        caps = (prospect.MAX_PATTERN + prospect.MAX_BREAKOUT + prospect.MAX_RSI
                + prospect.MAX_RS + prospect.MAX_VALUE + prospect.MAX_INSIDER)
        self.assertEqual(caps, 100.0)

    def test_diem_tin_khong_tron_vao_diem_do_duoc(self):
        row = prospect.score_row(_row())
        base = row.base_score
        row.news = NewsVerdict(score=12.0, label="tin tốt")
        self.assertEqual(row.base_score, base, "phần đo được không được đổi")
        self.assertAlmostEqual(row.total, base + 12.0, places=5)

    def test_chua_cham_tin_khac_cham_ra_khong(self):
        unscored = prospect.score_row(_row())
        scored = prospect.score_row(_row())
        scored.news = NewsVerdict(score=0.0, label="trung tính")
        self.assertFalse(unscored.news_scored)
        self.assertTrue(scored.news_scored)
        self.assertEqual(unscored.total, scored.total)   # cùng số…
        self.assertNotEqual(unscored.to_dict()["news"],  # …nhưng khác nghĩa
                            scored.to_dict()["news"])

    def test_diem_tin_bi_cat_tai_tran(self):
        v = NewsVerdict.from_dict({"score": 999})
        self.assertEqual(v.score, MAX_NEWS)
        v = NewsVerdict.from_dict({"score": -999})
        self.assertEqual(v.score, -MAX_NEWS)


class RoundTripTest(unittest.TestCase):
    def test_ghi_ra_json_roi_doc_lai_khong_mat_gi(self):
        row = prospect.score_row(_row(symbol="XYZ"))
        row.news = NewsVerdict(score=7.0, label="tin tốt", summary="abc",
                               good=["a"], bad=["b"], source="claude")
        row.sector = SectorView(sector="cntt", label="CNTT", n_rows=5,
                                comparable=True, breadth_up=60.0)
        board = ProspectBoard(as_of="2026-09-10", generated="2026-09-10 10:00",
                              universe="test", rows=[row])
        with tempfile.TemporaryDirectory() as tmp:
            path = prospect.save_json(board, out_dir=tmp)
            again = prospect.load_board(path)
        self.assertEqual(len(again.rows), 1)
        back = again.rows[0]
        self.assertEqual(back.symbol, "XYZ")
        self.assertAlmostEqual(back.base_score, row.base_score, places=5)
        self.assertAlmostEqual(back.total, row.total, places=5)
        self.assertEqual(back.news.source, "claude")
        self.assertEqual(back.sector.label, "CNTT")
        self.assertEqual(len(back.components), len(row.components))

    def test_bang_hoi_tuong_khong_dung_con_tro_cua_phien_that(self):
        board = ProspectBoard(as_of="2025-01-02", generated="x", universe="test",
                              as_of_requested="01/01/2025",
                              rows=[prospect.score_row(_row())])
        before = (prospect.LATEST_JSON.read_bytes()
                  if prospect.LATEST_JSON.is_file() else None)
        with tempfile.TemporaryDirectory() as tmp:
            prospect.save_json(board, out_dir=tmp)
        after = (prospect.LATEST_JSON.read_bytes()
                 if prospect.LATEST_JSON.is_file() else None)
        self.assertEqual(before, after)


class ShortlistTest(unittest.TestCase):
    def test_xep_theo_diem_do_duoc_chu_khong_theo_tong(self):
        """Dùng tổng điểm ở đây là để lượt trước quyết định lượt sau đọc gì."""
        low_base = prospect.score_row(_row(symbol="AAA", rsi=50.0))
        low_base.base_score = 30.0
        low_base.news = NewsVerdict(score=25.0)          # tổng 55
        high_base = prospect.score_row(_row(symbol="BBB", rsi=50.0))
        high_base.base_score = 50.0                       # tổng 50
        board = ProspectBoard(as_of="x", generated="y", universe="z",
                              rows=[low_base, high_base])
        picked = [r.symbol for r in prospect.shortlist(board, top=1)]
        self.assertEqual(picked, ["BBB"])


class VerdictParseTest(unittest.TestCase):
    def test_doc_duoc_ca_dang_dict_va_dang_mang(self):
        as_dict = verdict_mod.parse_verdicts('{"FPT": {"score": 5}}')
        as_list = verdict_mod.parse_verdicts('[{"symbol": "FPT", "score": 5}]')
        self.assertEqual(set(as_dict), {"FPT"})
        self.assertEqual(set(as_list), {"FPT"})

    def test_boc_duoc_json_trong_khoi_ma(self):
        raw = 'Đây là điểm:\n```json\n{"HPG": {"score": -3}}\n```\nxong.'
        parsed = verdict_mod.parse_verdicts(raw)
        self.assertEqual(parsed["HPG"]["score"], -3)

    def test_diem_vuot_tran_bi_cat(self):
        parsed = verdict_mod.parse_verdicts('{"FPT": {"score": 500}}')
        self.assertEqual(parsed["FPT"]["score"], verdict_mod.MAX_NEWS)

    def test_rac_thi_tra_rong_chu_khong_no(self):
        self.assertEqual(verdict_mod.parse_verdicts("không phải json"), {})

    def test_mac_dinh_ghi_nguon_la_claude(self):
        parsed = verdict_mod.parse_verdicts('{"FPT": {"score": 1}}')
        self.assertEqual(parsed["FPT"]["source"], verdict_mod.SRC_CLAUDE)


class VerdictStoreTest(unittest.TestCase):
    #: Ngày của bản nhận định phải bám theo *hôm nay*, không phải một ngày gõ
    #: cứng: `load_verdict` bỏ bản quá `max_age_days`, nên một ngày cố định biến
    #: hai test dưới đây thành bom hẹn giờ — chúng đỏ vào đúng ngày thứ 8 sau
    #: mốc đó, mà cái chúng kiểm lại không liên quan gì tới thời gian.
    TODAY = datetime.now().strftime("%Y-%m-%d")

    def test_ban_cua_claude_khong_bi_gemini_ghi_de(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            verdict_mod.save_verdict(
                "FPT", {"score": 10, "source": "claude", "as_of": self.TODAY}, root)
            written = verdict_mod.save_verdict(
                "FPT", {"score": -10, "source": "gemini:x", "as_of": self.TODAY}, root)
            self.assertIsNone(written, "Gemini không được đè bản đọc kỹ hơn")
            kept = verdict_mod.load_verdict("FPT", root=root)
            self.assertEqual(kept["score"], 10)

    def test_ban_cua_claude_de_duoc_ban_gemini(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            verdict_mod.save_verdict(
                "FPT", {"score": -10, "source": "gemini:x", "as_of": self.TODAY}, root)
            verdict_mod.save_verdict(
                "FPT", {"score": 10, "source": "claude", "as_of": self.TODAY}, root)
            self.assertEqual(verdict_mod.load_verdict("FPT", root=root)["score"], 10)

    def test_nhan_dinh_qua_cu_thi_khong_dung(self):
        """Điểm tin của tháng trước nói về những bài không còn liên quan."""
        from datetime import datetime
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            verdict_mod.save_verdict(
                "FPT", {"score": 20, "source": "claude", "as_of": "2026-01-01"}, root)
            fresh = verdict_mod.load_verdict(
                "FPT", as_of=datetime(2026, 1, 3), root=root)
            stale = verdict_mod.load_verdict(
                "FPT", as_of=datetime(2026, 3, 1), root=root)
            self.assertIsNotNone(fresh)
            self.assertIsNone(stale)

    def test_khong_doc_ban_muon_hon_moc(self):
        """Đọc nhận định của tương lai là đúng cái nhìn trước mà as_of chặn."""
        from datetime import datetime
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            verdict_mod.save_verdict(
                "FPT", {"score": 20, "source": "claude", "as_of": "2026-09-10"}, root)
            self.assertIsNone(verdict_mod.load_verdict(
                "FPT", as_of=datetime(2026, 9, 1), root=root))


if __name__ == "__main__":
    unittest.main()


class CoDoTest(unittest.TestCase):
    """Cờ đỏ là thành phần duy nhất có thể một mình quyết định thứ hạng."""

    @staticmethod
    def _flags(penalty, level=None, key="hinh_su", n=1):
        from src.news import redflag as rf

        out = rf.RedFlags(symbol="AAA", as_of="2026-09-10", penalty=penalty,
                          level=level or rf.level_for(penalty), n_scanned=50)
        out.flags = [rf.Flag(key=key, label="Hình sự",
                             title="AAA: Chủ tịch HĐQT bị khởi tố",
                             published="2026-08-01", score=penalty)
                     for _ in range(n)]
        return out

    def test_mau_hinh_dep_khong_bu_duoc_an_hinh_su(self):
        """+80 điểm mẫu hình mà dính khởi tố phải rơi xuống ~30, không phải 78."""
        sach = prospect.score_row(_row(rsi=50.0), redflags=self._flags(0.0))
        dinh_an = prospect.score_row(_row(rsi=50.0), redflags=self._flags(50.0))
        self.assertAlmostEqual(dinh_an.base_score, sach.base_score - 50.0, places=1)

    def test_diem_tru_luon_thao_ra_duoc_thanh_phan(self):
        scored = prospect.score_row(_row(), redflags=self._flags(50.0))
        comp = scored.component("redflag")
        self.assertEqual(comp.points, -50.0)
        # Điểm trừ phải truy được về một tiêu đề có thật, ngay trong `note`.
        self.assertIn("bị khởi tố", comp.note)

    def test_chua_quet_duoc_khac_da_quet_va_sach(self):
        """Hai trạng thái cùng 0 điểm, nhưng không được nói giống nhau."""
        chua_quet = prospect.score_row(_row(), redflags=None)
        da_quet = prospect.score_row(_row(), redflags=self._flags(0.0))
        self.assertEqual(chua_quet.component("redflag").points, 0.0)
        self.assertEqual(da_quet.component("redflag").points, 0.0)
        self.assertIn("chưa quét được", chua_quet.component("redflag").note)
        self.assertIn("không có cờ", da_quet.component("redflag").note)
        self.assertTrue(any("chưa quét được cờ đỏ" in w
                            for w in chua_quet.warnings))

    def test_co_hinh_su_len_thang_warnings(self):
        scored = prospect.score_row(_row(), redflags=self._flags(50.0))
        self.assertTrue(any("CỜ ĐỎ HÌNH SỰ" in w for w in scored.warnings))

    def test_co_do_song_qua_vong_ghi_va_doc_lai_json(self):
        scored = prospect.score_row(_row(), redflags=self._flags(45.0))
        again = ProspectRow.from_dict(json.loads(json.dumps(scored.to_dict())))
        self.assertIsNotNone(again.redflags)
        self.assertEqual(again.redflags.penalty, 45.0)
        self.assertEqual(again.redflags.flags[0].title,
                         "AAA: Chủ tịch HĐQT bị khởi tố")

    def test_ma_dinh_co_tut_duoi_ma_sach_co_diem_thap_hon(self):
        cao_nhung_dinh_co = prospect.score_row(
            _row(symbol="BBB", rsi=50.0), redflags=self._flags(50.0))
        thap_nhung_sach = prospect.score_row(
            _row(symbol="CCC", rsi=80.0, rvol=1.0,
                 pattern=_pattern(state="partial", confidence=40.0)),
            redflags=self._flags(0.0))
        board = ProspectBoard(as_of="2026-09-10", generated="", universe="all")
        board.rows = [cao_nhung_dinh_co, thap_nhung_sach]
        self.assertEqual(board.scored_rows[0].symbol, "CCC")
