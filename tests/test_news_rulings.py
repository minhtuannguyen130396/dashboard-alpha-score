"""Phán quyết cờ đỏ — mỗi test ở đây khoá một cách *im lặng* mà tầng này hỏng.

Cả tầng sinh ra từ một lỗi có thật: cùng một bài báo gắn nhiều mã thì bộ lọc
cụm từ gắn **một** nhãn xấu cho tất cả, kể cả những mã mà sự kiện đó có lợi.
Nên ca đầu tiên dưới đây là đúng ca đó, viết ngược hai chiều trên cùng một bài.

Ba kiểu hỏng còn lại đều là kiểu *không ai phát hiện được*: một cờ bị bác rồi
biến mất khỏi trang, một ứng viên chưa ai đọc trông y hệt một ứng viên đã được
duyệt, và một phán quyết bị validator loại trong im lặng trong khi ứng viên vẫn
mang điểm trừ của máy.
"""
import json
from datetime import datetime

import pytest

from src.news import format as news_format
from src.news import redflag as rf
from src.news import rulings as ru

AS_OF = datetime(2026, 9, 15)


def _post(title, post_id=1, symbol="ABC", tagged=None, description="",
          date="2026-09-01T09:00:00+07:00", title_hash=None):
    return {
        "post_id": post_id, "symbol": symbol, "title": title,
        "description": description, "date": date,
        "source": "test", "source_url": "", "is_disclosure": 0,
        "tagged_symbols": tagged if tagged is not None else [symbol],
        "title_hash": title_hash or f"h{post_id}",
    }


def _scan(symbol, rows):
    out = rf.RedFlags(symbol=symbol, as_of="2026-09-15", n_scanned=len(rows))
    out.flags = rf.scan_rows(symbol, rows, AS_OF)
    out.penalty = rf.aggregate(out.flags)
    out.level = rf.level_for(out.penalty)
    return out


def _rule(flags, ref, verdict, reason="vì tiêu đề nói vậy", level=None):
    payload = {"ref": ref, "ket_luan": verdict, "ly_do": reason}
    if level:
        payload["muc_do"] = level
    return json.dumps([payload], ensure_ascii=False)


# --- ca gốc: một tin, hai mã, hai chiều ------------------------------------
def test_cung_mot_bai_hai_ma_hai_chieu(tmp_path):
    """Đây là lỗi mà cả tầng này sinh ra để chữa.

    Một cuộc điều tra chống bán phá giá: bên bị điều tra ăn cờ đỏ, bên đề nghị
    điều tra thì ngược lại. Bộ lọc cụm từ thấy đúng một cụm và gắn đúng một
    nhãn cho cả hai — chiều của sự kiện là thứ phải đọc mới biết.
    """
    row = _post("Bộ Công Thương điều tra chống bán phá giá thép mạ nhập khẩu",
                post_id=501, symbol="ABC", tagged=["ABC", "XYZ"])
    scan_a = _scan("ABC", [row])
    scan_b = _scan("XYZ", [dict(row, symbol="XYZ")])
    assert scan_a.flags and scan_b.flags, "bộ lọc phải bắt được cả hai mã"
    assert scan_a.penalty > 0 and scan_b.penalty > 0

    for sym, scan, verdict in (("ABC", scan_a, ru.V_APPLIES),
                               ("XYZ", scan_b, ru.V_FAVOURABLE)):
        parsed, bad = ru.parse_submission(
            _rule(scan.flags, "501", verdict,
                  level="vua" if verdict == ru.V_APPLIES else None),
            symbol=sym, flags=scan.flags, source="Model X")
        assert not bad, bad
        ru.save(sym, parsed, root=tmp_path)

    judged_a = ru.apply(scan_a, root=tmp_path)
    judged_b = ru.apply(scan_b, root=tmp_path)
    assert judged_a.penalty > 0, "bên bị điều tra vẫn phải mang cờ"
    assert judged_b.penalty == 0, "bên đề nghị điều tra không được mang cờ"
    assert judged_b.dismissed and not judged_b.flags


