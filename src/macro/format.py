"""Toàn bộ câu chữ tiếng Việt của tầng ngành — một chỗ, như ``src/ta/format.py``.

Sửa một câu ở đây là cả terminal lẫn file HTML đổi theo. Đó là lý do file HTML
không tự viết chữ mà render lại markdown của module này.
"""
import html as html_escape
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence

from src.macro import members as members_mod
from src.macro import rrg
from src.macro.score import Board, SectorScore
from src.macro.verdict import STANCE_VN, Verdict

DISCLAIMER = (
    "*Đây là số liệu kỹ thuật và mô tả hiện trạng, không phải khuyến nghị đầu "
    "tư. Không có phần nào ở đây là dự báo.*"
)


def _pct(v: Optional[float], digits: int = 1) -> str:
    return "—" if v is None else f"{v:+.{digits}f}"


def _bar(points: float, cap: float, width: int = 10) -> str:
    if cap <= 0:
        return ""
    filled = int(round(points / cap * width))
    return "█" * max(0, min(width, filled)) + "·" * (width - max(0, min(width, filled)))


# ---------------------------------------------------------------------------
def format_board(board: Board, top: int = 25,
                 show_components: bool = True) -> str:
    """Bảng ngành cho terminal. Điểm **không bao giờ** đứng một mình."""
    lines = [f"# Bảng ngành — {board.as_of}", "",
             f"Dựng lúc {board.generated} · {len(board.rows)} ngành", ""]

    # Kết luận hiệu chuẩn đứng TRÊN bảng, không phải chú thích cuối trang: nó
    # quyết định người đọc được phép làm gì với thứ tự bên dưới.
    lines += ["> " + board.calibration.replace("\n", "\n> "), ""]

    lines += ["| # | Ngành | Cấp | Điểm | Mạnh/yếu | RRG | Độ rộng | Dòng tiền | Nền tảng | Tin |",
              "|--:|---|--:|--:|--:|--:|--:|--:|--:|--:|"]
    for i, r in enumerate(board.rows[:top], 1):
        cells = {c.key: c for c in r.components}

        def val(key: str) -> str:
            c = cells.get(key)
            if c is None or not c.measured:
                return "—"
            return f"{c.points:.0f}"

        news = ("—" if r.news_score is None else f"{r.news_score:+.0f}")
        lines.append(
            f"| {i} | **{r.name}** `{r.code}` | {r.level} | **{r.base:.0f}** | "
            f"{val('relative')} | {val('rotation')} | {val('breadth')} | "
            f"{val('flow')} | {val('fundamental')} | {news} |")

    lines += ["",
              "Cột `Tin` **để trống** nghĩa là chưa ai chấm — khác hẳn *đã chấm "
              "và thấy trung tính*. Điểm đo được và điểm tin **không cộng vào "
              "nhau** ở bảng này.", ""]

    if show_components:
        lines += ["---", "", "## Điểm tháo ra từng thành phần", ""]
        for r in board.rows[:top]:
            lines += format_row(r).splitlines() + [""]

    lines += ["---", "", DISCLAIMER]
    return "\n".join(lines)


def format_row(r: SectorScore) -> str:
    """Một ngành: điểm + mọi thành phần + lý do từng con số."""
    lines = [f"### {r.name} (`{r.code}`, cấp {r.level}) — **{r.base:.1f}"
             f"/{r.measured_caps:.0f}**"]
    if r.gaps:
        lines.append(f"*Chưa đo được: {', '.join(r.gaps)} — phần trần tương ứng "
                     f"bị trừ khỏi mẫu số, không tính là 0.*")
    lines.append("")
    for c in r.components:
        if not c.measured:
            lines.append(f"- {c.label}: **chưa đo được** — {c.detail}")
            continue
        lines.append(f"- {c.label}: **{c.points:.1f}**/{c.cap:.0f} "
                     f"`{_bar(c.points, c.cap)}` — {c.detail}")
    if r.news_score is not None:
        lines += ["", f"- Tin: **{r.news_score:+.0f}**/25 — {r.news_label} "
                      f"*(nhận định của {r.news_source or 'không rõ'}, không "
                      f"phải phép đo)*"]
    else:
        lines += ["", "- Tin: **chưa chấm** — chạy `sector_evidence` rồi "
                      "`sector_submit`"]
    return "\n".join(lines)


