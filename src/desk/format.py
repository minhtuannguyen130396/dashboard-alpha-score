"""Câu chữ của tầng bàn phân tích — tập trung một chỗ, như ``ta/format.py``.

Mọi dataclass ở các module bên cạnh giữ nguyên chất; chỗ duy nhất biến chúng
thành tiếng Việt là file này, nên sửa một câu ở đây là terminal lẫn file HTML
đổi theo.
"""
from typing import Any, Dict, List, Optional, Sequence

from src.desk import calibrate_flows as cal_mod
from src.desk.estimates import Valuation
from src.desk.flows import FlowBoard, SectorFlow, SymbolFlow, sort_rows
from src.desk.ledger import Entry, Standing

DISCLAIMER = ("_Số liệu kỹ thuật và dòng tiền, không phải khuyến nghị đầu tư._")


def _bn(value: Optional[float], digits: int = 1) -> str:
    if value is None:
        return "—"
    return f"{value:+,.{digits}f}"


def _pct(value: Optional[float], digits: int = 1) -> str:
    return "—" if value is None else f"{value:+,.{digits}f}%"


# ---------------------------------------------------------------------------
# Dòng tiền
# ---------------------------------------------------------------------------
def format_symbol_flow(flow: SymbolFlow) -> str:
    if flow.is_empty:
        return f"**{flow.symbol}** — chưa đọc được giá, dòng tiền **chưa đo được**."
    note, _ = cal_mod.calibration_note()
    lines = [
        f"### {flow.symbol} — dòng tiền (phiên {flow.as_of})",
        "",
        f"- Khối ngoại phiên: `{_bn(flow.foreign_net_bn)}` tỷ · "
        f"{_pct(flow.foreign_net_pct)} giá trị khớp TB20 · {flow.streak_label}",
        f"- Cộng dồn: 5 phiên `{_bn(flow.foreign_net_5d_bn)}` tỷ · "
        f"20 phiên `{_bn(flow.foreign_net_20d_bn)}` tỷ",
    ]
    if flow.prop_available:
        lines.append(f"- Tự doanh phiên: `{_bn(flow.prop_net_bn, 2)}` tỷ · "
                     f"5 phiên `{_bn(flow.prop_net_5d_bn, 2)}` tỷ")
    else:
        lines.append("- Tự doanh: **chưa có số** trong khoảng này")
    lines.append(f"- Thanh khoản khớp lệnh TB20: `{flow.adv20_bn or 0:,.1f}` tỷ/phiên"
                 + (f" · thoả thuận phiên này {flow.pt_share_pct:g}% giá trị"
                    if flow.pt_share_pct else ""))
    for n in flow.notes:
        lines.append(f"- ⚠️ {n}")
    lines += ["", note, "", DISCLAIMER]
    return "\n".join(lines)


def _flow_row(flow: SymbolFlow) -> str:
    flags = []
    if flow.room_capped:
        flags.append("kín room")
    if flow.etf_window:
        flags.append("tuần ETF")
    if flow.pt_share_pct and flow.pt_share_pct >= 30:
        flags.append("thoả thuận")
    return (f"| {flow.symbol} | {_bn(flow.foreign_net_bn)} | "
            f"{_pct(flow.foreign_net_pct)} | {_bn(flow.foreign_net_5d_bn)} | "
            f"{flow.foreign_streak:+d} | {_bn(flow.prop_net_bn, 2)} | "
            f"{flow.adv20_bn or 0:,.0f} | {', '.join(flags) or ''} |")


def _sector_row(sec: SectorFlow) -> str:
    cover = (f"{sec.n_members}/{sec.n_total}" if sec.n_total else str(sec.n_members))
    thin = " ⚠️" if sec.thin else ""
    return (f"| {sec.name} | {cover}{thin} | {_bn(sec.foreign_net_bn)} | "
            f"{_pct(sec.foreign_net_pct)} | {_bn(sec.foreign_net_5d_bn)} |")


