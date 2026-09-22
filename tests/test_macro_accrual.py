"""Tích luỹ điểm tin ngành — chấm nền bằng Gemini, và feature tin cơ học.

Hai nhánh của cùng một món nợ (H3 — *điểm tin có thêm gì ngoài các cột đo
được*), và chúng khác nhau ở một điểm quyết định:

* Điểm LLM **không backfill được**. Model chấm tin tháng 3 vào hôm nay đã biết
  thị trường đi đâu sau đó; ``as_of`` cắt được dữ liệu, không cắt được trí nhớ.
  Nên chỉ tích luỹ tiến — và nó chỉ tích luỹ nếu có cái gì chạy đều.
* Sắc thái FireAnt gán **lúc đăng** thì backfill được, vì nó tồn tại từ thời
  điểm bài ra. Kiểm được ngay.
"""
import json
from datetime import datetime

import pytest

from src.macro import gemini as gemini_mod
from src.macro import newsfeat as nf_mod
from src.macro import verdict as verdict_mod


def _verdict(code="60", as_of="2026-09-16", source="gemini:gemini-flash-latest",
             score=10.0):
    return verdict_mod.Verdict(code=code, as_of=as_of, source=source,
                               score=score, stance="tang_cho")


class TestNguonNhanDinh:
    def test_nhan_ra_ban_cua_gemini(self):
        assert gemini_mod.is_gemini("gemini:gemini-flash-latest")
        assert not gemini_mod.is_gemini("Claude Opus 5")
        assert not gemini_mod.is_gemini("")

    def test_ban_nguoi_viet_DE_ban_gemini(self, tmp_path):
        """Luật một chiều, kế thừa từ tầng mã.

        Một lượt chạy nền lúc 2 giờ sáng không được phép xoá nhận định mà người
        dùng vừa viết tay chiều hôm trước.
        """
        human = _verdict(source="Claude Opus 5", score=20.0)
        verdict_mod.save(human, root=tmp_path)

        assert gemini_mod._save_if_allowed(_verdict(score=-5.0),
                                           root=tmp_path) is False
        again = verdict_mod.load("60", datetime(2026, 9, 16), root=tmp_path)
        assert again.source == "Claude Opus 5"
        assert again.score == 20.0

    def test_gemini_de_len_gemini_cua_chinh_no(self, tmp_path):
        verdict_mod.save(_verdict(score=5.0), root=tmp_path)
        assert gemini_mod._save_if_allowed(_verdict(score=-8.0),
                                           root=tmp_path) is True
        again = verdict_mod.load("60", datetime(2026, 9, 16), root=tmp_path)
        assert again.score == -8.0

    def test_source_do_CODE_dat_khong_de_model_tu_khai(self):
        """Để model tự khai `source` là mở đường cho nó ký tên người khác.

        Luật "bản người viết đè bản Gemini" dựa vào chính trường này để biết
        được phép đè lên cái gì.
        """
        src = open("src/macro/gemini.py", encoding="utf-8").read()
        assert 'payload["source"] = f"{SOURCE_PREFIX}{model}"' in src


class TestChayNen:
    def test_hong_thi_tra_error_khong_tra_diem_0(self, monkeypatch):
        """0 = *đã đọc và thấy trung tính*; hỏng = *chưa đọc được*."""
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
        out = gemini_mod.score_one("60")
        assert out.error
        assert out.verdict is None
        assert not out.ok

    def test_khong_co_tin_thi_BO_QUA_khong_goi_model(self, monkeypatch):
        """Bắt model chấm một gói rỗng là mời nó dựng nhận định từ chỗ không có gì.

        Và nó sẽ làm, vì được yêu cầu.
        """
        monkeypatch.setenv("GEMINI_API_KEY", "x")
        ev = verdict_mod.SectorEvidence(code="60", name="Năng lượng",
                                        as_of="2026-09-16")
        monkeypatch.setattr(verdict_mod, "build_evidence",
                            lambda *a, **k: ev)
        called = []
        monkeypatch.setattr(gemini_mod, "_extract_json",
                            lambda *a: called.append(1))
        out = gemini_mod.score_one("60")
        assert out.skipped and "chưa chấm được" in out.skipped
        assert not called, "đã gọi model dù gói bằng chứng rỗng"

    def test_bao_cao_phan_biet_bo_qua_voi_loi(self):
        rows = [
            gemini_mod.Scored(code="60", name="Năng lượng",
                              verdict=_verdict()),
            gemini_mod.Scored(code="10", name="Công nghệ",
                              skipped="không có tin nào"),
            gemini_mod.Scored(code="15", name="Viễn thông", error="hết quota"),
        ]
        out = gemini_mod.format_run(rows)
        assert "1/3" in out
        assert "Không có tin" in out
        assert "hết quota" in out
        assert "chưa chấm được" in out

    def test_uu_tien_SDK_moi_vi_ban_cu_da_het_vong_doi(self):
        """Job này chạy không người trông suốt sáu tháng.

        SDK hỏng thì việc tích luỹ dừng **im lặng**, và H3 vĩnh viễn không kiểm
        được — đúng thứ cả nhánh này sinh ra để tránh.
        """
        src = open("src/macro/gemini.py", encoding="utf-8").read()
        assert "from google import genai" in src
        assert "google.generativeai as legacy" in src
        i_new = src.index("from google import genai")
        i_old = src.index("google.generativeai as legacy")
        assert i_new < i_old, "phải thử SDK mới trước"

    def test_ban_gemini_di_qua_CUNG_validator(self):
        """Miễn kiểm cho bản chạy nền là áp validator cho đúng những lượt ít
        cần nó nhất — lượt có người ngồi xem."""
        src = open("src/macro/gemini.py", encoding="utf-8").read()
        assert "verdict_mod.validate(payload, ev, day)" in src