# --- bác không có nghĩa là xoá --------------------------------------------
def test_co_bi_bac_van_in_ra_kem_ly_do_va_ten_nguoi_bac(tmp_path):
    """Một cái bác không đọc lại được là một cái bác không bác lại được."""
    scan = _scan("ABC", [_post("ABC: Chủ tịch HĐQT bị khởi tố", post_id=7)])
    parsed, _ = ru.parse_submission(
        _rule(scan.flags, "7", ru.V_UNRELATED,
              reason="bài nói về chủ tịch một công ty khác trong cùng tập đoàn"),
        symbol="ABC", flags=scan.flags, source="Claude Opus 5")
    ru.save("ABC", parsed, root=tmp_path)

    judged = ru.apply(scan, root=tmp_path)
    md = news_format.format_redflags(judged)
    assert "ABC: Chủ tịch HĐQT bị khởi tố" in md, "tiêu đề gốc phải còn"
    assert "công ty khác trong cùng tập đoàn" in md, "lý do bác phải còn"
    assert "Claude Opus 5" in md, "tên người bác phải còn"


def test_bac_het_khac_han_khong_co_co_nao(tmp_path):
    """Kho tin sạch và *có người quyết định rằng nó sạch* là hai chuyện khác."""
    scan = _scan("ABC", [_post("ABC: Chủ tịch HĐQT bị khởi tố", post_id=7)])
    parsed, _ = ru.parse_submission(
        _rule(scan.flags, "7", ru.V_UNRELATED, reason="nói về mã khác"),
        symbol="ABC", flags=scan.flags, source="Model X")
    ru.save("ABC", parsed, root=tmp_path)

    md = news_format.format_redflags(ru.apply(scan, root=tmp_path))
    assert "Không còn cờ nào sau khi đọc" in md
    assert "Không có cờ nào" not in md

    sach = rf.RedFlags(symbol="ABC", as_of="2026-09-15", n_scanned=120)
    assert "Không có cờ nào" in news_format.format_redflags(sach)


def test_bac_co_hinh_su_go_luon_co_che_chan_tu_the_tang(tmp_path):
    """Bác xong thì ``has_critical`` phải tắt — nếu không, cờ đã bác vẫn chặn.

    Đây là chỗ hai luật gặp nhau: ``thesis.redflag_conflict`` in cảnh báo khi
    kết luận nghiêng tăng mà cờ hình sự đang bật. Giữ cờ đã bác trong ``flags``
    thì cảnh báo đó bắn vào một cờ không còn hiệu lực, và người đọc học được
    cách bỏ qua nó — mất luôn cả những lần cảnh báo đúng.
    """
    scan = _scan("ABC", [_post("ABC: Chủ tịch HĐQT bị khởi tố", post_id=7)])
    assert scan.has_critical
    parsed, _ = ru.parse_submission(
        _rule(scan.flags, "7", ru.V_UNRELATED, reason="chủ tịch của công ty khác"),
        symbol="ABC", flags=scan.flags, source="Model X")
    ru.save("ABC", parsed, root=tmp_path)
    assert not ru.apply(scan, root=tmp_path).has_critical


# --- chấm lại điểm --------------------------------------------------------
def test_nac_muc_do_quyet_dinh_diem_chu_khong_phai_model(tmp_path):
    """Model chọn nấc, code tính số — cùng luật với sổ của bàn."""
    scan = _scan("ABC", [_post("ABC: Chủ tịch HĐQT bị khởi tố", post_id=7)])
    flag = scan.flags[0]
    diem = {}
    for level in ("nang", "vua", "nhe"):
        parsed, bad = ru.parse_submission(
            _rule(scan.flags, "7", ru.V_APPLIES, level=level),
            symbol="ABC", flags=scan.flags, source="Model X")
        assert not bad, bad
        ru.save("ABC", parsed, root=tmp_path)
        diem[level] = ru.apply(scan, root=tmp_path).flags[0].score
    assert diem["nang"] > diem["vua"] > diem["nhe"] > 0
    assert diem["nang"] == pytest.approx(
        flag.weight * rf.decay_factor(flag.age_days), abs=0.05)


def test_xac_nhan_dung_chu_the_go_bot_chiet_khau_cua_may(tmp_path):
    """Độ tin cậy của máy là phép **đoán** chủ thể — model vừa trả lời thẳng.

    Giữ cả hai là phạt nhẹ hai lần cho một điều đã hết là ẩn số, và nó đi một
    chiều: cờ nào máy không dám chấm nặng thì mãi mãi nhẹ, kể cả sau khi có
    người xác nhận đúng chủ thể.
    """
    # Bài không mang tiền tố mã và không nêu chức danh → máy hạ mạnh độ tin cậy.
    scan = _scan("ABC", [_post("Khởi tố vụ án tại một doanh nghiệp thép",
                               post_id=9, symbol="ABC")])
    assert scan.flags[0].confidence < 1.0
    parsed, _ = ru.parse_submission(
        _rule(scan.flags, "9", ru.V_APPLIES, level="nang",
              reason="phần mô tả nêu đích danh doanh nghiệp này"),
        symbol="ABC", flags=scan.flags, source="Model X")
    ru.save("ABC", parsed, root=tmp_path)
    judged = ru.apply(scan, root=tmp_path)
    assert judged.flags[0].score > judged.flags[0].raw_score