def format_sector(code: str, r: SectorScore, v: Optional[Verdict] = None,
                  rrg_view: Optional[rrg.RrgView] = None,
                  membership: Optional[members_mod.Membership] = None,
                  calibration: str = "") -> str:
    """Hồ sơ một ngành."""
    from src.macro.verdict import format_verdict

    lines = [f"# {r.name} (`{code}`) — {r.as_of}", ""]
    if calibration:
        lines += ["> " + calibration.replace("\n", "\n> "), ""]

    if membership:
        cov = "—" if membership.coverage is None else f"{membership.coverage:.0%}"
        lines += [f"**{membership.listed} mã niêm yết** trên cả ba sàn · rổ "
                  f"`data/` có **{len(membership.in_data)}** ({cov}): "
                  f"{', '.join(membership.in_data) or 'không mã nào'}", "",
                  "*Chỉ số ngành chạy theo con số thứ nhất, không phải rổ của "
                  "bạn — một ngành mạnh với độ phủ thấp nghĩa là phần lớn sức "
                  "mạnh nằm ở mã bạn không có.*", ""]

    lines += [format_row(r), ""]

    if rrg_view and rrg_view.rs is not None:
        lines += ["## Vòng xoay RRG", "",
                  f"- RS-Ratio **{rrg_view.rs}** · RS-Momentum **{rrg_view.rm}** "
                  f"→ góc **{rrg_view.label}** ({rrg.QUADRANT_NOTE.get(rrg_view.quadrant, '')})",
                  f"- Đã ở góc này **{rrg_view.sessions_in_quadrant} phiên**"
                  + (f", trước đó *{rrg.QUADRANT_VN.get(rrg_view.prev_quadrant, '—')}*"
                     if rrg_view.prev_quadrant else ""),
                  f"- 5 phiên: RS {_pct(rrg_view.rs_delta_5, 2)} · "
                  f"RM {_pct(rrg_view.rm_delta_5, 2)}"]
        if rrg_view.note:
            lines.append(f"- ⚠️ {rrg_view.note}")
        lines.append("")

    lines += ["## Nhận định", ""]
    lines.append(format_verdict(v) if v else
                 "*Chưa có nhận định cho phiên này.* Chạy `sector_evidence` để "
                 "lấy gói bằng chứng, đọc, rồi nộp qua `sector_submit`. "
                 "**Chưa có nhận định** khác *nhận định trung tính*.")
    lines += ["", "---", "", DISCLAIMER]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# HTML — tự chứa, không CDN
# ---------------------------------------------------------------------------
_CSS = """
:root{--bg:#fff;--fg:#1a1a1a;--mut:#666;--line:#e3e3e3;--up:#0a7a3d;--dn:#b3261e;
--hd:#f6f7f9;--warn:#fff4e5;--warnb:#d97706}
*{box-sizing:border-box}
body{margin:0;padding:24px;font:14px/1.6 -apple-system,BlinkMacSystemFont,
"Segoe UI",Roboto,Helvetica,Arial,sans-serif;color:var(--fg);background:var(--bg)}
.wrap{max-width:1180px;margin:0 auto}
h1{font-size:24px;margin:0 0 4px}h2{font-size:18px;margin:28px 0 8px}
h3{font-size:15px;margin:20px 0 6px}
.sub{color:var(--mut);margin-bottom:16px}
.note{background:var(--warn);border-left:3px solid var(--warnb);padding:12px 14px;
margin:16px 0;border-radius:4px}
table{border-collapse:collapse;width:100%;margin:12px 0;font-size:13px}
th,td{border-bottom:1px solid var(--line);padding:7px 9px;text-align:right}
th:nth-child(2),td:nth-child(2){text-align:left}
th{background:var(--hd);font-weight:600;cursor:pointer;user-select:none;
position:sticky;top:0}
th:hover{background:#eceef1}
tbody tr:hover{background:#fafbfc}
.score{font-weight:700}
.bar{display:inline-block;height:8px;border-radius:2px;background:#4a7fd4;
vertical-align:middle}
.barbg{display:inline-block;width:70px;height:8px;border-radius:2px;
background:var(--line);vertical-align:middle;margin-right:6px}
.mut{color:var(--mut)}
.comp{margin:4px 0;font-size:13px}
details{margin:8px 0}summary{cursor:pointer;font-weight:600}
@media(max-width:640px){body{padding:14px}table{font-size:12px}}
@media(prefers-color-scheme:dark){:root:not([data-theme=light]){
--bg:#16181c;--fg:#e8e8e8;--mut:#9aa0a6;--line:#2a2e35;--hd:#1e2127;
--warn:#2a2418;--warnb:#d97706}
tbody tr:hover{background:#1c1f25}th:hover{background:#252932}}
"""

