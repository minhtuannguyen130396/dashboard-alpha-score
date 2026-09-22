"""Test nạp bài viết — nhận diện CBTT, khử trùng lặp, và kho. Không gọi mạng."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.news import store
from src.news.posts import (
    KIND_ANNOUNCE,
    KIND_RESULT,
    Post,
    dedupe,
    disclosure_kind,
    is_disclosure,
    parse_post,
    parse_posts,
    title_hash,
)


def _row(pid=1, title="Hòa Phát ký hợp đồng mới", when="2026-06-05T09:30:00+07:00",
         desc="Nội dung tóm tắt", source="CafeF", tagged=("HPG",)):
    return {
        "postID": pid, "title": title, "description": desc, "date": when,
        "postSource": {"name": source, "url": "https://cafef.vn/"},
        "postGroup": {"name": "Thị trường"},
        "taggedSymbols": [{"symbol": s} for s in tagged],
        "sentiment": 0, "isAIGenerated": False,
    }


# --- Nhận diện CBTT trong feed tin tức -------------------------------------

def test_tien_to_ma_nhan_dien_ban_cong_bo_dang_lai():
    assert is_disclosure("HPG: Báo cáo kết quả giao dịch cổ phiếu", "HPG") is True
    assert is_disclosure("Hòa Phát ký hợp đồng mới", "HPG") is False


def test_tien_to_ma_khac_khong_tinh_la_cbtt_cua_ma_nay():
    """Bài 'FPT: ...' xuất hiện trong feed HPG không phải công bố của HPG."""
    assert is_disclosure("FPT: Thông báo giao dịch cổ phiếu", "HPG") is False


def test_phan_biet_thong_bao_truoc_va_bao_cao_sau():
    """Hai loại này có ngày khác nhau và nghĩa khác hẳn — trộn là đo nhầm sự kiện."""
    assert disclosure_kind(
        "FPT: Thông báo giao dịch cổ phiếu ESOP của Người nội bộ") == KIND_ANNOUNCE
    assert disclosure_kind(
        "HPG: Báo cáo kết quả giao dịch cổ phiếu của người có liên quan") == KIND_RESULT


def test_bao_cao_ket_qua_thang_khi_tieu_de_khop_ca_hai_mau():
    """Tiêu đề chứa cả 'báo cáo kết quả' lẫn 'đăng ký mua' thì nghĩa là KẾT QUẢ."""
    title = ("HPG: Báo cáo kết quả giao dịch của người nội bộ "
             "đã đăng ký mua cổ phiếu")
    assert disclosure_kind(title) == KIND_RESULT


def test_tin_thuong_khong_bi_gan_nhan_cbtt():
    assert disclosure_kind("Hòa Phát và N&G đầu tư hai khu công nghiệp") is None
    assert disclosure_kind("") is None


def test_tin_bao_chi_ve_giao_dich_noi_bo_van_duoc_nhan_dien():
    """Không phải CBTT nhưng vẫn là tin về giao dịch nội bộ — vẫn cần bắt."""
    p = parse_post(_row(title="Lãnh đạo Hòa Phát muốn bán 6,6 triệu cổ phiếu HPG"), "HPG")
    assert p.is_disclosure is False        # không có tiền tố mã
    assert p.disclosure_kind == KIND_ANNOUNCE
    assert p.is_insider_news is True


# --- parse ----------------------------------------------------------------

def test_parse_lay_du_field_tu_list_khong_can_goi_detail():
    p = parse_post(_row(), "HPG")
    assert p.post_id == 1
    assert p.source == "CafeF"
    assert p.tagged_symbols == ["HPG"]
    assert p.body is None                  # toàn văn nạp lười


def test_bai_thieu_ngay_bi_bo():
    """Không có ngày thì vô dụng cho xếp lịch, as_of và đo phản ứng."""
    row = _row(); row["date"] = None
    assert parse_post(row, "HPG") is None


def test_bai_thieu_id_bi_bo():
    row = _row(); row["postID"] = None
    assert parse_post(row, "HPG") is None


# --- Khử trùng lặp --------------------------------------------------------

def test_tieu_de_lech_dau_cau_van_coi_la_mot_tin():
    """Báo VN chép chéo nhau; đếm số bài thô là thổi phồng mức độ chú ý."""
    a = title_hash("Hòa Phát ký hợp đồng mới!")
    b = title_hash("Hoa Phat ky hop dong moi")
    assert a == b


def test_dedupe_giu_ban_SOM_NHAT_khong_phai_moi_nhat():
    """Bản sớm nhất là bản gốc — và ngày đó mới là ngày tin ra thị trường."""
    early = parse_post(_row(pid=1, when="2026-06-05T09:00:00+07:00"), "HPG")
    late = parse_post(_row(pid=2, when="2026-06-07T09:00:00+07:00"), "HPG")
    kept = dedupe([late, early])
    assert len(kept) == 1
    assert kept[0].post_id == 1


def test_dedupe_giu_lai_cac_tin_khac_nhau():
    a = parse_post(_row(pid=1, title="Tin A"), "HPG")
    b = parse_post(_row(pid=2, title="Tin B"), "HPG")
    assert len(dedupe([a, b])) == 2


# --- Kho ------------------------------------------------------------------

@pytest.fixture
def db(tmp_path):
    return tmp_path / "posts.db"


def test_ghi_roi_doc_lai(db):
    items = parse_posts([_row(pid=1), _row(pid=2, title="Tin khac")], "HPG")
    with store.connect(db) as conn:
        assert store.upsert_posts(conn, items) == 2
        rows = store.load_posts(conn, "HPG")
    assert len(rows) == 2
    assert rows[0]["tagged_symbols"] == ["HPG"]


def test_insider_only_loc_dung_tap_de_ghep_voi_giao_dich(db):
    items = parse_posts([
        _row(pid=1, title="Hòa Phát ký hợp đồng mới"),
        _row(pid=2, title="HPG: Thông báo giao dịch cổ phiếu của Người nội bộ"),
    ], "HPG")
    with store.connect(db) as conn:
        store.upsert_posts(conn, items)
        rows = store.load_posts(conn, "HPG", insider_only=True)
    assert [r["post_id"] for r in rows] == [2]
    assert rows[0]["disclosure_kind"] == KIND_ANNOUNCE


def test_nap_lai_khong_xoa_mat_toan_van_da_ton_request_de_lay(db):
    """Nạp lười: lượt ghi sau để body=None, không được ghi đè lên body đã có."""
    item = parse_posts([_row(pid=1)], "HPG")[0]
    item.body = "<p>toàn văn đã tải</p>"
    with store.connect(db) as conn:
        store.upsert_posts(conn, [item])
    again = parse_posts([_row(pid=1)], "HPG")      # body=None
    with store.connect(db) as conn:
        store.upsert_posts(conn, again)
        row = store.load_posts(conn, "HPG")[0]
    assert row["body"] == "<p>toàn văn đã tải</p>"


def test_as_of_cat_bai_dang_sau_moc(db):
    items = parse_posts([
        _row(pid=1, when="2025-01-10T09:00:00+07:00"),
        _row(pid=2, title="Tin sau", when="2026-06-01T09:00:00+07:00"),
    ], "HPG")
    with store.connect(db) as conn:
        store.upsert_posts(conn, items)
        rows = store.load_posts(conn, "HPG", as_of="2025-06-01")
    assert [r["post_id"] for r in rows] == [1]


# --- Dương tính giả bắt được từ dữ liệu thật -------------------------------

def test_dang_ky_mua_NHA_khong_phai_giao_dich_co_phieu():
    """'HPG: Hòa Phát nhận hồ sơ đăng ký mua nhà ở xã hội' — đối tượng là nhà."""
    assert disclosure_kind(
        "HPG: Hòa Phát nhận hồ sơ đăng ký mua nhà ở xã hội tại Hưng Yên") is None


def test_quy_ETF_mua_ban_co_phieu_khong_phai_giao_dich_noi_bo():
    """Có 'cổ phiếu' nhưng chủ thể là quỹ, không phải người nội bộ."""
    assert disclosure_kind(
        "Fubon ETF dự kiến mua, bán cổ phiếu nào kỳ review tháng 9/2026?") is None


def test_phat_hanh_co_phieu_tra_co_tuc_khong_phai_giao_dich_noi_bo():
    assert disclosure_kind(
        "HPG: Báo cáo kết quả đợt phát hành cổ phiếu để trả cổ tức năm 2025") is None


def test_cac_ca_that_van_duoc_nhan_dien_sau_khi_siet_luat():
    """Siết luật không được làm mất những ca đúng đã quan sát trên dữ liệu thật."""
    assert disclosure_kind(
        "HPG: Báo cáo kết quả giao dịch cổ phiếu của người nội bộ Nguyễn Ngọc Quang"
    ) == KIND_RESULT
    assert disclosure_kind(
        "Thành viên HĐQT Hòa Phát muốn bán 6,6 triệu cổ phiếu") == KIND_ANNOUNCE
    assert disclosure_kind(
        "FPT: Thông báo giao dịch cổ phiếu ESOP của Người nội bộ") == KIND_ANNOUNCE
    assert disclosure_kind(
        "Vì sao con trai Chủ tịch Tập đoàn Hòa Phát không mua đủ số cổ phiếu như đăng ký?"
    ) == KIND_RESULT
