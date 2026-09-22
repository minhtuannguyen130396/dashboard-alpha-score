"""Đầu mục tin tức + trạng thái "đã vào giá chưa".

Bốn nhóm test, mỗi nhóm chặn một lỗi đã suýt xảy ra khi dựng module:

1. ``effective_session`` — ranh giới 14:45 và ngày nghỉ. Đây là chỗ sai âm thầm
   nhất: lấy ngày đăng làm ``t0`` cho một bài đăng 21:00 là so tin với giá đóng
   cửa đã chốt *trước khi tin tồn tại*, và sai lệch đó một chiều.
2. ``classify_status`` — thang trạng thái, dựng từ ``Reaction`` tay nên không
   phụ thuộc dữ liệu trên đĩa.
3. ``classify_post`` — ba ca dương tính giả thật đã bắt được từ kho.
4. ``as_of`` — không rò rỉ phiên tương lai vào phép đo.
"""
from datetime import datetime

import pytest

from src.news import digest as dg
from src.news.reaction import Reaction

# 20/08 … 07/09/2026. Có khoảng nghỉ Quốc khánh thật: sau 28/08 nhảy thẳng
# sang 03/09 — dùng luôn để test ánh xạ qua kỳ nghỉ dài.
SESSIONS = ["2026-08-20", "2026-08-21", "2026-08-24", "2026-08-25",
            "2026-08-26", "2026-08-27", "2026-08-28", "2026-09-03",
            "2026-09-04", "2026-09-07"]


# --- 1. Ánh xạ ngày đăng → phiên bị ảnh hưởng ----------------------------

def test_bai_dang_truoc_gio_dong_cua_thuoc_ve_chinh_phien_do():
    assert dg.effective_session("2026-08-25T09:30:00+07:00", SESSIONS) \
        == "2026-08-25"


def test_ranh_gioi_1445_dung_o_dung_mot_phut():
    """14:44 còn kịp vào phiên; 14:45 là hết ATC nên phải sang phiên sau.

    Sai một phút ở đây thì mọi bài đăng đúng giờ đóng cửa bị đo ngược.
    """
    assert dg.effective_session("2026-08-25T14:44:00+07:00", SESSIONS) \
        == "2026-08-25"
    assert dg.effective_session("2026-08-25T14:45:00+07:00", SESSIONS) \
        == "2026-08-26"


def test_bai_dang_toi_muon_thuoc_ve_phien_hom_sau():
    assert dg.effective_session("2026-08-25T21:28:00+07:00", SESSIONS) \
        == "2026-08-26"


def test_bai_dang_ngay_nghi_nhay_qua_ca_ky_nghi():
    """Chủ nhật 30/08 + nghỉ Quốc khánh → phiên sớm nhất là 03/09.

    Không được rơi vào 28/08: phiên đó đóng cửa *trước* khi bài ra.
    """
    assert dg.effective_session("2026-08-30T10:25:00+07:00", SESSIONS) \
        == "2026-09-03"


def test_tin_ra_sau_phien_cuoi_thi_khong_co_phien():
    """``None`` là một câu trả lời ("chưa có gì để đo"), không phải lỗi."""
    assert dg.effective_session("2026-09-07T18:00:00+07:00", SESSIONS) is None


def test_ngay_khong_doc_duoc_thi_tra_none_chu_khong_no():
    assert dg.effective_session("", SESSIONS) is None
    assert dg.effective_session("không phải ngày", SESSIONS) is None


def test_khong_doi_mui_gio():
    """+07:00 là giờ sàn. Quy về UTC là đẩy bài 21:00 lùi về 14:00 cùng ngày —
    đúng vào vùng còn khớp lệnh, tức là đảo ngược kết luận."""
    assert dg.effective_session("2026-08-25T21:00:00+07:00", SESSIONS) \
        == "2026-08-26"


# --- 2. Thang trạng thái -------------------------------------------------

def _reaction(pre=0.0, imm=0.0, post=0.0, beta=1.0) -> Reaction:
    return Reaction(symbol="X", t0_requested="2026-08-20",
                    t0_actual="2026-08-20", benchmark="VNINDEX",
                    n_est_bars=120, alpha=0.0, beta=beta,
                    car_pre=pre, car_immediate=imm, car_post=post)


def test_khong_co_phien_thi_chua_co_gi_de_do():
    assert dg.classify_status(None, -1) == dg.ST_NO_SESSION


def test_moi_mot_phien_thi_chua_du_cua_so_tuc_thi():
    """t0 đã đóng nhưng chưa có t+1 — cửa sổ tức thì là AR[t0]+AR[t+1]."""
    assert dg.classify_status(_reaction(imm=0.09), 0) == dg.ST_FRESH


def test_phan_ung_tuc_thi_vuot_nguong_thi_da_vao_gia():
    assert dg.classify_status(_reaction(imm=0.05), 3) == dg.ST_PRICED_IN
    assert dg.classify_status(_reaction(imm=-0.05), 3) == dg.ST_PRICED_IN