def format_flow_board(board: FlowBoard, by: str = "rong_pct", limit: int = 12) -> str:
    """Bảng dòng tiền cả rổ — hai đầu bảng, ngành, rồi mới tới cảnh báo."""
    if not board.rows:
        return ("⚠️ Chưa đọc được dòng tiền của mã nào — **chưa đo được**, đừng "
                "đọc thành 'không có dòng tiền'.")
    note, _ = cal_mod.calibration_note()
    m = board.market
    lines = [f"## Dòng tiền — phiên {board.as_of}", ""]
    if board.as_of_requested and board.as_of_requested != board.as_of:
        lines += [f"> Mốc yêu cầu `{board.as_of_requested}`, phiên có thật gần nhất "
                  f"`{board.as_of}`.", ""]
    if m is not None:
        lines += [
            f"- **Rổ {m.n_symbols} mã** (không phải cả sàn): khối ngoại "
            f"`{_bn(m.foreign_net_bn)}` tỷ phiên này · `{_bn(m.foreign_net_5d_bn)}` "
            f"tỷ 5 phiên",
            f"- Độ rộng dòng tiền ngoại: {m.buyers} mã mua ròng / {m.sellers} mã "
            f"bán ròng ({m.breadth_pct if m.breadth_pct is not None else '—'}%)",
            f"- Tự doanh: `{_bn(m.prop_net_bn, 1)}` tỷ" if m.prop_net_bn is not None
            else "- Tự doanh: **chưa có số**",
            "",
        ]
        if m.sessions_lag:
            lines += [f"> ⚠️ {len(m.sessions_lag)} mã dừng ở phiên khác phiên chung "
                      f"({', '.join(m.sessions_lag[:8])}…) — số của chúng nói về một "
                      "phiên khác.", ""]

    rows = sort_rows(board.rows, by)
    header = ("| Mã | Ròng (tỷ) | % TB20 | 5 phiên | Chuỗi | Tự doanh | TB20 (tỷ) | Cờ |"
              "\n|---|---:|---:|---:|---:|---:|---:|---|")
    lines += [f"### Mua ròng mạnh nhất ({limit} mã)", "", header]
    lines += [_flow_row(r) for r in rows[:limit]]
    lines += ["", f"### Bán ròng mạnh nhất ({limit} mã)", "", header]
    lines += [_flow_row(r) for r in rows[::-1][:limit]]

    if board.sectors:
        lines += ["", "### Theo ngành (ICB cấp 1)", "",
                  "| Ngành | Mã trong rổ / ngành | Ròng (tỷ) | % thanh khoản | 5 phiên |",
                  "|---|---|---:|---:|---:|"]
        lines += [_sector_row(s) for s in board.sectors]
        lines.append("")
        lines.append("> Cột thứ hai là **số mã của ngành nằm trong rổ 80 mã**, không "
                     "phải số thành viên thật của ngành. ⚠️ = dưới 3 mã, con số khi "
                     "đó là của mấy cái tên cụ thể chứ không phải của ngành.")

    if board.skipped:
        lines += ["", f"> Bỏ qua {len(board.skipped)} mã chưa đọc được giá: "
                  f"{', '.join(board.skipped[:10])}"]
    lines += ["", note, "", DISCLAIMER]
    return "\n".join(lines)


def format_flow_calibration(cal: Optional[cal_mod.FlowCalibration]) -> str:
    """Bảng hiệu chuẩn dòng tiền — dùng chung khuôn với bảng định giá.

    Hai bảng in bằng hai hàm khác nhau là hai bảng trôi xa nhau, và bản nào sai
    thì không ai biết. Khuôn chung nằm ở ``_format_calibration``.
    """
    if cal is None:
        return cal_mod.NO_CALIBRATION
    return _format_calibration("Hiệu chuẩn dòng tiền", cal, robustness=True)


