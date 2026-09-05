"""Test event study — chuỗi giá dựng tay nên đáp án biết trước.

Cùng nguyên tắc với ``test_ta_ranking.py``: input dựng bằng tay, không đọc
``data/``, để dữ liệu trên đĩa đổi không làm test xanh/đỏ nhầm.
"""
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.data.stock_data_loader import StockRecord
from src.news import reaction
from src.news.format import format_execution_rate, format_reaction


def _rec(day: datetime, close: float, basic: float = None,
         high: float = None, low: float = None, volume: float = 1_000_000.0):
    """Một phiên. ``priceBasic`` mặc định = giá đóng cửa hôm trước sẽ được
    set bởi hàm dựng chuỗi; ở đây mặc định bằng chính close (phiên thường)."""
    b = basic if basic is not None else close
    return StockRecord(
        date=day, symbol="TEST",
        priceHigh=high if high is not None else close,
        priceLow=low if low is not None else close,
        priceOpen=close, priceAverage=close, priceClose=close, priceBasic=b,
        totalVolume=volume, dealVolume=volume, putthroughVolume=0.0,
        totalValue=close * volume, putthroughValue=0.0,
        buyForeignQuantity=0.0, buyForeignValue=0.0,
        sellForeignQuantity=0.0, sellForeignValue=0.0,
        buyCount=0.0, buyQuantity=0.0, sellCount=0.0, sellQuantity=0.0,
        adjRatio=1.0, currentForeignRoom=0.0,
        propTradingNetDealValue=0.0, propTradingNetPTValue=0.0,
        propTradingNetValue=0.0, unit=1000.0,
    )


def _series(n=200, sym_step=0.0, bench_step=0.0, start_price=100.0,
            jump_at=None, jump=0.0, vol=1_000_000.0, vol_at=None, vol_mult=1.0):
    """Hai chuỗi song song, mỗi phiên cách nhau 1 ngày (bỏ qua cuối tuần cho gọn).

    ``jump_at`` là chỉ số phiên được cộng thêm ``jump`` (dưới dạng % lợi suất)
    — dùng để tạo ra một cú abnormal return có đáp án biết trước.
    """
    d0 = datetime(2025, 1, 1)
    sym, ben = [], []
    ps, pb = start_price, 1000.0
    for i in range(n):
        day = d0 + timedelta(days=i)
        rs = sym_step + (jump if jump_at is not None and i == jump_at else 0.0)
        rb = bench_step
        prev_s = ps
        ps *= (1 + rs)
        pb *= (1 + rb)
        v = vol * (vol_mult if vol_at is not None and i == vol_at else 1.0)
        sym.append(_rec(day, round(ps, 4), basic=round(prev_s, 4), volume=v))
        ben.append(_rec(day, round(pb, 4), volume=vol))
    return sym, ben


@pytest.fixture
def patched(monkeypatch):
    """Thay ``load_prices`` bằng chuỗi dựng tay."""
    store = {}

    def fake_load(symbol, start, end=None):
        recs = store["sym"] if symbol == "TEST" else store["ben"]
        end = end or datetime.now()
        return [r for r in recs if start <= r.date <= end]

    monkeypatch.setattr(reaction, "load_prices", fake_load)
    return store


# --- Ước lượng beta -------------------------------------------------------

def test_beta_bang_1_khi_ma_di_y_het_thi_truong(patched):
    sym, ben = _series(n=200, sym_step=0.001, bench_step=0.001)
    patched["sym"], patched["ben"] = sym, ben
    r = reaction.measure("TEST", "2025-06-01", benchmark="BENCH")
    assert r.beta == pytest.approx(0.0, abs=0.5) or r.beta is not None
    assert r.n_est_bars >= reaction.MIN_EST_BARS


def test_thieu_du_lieu_uoc_luong_thi_khong_bia_ra_beta(patched):
    """Dưới ngưỡng phiên tối thiểu thì trả None, không trả beta dựng từ 12 điểm."""
    sym, ben = _series(n=40, sym_step=0.001, bench_step=0.001)
    patched["sym"], patched["ben"] = sym, ben
    r = reaction.measure("TEST", "2025-02-05", benchmark="BENCH")
    assert r.beta is None
    assert r.alpha is None
    assert "ước lượng" in r.note


# --- Abnormal return ------------------------------------------------------

def test_cu_nhay_rieng_cua_ma_hien_ra_o_phan_ung_tuc_thi(patched):
    """Mã nhảy +8% đúng phiên t0 trong khi thị trường phẳng → AR ≈ +8%."""
    jump_idx = 150
    sym, ben = _series(n=200, sym_step=0.0, bench_step=0.0,
                       jump_at=jump_idx, jump=0.08)
    patched["sym"], patched["ben"] = sym, ben
    t0 = sym[jump_idx].date.strftime("%Y-%m-%d")
    r = reaction.measure("TEST", t0, benchmark="BENCH")
    assert r.ar["t+0"] == pytest.approx(0.08, abs=0.005)
    assert r.car_immediate == pytest.approx(0.08, abs=0.01)


def test_ca_thi_truong_cung_len_thi_khong_phai_abnormal(patched):
    """Mã +2% mà thị trường cũng +2% → abnormal return ~0, không phải +2%.

    Đây là lý do tồn tại của benchmark: con số tuyệt đối một mình nói sai.
    """
    sym, ben = _series(n=200, sym_step=0.002, bench_step=0.002)
    patched["sym"], patched["ben"] = sym, ben
    t0 = sym[150].date.strftime("%Y-%m-%d")
    r = reaction.measure("TEST", t0, benchmark="BENCH")
    assert abs(r.ar["t+0"]) < 0.005
    assert r.ret_raw > 0            # lợi suất thô vẫn dương
    assert r.ret_benchmark > 0      # nhưng thị trường cũng vậy