def test_tuc_thi_xet_truoc_ro_ri():
    """Cả hai cửa sổ đều lớn thì cái đáng gọi tên là phản ứng *tại* tin.

    Đảo thứ tự thì mọi tin ra sau một nhịp tăng đều bị dán nhãn "chạy trước tin".
    """
    assert dg.classify_status(_reaction(pre=0.08, imm=0.05), 3) \
        == dg.ST_PRICED_IN


def test_bien_dong_nam_truoc_tin_thi_goi_dung_ten():
    assert dg.classify_status(_reaction(pre=0.06, imm=0.01), 3) \
        == dg.ST_RAN_BEFORE


def test_chua_du_10_phien_thi_khong_ket_luan_phan_troi():
    """Cửa sổ trôi cần 10 phiên. Kết luận "chưa phản ứng" khi mới 4 phiên là
    phát biểu về dữ liệu chưa tồn tại."""
    assert dg.classify_status(_reaction(post=0.09), 4) == dg.ST_TOO_EARLY


def test_du_10_phien_va_troi_tiep():
    assert dg.classify_status(_reaction(post=0.06), 10) == dg.ST_DRIFTING


def test_du_10_phien_ma_khong_cua_so_nao_vuot_thi_chua_phan_ung():
    assert dg.classify_status(_reaction(pre=0.005, imm=0.004, post=0.01), 12) \
        == dg.ST_NO_REACT


def test_khong_uoc_luong_duoc_beta_thi_noi_thang_la_khong_do_duoc():
    """Không được lẫn với "chưa phản ứng" — một cái là thiếu dữ liệu, cái kia
    là đã đo và thấy phẳng."""
    r = _reaction(beta=None)
    assert dg.classify_status(r, 12) == dg.ST_UNMEASURABLE


def test_nguong_nam_tren_nen_placebo():
    """§8b: trung vị placebo −0,33%. Ngưỡng phải xa hẳn vùng đó, nếu không thì
    nhiễu nền bị đọc thành phản ứng."""
    assert dg.BIG_MOVE >= 0.02
    assert dg.classify_status(_reaction(imm=-0.004), 12) == dg.ST_NO_REACT


# --- 3. Phân nhóm bằng chứng --------------------------------------------

def test_bai_gan_nhan_cbtt_noi_bo_len_nhom_cbtt():
    row = {"disclosure_kind": "thong_bao_giao_dich", "tagged_symbols": []}
    assert dg.classify_post(row) == dg.GROUP_DISCLOSURE


def test_tien_to_ma_len_nhom_cbtt():
    row = {"is_disclosure": 1, "tagged_symbols": ["FPT"]}
    assert dg.classify_post(row) == dg.GROUP_DISCLOSURE


def test_bai_gan_it_ma_la_tin_doanh_nghiep():
    row = {"tagged_symbols": ["FPT"]}
    assert dg.classify_post(row) == dg.GROUP_COMPANY


def test_diem_tin_gan_nhieu_ma_la_tin_nganh():
    """Bài gắn 10 mã không nói gì riêng về một mã. Đo nó như tin riêng là đọc
    nhiễu thành tín hiệu — ca thật: bài SCIC thoái vốn gắn 10 mã."""
    row = {"tagged_symbols": [f"M{i}" for i in range(10)]}
    assert dg.classify_post(row) == dg.GROUP_SECTOR


def test_evidence_noi_ra_vi_sao_vao_nhom_do():
    """Nhãn không được im lặng: người đọc phải bác được nó."""
    ev = dg._post_evidence({"disclosure_kind": "bao_cao_ket_qua",
                            "tagged_symbols": ["A"] * 9})
    assert any("báo cáo kết quả" in e for e in ev)
    assert any("9 mã" in e for e in ev)


# --- 4. Gom theo phiên, và as_of -----------------------------------------

def test_phien_toan_tin_nganh_thi_khong_do():
    """Một phiên chỉ có điểm tin thị trường không được mang abnormal return."""
    node = dg.SessionNews(session="2026-08-20", items=[
        dg.NewsItem(title="điểm tin", published="2026-08-20", session="2026-08-20",
                    group=dg.GROUP_SECTOR),
    ])
    assert node.top_group == dg.GROUP_SECTOR


def test_phien_co_mot_tin_doanh_nghiep_thi_van_do():
    """Lẫn tin ngành không làm mất quyền đo — miễn là có ít nhất một tin riêng."""
    node = dg.SessionNews(session="2026-08-20", items=[
        dg.NewsItem(title="điểm tin", published="2026-08-20",
                    session="2026-08-20", group=dg.GROUP_SECTOR),
        dg.NewsItem(title="tin của mã", published="2026-08-20",
                    session="2026-08-20", group=dg.GROUP_COMPANY),
    ])
    assert node.top_group == dg.GROUP_COMPANY