def test_khong_ro_giu_nguyen_diem_cua_may(tmp_path):
    """Đọc xong mà không chắc thì hiểu biết y như trước khi đọc, không tốt hơn."""
    scan = _scan("ABC", [_post("ABC: Chủ tịch HĐQT bị khởi tố", post_id=7)])
    parsed, _ = ru.parse_submission(
        _rule(scan.flags, "7", ru.V_UNCLEAR, reason="tiêu đề không nói rõ ai"),
        symbol="ABC", flags=scan.flags, source="Model X")
    ru.save("ABC", parsed, root=tmp_path)
    judged = ru.apply(scan, root=tmp_path)
    assert judged.flags[0].score == scan.flags[0].score
    assert judged.n_pending == 0, "đã đọc rồi, chỉ là không kết luận được"


def test_giu_lai_diem_may_de_in_duoc_ca_hai(tmp_path):
    scan = _scan("ABC", [_post("ABC: Chủ tịch HĐQT bị khởi tố", post_id=7)])
    parsed, _ = ru.parse_submission(
        _rule(scan.flags, "7", ru.V_APPLIES, level="nhe"),
        symbol="ABC", flags=scan.flags, source="Model X")
    ru.save("ABC", parsed, root=tmp_path)
    judged = ru.apply(scan, root=tmp_path)
    assert judged.penalty_raw > judged.penalty
    assert "máy chấm" in news_format.format_redflags(judged)


# --- chưa ai đọc ----------------------------------------------------------
def test_chua_ai_doc_khac_da_doc_va_thay_khong_sao(tmp_path):
    """Mặc định im lặng biến một bộ lọc chưa duyệt thành một bộ lọc đã duyệt."""
    scan = _scan("ABC", [_post("ABC: Chủ tịch HĐQT bị khởi tố", post_id=7)])
    md = news_format.format_redflags(ru.apply(scan, root=tmp_path))
    assert "chưa ai đọc" in md
    assert ru.apply(scan, root=tmp_path).n_pending == 1

    parsed, _ = ru.parse_submission(
        _rule(scan.flags, "7", ru.V_APPLIES, level="nang"),
        symbol="ABC", flags=scan.flags, source="Model X")
    ru.save("ABC", parsed, root=tmp_path)
    judged = ru.apply(scan, root=tmp_path)
    assert judged.n_pending == 0 and judged.fully_judged
    assert "chưa ai đọc" not in news_format.format_redflags(judged)


def test_goi_yeu_cau_phan_quyet_rong_khi_khong_con_gi_de_phan(tmp_path):
    """Lời nhắc hiện thường trực ở trạng thái rỗng thì sau hai lần không ai đọc."""
    scan = _scan("ABC", [_post("ABC: Chủ tịch HĐQT bị khởi tố", post_id=7)])
    assert "ref=7" in ru.format_pending(ru.apply(scan, root=tmp_path))
    parsed, _ = ru.parse_submission(
        _rule(scan.flags, "7", ru.V_APPLIES, level="nang"),
        symbol="ABC", flags=scan.flags, source="Model X")
    ru.save("ABC", parsed, root=tmp_path)
    assert ru.format_pending(ru.apply(scan, root=tmp_path)) == ""


# --- validator ------------------------------------------------------------
def test_thieu_ly_do_bi_loai_va_noi_ro_vi_sao():
    scan = _scan("ABC", [_post("ABC: Chủ tịch HĐQT bị khởi tố", post_id=7)])
    parsed, bad = ru.parse_submission(
        json.dumps([{"ref": "7", "ket_luan": ru.V_UNRELATED}]),
        symbol="ABC", flags=scan.flags, source="Model X")
    assert not parsed and len(bad) == 1
    assert "ly_do" in bad[0]


def test_ket_luan_dung_ma_thieu_muc_do_bi_loai():
    scan = _scan("ABC", [_post("ABC: Chủ tịch HĐQT bị khởi tố", post_id=7)])
    parsed, bad = ru.parse_submission(
        _rule(scan.flags, "7", ru.V_APPLIES), symbol="ABC",
        flags=scan.flags, source="Model X")
    assert not parsed and "muc_do" in bad[0]