_JS = """
document.querySelectorAll('table').forEach(function(t){
  t.querySelectorAll('th').forEach(function(th,i){
    th.addEventListener('click',function(){
      var body=t.tBodies[0],rows=Array.from(body.rows);
      var asc=th.dataset.asc!=='1';
      rows.sort(function(a,b){
        var x=a.cells[i].dataset.v||a.cells[i].textContent.trim();
        var y=b.cells[i].dataset.v||b.cells[i].textContent.trim();
        var nx=parseFloat(String(x).replace(/[^0-9.+-]/g,''));
        var ny=parseFloat(String(y).replace(/[^0-9.+-]/g,''));
        if(!isNaN(nx)&&!isNaN(ny))return asc?nx-ny:ny-nx;
        return asc?String(x).localeCompare(String(y)):String(y).localeCompare(String(x));
      });
      t.querySelectorAll('th').forEach(function(o){o.dataset.asc='';});
      th.dataset.asc=asc?'1':'0';
      rows.forEach(function(r){body.appendChild(r);});
    });
  });
});
"""


def _esc(text: Any) -> str:
    return html_escape.escape(str(text if text is not None else ""))


def _cell_bar(points: float, cap: float) -> str:
    if cap <= 0:
        return "—"
    w = max(0, min(70, int(round(points / cap * 70))))
    return (f'<span class="barbg"><span class="bar" style="width:{w}px"></span>'
            f'</span>{points:.0f}')


def board_html(board: Board) -> str:
    """File HTML tự chứa — CSS và JS nhúng thẳng, không link CDN.

    Cùng ràng buộc với ``dossier.py``: file còn phải mở được khi offline hoặc
    sau khi gửi đi nơi khác.
    """
    rows = []
    for i, r in enumerate(board.rows, 1):
        cells = {c.key: c for c in r.components}

        def td(key: str) -> str:
            c = cells.get(key)
            if c is None or not c.measured:
                return '<td class="mut" data-v="-1">chưa đo</td>'
            return (f'<td data-v="{c.points}" title="{_esc(c.detail)}">'
                    f'{_cell_bar(c.points, c.cap)}</td>')

        news = ('<td class="mut" data-v="-99">chưa chấm</td>'
                if r.news_score is None
                else f'<td data-v="{r.news_score}">{r.news_score:+.0f}</td>')
        comps = "".join(
            f'<div class="comp">{_esc(c.label)}: '
            + (f'<b>{c.points:.1f}</b>/{c.cap:.0f} — {_esc(c.detail)}'
               if c.measured else f'<span class="mut">chưa đo được — {_esc(c.detail)}</span>')
            + "</div>"
            for c in r.components)
        rows.append(
            f'<tr><td data-v="{i}">{i}</td>'
            f'<td><b>{_esc(r.name)}</b> <span class="mut">{_esc(r.code)}</span>'
            f'<details><summary class="mut">thành phần</summary>{comps}</details></td>'
            f'<td data-v="{r.level}">{r.level}</td>'
            f'<td class="score" data-v="{r.base}">{r.base:.0f}</td>'
            + td("relative") + td("rotation") + td("breadth") + td("flow")
            + td("fundamental") + news + "</tr>")

    return f"""<!doctype html>
<html lang="vi"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Bảng ngành — {_esc(board.as_of)}</title>
<style>{_CSS}</style></head><body><div class="wrap">
<h1>Bảng ngành — {_esc(board.as_of)}</h1>
<div class="sub">Dựng lúc {_esc(board.generated)} · {len(board.rows)} ngành ·
bấm tiêu đề cột để sắp xếp</div>
<div class="note">{_esc(board.calibration)}</div>
<table><thead><tr>
<th>#</th><th>Ngành</th><th>Cấp</th><th>Điểm</th><th>Mạnh/yếu</th>
<th>RRG</th><th>Độ rộng</th><th>Dòng tiền</th><th>Nền tảng</th><th>Tin</th>
</tr></thead><tbody>{''.join(rows)}</tbody></table>
<p class="mut">Cột <b>Tin</b> để trống nghĩa là chưa ai chấm — khác hẳn
<i>đã chấm và thấy trung tính</i>. Điểm đo được và điểm tin không cộng vào nhau.</p>
<p class="mut">{_esc(DISCLAIMER.strip('*'))}</p>
</div><script>{_JS}</script></body></html>"""