# ---------------------------------------------------------------------------
# Sổ
# ---------------------------------------------------------------------------
def format_entry(entry: Entry, status: str = "", age: Optional[int] = None) -> str:
    bits = [f"**{entry.subject}** · {entry.stance_label} · {entry.confidence_label}"]
    if status:
        bits.append(status)
    if age is not None:
        bits.append(f"{age}/{entry.horizon_sessions} phiên")
    lines = [f"- {' · '.join(bits)}",
             f"  - {entry.headline}",
             f"  - Kích hoạt: {entry.trigger}",
             f"  - Huỷ khi: {entry.invalidation}"]
    if entry.target:
        lines.append(f"  - Mục tiêu: {entry.target}")
    if entry.weight_pct is not None:
        lines.append(f"  - Tỷ trọng mô phỏng: {entry.weight_pct:g}%")
    lines.append(f"  - {entry.author} · phiên {entry.session} · `{entry.entry_id}`")
    if entry.supersedes:
        lines.append(f"  - thay cho `{entry.supersedes}`")
    return "\n".join(lines)


def format_standings(rows: Sequence[Standing], title: str = "Sổ của bàn") -> str:
    if not rows:
        return (f"## {title}\n\n**Sổ trống.** Đây là *chưa có ai viết gì*, không "
                "phải *bàn này trung lập*. Ghi quan điểm đầu tiên bằng "
                "`desk_log_view`.")
    from src.desk.ledger import KINDS
    lines = [f"## {title}", ""]
    for kind, label in KINDS.items():
        mine = [s for s in rows if s.entry.kind == kind]
        if not mine:
            continue
        lines += [f"### Cấp {label} ({len(mine)})", ""]
        lines += [format_entry(s.entry, s.status_label, s.age_sessions) for s in mine]
        lines.append("")
    return "\n".join(lines)


def format_ledger_stats(stats: Dict[str, Any]) -> str:
    if not stats.get("n"):
        return ("**Sổ trống.** Không backfill được — mỗi phiên không ghi là một "
                "phiên vĩnh viễn không có gì để chấm lại.")
    from src.desk.ledger import EXPIRED, KINDS, OPEN, SUPERSEDED
    lines = [f"- Tổng {stats['n']} quan điểm · phiên đầu {stats['first_session']} → "
             f"phiên cuối {stats['last_session']}",
             f"- Người viết: {', '.join(stats['authors'])}", "",
             "| Cấp | Còn hiệu lực | Đã bị thay | Hết hạn |", "|---|---:|---:|---:|"]
    for kind, label in KINDS.items():
        slot = stats["by_kind"].get(kind)
        if not slot:
            continue
        lines.append(f"| {label} | {slot.get(OPEN, 0)} | {slot.get(SUPERSEDED, 0)} "
                     f"| {slot.get(EXPIRED, 0)} |")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Định giá dựng sẵn
# ---------------------------------------------------------------------------
#: Chênh lệch vượt ngưỡng này gần như chắc chắn là lệch đơn vị giá, không phải
#: một mã rẻ bất thường — xem ``Valuation.upside_pct``.
UPSIDE_SANITY_PCT = 300.0


