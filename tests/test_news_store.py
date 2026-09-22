"""Test tầng tin tức — parse, kho, và bộ lọc as_of. Không gọi mạng."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.news import store
from src.news.models import PURCHASED, SOLD, SRC_SWAGGER
from src.news.parse import (
    parse_holder_transaction,
    parse_holder_transactions,
    parse_mark_title,
    parse_timescale_mark,
)


# --- Fixture: đúng hình dạng payload FireAnt trả về -------------------------

def _tx(tid=1, type_=PURCHASED, reg=2_000_000.0, ex=250_000.0,
        position=None, name="Công ty TNHH MTV Đầu tư SCIC"):
    return {
        "transactionID": tid, "symbol": "FPT", "name": name,
        "position": position, "type": type_,
        "registeredVolume": reg, "executionVolume": ex,
        "startDate": "2026-03-01T00:00:00", "endDate": "2026-03-30T00:00:00",
        "executionDate": "2026-03-26T00:00:00",
        "majorHolderID": 10, "individualHolderID": None,
        "institutionHolderID": 5, "isOrganization": True,
    }


# --- parse: chiều giao dịch -----------------------------------------------

def test_direction_lay_tu_enum_swagger_khong_phai_suy_doan():
    tx = parse_holder_transaction(_tx(type_=SOLD), "FPT")
    assert tx.direction == SOLD
    assert tx.direction_source == SRC_SWAGGER


def test_dong_thieu_type_bi_bo_vi_khong_biet_chieu():
    row = _tx()
    row["type"] = None
    assert parse_holder_transaction(row, "FPT") is None
    assert parse_holder_transactions([row, _tx(tid=2)], "FPT") == [
        parse_holder_transaction(_tx(tid=2), "FPT")
    ]


def test_position_phan_biet_noi_bo_voi_co_dong_lon():
    insider = parse_holder_transaction(
        _tx(position="Phó Chủ tịch HĐQT", name="Bùi Quang Ngọc"), "FPT")
    holder = parse_holder_transaction(_tx(), "FPT")
    assert insider.is_insider is True
    assert holder.is_insider is False


# --- parse: tỷ lệ thực hiện, và chỗ None khác 0 ----------------------------

def test_ty_le_thuc_hien():
    tx = parse_holder_transaction(_tx(reg=2_000_000.0, ex=250_000.0), "FPT")
    assert tx.execution_rate == pytest.approx(0.125)


def test_dang_ky_roi_khong_lam_la_0_phan_tram():
    tx = parse_holder_transaction(_tx(reg=2_000_000.0, ex=0.0), "FPT")
    assert tx.execution_rate == 0.0


def test_khong_co_dang_ky_thi_ty_le_la_None_khong_phai_0():
    """Bản ghi cũ chưa bắt buộc đăng ký trước — 'không đo được' khác 'không làm'."""
    tx = parse_holder_transaction(_tx(reg=None, ex=7_100.0), "FPT")
    assert tx.execution_rate is None


def test_t0_dung_start_date_va_khai_bao_la_moc_thay_the():
    tx = parse_holder_transaction(_tx(), "FPT")
    assert tx.t0.startswith("2026-03-01")
    assert tx.t0_source == "start_date_proxy"


# --- parse: chuỗi title của timescale-marks -------------------------------

def test_parse_title_bctc_rut_duoc_doanh_thu_va_yoy():
    p = parse_mark_title(
        "BCTC quý 4/2025|DT: 20.225,5 tỷ, +14,9% (vs. Q4/24)"
        "|LN: 2.502,7 tỷ, +19,9% (vs. Q4/24)")
    assert p["year"] == 2025 and p["quarter"] == 4
    assert p["doanh_thu_ty"] == pytest.approx(20225.5)
    assert p["doanh_thu_yoy_pct"] == pytest.approx(14.9)
    assert p["loi_nhuan_ty"] == pytest.approx(2502.7)


def test_parse_title_co_tuc_rut_duoc_ngay_gdkhq():
    p = parse_mark_title(
        "Cổ tức đợt 2/2025 bằng tiền, tỷ lệ 1.000đ/CP|Ngày KHQ: 28/05/2026")
    assert p["ngay_gdkhq"] == "28/05/2026"
    assert p["co_tuc_tien_dong"] == pytest.approx(1000.0)


def test_parse_title_bctc_nam():
    p = parse_mark_title("BCTC năm 2025|DT: 70.112,8 tỷ, +11,6% (vs. 2024)")
    assert p["year"] == 2025 and p["quarter"] == 0


def test_title_la_lung_thi_tra_dict_rong_chu_khong_no():
    """Format do FireAnt viết cho người đọc — đổi lúc nào không báo. Không được ném lỗi."""
    assert parse_mark_title("một chuỗi hoàn toàn khác") == {}
    assert parse_mark_title("") == {}


def test_raw_title_luon_duoc_giu_ben_canh_ban_parse():
    title = "BCTC quý 2/2026|DT: 13.788,5 tỷ, -18,9% (vs. Q2/25)"
    mark = parse_timescale_mark(
        {"id": "F_2026_2", "label": "F", "date": "2026-07-29T00:00:00",
         "title": title, "color": "#00C800"}, "FPT")
    assert mark.raw_title == title
    assert mark.kind == "bctc"
    assert mark.parsed["doanh_thu_yoy_pct"] == pytest.approx(-18.9)


# --- kho ------------------------------------------------------------------

@pytest.fixture
def db(tmp_path):
    return tmp_path / "test_index.db"


def test_upsert_roi_doc_lai_ra_dung_so(db):
    txs = parse_holder_transactions([_tx(tid=1), _tx(tid=2, type_=SOLD)], "FPT")
    with store.connect(db) as conn:
        assert store.upsert_holder_transactions(conn, txs) == 2
    with store.connect(db) as conn:
        rows = store.load_holder_transactions(conn, "FPT")
    assert len(rows) == 2
    assert {r["direction"] for r in rows} == {PURCHASED, SOLD}


def test_chay_lai_ingest_khong_nhan_doi_ban_ghi(db):
    txs = parse_holder_transactions([_tx(tid=1)], "FPT")
    for _ in range(3):
        with store.connect(db) as conn:
            store.upsert_holder_transactions(conn, txs)
    with store.connect(db) as conn:
        assert len(store.load_holder_transactions(conn, "FPT")) == 1


def test_first_seen_khong_bi_ghi_de_khi_cap_nhat(db):
    with store.connect(db) as conn:
        store.upsert_holder_transactions(
            conn, parse_holder_transactions([_tx(tid=1, ex=0.0)], "FPT"))
        first = store.load_holder_transactions(conn, "FPT")[0]["first_seen"]
        # lần sau API trả về bản đã thực hiện
        store.upsert_holder_transactions(
            conn, parse_holder_transactions([_tx(tid=1, ex=250_000.0)], "FPT"))
        row = store.load_holder_transactions(conn, "FPT")[0]
    assert row["first_seen"] == first
    assert row["execution_volume"] == 250_000.0


def test_registered_volume_None_khong_bi_bien_thanh_0_khi_qua_kho(db):
    with store.connect(db) as conn:
        store.upsert_holder_transactions(
            conn, parse_holder_transactions([_tx(tid=9, reg=None)], "FPT"))
        row = store.load_holder_transactions(conn, "FPT")[0]
    assert row["registered_volume"] is None


def test_as_of_cat_su_kien_sau_moc(db):
    early = _tx(tid=1); early["startDate"] = "2025-01-10T00:00:00"
    late = _tx(tid=2);  late["startDate"] = "2026-06-01T00:00:00"
    with store.connect(db) as conn:
        store.upsert_holder_transactions(
            conn, parse_holder_transactions([early, late], "FPT"))
        rows = store.load_holder_transactions(conn, "FPT", as_of="2025-06-01")
    assert [r["transaction_id"] for r in rows] == [1]


def test_backfill_van_hoi_tuong_duoc_first_seen_khong_chan_mac_dinh(db):
    """Nạp lịch sử hôm nay vẫn phải replay được quá khứ.

    Đây là chỗ thiết kế đầu tiên sai: lọc theo ``first_seen`` mặc định thì mọi
    backfill thành vô dụng và phần hiệu chuẩn base rate (§8) chết theo. Với dữ
    liệu có cấu trúc bất biến, ngày sự kiện mới là mốc đúng.
    """
    old_event = _tx(tid=1)
    old_event["startDate"] = "2020-01-01T00:00:00"
    with store.connect(db) as conn:
        store.upsert_holder_transactions(
            conn, parse_holder_transactions([old_event], "FPT"))
        rows = store.load_holder_transactions(conn, "FPT", as_of="2021-01-01")
    assert [r["transaction_id"] for r in rows] == [1]


def test_strict_first_seen_bat_len_thi_moi_chan_theo_ngay_nap(db):
    """Chế độ chặt vẫn phải dùng được khi muốn mô phỏng 'kho lúc đó có gì'."""
    old_event = _tx(tid=1)
    old_event["startDate"] = "2020-01-01T00:00:00"
    with store.connect(db) as conn:
        store.upsert_holder_transactions(
            conn, parse_holder_transactions([old_event], "FPT"))
        rows = store.load_holder_transactions(
            conn, "FPT", as_of="2021-01-01", strict_first_seen=True)
    assert rows == []


def test_marks_luu_va_doc_lai_ca_phan_parse(db):
    marks = [parse_timescale_mark(
        {"id": "D_1", "label": "D", "date": "2026-05-28T00:00:00",
         "title": "Cổ tức đợt 2/2025 bằng tiền, tỷ lệ 1.000đ/CP|Ngày KHQ: 28/05/2026"},
        "FPT")]
    with store.connect(db) as conn:
        assert store.upsert_timescale_marks(conn, marks) == 1
        row = store.load_marks(conn, "FPT")[0]
    assert row["parsed"]["ngay_gdkhq"] == "28/05/2026"
    assert "parsed_json" not in row
