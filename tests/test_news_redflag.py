"""Cờ đỏ — phần lớn test ở đây là **dương tính giả đã bắt được trên kho thật**.

Mỗi ca trong ``test_khong_bat_nham_*`` từng là một cờ có thật do bộ luật gắn
sai, tìm ra bằng cách quét cả 57.928 bài rồi đếm từng cụm. Giữ chúng lại ở đây
vì một lexicon tiếng Việt bỏ dấu là thứ rất dễ vô tình nới rộng: thêm một cụm
trông vô hại như ``"an tu"`` là gắn cờ hình sự cho 1.532 nghị quyết tăng vốn.
"""
from datetime import datetime

import pytest

from src.news import redflag as rf


def _post(title, description="", date="2026-09-01T09:00:00+07:00",
          symbol="ABC", tagged=None, post_id=1, title_hash=None):
    return {
        "post_id": post_id, "symbol": symbol, "title": title,
        "description": description, "date": date,
        "source": "test", "source_url": "", "is_disclosure": 0,
        "tagged_symbols": tagged if tagged is not None else [symbol],
        "title_hash": title_hash or f"h{post_id}",
    }


AS_OF = datetime(2026, 9, 15)


# --- nhận diện ------------------------------------------------------------
@pytest.mark.parametrize("title,key", [
    ("ABC: Chủ tịch HĐQT bị khởi tố về tội thao túng thị trường", "hinh_su"),
    ("ABC: Tổng giám đốc bị bắt tạm giam", "hinh_su"),
    ("ABC: Chủ tịch bị cấm đi khỏi nơi cư trú", "hinh_su"),
    ("ABC: Nhận được quyết định xử phạt vi phạm hành chính về thuế", "che_tai"),
    ("ABC: Cổ phiếu bị đưa vào diện cảnh báo", "niem_yet"),
    ("ABC: Chậm thanh toán gốc lãi trái phiếu đến hạn", "no_nan"),
    ("ABC: Kiểm toán từ chối đưa ra ý kiến với báo cáo tài chính 2025", "kiem_toan"),
    ("ABC: Doanh nghiệp bác bỏ tin đồn liên quan lãnh đạo", "tin_don"),
    ("ABC: Báo lỗ quý 2, lợi nhuận lao dốc", "trien_vong"),
])
def test_bat_dung_nhom(title, key):
    matches = rf.classify(title)
    assert matches, f"không bắt được: {title}"
    assert matches[0][0].key == key


def test_bo_dau_nen_khop_ca_hai_kieu_go():
    """``huỷ`` và ``hủy`` là hai chuỗi Unicode khác nhau, cả hai đều có trong kho."""
    for spelling in ("ABC: Thông báo huỷ niêm yết cổ phiếu",
                     "ABC: Thông báo hủy niêm yết cổ phiếu"):
        assert rf.classify(spelling)[0][0].key == "niem_yet"


# --- dương tính giả đã gặp thật -------------------------------------------
@pytest.mark.parametrize("title", [
    # "an tu" ≡ "ần từ" — 1.532 bài, gần hết là nghị quyết tăng vốn
    "ABC: Báo cáo kết quả phát hành cổ phiếu để tăng vốn cổ phần từ NVCSH",
    # "nam tu" ≡ "năm từ" — 125 bài
    "ABC: Ông Trần Tấn Lộc tiếp tục làm Tổng Giám đốc thêm nhiệm kỳ 3 năm từ 2025",
    # "bi phat" ≡ "bị phát" (hành)
    "ABC: MBBank chuẩn bị phát hành 65 triệu cổ phiếu riêng lẻ",
    # "dung du an" ≡ "dựng dự án"
    "ABC: Quá trình hình thành và xây dựng dự án giai đoạn 1977 đến nay",
    # "no thue" ≡ "nợ thuê"
    "ABC: Lo nợ xấu, ngân hàng cũng sử dụng công cụ đòi nợ thuê?",
    # "bi bat" + "buộc"
    "ABC: Doanh nghiệp bị bắt buộc áp dụng chuẩn mực kế toán mới",
    # "thanh tra" ≡ tên người
    "ABC: Báo cáo kết quả giao dịch cổ phiếu của Người nội bộ Mai Trần Thanh Tran",
])
def test_khong_bat_nham_cum_trung_am(title):
    assert rf.classify(title) == [], f"bắt nhầm: {title}"


def test_phat_tu_khong_bi_doc_thanh_an_tu():
    """*"đề nghị xử phạt từ 2 - 3 tỷ"* là chế tài hành chính, không phải án tù.

    Bỏ dấu xong ``"phạt từ"`` trùng khít ``"phạt tù"``. Cờ đúng ở đây là
    ``che_tai`` (−25) chứ không phải ``hinh_su`` (−50) — sai bậc gấp đôi.
    """
    keys = [r.key for r, _ in rf.classify(
        "Bia Sài Gòn Việt Nam bị đề nghị xử phạt từ 2 - 3 tỷ đồng")]
    assert "hinh_su" not in keys
    assert "che_tai" in keys


@pytest.mark.parametrize("title", [
    "ABC: Ngân hàng cảnh báo 30 kịch bản lừa đảo trực tuyến phổ biến",
    "ABC: Được Bộ Công an trao Bằng khen vì thành tích xuất sắc",
    "ABC: Hoà Phát đề nghị điều tra thép Trung Quốc bán phá giá",
])
def test_vai_nan_nhan_hoac_nguyen_don_khong_thanh_co(title):
    """Cùng từ khoá, ngược vai — và ngược vai thì ngược nghĩa."""
    flags = rf.scan_rows("ABC", [_post(title)], AS_OF)
    assert not [f for f in flags if f.key in rf.SUBJECT_SENSITIVE]