def format_valuation(val: Optional[Valuation], symbol: str = "",
                     close: Optional[float] = None, unit: float = 1.0) -> str:
    if val is None:
        from src.desk import estimates as est_mod
        if est_mod.returned_empty(symbol):
            return (f"**{symbol}** — FireAnt **không tính** định giá cho mã này. Đây "
                    "là *đã hỏi và không có*, khác hẳn *chưa chạy*: đo ngày "
                    "19/09/2026 thì 27/80 mã của rổ trả rỗng và **cả 27 đều là ngân "
                    "hàng, công ty chứng khoán hoặc bảo hiểm** — mô hình của FireAnt "
                    "không phủ nhóm tài chính. Với những mã này, cột định giá phải "
                    "để trống chứ không được thay bằng một nguồn khác rồi in cùng "
                    "một cái nhãn.")
        return (f"**{symbol}** — chưa có ảnh chụp định giá **≤ mốc**. Đây là *chưa "
                "đóng băng ngày nào*, không phải *không có định giá*; chạy "
                "`python -m src.desk.freeze` để bắt đầu tích luỹ.")
    lines = [f"### {val.symbol} — định giá dựng sẵn của FireAnt "
             f"(ảnh chụp {val.snapshot_date})", ""]
    if val.stale_days:
        lines += [f"> Ảnh chụp cũ hơn mốc {val.stale_days} ngày.", ""]
    lines += ["| Mô hình | Giá | Trọng số |", "|---|---:|---:|"]
    for m in val.models:
        price = f"{m.price:,.0f}" if m.price else "—"
        weight = f"{m.weight_pct:.1f}%" if m.weight_pct is not None else "—"
        lines.append(f"| {m.name} | {price} | {weight} |")
    lines += ["", f"- **Tổng hợp: {val.composed:,.0f}**" if val.composed else
              "- Tổng hợp: —"]
    spread = val.spread_pct()
    if spread is not None:
        lines.append(f"- Độ trải giữa sáu mô hình: **{spread:g}%** của giá tổng hợp — "
                     "con số tổng hợp trông chính xác hơn thực tế đúng bằng chừng đó")
    up = val.upside_pct(close, unit)
    if up is not None and abs(up) > UPSIDE_SANITY_PCT:
        lines.append(f"- ⚠️ So với giá hiện tại ra `{up:+,.0f}%` — **con số này không "
                     "dùng được**. Chênh lệch cỡ đó gần như chắc chắn là lệch đơn vị "
                     "giá (`estimated-price` trả *đồng*, chuỗi trong `data/` là "
                     "*nghìn đồng*, hệ số ở `StockRecord.unit`), không phải một mã rẻ "
                     "bất thường. In kèm để soi lại được, không phải để đọc.")
    elif up is not None:
        lines.append(f"- So với giá hiện tại: {up:+g}%")
    lines += ["", "> Đây là **mô hình hộp đen của FireAnt**, không phải giá mục tiêu "
              "của bàn: không công bố tỷ lệ chiết khấu, giả định tăng trưởng hay kỳ "
              "EPS. Đọc nó như ý kiến của một bên thứ ba có tên — và không bao giờ "
              "lấy trung bình nó với đồng thuận CTCK hay dải định giá tự tính."]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Dải định giá lịch sử
# ---------------------------------------------------------------------------
def _format_calibration(title: str, cal: Any, robustness: bool = True) -> str:
    """Khuôn chung cho mọi bảng hiệu chuẩn của tầng bàn phân tích."""
    lines = [f"## {title} — {cal.generated}", "",
             f"Rổ `{cal.universe}` · {cal.n_symbols} mã · ngưỡng Bonferroni "
             f"`{cal.alpha:.5f}` cho {cal.n_tests} phép kiểm chính", "",
             cal.note, ""]
    if getattr(cal, "postscript", ""):
        lines += [cal.postscript, ""]
    for h in cal.hypotheses:
        mark = "✅ đạt" if h.passed else "❌ không đạt"
        lines += [f"### {h.name} — {mark}", "", f"_{h.question}_", "",
                  f"Nền cả mẫu: trung vị `{h.pool_median}`% · n `{h.pool_n}`", "",
                  "| Nhóm | n | Trung vị | Nền placebo | Chênh | % vượt TT | p |",
                  "|---|---:|---:|---:|---:|---:|---:|"]
        for b in h.buckets:
            lines.append(
                f"| {b.name} | {b.n_independent} | "
                f"{b.median_rel if b.median_rel is not None else '—'} | "
                f"{b.placebo_median if b.placebo_median is not None else '—'} | "
                f"{b.edge if b.edge is not None else '—'} | "
                f"{b.hit_rate if b.hit_rate is not None else '—'} | "
                f"{b.p_value if b.p_value is not None else '—'} |")
        lines += ["", f"→ {h.note}", ""]
    if robustness and getattr(cal, "robustness", None):
        lines += ["### Kiểm tra bền vững (đã loại phiên kín room / tuần ETF)", "",
                  "| Giả thuyết | Kết quả |", "|---|---|"]
        for h in cal.robustness:
            lines.append(f"| {h.name} | {'đạt' if h.passed else 'không đạt'} — {h.note} |")
    return "\n".join(lines)


