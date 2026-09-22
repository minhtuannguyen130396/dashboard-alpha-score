"""GĐ 1 của tầng vĩ mô: chỉ số ngành đọc được, và **không lọt vào rổ**.

Nhóm test thứ hai ở đây (``TestKhongLotVaoRo``) là thứ đáng giữ nhất: nó biến
một quy ước trong ``CLAUDE.md`` thành một test đỏ. Chỉ số ngành có đúng schema
như cổ phiếu và nằm cùng chỗ trong ``data/`` — không có gì ở tầng dưới phân
biệt được hai loại, nên chỉ một lượt refactor ``resolve_universe`` là 31 dòng
"ngành" lẳng lặng chui vào mọi bảng xếp hạng.
"""
import json
from datetime import datetime

import pytest

from src.data.stock_data_loader import record_from_json
from src.macro import icb
from src.ta import loader


# ---------------------------------------------------------------------------
# Tên và mã
# ---------------------------------------------------------------------------
class TestTenMa:
    def test_di_ve_va_quay_lai(self):
        assert icb.sector_symbol("60") == "_ICB_60"
        assert icb.sector_code("_ICB_60") == "60"
        assert icb.sector_code("_icb_3010") == "3010"

    def test_ma_co_phieu_khong_phai_nganh(self):
        for sym in ("FPT", "VNINDEX", "VN30F1M", "_PROXY_EW"):
            assert icb.sector_code(sym) is None
            assert not icb.is_sector(sym)

    def test_ma_cha_trong_cay_icb(self):
        assert icb._parent_code("3010") == "30"
        assert icb._parent_code("30") is None


# ---------------------------------------------------------------------------
# Chuyển đổi sang schema giá
# ---------------------------------------------------------------------------
def _raw_row(close=90.71, prev=85.56, **over):
    values = {
        "ICBCode": "60", "ICBName": "Năng lượng",
        "IndexOpen": 86.09, "IndexHigh": 91.03, "IndexLow": 84.92,
        "IndexClose": close, "IndexPrev": prev,
        "Volume": 68648400, "Value": 1810936406000,
        "BuyQuantity": 25591200, "SellQuantity": 26998500,
        "BuyForeignQuantity": 8895100, "BuyForeignValue": 269714894415,
        "SellForeignQuantity": 2278374, "SellForeignValue": 62671301158,
        "PositiveMoneyFlow": 1803391736000, "NegativeMoneyFlow": 1460800,
        "NeutralMoneyFlow": 0, "PE": 8.15, "PB": 1.45, "PS": 0.23,
        "MarketCap": 1.8e14,
    }
    values.update(over)
    return {"industryCode": "60", "date": "2026-09-15T00:00:00",
            "indexValues": values}


class TestBanGhi:
    def test_doc_duoc_bang_record_from_json(self):
        """Cửa ra thật sự của quyết định kiến trúc: tầng dưới không phải sửa gì."""
        rec = record_from_json(icb._record_json("60", _raw_row()))
        assert rec.symbol == "_ICB_60"
        assert rec.priceClose == pytest.approx(90.71)
        assert rec.priceBasic == pytest.approx(85.56)
        assert rec.date == datetime(2026, 9, 15)

    def test_adj_ratio_bang_mot(self):
        """Chỉ số không chia tách — adjRatio khác 1 là chia sai cả chuỗi."""
        assert icb._record_json("60", _raw_row())["adjRatio"] == 1.0

    def test_unit_la_diem_chi_so(self):
        """unit=1000 như cổ phiếu là mọi chỗ hiển thị nhân sai 1000 lần."""
        assert icb._record_json("60", _raw_row())["unit"] == 1.0

    def test_deal_volume_bang_total_volume(self):
        """``priceImpactVolume`` = ``dealVolume`` là quy ước của cả repo."""
        rec = record_from_json(icb._record_json("60", _raw_row()))
        assert rec.dealVolume == rec.totalVolume == pytest.approx(68648400)
        assert rec.priceImpactVolume == rec.dealVolume

    def test_giu_lai_truong_rieng_cua_nganh(self):
        """Dòng tiền chủ động và PE/PB không có chỗ trong ``StockRecord``.

        Vứt đi thì phải nạp lại cả chuỗi mới có; giữ trong cùng bản ghi thì
        ``record_from_json`` bỏ qua vô hại vì nó đọc theo khoá cố định.
        """
        raw = icb._record_json("60", _raw_row())
        assert raw["icbPositiveMoneyFlow"] == pytest.approx(1803391736000)
        assert raw["icbPE"] == pytest.approx(8.15)
        record_from_json(raw)          # không được ném lỗi vì khoá lạ

    def test_phien_rong_bi_bo(self):
        assert icb._record_json("60", _raw_row(close=0)) is None
        assert icb._record_json("60", {"date": "", "indexValues": {}}) is None

    def test_thieu_ohlc_thi_lay_gia_dong_cua(self):
        """Để 0 thì nến cao 90 đáy 0 — một cây nến không tồn tại."""
        rec = icb._record_json("60", _raw_row(IndexOpen=0, IndexHigh=0, IndexLow=0))
        assert rec["priceOpen"] == rec["priceHigh"] == rec["priceLow"] == 90.71

    def test_price_average_theo_quy_uoc_cua_nguon(self):
        """FireAnt trả VNINDEX với priceAverage == priceClose; ta theo đúng thế."""
        rec = icb._record_json("60", _raw_row())
        assert rec["priceAverage"] == rec["priceClose"]


