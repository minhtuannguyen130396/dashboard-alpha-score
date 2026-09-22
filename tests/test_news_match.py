"""Test ghép bài viết ↔ giao dịch nội bộ. Dữ liệu dựng tay, không gọi mạng.

Các ca dưới đây lấy nguyên từ dữ liệu thật của HPG — đó là lý do chúng đáng tin
hơn ví dụ tự nghĩ ra.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.news.match import (
    MIN_SCORE,
    effective_t0,
    find_announcement,
    match_symbol,
    name_matches,
    score_pair,
    volume_matches,
    volume_variants,
)
from src.news.posts import KIND_ANNOUNCE, KIND_RESULT


def _tx(tid=1, name="Nguyễn Ngọc Quang", reg=6_600_000.0, start="2026-06-11"):
    return {"transaction_id": tid, "name": name, "position": "Thành viên HĐQT",
            "registered_volume": reg, "execution_volume": reg,
            "start_date": f"{start}T00:00:00", "execution_date": f"{start}T00:00:00"}


def _post(pid=1, title="", when="2026-06-05", kind=KIND_ANNOUNCE, disc=True, desc=""):
    return {"post_id": pid, "title": title, "description": desc,
            "date": f"{when}T09:00:00+07:00",
            "disclosure_kind": kind, "is_disclosure": disc}


# --- Biến thể khối lượng --------------------------------------------------

def test_khoi_luong_le_viet_kieu_bao_chi():
    """6.600.000 xuất hiện là '6,6 triệu' — dấu phẩy thập phân kiểu Việt."""
    assert "6,6 trieu" in volume_variants(6_600_000)


def test_khoi_luong_tron_khong_co_phan_thap_phan():
    assert "50 trieu" in volume_variants(50_000_000)
    assert "50,0 trieu" not in volume_variants(50_000_000)


def test_khoi_luong_co_ca_dang_phan_nhom_dau_cham():
    assert "6.600.000" in volume_variants(6_600_000)


def test_khoi_luong_rong_hoac_0_khong_sinh_bien_the():
    assert volume_variants(None) == []
    assert volume_variants(0) == []


def test_volume_matches_tren_tieu_de_that():
    assert volume_matches(
        6_600_000, "Thành viên HĐQT Hòa Phát muốn bán 6,6 triệu cổ phiếu") is True
    assert volume_matches(
        6_600_000, "Hòa Phát ký hợp đồng cung cấp vỏ container") is False


# --- Khớp tên -------------------------------------------------------------

def test_ten_khop_du_tieu_de_khac_kieu_dau():
    assert name_matches(
        "Nguyễn Ngọc Quang",
        "HPG: Bao cao ket qua giao dich cua nguoi noi bo NGUYEN NGOC QUANG") is True


def test_ten_qua_ngan_khong_dung_de_khop():
    """Tên ngắn dễ trùng chuỗi con bừa — không đủ làm bằng chứng."""
    assert name_matches("Lê", "Công ty Lê Gia bán cổ phiếu") is False


def test_ten_khong_co_trong_bai_thi_khong_khop():
    assert name_matches(
        "Trần Vũ Minh", "Thành viên HĐQT Hòa Phát muốn bán 6,6 triệu cổ phiếu") is False


# --- Chấm điểm ------------------------------------------------------------

def test_cbtt_neu_dich_danh_ten_duoc_diem_cao_nhat():
    tx = _tx()
    post = _post(title="HPG: Thông báo giao dịch cổ phiếu của người nội bộ Nguyễn Ngọc Quang")
    score, reasons = score_pair(tx, post)
    assert score >= MIN_SCORE
    assert "tên người khớp" in reasons
    assert "bản CBTT đăng lại" in reasons


def test_bai_bao_khong_neu_ten_van_ghep_duoc_nho_khoi_luong():
    """Báo chí thường nêu số thay vì tên — khối lượng là bằng chứng độc lập."""
    tx = _tx()
    post = _post(pid=2, title="Thành viên HĐQT Hòa Phát muốn bán 6,6 triệu cổ phiếu",
                 disc=False)
    score, reasons = score_pair(tx, post)
    assert score >= MIN_SCORE
    assert "khối lượng khớp" in reasons


def test_bai_khong_lien_quan_khong_du_diem():
    tx = _tx()
    post = _post(title="Hòa Phát và N&G đầu tư hai khu công nghiệp", kind=None, disc=False)
    score, _ = score_pair(tx, post)
    assert score < MIN_SCORE


# --- Tìm bài công bố ------------------------------------------------------

def test_ghep_dung_cap_that_cua_HPG():
    """Ca thật: startDate 11/06/2026, công bố 05/06/2026 → lệch 6 ngày."""
    tx = _tx(start="2026-06-11")
    posts = [
        _post(pid=1, title="HPG: Thông báo giao dịch cổ phiếu của người nội bộ Nguyễn Ngọc Quang",
              when="2026-06-05"),
        _post(pid=2, title="Hòa Phát ký hợp đồng mới", when="2026-06-08",
              kind=None, disc=False),
    ]
    m = find_announcement(tx, posts)
    assert m is not None
    assert m.post_id == 1
    assert m.post_date == "2026-06-05"
    assert m.days_before_start == 6


def test_bai_ngoai_cua_so_thoi_gian_khong_duoc_ghep():
    """Bài cùng nội dung nhưng cách 6 tháng là tin của đợt giao dịch khác."""
    tx = _tx(start="2026-06-11")
    posts = [_post(title="HPG: Thông báo giao dịch cổ phiếu của người nội bộ Nguyễn Ngọc Quang",
                   when="2025-11-01")]
    assert find_announcement(tx, posts) is None


def test_bao_cao_ket_qua_khong_duoc_coi_la_thong_bao():
    """Báo cáo kết quả ra sau khi xong — không phải ngày công bố ý định."""
    tx = _tx(start="2026-06-11")
    posts = [_post(title="HPG: Báo cáo kết quả giao dịch cổ phiếu của người nội bộ Nguyễn Ngọc Quang",
                   when="2026-07-09", kind=KIND_RESULT)]
    assert find_announcement(tx, posts, allow_result_fallback=False) is None


def test_khong_co_thong_bao_thi_lui_ve_bao_cao_ket_qua_nhung_danh_dau_khac():
    """Nhiều bản ghi cũ chưa từng có thông báo trước (``registeredVolume=None``),
    nên bản tin kết quả là lần đầu thị trường biết. Vẫn dùng được làm mốc, nhưng
    phải mang nhãn khác vì nó đo *sự kiện khác*: xác nhận đã xong, không phải ý định."""
    tx = _tx(start="2026-06-11")
    posts = [_post(title="HPG: Báo cáo kết quả giao dịch cổ phiếu của người nội bộ Nguyễn Ngọc Quang",
                   when="2026-07-09", kind=KIND_RESULT)]
    m = find_announcement(tx, posts)
    assert m is not None and m.kind == KIND_RESULT
    t0, src = effective_t0(tx, m)
    assert t0 == "2026-07-09"
    assert src == "post_result_date"


def test_ten_khop_thi_ghep_du_bai_khong_duoc_gan_nhan_cbtt():
    """Ca thật của FPT: 'Lão tướng FPT Bùi Quang Ngọc bán xong 2 triệu cổ phiếu'
    không có từ chỉ chức vụ nên ``disclosure_kind`` bỏ qua — nhưng tên khớp."""
    tx = _tx(name="Bùi Quang Ngọc", reg=2_000_000.0, start="2025-02-06")
    posts = [_post(title='FPT: "Lão tướng" FPT Bùi Quang Ngọc bán xong 2 triệu cổ phiếu',
                   when="2025-02-17", kind=None, disc=True)]
    m = find_announcement(tx, posts)
    assert m is not None
    assert "tên người khớp" in m.reasons


def test_chi_khoi_luong_khop_ma_bai_khong_phai_tin_noi_bo_thi_khong_ghep():
    """'2 triệu' xuất hiện đầy trong tin thường ngày — một mình nó không đủ tin."""
    tx = _tx(name="Bùi Quang Ngọc", reg=2_000_000.0, start="2025-02-06")
    posts = [_post(title="Khối ngoại mua ròng 2 triệu cổ phiếu phiên hôm nay",
                   when="2025-02-05", kind=None, disc=False)]
    assert find_announcement(tx, posts) is None


def test_hai_bai_cung_diem_thi_chon_bai_SOM_HON():
    """CBTT ra trước, báo viết lại sau — ngày thị trường biết là ngày đầu tiên."""
    tx = _tx(start="2026-06-11")
    posts = [
        _post(pid=9, title="HPG: Lãnh đạo Hòa Phát muốn bán 6,6 triệu cổ phiếu Nguyễn Ngọc Quang",
              when="2026-06-06"),
        _post(pid=8, title="HPG: Thông báo giao dịch cổ phiếu của Nguyễn Ngọc Quang 6,6 triệu",
              when="2026-06-05"),
    ]
    m = find_announcement(tx, posts)
    assert m.post_id == 8


def test_khong_co_bai_nao_thi_tra_None_chu_khong_ghep_bua():
    """Ghép sai làm hỏng t0, mà t0 sai thì cả event study sai theo hướng khó thấy."""
    tx = _tx()
    assert find_announcement(tx, []) is None


# --- t0 hiệu dụng ---------------------------------------------------------

def test_co_bai_thi_t0_la_ngay_bai_va_nguon_duoc_ghi_ro():
    tx = _tx(start="2026-06-11")
    posts = [_post(title="HPG: Thông báo giao dịch cổ phiếu của người nội bộ Nguyễn Ngọc Quang",
                   when="2026-06-05")]
    m = find_announcement(tx, posts)
    t0, src = effective_t0(tx, m)
    assert t0 == "2026-06-05"
    assert src == "post_date"


def test_khong_co_bai_thi_lui_ve_start_date_va_khai_bao_la_thay_the():
    tx = _tx(start="2026-06-11")
    t0, src = effective_t0(tx, None)
    assert t0 == "2026-06-11"
    assert src == "start_date_proxy"


def test_match_symbol_tra_ve_map_theo_transaction_id():
    txs = [_tx(tid=1, start="2026-06-11"),
           _tx(tid=2, name="Không Ai Cả", reg=123.0, start="2020-01-01")]
    posts = [_post(title="HPG: Thông báo giao dịch cổ phiếu của người nội bộ Nguyễn Ngọc Quang",
                   when="2026-06-05")]
    out = match_symbol(txs, posts)
    assert set(out) == {1}


# --- Tích hợp với stats ---------------------------------------------------

def test_stats_dem_rieng_ca_ghep_duoc_va_ca_dung_moc_thay_the():
    """Đọc bảng base rate mà không biết bao nhiêu phần dùng mốc thật là đọc mù."""
    from src.news.stats import BucketStats, Distribution, format_stats
    b = BucketStats(label="nội bộ · mua · thực hiện đủ", n_events=40,
                    n_matched_t0=30, n_proxy_t0=10)
    b.car_immediate = Distribution.of([0.01] * 40)
    text = format_stats({b.label: b})
    assert "30/40" in text
    assert "thông báo" in text


def test_ngay_bao_cao_ket_qua_khong_bi_dem_thanh_moc_thay_the():
    """Ba nguồn mốc, ba ý nghĩa. Xếp ngày báo cáo kết quả chung với `startDate`
    là nói sai về chất lượng số liệu, và giấu mất chuyện một phần đang đo
    *xác nhận đã xong* chứ không phải *ý định*."""
    from src.news.stats import BucketStats, Distribution, format_stats
    b = BucketStats(label="nội bộ · mua · thực hiện đủ", n_events=40,
                    n_matched_t0=25, n_result_t0=15, n_proxy_t0=0)
    b.car_immediate = Distribution.of([0.01] * 40)
    text = format_stats({b.label: b})
    assert "25/40" in text
    assert "15 ngày **báo cáo kết quả**" in text
    assert "0 lùi về" in text
    assert "sự kiện khác" in text


def test_canh_bao_khi_phan_lon_van_la_moc_thay_the():
    from src.news.stats import BucketStats, Distribution, format_stats
    b = BucketStats(label="nội bộ · mua · thực hiện đủ", n_events=40,
                    n_matched_t0=5, n_proxy_t0=35)
    b.car_immediate = Distribution.of([0.01] * 40)
    text = format_stats({b.label: b})
    assert "⚠️" in text and "trung vị 6 ngày" in text


# --- Tên tổ chức: phần phân biệt được, không phải hình thức pháp lý --------

def test_ten_to_chuc_rut_duoc_tu_viet_tat():
    """Bản ghi ghi 'Công ty TNHH MTV Đầu tư SCIC', báo viết 'Thành viên SCIC'."""
    from src.news.match import name_variants
    assert "scic" in name_variants("Công ty TNHH MTV Đầu tư SCIC")


def test_to_chuc_khop_duoc_voi_tieu_de_that():
    assert name_matches(
        "Công ty TNHH MTV Đầu tư SCIC",
        "Thành viên SCIC không mua hết lượng cổ phiếu FPT đã đăng ký") is True


def test_bo_hinh_thuc_phap_ly_giu_phan_loi():
    from src.news.match import name_variants
    assert "platinum victory" in name_variants("Platinum Victory PTE.Ltd")


def test_viet_tat_qua_pho_thong_khong_dung_lam_khoa():
    """'TNHH', 'MTV', 'PTE' có ở hàng nghìn tên — khớp bằng chúng là khớp bừa."""
    from src.news.match import name_variants
    v = name_variants("Công ty TNHH MTV Đầu tư SCIC")
    assert "tnhh" not in v and "mtv" not in v


def test_ten_nguoi_khong_bi_anh_huong_boi_luat_to_chuc():
    assert name_matches("Nguyễn Ngọc Quang",
                        "HPG: ... của người nội bộ Nguyễn Ngọc Quang") is True


def test_to_chuc_khong_khop_bai_khong_lien_quan():
    assert name_matches("Công ty TNHH MTV Đầu tư SCIC",
                        "Hòa Phát ký hợp đồng cung cấp vỏ container") is False