def test_measure_ton_trong_as_of_khong_doc_gia_tuong_lai():
    """``measure`` mặc định nạp tới ``t0 + 40 ngày``. Không cắt thì hồ sơ hồi
    tưởng kết luận "đã vào giá" bằng những phiên chưa xảy ra tại mốc đó."""
    from src.news import reaction as rx
    t0 = "2026-08-06"
    full = rx.measure("FPT", t0)
    cut = rx.measure("FPT", t0, as_of=datetime(2026, 8, 12))
    if full.beta is None:
        pytest.skip("không đủ dữ liệu giá FPT để đo")
    assert full.car_post is not None
    # Cắt ở 12/08 thì cửa sổ +10 phiên không thể đầy.
    assert cut.incomplete
    assert full.ar.keys() > cut.ar.keys()


# --- tin tiêu biểu --------------------------------------------------------
def _day(session, status, items, imm=None, post=None):
    react = None
    if imm is not None or post is not None:
        react = _reaction(imm=imm or 0.0, post=post or 0.0)
    return dg.SessionNews(session=session, items=list(items), status=status,
                          sessions_after=12, reaction=react)


def _item(title, group=dg.GROUP_COMPANY, tagged=1, published="2026-08-20"):
    return dg.NewsItem(title=title, published=published, session=published,
                       group=group, tagged_count=tagged)


def _digest(days):
    return dg.NewsDigest(symbol="X", session_from=days[0].session,
                         session_to=days[-1].session, sessions=20,
                         days=list(days),
                         n_items=sum(len(d.items) for d in days))


def test_tin_tieu_bieu_xep_theo_do_lon_phan_ung():
    """Xếp theo phép ĐO, không theo ngày và cũng không theo nội dung bài."""
    d = _digest([
        _day("2026-08-10", dg.ST_PRICED_IN, [_item("nhỏ")], imm=0.035),
        _day("2026-08-20", dg.ST_DRIFTING, [_item("lớn")], imm=0.0, post=0.09),
    ])
    picks = dg.highlights(d)
    assert [h.title for h in picks] == ["lớn", "nhỏ"]


def test_phien_chua_do_duoc_khong_vao_tin_tieu_bieu():
    """Nêu một đầu mục 'tiêu biểu' dựa trên cửa sổ chưa đầy là nói về dữ liệu
    chưa tồn tại — đúng luật 'chưa đo được ≠ đã đo và thấy phẳng'."""
    d = _digest([
        _day("2026-08-19", dg.ST_TOO_EARLY, [_item("mới ra")], imm=0.01),
        _day("2026-08-20", dg.ST_FRESH, [_item("hôm qua")]),
    ])
    assert dg.highlights(d) == []


def test_phien_do_xong_thay_phang_khong_phai_tieu_bieu():
    """``chưa phản ứng`` là kết luận thật, nhưng một tin không làm giá nhúc
    nhích thì không phải *tin tiêu biểu*."""
    d = _digest([_day("2026-08-20", dg.ST_NO_REACT, [_item("im")], imm=0.001)])
    assert dg.highlights(d) == []


def test_tin_nganh_khong_duoc_neu_lam_tin_tieu_bieu():
    """Bài gắn cả rổ không nói gì riêng về mã này — quy CAR cho nó là đọc nhiễu."""
    d = _digest([_day("2026-08-20", dg.ST_PRICED_IN,
                      [_item("điểm tin cả rổ", group=dg.GROUP_SECTOR, tagged=15)],
                      imm=0.06)])
    assert dg.highlights(d) == []


def test_dai_dien_phien_uu_tien_cbtt_roi_toi_bai_gan_it_ma():
    d = _digest([_day("2026-08-20", dg.ST_PRICED_IN, [
        _item("điểm tin ngành", group=dg.GROUP_SECTOR, tagged=12),
        _item("bài thường", group=dg.GROUP_COMPANY, tagged=2),
        _item("CBTT", group=dg.GROUP_DISCLOSURE, tagged=1),
    ], imm=0.05)])
    assert dg.highlights(d)[0].title == "CBTT"


def test_phien_nhieu_dau_muc_phai_noi_ra_so_luong():
    """Không nói ra thì người đọc đọc thành 'tin này làm giá chạy 5%' — một
    quan hệ nhân quả mà phép đo này không phân giải nổi."""
    from src.news import format as nf

    d = _digest([_day("2026-08-20", dg.ST_PRICED_IN,
                      [_item("a"), _item("b"), _item("c")], imm=0.05)])
    assert dg.highlights(d)[0].n_items == 3
    md = nf.format_highlights(d)
    assert "3 đầu mục" in md


def test_khoi_tin_tieu_bieu_rong_van_noi_ro_vi_sao():
    from src.news import format as nf

    d = _digest([_day("2026-08-20", dg.ST_TOO_EARLY, [_item("a")], imm=0.001)])
    md = nf.format_highlights(d)
    assert "chưa phiên nào đo được" in md
    assert "chưa đo được" in nf.format_highlights(None)