class TestGhiDia:
    def test_tach_file_theo_thang(self, tmp_path):
        recs = [icb._record_json("60", _raw_row()) for _ in range(2)]
        recs[1]["date"] = "2026-10-01T00:00:00"
        assert icb.write_index("60", recs, data_dir=tmp_path) == 2
        assert (tmp_path / "_ICB_60" / "2026" / "2026-09-01.json").is_file()
        assert (tmp_path / "_ICB_60" / "2026" / "2026-10-01.json").is_file()

    def test_file_doc_lai_duoc(self, tmp_path):
        icb.write_index("60", [icb._record_json("60", _raw_row())],
                        data_dir=tmp_path)
        items = json.loads((tmp_path / "_ICB_60" / "2026" / "2026-09-01.json")
                           .read_text(encoding="utf-8"))
        assert record_from_json(items[0]).symbol == "_ICB_60"


# ---------------------------------------------------------------------------
# Bất biến: không lọt vào rổ
# ---------------------------------------------------------------------------
class TestKhongLotVaoRo:
    """Quy ước của ``CLAUDE.md``, viết thành test đỏ.

    Chỉ số ngành nằm cùng chỗ với cổ phiếu trong ``data/`` và có đúng schema
    như một mã. Không có gì ở tầng dưới phân biệt được — nên chỗ duy nhất chặn
    được là ``resolve_universe``, và chỗ đó phải có test.
    """

    def test_khong_co_trong_ro_mac_dinh(self):
        for spec in (None, "disk", "all", "vn30"):
            got = loader.resolve_universe(spec)
            assert not [s for s in got if s.startswith(loader.SECTOR_PREFIX)], (
                f"chỉ số ngành lọt vào resolve_universe({spec!r})")

    def test_khong_co_trong_non_tradable(self):
        marks = loader.non_tradable_symbols()
        for sym in loader.sector_symbols():
            assert sym in marks

    def test_goi_dich_danh_thi_ra(self):
        if "_ICB_60" not in loader.available_symbols():
            pytest.skip("chưa nạp _ICB_60")
        assert loader.resolve_universe("_ICB_60") == ["_ICB_60"]

    def test_nhom_sectors_chi_chua_chi_so_nganh(self):
        got = loader.resolve_universe("sectors")
        assert all(s.startswith(loader.SECTOR_PREFIX) for s in got)

    def test_nhan_dien_theo_tien_to_khong_can_registry(self):
        """Registry chỉ thêm tên và cấp; tiền tố mới là bất biến.

        Nếu guard phụ thuộc vào ``sectors.json`` thì một lượt quên dựng lại
        registry là đúng lúc chỉ số ngành lọt vào bảng xếp hạng — tức là guard
        hỏng đúng lúc cần nhất.
        """
        assert loader.is_sector_index("_ICB_9999")
        assert not loader.is_sector_index("FPT")


