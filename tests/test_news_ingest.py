"""Test lượt nạp tin — mốc lùi nối tiếp, đếm bài mới, và cờ cắt cụt.

Không gọi mạng: ``fireant.posts`` được thay bằng một kho giả trong bộ nhớ, nên
cái được kiểm ở đây là **luật phân trang và luật chọn mốc**, không phải API.
"""
import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.news import ingest, posts as posts_mod, store
from src.news.ingest import NEWS_MODES, resume_since


@pytest.fixture
def db(tmp_path):
    return tmp_path / "test_index.db"


def _row(pid, when, title=None):
    return {
        "postID": pid, "title": title or f"Tin so {pid}",
        "description": "Tom tat", "date": f"{when}T09:30:00+07:00",
        "postSource": {"name": "CafeF", "url": "https://cafef.vn/"},
        "postGroup": {"name": "Thi truong"},
        "taggedSymbols": [{"symbol": "FPT"}],
        "sentiment": 0, "isAIGenerated": False,
    }


def _store_post(conn, pid, when, symbol="FPT"):
    store.upsert_posts(conn, posts_mod.parse_posts([_row(pid, when)], symbol))


def _paged(monkeypatch, pages):
    """Thay feed FireAnt bằng một kho giả, phân trang theo đúng offset."""
    def fake(symbol, kind=1, offset=0, limit=100):
        idx = offset // posts_mod.PAGE
        return pages[idx] if idx < len(pages) else []

    monkeypatch.setattr(posts_mod.fireant, "posts", fake)


def _no_structured(monkeypatch):
    """Tắt hai request giao dịch/mốc — test này chỉ nói về phần bài viết."""
    monkeypatch.setattr(ingest.fireant, "holder_transactions", lambda *a, **kw: [])
    monkeypatch.setattr(ingest.fireant, "timescale_marks", lambda *a, **kw: [])


# --- mốc lùi: nối tiếp chỗ kho đang dừng ----------------------------------

def test_kho_dung_xa_hon_cua_so_mode_thi_lui_theo_KHO(db):
    """Cái bẫy thật: kho dừng 04/09, chạy `latest` (7 ngày) hôm 17/09.

    Lấy một mình cửa sổ mode thì mốc là 10/09 và các bài 05→09/09 không bao giờ
    được nạp — lượt chạy vẫn báo "xong", lỗ thủng nằm lại vĩnh viễn.
    """
    with store.connect(db) as conn:
        _store_post(conn, 1, "2026-09-04")
        since = resume_since(conn, "FPT", NEWS_MODES["latest"],
                             today=date(2026, 9, 17))
    assert since == "2026-09-01"          # 04/09 trừ OVERLAP_DAYS


def test_kho_dang_moi_thi_van_lui_du_cua_so_cua_mode(db):
    with store.connect(db) as conn:
        _store_post(conn, 1, "2026-09-17")
        since = resume_since(conn, "FPT", NEWS_MODES["latest"],
                             today=date(2026, 9, 17))
    assert since == "2026-09-10"          # cửa sổ mode xa hơn chỗ nối tiếp


def test_ma_chua_co_bai_nao_thi_lui_xa_chu_khong_phai_7_ngay(db):
    with store.connect(db) as conn:
        since = resume_since(conn, "FPT", NEWS_MODES["latest"],
                             today=date(2026, 9, 17))
    assert since == "2025-08-13"          # FIRST_RUN_LOOKBACK_DAYS


def test_mode_full_khong_dat_moc_dung(db):
    with store.connect(db) as conn:
        _store_post(conn, 1, "2026-09-04")
        assert resume_since(conn, "FPT", NEWS_MODES["full"],
                            today=date(2026, 9, 17)) is None


def test_moc_khai_tay_de_len_plan(db, monkeypatch):
    seen = {}

    def spy(symbol, **kw):
        seen.update(kw)
        return posts_mod.PostFetch()

    monkeypatch.setattr(posts_mod, "fetch_posts_paged", spy)
    _no_structured(monkeypatch)
    with store.connect(db) as conn:
        _store_post(conn, 1, "2026-09-04")
        ingest.ingest_symbol(conn, "FPT", with_posts=True,
                             posts_since="2020-01-01",
                             posts_plan=NEWS_MODES["latest"],
                             marks_end="2026-09-17")
    assert seen["since"] == "2020-01-01"


def test_mode_la_khong_biet_thi_KHONG_am_tham_chay_latest(db):
    with pytest.raises(ValueError, match="quater"):
        ingest.ingest(["FPT"], db_path=db, posts_mode="quater")


# --- đếm: bài ghi khác bài mới --------------------------------------------