class TestFeatureTinCoHoc:
    def test_duoi_nguong_bai_thi_khong_do_duoc(self):
        f = nf_mod.NewsFeature(code="60", session="2026-09-16", n_posts=2)
        assert not f.measured
        f.n_posts = nf_mod.MIN_POSTS
        assert f.measured

    def test_sac_thai_trong_khac_sac_thai_bang_0(self):
        """``None`` = FireAnt không gán; ``0`` = gán là trung tính."""
        from src.macro import feed as feed_mod
        a = feed_mod.MacroPost(1, 9, "Hàng hóa", "t", "", "2026-09-16")
        assert a.sentiment is None
        b = feed_mod.MacroPost(2, 9, "Hàng hóa", "t", "", "2026-09-16",
                               sentiment=0)
        assert b.sentiment == 0

    def test_do_GIA_TANG_ben_trong_tung_goc_RRG(self):
        """Đo một mình thì feature tin tương quan với giá sẽ trông như có tác
        dụng, trong khi nó chỉ lặp lại điều cột giá đã nói."""
        src = open("src/macro/newsfeat.py", encoding="utf-8").read()
        assert "quad[day]" in src, "phải phân tầng theo góc RRG"
        assert "fwd[::horizon]" in src, "phải dùng mẫu không chồng lấn"

    def test_dung_nguong_da_hieu_chinh_khong_dung_0_05(self):
        from src.macro import calibrate as cal
        src = open("src/macro/newsfeat.py", encoding="utf-8").read()
        assert "ALPHA_ADJUSTED" in src
        assert cal.ALPHA_ADJUSTED < 0.05

    def test_cot_gan_nhu_hang_so_bi_LOAI_khong_thanh_ket_qua_am_tinh(self):
        """`sentiment` của FireAnt: 53.996/53.998 bài bằng 0 — trường rỗng.

        Một cột như vậy chạy trót lọt qua mọi phép kiểm và trả về *"không tách
        được khỏi nền"* — đọc như **đã đo và thấy vô dụng**, trong khi sự thật
        là **chưa đo được gì**.

        Phép kiểm phương sai **không đủ**: đúng 2 bài khác 0 trong 54.000 là đủ
        để phương sai khác 0 và lọt qua. Phải đo theo tỷ lệ giá trị trội.
        """
        rows = {("sắc thái", "dan_dat"): [(0.0, 0.01)] * 250 + [(1.0, 0.02)],
                ("khối lượng tin", "dan_dat"): [(float(i), 0.01)
                                                for i in range(60)]}
        dead = nf_mod._constant_features(rows)
        assert "sắc thái" in dead
        assert "khối lượng tin" not in dead
        assert "99" in dead["sắc thái"], "lý do phải nói ra tỷ lệ trội"
        assert "chưa đo được" in dead["sắc thái"]

    def test_bao_cao_noi_ro_feature_nao_khong_do_duoc(self):
        rows = [nf_mod.Incremental(name="sắc thái", bucket="—",
                                   verdict="**chưa đo được** — trường rỗng"),
                nf_mod.Incremental(name="khối lượng tin", bucket="dẫn dắt",
                                   n_high=40, n_low=40, median_high=0.01,
                                   median_low=0.0, gap=0.01, p_value=0.4,
                                   verdict="không tách được khỏi nền")]
        out = nf_mod.format_h3(rows)
        assert "1 feature không đo được" in out
        assert "loại khỏi" in out.replace("**", "")

    def test_ket_luan_am_tinh_khong_duoc_noi_qua(self):
        """Sắc thái FireAnt là cờ thô; LLM đọc được thứ cờ đó không mã hoá nổi.

        Nên âm tính ở đây là *bằng chứng*, không phải *chứng minh*.
        """
        rows = [nf_mod.Incremental(name="sắc thái", bucket="dẫn dắt",
                                   n_high=50, n_low=50, median_high=0.001,
                                   median_low=0.0, gap=0.001, p_value=0.9,
                                   verdict="không tách được khỏi nền")]
        out = nf_mod.format_h3(rows)
        assert "bằng chứng" in out and "chứng minh" in out
        assert "không thay thế H3" in out


class TestLichChayTuan:
    def test_script_co_du_ba_phan_dong_bang(self):
        """Ba thứ không chạy lại được: BCTC ngành, chuỗi vĩ mô, điểm tin."""
        src = open("weekly_macro.bat", encoding="utf-8").read()
        for mod in ("src.macro.fundamentals", "src.macro.series",
                    "src.macro.gemini"):
            assert mod in src, f"thiếu {mod} trong nhịp tuần"

    def test_script_noi_ro_vi_sao_khong_backfill_duoc(self):
        src = open("weekly_macro.bat", encoding="utf-8").read()
        assert "backfill" in src.lower()
        assert "vinh vien" in src.lower()