def format_valuation_calibration(cal: Any) -> str:
    if cal is None:
        from src.desk import calibrate_valuation as vcal
        return vcal.NO_CALIBRATION
    return _format_calibration("Hiệu chuẩn dải định giá", cal, robustness=False)


def format_valuation_series(series: Any, estimate_block: str = "") -> str:
    """Dải định giá của một mã — *rẻ hay đắt so với chính nó*."""
    from src.desk import calibrate_valuation as vcal
    if series is None or series.is_empty:
        body = "\n".join(f"- ⚠️ {n}" for n in (series.notes if series else []))
        return (f"### {getattr(series, 'symbol', '')} — dải định giá\n\n"
                "**Chưa dựng được chuỗi định giá.**\n" + body)
    note, _ = vcal.calibration_note()
    p = series.points[-1]
    lines = [f"### {series.symbol} — dải định giá (phiên {series.as_of}, "
             f"kỳ {series.latest_quarter})", ""]
    if not series.comparable:
        lines += [f"> ⚠️ mới {series.quarters_known} kỳ đã công bố — phân vị bên "
                  "dưới **chưa nói được gì**.", ""]
    lines += [
        f"- Giá `{p.price:,.0f}`đ · EPS 4 quý `{p.eps_ttm or 0:,.0f}`đ · "
        f"BVPS `{p.bvps or 0:,.0f}`đ",
    ]
    for band in (series.pe, series.pb):
        if band is None:
            continue
        lines.append(f"- {band.read(5)}"
                     + (f" · dải 5 năm `{band.low}`–`{band.high}`"
                        if band.low is not None else ""))
        if band.pct.get(3) is not None:
            lines.append(f"  - 3 năm: phân vị {band.pct[3]:.0f} · trung vị "
                         f"`{band.med.get(3)}` (n {band.n.get(3)})")
    for w in series.warnings:
        lines.append(f"- ⚠️ {w}")
    for n in series.notes:
        lines.append(f"- {n}")
    if estimate_block:
        lines += ["", estimate_block]
    lines += ["", note, "", DISCLAIMER]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Lịch xúc tác
