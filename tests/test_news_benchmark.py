"""Test chỉ số đối chứng đều tay. Chuỗi giá dựng tay, không đọc data/."""
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.data.stock_data_loader import StockRecord, record_from_json
from src.news import benchmark


def _rec(day, close, symbol="X"):
    return StockRecord(
        date=day, symbol=symbol, priceHigh=close, priceLow=close,
        priceOpen=close, priceAverage=close, priceClose=close, priceBasic=close,
        totalVolume=1e6, dealVolume=1e6, putthroughVolume=0.0,
        totalValue=0.0, putthroughValue=0.0,
        buyForeignQuantity=0.0, buyForeignValue=0.0,
        sellForeignQuantity=0.0, sellForeignValue=0.0,
        buyCount=0.0, buyQuantity=0.0, sellCount=0.0, sellQuantity=0.0,
        adjRatio=1.0, currentForeignRoom=0.0,
        propTradingNetDealValue=0.0, propTradingNetPTValue=0.0,
        propTradingNetValue=0.0, unit=1000.0,
    )


@pytest.fixture
def fake_prices(monkeypatch):
    """``{mã: [(ngày, giá), ...]}`` -> thay ``load_prices``."""
    store = {}

    def fake(symbol, start, end=None):
        return [_rec(d, c, symbol) for d, c in store.get(symbol, [])
                if start <= d <= (end or datetime.now())]

    monkeypatch.setattr(benchmark, "load_prices", fake)
    return store


def _days(n, base=datetime(2020, 1, 1)):
    return [base + timedelta(days=i) for i in range(n)]


# --- Trọng số đều tay ------------------------------------------------------

def test_moi_ma_dong_gop_bang_nhau_bat_ke_gia_cao_thap(fake_prices):
    """Đây là điểm khác biệt duy nhất so với chỉ số trọng số vốn hoá.

    Một mã giá 200 và một mã giá 8, cùng tăng/giảm ngược chiều cùng biên độ
    phần trăm, phải triệt tiêu nhau hoàn toàn.
    """
    d = _days(3)
    fake_prices["A"] = [(d[0], 200.0), (d[1], 220.0), (d[2], 220.0)]   # +10%, 0%
    fake_prices["B"] = [(d[0], 8.0), (d[1], 7.2), (d[2], 7.2)]         # -10%, 0%
    series, _ = benchmark.build_series(["A", "B"], d[0], d[2], min_members=2)
    # phiên đầu tiên có lợi suất là d[1]: (+10% + -10%)/2 = 0
    assert series[0][3] == pytest.approx(0.0, abs=1e-9)
    assert series[0][1] == pytest.approx(benchmark.BASE_LEVEL)


def test_trung_binh_loi_suat_khong_phai_trung_binh_gia(fake_prices):
    """Trung bình *giá* thì mã giá cao lấn át — lại thành trọng số theo giá."""
    d = _days(2)
    fake_prices["A"] = [(d[0], 100.0), (d[1], 110.0)]   # +10%
    fake_prices["B"] = [(d[0], 10.0), (d[1], 12.0)]     # +20%
    series, _ = benchmark.build_series(["A", "B"], d[0], d[1], min_members=2)
    assert series[0][3] == pytest.approx(0.15)          # (10+20)/2


def test_chi_so_cong_don_qua_nhieu_phien(fake_prices):
    d = _days(3)
    fake_prices["A"] = [(d[0], 100.0), (d[1], 110.0), (d[2], 121.0)]
    series, _ = benchmark.build_series(["A"], d[0], d[2], min_members=1)
    assert series[-1][1] == pytest.approx(benchmark.BASE_LEVEL * 1.21)


# --- Mã chưa niêm yết ------------------------------------------------------

def test_ma_chua_niem_yet_khong_duoc_noi_suy_chi_la_vang_mat(fake_prices):
    """Mã lên sàn muộn thì những phiên trước đó nó **không có mặt**, không phải
    'lợi suất 0'. Điền 0 vào là kéo chỉ số về phía không biến động một cách giả."""
    d = _days(4)
    fake_prices["A"] = [(dd, 100.0 * (1.1 ** i)) for i, dd in enumerate(d)]
    fake_prices["B"] = [(d[2], 50.0), (d[3], 60.0)]     # lên sàn muộn
    series, _ = benchmark.build_series(["A", "B"], d[0], d[3], min_members=1)
    members = {day.strftime("%m-%d"): m for day, _, m, _ in series}
    assert members["01-02"] == 1        # chỉ A
    assert members["01-04"] == 2        # cả hai


def test_phien_qua_it_thanh_vien_bi_bo(fake_prices):
    """Trung bình của 3 mã không phải 'thị trường', nó là nhiễu của 3 mã đó."""
    d = _days(3)
    fake_prices["A"] = [(dd, 100.0) for dd in d]
    series, skipped = benchmark.build_series(["A"], d[0], d[2], min_members=20)
    assert series == [] and skipped == 2


# --- Ghi ra đĩa đúng schema ------------------------------------------------

def test_ghi_ra_doc_lai_duoc_bang_record_from_json(tmp_path, fake_prices):
    """File phải đọc được bằng đúng parser của repo, không cần đường riêng."""
    d = _days(3)
    fake_prices["A"] = [(d[0], 100.0), (d[1], 110.0), (d[2], 99.0)]
    series, _ = benchmark.build_series(["A"], d[0], d[2], min_members=1)
    benchmark.write_proxy(series, data_dir=tmp_path)

    files = list((tmp_path / benchmark.PROXY_SYMBOL).rglob("*.json"))
    assert files
    items = json.loads(files[0].read_text(encoding="utf-8"))
    rec = record_from_json(items[0])
    assert rec.symbol == benchmark.PROXY_SYMBOL
    assert rec.adjRatio == 1.0


def test_price_basic_la_muc_phien_truoc(tmp_path, fake_prices):
    """priceBasic đúng nghĩa 'giá tham chiếu' — nếu để bằng chính nó thì mọi
    phép tính % thay đổi trên chỉ số ra 0."""
    d = _days(3)
    fake_prices["A"] = [(d[0], 100.0), (d[1], 110.0), (d[2], 121.0)]
    series, _ = benchmark.build_series(["A"], d[0], d[2], min_members=1)
    benchmark.write_proxy(series, data_dir=tmp_path)
    items = json.loads(
        next((tmp_path / benchmark.PROXY_SYMBOL).rglob("*.json")).read_text(encoding="utf-8"))
    assert items[0]["priceBasic"] == pytest.approx(benchmark.BASE_LEVEL)
    assert items[1]["priceBasic"] == pytest.approx(items[0]["priceClose"])


def test_ohlc_de_phang_khong_bia_bien_do_trong_phien(tmp_path, fake_prices):
    """Chỉ số này không có dữ liệu trong phiên; bịa ra biên độ giả tệ hơn để phẳng."""
    d = _days(2)
    fake_prices["A"] = [(d[0], 100.0), (d[1], 110.0)]
    series, _ = benchmark.build_series(["A"], d[0], d[1], min_members=1)
    benchmark.write_proxy(series, data_dir=tmp_path)
    item = json.loads(
        next((tmp_path / benchmark.PROXY_SYMBOL).rglob("*.json")).read_text(encoding="utf-8"))[0]
    assert item["priceHigh"] == item["priceLow"] == item["priceClose"]


def test_khong_co_du_lieu_thi_khong_ghi_gi(tmp_path, fake_prices):
    out = benchmark.build(["A"], datetime(2020, 1, 1), datetime(2020, 1, 5),
                          min_members=1, data_dir=tmp_path)
    assert out.sessions == 0 and out.files_written == 0
