"""Test hiệu chuẩn base rate — phân phối, ngưỡng n, và loại phiên trần/sàn."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.news.models import PURCHASED, SOLD
from src.news.stats import (
    MIN_N,
    BucketStats,
    Distribution,
    _bucket_label,
    format_stats,
)


# --- Phân phối ------------------------------------------------------------

def test_trung_vi_khong_bi_mot_ca_ngoai_le_keo_di():
    """Lý do dùng trung vị chứ không trung bình: đuôi dày."""
    vals = [0.01, 0.02, 0.03, 0.02, 0.80]     # một ca +80%
    d = Distribution.of(vals)
    assert d.median == pytest.approx(0.02)
    assert sum(vals) / len(vals) > 0.15        # trung bình bị kéo lệch hẳn


def test_phan_vi_va_ty_le_duong():
    d = Distribution.of([-0.02, -0.01, 0.01, 0.03])
    assert d.n == 4
    assert d.pct_positive == pytest.approx(0.5)
    assert d.p25 < d.median < d.p75


def test_rong_thi_tra_None_khong_phai_0():
    d = Distribution.of([])
    assert d.n == 0 and d.median is None and d.pct_positive is None


def test_gia_tri_None_bi_bo_khong_tinh_thanh_0():
    d = Distribution.of([0.05, None, 0.05])
    assert d.n == 2 and d.median == pytest.approx(0.05)


# --- Xếp nhóm -------------------------------------------------------------

def _row(direction=PURCHASED, position=None, reg=1000.0, ex=1000.0):
    return {"direction": direction, "position": position,
            "registered_volume": reg, "execution_volume": ex}


def test_noi_bo_tach_khoi_co_dong_lon():
    assert "nội bộ" in _bucket_label(_row(position="Thành viên HĐQT"))
    assert "cổ đông lớn" in _bucket_label(_row(position=None))


def test_ba_muc_thuc_hien_duoc_tach_rieng():
    assert "thực hiện đủ" in _bucket_label(_row(reg=1000.0, ex=1000.0))
    assert "thực hiện một phần" in _bucket_label(_row(reg=1000.0, ex=400.0))
    assert "không thực hiện" in _bucket_label(_row(reg=1000.0, ex=0.0))


def test_khong_co_dang_ky_khong_bi_xep_thanh_khong_thuc_hien():
    """``reg=None`` là 'không đo được', khác hẳn 'đăng ký rồi không làm'."""
    label = _bucket_label(_row(reg=None, ex=7100.0))
    assert "không rõ đăng ký" in label
    assert "không thực hiện" not in label


def test_quyen_mua_khong_bi_gop_vao_mua_ban_thuong():
    """Mua/bán quyền mua có cơ chế khác — gộp vào là trộn hai thứ khác nhau."""
    assert _bucket_label(_row(direction=2)) is None
    assert _bucket_label(_row(direction=3)) is None


def test_chieu_hien_trong_nhan():
    assert "mua" in _bucket_label(_row(direction=PURCHASED))
    assert "bán" in _bucket_label(_row(direction=SOLD))


# --- Ngưỡng phát biểu -----------------------------------------------------

def test_duoi_nguong_n_thi_khong_duoc_coi_la_phat_bieu_duoc():
    b = BucketStats(label="x", n_events=MIN_N - 1)
    assert b.reportable is False
    assert BucketStats(label="x", n_events=MIN_N).reportable is True


def test_format_khong_in_so_cho_nhom_thieu_quan_sat():
    """n nhỏ mà vẫn in trung vị là cách nói dối bằng số tinh vi nhất."""
    thin = BucketStats(label="nội bộ · mua · thực hiện đủ", n_events=3)
    thin.car_immediate = Distribution.of([0.05, 0.06, 0.07])
    text = format_stats({thin.label: thin})
    assert "Chưa đủ quan sát" in text
    assert "n=3" in text
    assert "+6.0%" not in text          # trung vị không được lộ ra


def test_format_in_bang_khi_du_quan_sat():
    b = BucketStats(label="nội bộ · mua · thực hiện đủ", n_events=MIN_N)
    b.car_immediate = Distribution.of([0.01] * MIN_N)
    b.car_pre = Distribution.of([0.0] * MIN_N)
    b.car_post = Distribution.of([0.02] * MIN_N)
    text = format_stats({b.label: b})
    assert "| nội bộ · mua · thực hiện đủ |" in text
    assert "p25" in text                 # khoảng tứ phân vị phải hiện
    assert "không phải khuyến nghị" in text


def test_format_noi_ro_so_su_kien_bi_loai_vi_tran_san():
    b = BucketStats(label="nội bộ · mua · thực hiện đủ", n_events=MIN_N,
                    n_limit_excluded=7)
    b.car_immediate = Distribution.of([0.01] * MIN_N)
    text = format_stats({b.label: b})
    assert "7 sự kiện" in text
    assert "cắt cụt" in text


def test_khong_co_gi_thi_noi_thang():
    assert "Chưa có sự kiện" in format_stats({})