def test_ref_khong_co_trong_danh_sach_bi_loai():
    """Phán quyết phải trỏ vào một cờ đang hiện, không phải một bài bất kỳ."""
    scan = _scan("ABC", [_post("ABC: Chủ tịch HĐQT bị khởi tố", post_id=7)])
    parsed, bad = ru.parse_submission(
        _rule(scan.flags, "999", ru.V_UNRELATED), symbol="ABC",
        flags=scan.flags, source="Model X")
    assert not parsed and "999" in bad[0]


def test_ket_luan_ngoai_bon_nhan_bi_loai():
    scan = _scan("ABC", [_post("ABC: Chủ tịch HĐQT bị khởi tố", post_id=7)])
    parsed, bad = ru.parse_submission(
        _rule(scan.flags, "7", "tin_xau"), symbol="ABC",
        flags=scan.flags, source="Model X")
    assert not parsed and bad


def test_source_do_code_dat_khong_doc_tu_json():
    """Để model tự khai tên là để nó tự cấp quyền đè phán quyết của người khác."""
    scan = _scan("ABC", [_post("ABC: Chủ tịch HĐQT bị khởi tố", post_id=7)])
    parsed, _ = ru.parse_submission(
        json.dumps([{"ref": "7", "ket_luan": ru.V_UNRELATED,
                     "ly_do": "x", "source": "Người khác"}]),
        symbol="ABC", flags=scan.flags, source="Model X")
    assert parsed[0].source == "Model X"


# --- kho ------------------------------------------------------------------
def test_tieu_de_doi_thi_phan_quyet_cu_het_hieu_luc(tmp_path):
    """Bài được toà soạn sửa tiêu đề thì phán quyết cũ nói về chữ không còn nữa."""
    scan = _scan("ABC", [_post("ABC: Chủ tịch HĐQT bị khởi tố", post_id=7,
                               title_hash="cu")])
    parsed, _ = ru.parse_submission(
        _rule(scan.flags, "7", ru.V_UNRELATED, reason="nói về mã khác"),
        symbol="ABC", flags=scan.flags, source="Model X")
    ru.save("ABC", parsed, root=tmp_path)

    moi = _scan("ABC", [_post("ABC: Chủ tịch HĐQT bị khởi tố, bắt tạm giam",
                              post_id=7, title_hash="moi")])
    judged = ru.apply(moi, root=tmp_path)
    assert judged.n_pending == 1, "phải quay về trạng thái chưa ai đọc"
    assert judged.penalty > 0
    assert any("đổi tiêu đề" in n for n in judged.flags[0].notes)


def test_ghi_de_thi_ban_cu_xuong_history_chu_khong_mat(tmp_path):
    scan = _scan("ABC", [_post("ABC: Chủ tịch HĐQT bị khởi tố", post_id=7)])
    for verdict, reason in ((ru.V_UNRELATED, "tưởng là mã khác"),
                            (ru.V_APPLIES, "đọc lại thì đúng là mã này")):
        parsed, _ = ru.parse_submission(
            _rule(scan.flags, "7", verdict, reason=reason,
                  level="nang" if verdict == ru.V_APPLIES else None),
            symbol="ABC", flags=scan.flags, source="Model X")
        ru.save("ABC", parsed, root=tmp_path)

    store = ru.load("ABC", root=tmp_path)
    assert store["7"].verdict == ru.V_APPLIES
    assert store["7"].history and store["7"].history[0]["verdict"] == ru.V_UNRELATED


def test_kho_rong_thi_moi_thu_giu_nguyen_nhu_truoc(tmp_path):
    """Chưa ai phán quyết gì thì kết quả phải bằng đúng bản của máy."""
    scan = _scan("ABC", [_post("ABC: Chủ tịch HĐQT bị khởi tố", post_id=7),
                         _post("ABC: Bị xử phạt vi phạm hành chính về thuế",
                               post_id=8)])
    judged = ru.apply(scan, root=tmp_path)
    assert judged.penalty == scan.penalty == judged.penalty_raw
    assert [f.score for f in judged.flags] == [f.score for f in scan.flags]
    assert not judged.dismissed


def test_ref_ben_qua_cac_luot_quet():
    """Khoá phán quyết phải bền, nếu không thì mỗi lượt quét là một lượt đọc lại."""
    rows = [_post("ABC: Chủ tịch HĐQT bị khởi tố", post_id=7)]
    assert _scan("ABC", rows).flags[0].ref == _scan("ABC", rows).flags[0].ref == "7"
    khong_id = _scan("ABC", [_post("ABC: Chủ tịch HĐQT bị khởi tố", post_id=None,
                                   title_hash="abc123")])
    assert khong_id.flags[0].ref.startswith("t")