# ---------------------------------------------------------------------------
def format_calendar(cal: Any, limit: int = 25) -> str:
    if cal is None or not cal.events:
        return ("### Lịch xúc tác\n\n**Chưa có sự kiện nào trong khoảng này** — "
                "và đây là *chưa nạp được*, không phải *không có gì sắp xảy ra*.")
    lines = [f"### Lịch xúc tác {cal.start} → {cal.end}", "",
             "| Ngày | Loại | Đối tượng | Nội dung |", "|---|---|---|---|"]
    for e in cal.events[:limit]:
        mark = "" if e.certain else " ⚠️"
        lines.append(f"| {e.date} | {e.kind_label}{mark} | {e.subject} | "
                     f"{e.title} |")
    if len(cal.events) > limit:
        lines.append(f"| … | | | còn {len(cal.events) - limit} sự kiện nữa |")
    lines += ["", "> ⚠️ = **ước lượng**, không phải lịch đã công bố. Ngày đáo hạn "
              "và ngày giao dịch không hưởng quyền là sự thật lịch; mùa BCTC là "
              "suy từ chính lịch các quý trước của từng mã."]
    for n in cal.notes:
        lines.append(">")
        lines.append(f"> {n}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Đồng thuận CTCK
# ---------------------------------------------------------------------------
def format_coverage(cov: Any) -> str:
    if cov is None:
        return "Chưa đọc được kho báo cáo CTCK."
    lines = [f"### {cov.symbol} — báo cáo của các CTCK ({cov.months} tháng)", ""]
    if not cov.covered:
        lines += ["**Không có báo cáo nào trong kho.**", "", f"> {cov.note}"]
        return "\n".join(lines)
    lines += [f"- **{cov.n} báo cáo** từ {len(cov.sources)} đơn vị · gần nhất "
              f"{cov.last_date}",
              f"- Nguồn: {', '.join(cov.sources[:10])}"
              + ("…" if len(cov.sources) > 10 else "")]
    if cov.bursts:
        b = cov.bursts[-1]
        lines.append(f"- **Cụm phát hành**: {b.n} bản trong {b.start} → {b.end} "
                     f"({', '.join(b.sources[:5])}) — bản thân cụm là một sự kiện")
    lines += ["", "| Ngày | Nguồn | Tiêu đề |", "|---|---|---|"]
    for r in cov.latest:
        lines.append(f"| {r.date} | {r.source_name} | {r.title[:90]} |")
    if cov.ratings:
        lines += ["", "**Từ khuyến nghị rút được** (nguyên văn câu chứa nó):"]
        for r in cov.ratings:
            lines.append(f"- `{r.word}` ({r.where}) — {r.quote}")
    else:
        lines += ["", "> Không bản nào mang từ khuyến nghị. Đo thật trên 40 tóm "
                  "tắt: chỉ 16 bản có. Cột này trống nghĩa là **không nói**, "
                  "không phải *trung lập* — và **giá mục tiêu thì API không đưa** "
                  "(nó nằm trong thân file PDF)."]
    return "\n".join(lines)


def format_source_scores(rows: Sequence[Any], as_of: str = "") -> str:
    if not rows:
        return "Chưa đo được bảng điểm nguồn."
    enough = [r for r in rows if r.enough]
    lines = [f"### Bảng điểm các CTCK{f' (tới {as_of})' if as_of else ''}", "",
             "| Nguồn | n | CAR trước | Phản ứng ngay | CAR sau 10 phiên | % dương |",
             "|---|---:|---:|---:|---:|---:|"]
    for r in enough:
        lines.append(f"| {r.source} | {r.n} | {r.car_pre:+.2f}% | "
                     f"{r.car_immediate:+.2f}% | {r.car_post:+.2f}% | "
                     f"{r.hit_rate:.0f}% |")
    thin = [r for r in rows if not r.enough]
    if thin:
        lines += ["", f"> {len(thin)} nguồn dưới ngưỡng quan sát tối thiểu — "
                  "**không phát biểu số** cho các nguồn đó."]
    lines += ["", "> ⚠️ **Ngày báo cáo không phải ngày thông tin ra thị trường.** "
              "Khách hàng tổ chức đọc trước khi bản đó lên FireAnt, nên cửa sổ đo "
              "đã bị dịch — và sai lệch đi **một chiều**, nó làm CTCK trông như "
              "viết sau khi giá đã chạy. Cột *CAR trước* là để đo chính độ dịch "
              "đó: phần tăng đã xảy ra trước ngày phát hành.", "", DISCLAIMER]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Sổ lệnh mô phỏng, kiểm tra chéo, bảng điểm
# ---------------------------------------------------------------------------
def format_book(book: Any) -> str:
    """Sổ mô phỏng. **Tiền mặt luôn là một dòng**, không phải phần dư im lặng."""
    if book is None:
        return "## Sổ mô phỏng\n\nChưa dựng được sổ."
    lines = [f"## Sổ mô phỏng — {book.as_of}", "",
             f"- Cổ phiếu **{book.invested_pct:g}%** · tiền mặt "
             f"**{book.cash_pct:g}%**"]
    if not book.positions:
        lines += ["", "**Sổ toàn tiền mặt.**"]
        for n in book.notes:
            lines.append(f"> {n}")
        return "\n".join(lines)

    lines += ["", "| Mã | Tư thế | Tin cậy | Tỷ trọng | ATR% | Ngành | Cắt bởi |",
              "|---|---|---|---:|---:|---|---|"]
    from src.desk.ledger import CONFIDENCE, STANCES
    for p in book.positions:
        lines.append(
            f"| {p.symbol} | {STANCES.get(p.stance, p.stance)} | "
            f"{CONFIDENCE.get(p.confidence, p.confidence)} | {p.weight_pct:g}% | "
            f"{p.atr_pct if p.atr_pct is not None else '—'} | {p.sector or '—'} | "
            f"{p.capped_by or ''} |")
    lines += ["", "**Theo ngành:** "
              + " · ".join(f"{k} {v:g}%" for k, v in book.by_sector.items())]
    lines += ["", "> Trọng số do **quy tắc** tính từ nấc tin cậy và biến động của "
              "chính mã, không do model đặt: một con số phần trăm do model tự "
              "viết ra là để nó âm thầm quyết định đòn bẩy mà không ai duyệt được."]
    for n in book.notes:
        lines.append(f">\n> {n}")
    return "\n".join(lines)


def format_consistency(report: Any) -> str:
    """Kết quả kiểm tra chéo. Số vi phạm **in ra**, kể cả khi bằng 0."""
    if report is None:
        return ""
    head = ("✅ **không mâu thuẫn**" if not report.checks
            else f"{len(report.blocks)} lỗi chặn · {len(report.warns)} cảnh báo")
    lines = [f"## Kiểm tra chéo — {head}", ""]
    if not report.checks:
        lines.append("> Đã chạy đủ 5 phép kiểm trên "
                     f"{report.n_positions} vị thế và không thấy mâu thuẫn. "
                     "Đây là *đã kiểm*, không phải *chưa kiểm*.")
        return "\n".join(lines)
    for c in report.checks:
        mark = "❌" if c.level == "block" else "⚠️"
        lines.append(f"- {mark} `{c.code}` — {c.message}")
    if report.blocks:
        lines += ["", "> **Có lỗi chặn: bản này chưa xuất bản được.** Sửa rồi "
                  "chạy lại, đừng in kèm lời xin lỗi."]
    return "\n".join(lines)


def format_scorecard(card: Any) -> str:
    """Bảng điểm của chính bàn."""
    if card is None:
        return ""
    lines = [f"## Bảng điểm của bàn — {card.as_of}", ""]
    if not card.outcomes:
        lines.append(card.note or "Sổ trống.")
        return "\n".join(lines)
    lines.append(f"- {card.n_complete}/{len(card.outcomes)} quan điểm đã đủ hạn "
                 "(chỉ phần này vào thống kê)")
    if card.note:
        lines += ["", f"> {card.note}"]
    for title, groups in (("Theo cấp", card.by_kind),
                          ("Theo nấc tin cậy", card.by_confidence)):
        rows = [g for g in groups if g.n]
        if not rows:
            continue
        lines += ["", f"### {title}", "",
                  "| Nhóm | n | % đúng chiều | Trung vị tương đối | Sau chi phí | "
                  "Nền placebo | Chênh |", "|---|---:|---:|---:|---:|---:|---:|"]
        for g in rows:
            lines.append(
                f"| {g.name} | {g.n} | "
                f"{f'{g.hit_rate:.0f}%' if g.hit_rate is not None else '—'} | "
                f"{f'{g.median_rel:+.2f}%' if g.median_rel is not None else '—'} | "
                f"{f'{g.median_rel_net:+.2f}%' if g.median_rel_net is not None else '—'} | "
                f"{f'{g.placebo_median:+.2f}%' if g.placebo_median is not None else '—'} | "
                f"{f'{g.edge:+.2f}%' if g.edge is not None else '—'} |")
    lines += ["", "> Vào lệnh ở giá đóng cửa **phiên sau** phiên ra quan điểm; "
              "cột *sau chi phí* đã trừ phí + thuế + trượt giá. Lợi suất luôn so "
              "với VNINDEX, và nền placebo là mã bất kỳ cùng phiên vào, cùng thời "
              "gian nắm giữ.", "", DISCLAIMER]
    return "\n".join(lines)


def format_book_run(run: Any) -> str:
    if run is None:
        return ""
    if run.weighted_rel is None:
        return f"**Sổ {run.as_of}** — {run.note}"
    return (f"**Sổ {run.as_of}**: {run.n_positions} vị thế · cổ phiếu "
            f"{run.invested_pct:g}% · tiền mặt {run.cash_pct:g}% · đóng góp "
            f"tương đối **{run.weighted_rel:+.2f}%** (sau chi phí "
            f"{run.weighted_rel_net:+.2f}%)\n\n> {run.note}")