# --- độ tin cậy -----------------------------------------------------------
def test_ban_cbtt_cua_chinh_ma_an_du_diem():
    flags = rf.scan_rows("ABC", [_post("ABC: Chủ tịch HĐQT bị khởi tố")], AS_OF)
    assert flags[0].confidence == 1.0
    assert flags[0].score == pytest.approx(50.0 * rf.decay_factor(flags[0].age_days))


def test_ma_co_chu_so_van_nhan_ra_tien_to():
    """``PC1``, ``SJ1``, ``TV2`` là mã thật — ``isalpha`` loại hết nhóm này."""
    assert rf._prefix_symbol("PC1: Chủ tịch bị bắt") == "PC1"
    flags = rf.scan_rows("PC1", [_post("PC1: Chủ tịch HĐQT bị bắt tạm giam",
                                       symbol="PC1", tagged=["PC1"])], AS_OF)
    assert flags[0].confidence == 1.0


def test_chu_the_nhan_vien_nhe_hon_chu_the_lanh_dao():
    lanh_dao = rf.scan_rows("ABC", [_post("ABC: Chủ tịch HĐQT chiếm đoạt tài sản")],
                            AS_OF)[0]
    nhan_vien = rf.scan_rows("ABC", [_post("ABC: Nhân viên chiếm đoạt 84 điện thoại")],
                             AS_OF)[0]
    assert nhan_vien.score < lanh_dao.score / 2


def test_bai_gan_nhieu_ma_van_giu_co_nhung_nhe_diem():
    """Không bỏ sót là luật cứng; điểm trừ mới là chỗ điều chỉnh."""
    flags = rf.scan_rows(
        "ABC", [_post("Khởi tố lãnh đạo loạt doanh nghiệp niêm yết",
                      tagged=["ABC", "DEF", "GHI", "JKL", "MNO"])], AS_OF)
    assert flags, "bài điểm tin vẫn phải hiện ra"
    assert flags[0].score < 20


def test_phu_dinh_lam_nhe_chu_khong_xoa_co():
    flags = rf.scan_rows(
        "ABC", [_post("ABC: Doanh nghiệp khẳng định chủ tịch không bị khởi tố")],
        AS_OF)
    assert flags and flags[0].softened
    assert flags[0].score < 50


# --- gộp điểm -------------------------------------------------------------
def test_mot_su_kien_duoc_dua_tin_nhieu_lan_khong_thanh_nhieu_su_kien():
    rows = [_post("ABC: Chủ tịch HĐQT bị khởi tố", post_id=i, title_hash="same")
            for i in range(8)]
    flags = rf.scan_rows("ABC", rows, AS_OF)
    assert len(flags) == 1


def test_nhieu_co_nho_khong_bang_mot_co_nang():
    nho = [rf.Flag(key="trien_vong", label="x", title="t", published="2026-09-01",
                   score=10.0) for _ in range(9)]
    nang = [rf.Flag(key="hinh_su", label="y", title="t", published="2026-09-01",
                    score=50.0)]
    assert rf.aggregate(nho) < rf.aggregate(nang)
    assert rf.aggregate(nang) == rf.MAX_PENALTY


def test_diem_tru_khong_vuot_tran():
    many = [rf.Flag(key="hinh_su", label="y", title=str(i), published="2026-09-01",
                    score=50.0) for i in range(5)]
    assert rf.aggregate(many) == rf.MAX_PENALTY


def test_co_cu_nhe_diem_hon_co_moi():
    assert rf.decay_factor(5) > rf.decay_factor(120) > rf.decay_factor(400)
    assert rf.decay_factor(400) > 0, "khởi tố không tự hết theo thời gian"


# --- mức cờ ---------------------------------------------------------------
def test_muc_co_theo_diem():
    assert rf.level_for(0.0) == rf.LEVEL_CLEAN
    assert rf.level_for(5.0) == rf.LEVEL_NOTE
    assert rf.level_for(20.0) == rf.LEVEL_WARN
    assert rf.level_for(45.0) == rf.LEVEL_CRITICAL


def test_rong_khac_chua_quet_duoc():
    """Hai trạng thái, hai câu chữ — gộp lại là nói về dữ liệu chưa tồn tại."""
    from src.news import format as news_format

    quet_sach = rf.RedFlags(symbol="ABC", as_of="2026-09-15", n_scanned=120)
    assert "Không có cờ nào" in news_format.format_redflags(quet_sach)
    assert "Chưa quét được" in news_format.format_redflags(None)


def test_khoi_chu_luon_mang_nguyen_van_tieu_de():
    """Người đọc phải bác được cái cờ bằng chính câu đã kích hoạt nó."""
    from src.news import format as news_format

    out = rf.RedFlags(symbol="ABC", as_of="2026-09-15", penalty=50.0,
                      level=rf.LEVEL_CRITICAL, n_scanned=10)
    out.flags = rf.scan_rows("ABC", [_post("ABC: Chủ tịch HĐQT bị khởi tố")], AS_OF)
    md = news_format.format_redflags(out)
    assert "ABC: Chủ tịch HĐQT bị khởi tố" in md
    assert "khoi to" in md          # cụm đã khớp, để bác lại được