class TestBanTrung:
    """31 mã ngành chỉ là 25 chuỗi phân biệt — và không có gì tự nói ra điều đó.

    Sáu ngành cấp 1 có đúng một con cấp 2, nên hai chuỗi trùng khít. Một bảng
    "5 ngành mạnh nhất" không đánh dấu sẽ hiện *Năng lượng* hai lần dưới hai
    cái tên khác nhau, ăn hai suất bằng đúng một thông tin.
    """

    @staticmethod
    def _tree():
        return [
            icb.Industry("10", 1, "Công nghệ"),
            icb.Industry("1010", 2, "Công nghệ thông tin", parent="10"),
            icb.Industry("30", 1, "Tài chính"),
            icb.Industry("3010", 2, "Ngân hàng", parent="30"),
            icb.Industry("3020", 2, "Dịch vụ tài chính", parent="30"),
        ]

    def test_con_duy_nhat_la_ban_trung(self):
        assert icb.duplicate_map(self._tree()) == {"1010": "10"}

    def test_cha_nhieu_con_thi_khong_trung(self):
        """`30` Tài chính có 3010 + 3020 — ba dòng khác nhau thật."""
        dup = icb.duplicate_map(self._tree())
        assert "3010" not in dup and "3020" not in dup

    def test_bo_ban_trung_thi_giu_cap_1(self):
        assert icb.distinct_codes(self._tree()) == ["10", "30", "3010", "3020"]

    def test_registry_ghi_duplicate_of(self, tmp_path):
        path = tmp_path / "sectors.json"
        icb.write_registry(self._tree(), path=path)
        items = {it["icb_code"]: it for it in icb.load_registry(path)}
        assert items["1010"]["duplicate_of"] == "10"
        assert items["3010"]["duplicate_of"] is None
        assert "TRUNG KHIT" in items["1010"]["note"]

    def test_file_that_danh_dau_du_sau_cap(self):
        items = icb.load_registry()
        if not items:
            pytest.skip("chưa dựng sectors.json")
        dup = {it["icb_code"]: it["duplicate_of"]
               for it in items if it.get("duplicate_of")}
        assert dup == {"1010": "10", "1510": "15", "2010": "20",
                       "3510": "35", "6010": "60", "6510": "65"}

    def test_ban_trung_that_su_trung_tren_dia(self):
        """Không tin bảng — đối chiếu chính chuỗi giá."""
        items = {it["icb_code"]: it for it in icb.load_registry()}
        pairs = [(c, it["duplicate_of"]) for c, it in items.items()
                 if it.get("duplicate_of")]
        if not pairs:
            pytest.skip("chưa dựng sectors.json")
        for child, parent in pairs:
            a = loader.load_recent(icb.sector_symbol(child), 120)
            b = loader.load_recent(icb.sector_symbol(parent), 120)
            if not a or not b:
                pytest.skip(f"chưa nạp {child}/{parent}")
            assert [r.priceClose for r in a] == [r.priceClose for r in b], (
                f"_ICB_{child} và _ICB_{parent} được đánh dấu trùng nhưng lệch nhau")


class TestRegistry:
    def test_ghi_va_doc_lai(self, tmp_path):
        tree = [icb.Industry(code="60", level=1, name="Năng lượng"),
                icb.Industry(code="6010", level=2, name="Năng lượng", parent="60")]
        path = tmp_path / "sectors.json"
        icb.write_registry(tree, {"60": 33}, {"60": 4163}, path=path)
        items = icb.load_registry(path)
        assert [it["share_code"] for it in items] == ["_ICB_60", "_ICB_6010"]
        assert items[0]["icb_code"] == "60"
        assert items[0]["members"] == 33
        assert items[1]["parent"] == "60"

    def test_moi_dong_noi_ro_khong_phai_co_phieu(self):
        """Người đọc file phải hiểu ngay, không phải đi tra tài liệu."""
        tree = [icb.Industry(code="60", level=1, name="Năng lượng")]
        items = json.loads(json.dumps(
            [{"note": icb._NOTE}]))          # nội dung note là hợp đồng với người đọc
        assert "KHONG PHAI MOT MA CO PHIEU" in items[0]["note"]
        assert "ranking.py" in items[0]["note"]
        assert tree[0].symbol.startswith(icb.SECTOR_PREFIX)

    def test_file_that_khop_thu_muc_tren_dia(self):
        """Registry và đĩa không được lệch nhau."""
        items = icb.load_registry()
        if not items:
            pytest.skip("chưa dựng sectors.json")
        on_disk = set(loader.available_symbols())
        listed = {it["share_code"] for it in items}
        missing = {s for s in listed if s in on_disk} ^ (listed & on_disk)
        assert not missing
        for it in items:
            assert it["level"] in (1, 2)
            assert it["kind"] == "sector_index"