# --- nộp cho nhiều mã trong một lượt (đường của /prospect) -----------------
def test_mot_bai_hai_ma_hai_phan_quyet_trong_mot_lan_nop(tmp_path):
    """Đọc tiêu đề một lần, phán cho từng mã — và hai mã được phép ngược nhau."""
    row = _post("Bộ Công Thương điều tra chống bán phá giá thép mạ nhập khẩu",
                post_id=77, symbol="AAA", tagged=["AAA", "BBB"])
    scans = {"AAA": _scan("AAA", [row]),
             "BBB": _scan("BBB", [dict(row, symbol="BBB")])}
    raw = json.dumps({
        "AAA": [{"ref": "77", "ket_luan": "co_loi", "ly_do": "là bên đề nghị"}],
        "BBB": [{"ref": "77", "ket_luan": "dung", "muc_do": "vua",
                 "ly_do": "là bên bị điều tra"}],
    }, ensure_ascii=False)
    by_sym, bad = ru.parse_batch(raw, scans, source="Model X")
    assert not bad, bad
    ru.save_many(by_sym, root=tmp_path)

    judged = ru.apply_many(scans, root=tmp_path)
    assert judged["AAA"].penalty == 0 and judged["AAA"].dismissed
    assert judged["BBB"].penalty > 0 and not judged["BBB"].dismissed


def test_nop_hang_loat_nhan_ca_mang_phang_co_khoa_symbol(tmp_path):
    scan = _scan("ABC", [_post("ABC: Chủ tịch HĐQT bị khởi tố", post_id=7)])
    raw = json.dumps([{"symbol": "ABC", "ref": "7", "ket_luan": "khong_ro",
                       "ly_do": "không rõ ai"}])
    by_sym, bad = ru.parse_batch(raw, {"ABC": scan}, source="Model X")
    assert not bad and by_sym["ABC"][0].verdict == ru.V_UNCLEAR


def test_phan_quyet_khong_noi_thuoc_ma_nao_bi_loai():
    """Một phán quyết không có mã thì không biết áp vào đâu."""
    scan = _scan("ABC", [_post("ABC: Chủ tịch HĐQT bị khởi tố", post_id=7)])
    by_sym, bad = ru.parse_batch(
        json.dumps([{"ref": "7", "ket_luan": "khong_ro", "ly_do": "x"}]),
        {"ABC": scan}, source="Model X")
    assert not by_sym and "symbol" in bad[0]


def test_ma_ngoai_danh_sach_dang_xet_bi_loai():
    scan = _scan("ABC", [_post("ABC: Chủ tịch HĐQT bị khởi tố", post_id=7)])
    by_sym, bad = ru.parse_batch(
        json.dumps({"XYZ": [{"ref": "7", "ket_luan": "khong_ro", "ly_do": "x"}]}),
        {"ABC": scan}, source="Model X")
    assert not by_sym and "XYZ" in bad[0]


def test_apply_many_giu_nguyen_ma_chua_ai_phan(tmp_path):
    """Cả rổ 79 mã thì phần lớn chưa ai đọc — chúng phải y nguyên bản máy."""
    scans = {"ABC": _scan("ABC", [_post("ABC: Chủ tịch HĐQT bị khởi tố",
                                        post_id=7)])}
    judged = ru.apply_many(scans, root=tmp_path)
    assert judged["ABC"].penalty == scans["ABC"].penalty
    assert judged["ABC"].n_pending == 1


# --- khối "đã bác" gọn lại ------------------------------------------------
def test_da_bac_chi_con_mot_dong_nhung_van_bac_lai_duoc(tmp_path):
    """Bỏ phần lý lẽ của bộ lọc (bộ lọc vừa bị bác), giữ tiêu đề + lý do bác."""
    scan = _scan("ABC", [_post("ABC: Chủ tịch HĐQT bị khởi tố", post_id=7)])
    parsed, _ = ru.parse_submission(
        _rule(scan.flags, "7", ru.V_UNRELATED, reason="nói về công ty khác"),
        symbol="ABC", flags=scan.flags, source="Model X")
    ru.save("ABC", parsed, root=tmp_path)

    md = news_format.format_redflags(ru.apply(scan, root=tmp_path))
    assert "ABC: Chủ tịch HĐQT bị khởi tố" in md      # tiêu đề còn
    assert "nói về công ty khác" in md                # lý do bác còn
    assert "khớp cụm" not in md.split("### Đã bác")[1]  # lý lẽ máy thì không