def test_bai_da_co_trong_kho_khong_duoc_dem_la_moi(db, monkeypatch):
    """Lượt nạp cố ý chồng lấn vài ngày, nên phần lớn dòng ghi là ghi đè."""
    _paged(monkeypatch, [[_row(1, "2026-09-16"), _row(2, "2026-09-15")]])
    _no_structured(monkeypatch)
    with store.connect(db) as conn:
        _store_post(conn, 1, "2026-09-16")          # đã có sẵn 1 bài
        item = ingest.ingest_symbol(conn, "FPT", with_posts=True,
                                    posts_plan=NEWS_MODES["latest"],
                                    marks_end="2026-09-17",
                                    today=date(2026, 9, 17))
    assert item.posts == 2                          # ghi 2 dòng
    assert item.posts_new == 1                      # nhưng chỉ 1 bài là mới


def test_known_post_ids_hoi_theo_post_id_khong_theo_ma(db):
    """Bài gắn nhiều mã chỉ nằm dưới mã nạp trước — đếm theo mã sẽ tính lại nó."""
    with store.connect(db) as conn:
        _store_post(conn, 7, "2026-09-16", symbol="VIC")
        assert store.known_post_ids(conn, [7, 8]) == {7}


def test_known_post_ids_chia_lo_khi_nhieu_id(db):
    with store.connect(db) as conn:
        for pid in range(1, 501):
            _store_post(conn, pid, "2026-09-16")
        assert len(store.known_post_ids(conn, range(1, 1001))) == 500


def test_latest_post_date_doc_tu_bang_chu_khong_tu_log(db):
    with store.connect(db) as conn:
        _store_post(conn, 1, "2026-09-04")
        _store_post(conn, 2, "2026-08-30")
        store.log_ingest(conn, "FPT", "posts", 0)   # lượt chạy rỗng, kho không đổi
        assert store.latest_post_date(conn, "FPT") == "2026-09-04"
        assert store.latest_post_date(conn, "HPG") is None


# --- cờ cắt cụt: dừng vì hết trang khác dừng vì đã lùi đủ xa --------------

def _full_pages(n):
    return [[_row(i * 100 + j, "2026-09-16") for j in range(posts_mod.PAGE)]
            for i in range(n)]


def test_het_ngan_sach_trang_thi_bao_con_bai_chua_nap(monkeypatch):
    _paged(monkeypatch, _full_pages(4))
    out = posts_mod.fetch_posts_paged("FPT", since="2020-01-01", max_pages=2)
    assert out.pages == 2
    assert out.hit_page_cap is True


def test_lui_qua_moc_thi_KHONG_phai_cat_cut(monkeypatch):
    _paged(monkeypatch, [[_row(1, "2026-09-16"), _row(2, "2019-01-01")]])
    out = posts_mod.fetch_posts_paged("FPT", since="2020-01-01", max_pages=5)
    assert out.hit_page_cap is False
    assert out.oldest == "2019-01-01"


def test_trang_cuoi_khong_day_la_HET_KHO_khong_phai_cat_cut(monkeypatch):
    _paged(monkeypatch, [[_row(1, "2026-09-16")]])
    out = posts_mod.fetch_posts_paged("FPT", since="2020-01-01", max_pages=1)
    assert out.hit_page_cap is False


def test_kho_rong_khong_bi_doc_thanh_cat_cut(monkeypatch):
    _paged(monkeypatch, [[]])
    out = posts_mod.fetch_posts_paged("FPT", since="2020-01-01", max_pages=3)
    assert out.posts == []
    assert out.hit_page_cap is False
    assert out.pages == 1


def test_co_cat_cut_di_len_ket_qua_ca_luot(db, monkeypatch):
    _paged(monkeypatch, _full_pages(10))
    _no_structured(monkeypatch)
    result = ingest.ingest(["FPT"], db_path=db, with_posts=True,
                           posts_mode="latest", today=date(2026, 9, 17))
    assert [s.symbol for s in result.truncated] == ["FPT"]


# --- phần giao dịch/mốc không đổi khi tắt posts ---------------------------

def test_with_posts_tat_thi_khong_goi_toi_feed_bai(db, monkeypatch):
    def boom(*a, **kw):
        raise AssertionError("khong duoc goi feed bai khi with_posts=False")

    monkeypatch.setattr(posts_mod, "fetch_posts_paged", boom)
    _no_structured(monkeypatch)
    result = ingest.ingest(["FPT"], db_path=db, with_posts=False)
    assert result.total_posts == 0
    assert not result.failed


def test_mot_ma_loi_khong_giet_ca_luot(db, monkeypatch):
    def flaky(symbol, *a, **kw):
        if symbol == "FPT":
            raise RuntimeError("HTTP 500")
        return []

    monkeypatch.setattr(ingest.fireant, "holder_transactions", flaky)
    monkeypatch.setattr(ingest.fireant, "timescale_marks", lambda *a, **kw: [])
    result = ingest.ingest(["FPT", "HPG"], db_path=db, with_posts=False)
    assert [f.symbol for f in result.failed] == ["FPT"]
    assert len(result.symbols) == 2