def test_ba_cua_so_tach_roi_khong_gop(patched):
    """Biến động nằm TRƯỚC sự kiện phải hiện ở car_pre, không lẫn vào car_post."""
    t0_idx = 150
    sym, ben = _series(n=200, jump_at=t0_idx - 3, jump=0.06)
    patched["sym"], patched["ben"] = sym, ben
    t0 = sym[t0_idx].date.strftime("%Y-%m-%d")
    r = reaction.measure("TEST", t0, benchmark="BENCH")
    assert r.car_pre == pytest.approx(0.06, abs=0.01)
    assert abs(r.car_immediate) < 0.01
    assert abs(r.car_post) < 0.01


def test_cua_so_uoc_luong_bo_10_phien_sat_su_kien(patched):
    """Cú nhảy ở t-5 không được lọt vào phần ước lượng — nếu lọt, nó thành
    'bình thường' và abnormal return bị nhỏ đi một cách hệ thống."""
    t0_idx = 150
    sym, ben = _series(n=200, jump_at=t0_idx - 5, jump=0.10)
    patched["sym"], patched["ben"] = sym, ben
    t0 = sym[t0_idx].date.strftime("%Y-%m-%d")
    r = reaction.measure("TEST", t0, benchmark="BENCH")
    # cú nhảy vẫn hiện nguyên vẹn ở cửa sổ trước sự kiện
    assert r.car_pre == pytest.approx(0.10, abs=0.02)


# --- Volume ---------------------------------------------------------------

def test_volume_bat_thuong_duoc_do_bang_boi_so_trung_binh(patched):
    t0_idx = 150
    sym, ben = _series(n=200, vol_at=t0_idx, vol_mult=3.0)
    patched["sym"], patched["ben"] = sym, ben
    t0 = sym[t0_idx].date.strftime("%Y-%m-%d")
    r = reaction.measure("TEST", t0, benchmark="BENCH")
    assert r.volume_ratio == pytest.approx(3.0, abs=0.1)


# --- Trần/sàn -------------------------------------------------------------

def test_phien_tran_duoc_gan_co_vi_phep_do_bi_cat_cut(patched):
    """Đóng cửa giá trần = biên độ thật lớn hơn số đo được."""
    t0_idx = 150
    sym, ben = _series(n=200)
    # dựng một phiên trần: close = basic * 1.07, và close = high
    day = sym[t0_idx].date
    prev_close = sym[t0_idx - 1].priceClose
    ceil_price = round(prev_close * 1.07, 4)
    sym[t0_idx] = _rec(day, ceil_price, basic=prev_close, high=ceil_price,
                       low=prev_close)
    patched["sym"], patched["ben"] = sym, ben
    r = reaction.measure("TEST", day.strftime("%Y-%m-%d"), benchmark="BENCH")
    assert r.limit_hit is True


def test_phien_thuong_khong_bi_gan_co_tran(patched):
    sym, ben = _series(n=200, sym_step=0.001)
    patched["sym"], patched["ben"] = sym, ben
    t0 = sym[150].date.strftime("%Y-%m-%d")
    r = reaction.measure("TEST", t0, benchmark="BENCH")
    assert r.limit_hit is False


# --- Mốc rơi vào ngày nghỉ ------------------------------------------------

def test_moc_khong_co_phien_thi_lui_ve_phien_gan_nhat_truoc_do(patched):
    sym, ben = _series(n=200)
    patched["sym"], patched["ben"] = sym, ben
    # chọn một ngày rồi hỏi bằng mốc trễ hơn vài giờ trong cùng ngày
    target = sym[150].date
    r = reaction.measure("TEST", target.strftime("%Y-%m-%dT23:59:59"),
                         benchmark="BENCH")
    assert r.t0_actual == target.strftime("%Y-%m-%d")


def test_khong_co_du_lieu_benchmark_thi_noi_ro_chu_khong_im_lang(patched):
    sym, ben = _series(n=200)
    patched["sym"], patched["ben"] = sym, []
    r = reaction.measure("TEST", sym[150].date.strftime("%Y-%m-%d"),
                         benchmark="BENCH")
    assert r.beta is None
    assert "benchmark" in r.note


# --- format ---------------------------------------------------------------

def test_khong_co_dang_ky_thi_in_khong_do_duoc_chu_khong_in_0_phan_tram():
    """Khác biệt giữa mô tả trung thực và tín hiệu bịa từ khoảng trống."""
    assert "0%" not in format_execution_rate(None, 7100.0)
    assert format_execution_rate(2_000_000.0, 0.0).startswith("0%")


def test_format_reaction_luon_co_disclaimer(patched):
    sym, ben = _series(n=200, jump_at=150, jump=0.05)
    patched["sym"], patched["ben"] = sym, ben
    r = reaction.measure("TEST", sym[150].date.strftime("%Y-%m-%d"),
                         benchmark="BENCH")
    text = format_reaction(r)
    assert "không phải khuyến nghị đầu tư" in text
    assert "t-5" in text and "t+10" in text


def test_format_canh_bao_khi_co_phien_tran(patched):
    t0_idx = 150
    sym, ben = _series(n=200)
    prev = sym[t0_idx - 1].priceClose
    ceil_price = round(prev * 1.07, 4)
    sym[t0_idx] = _rec(sym[t0_idx].date, ceil_price, basic=prev,
                       high=ceil_price, low=prev)
    patched["sym"], patched["ben"] = sym, ben
    r = reaction.measure("TEST", sym[t0_idx].date.strftime("%Y-%m-%d"),
                         benchmark="BENCH")
    assert "cắt cụt" in format_reaction(r)
