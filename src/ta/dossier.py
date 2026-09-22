"""One symbol, one file: the whole deep dive with a chart you can work on.

``report.py`` embeds a matplotlib PNG — a *picture of* the structure. A dossier
draws that same structure on the interactive Lightweight Charts canvas the
desktop app uses: the consolidation box is a rectangle over the bars it actually
covers, every trendline and neckline answers *why it is drawn* on hover, the
panes scroll and zoom together. The full deep-dive text for the same session
sits underneath it in the same file.

None of the prose is written here. The markdown ``format.py`` already produces
is converted to HTML, so the file and the terminal cannot say different things —
add a sentence to ``format.py`` and it shows up in both.

Nothing is fetched when the file is opened: chart library, CSS and JS are all
inlined, so a dossier still works offline, on another machine, or as an email
attachment.
"""
import html as html_escape
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from src.analysis.market_behavior_analyzer import analyze_market_behavior
from src.news import digest as news_mod
from src.news import format as news_format
from src.news import redflag as redflag_mod
from src.news import rulings as rulings_mod
from src.reporting.chart_renderer_v2 import (
    CSS_PATH, JS_PATH, LIB_CDN, LIB_PATH,
    build_series, chart_body_html, chart_data_script, open_html_in_chrome,
)
from src.ta import asof as asof_mod
from src.ta.forecast import Forecast, check_all
from src.ta import futures as futures_mod
from src.ta.format import (
    DISCLAIMER, _n, _signed, format_deep_dive, format_forecast_list,
    format_futures_brief, format_snapshot, format_structure,
)
from src.ta.loader import PROJECT_ROOT
from src.ta.overlays import build_overlays
from src.ta.report import REPORT_CSS, _asof_html
from src.ta.snapshot import Snapshot, build_snapshot
from src.ta.structure import Structure, build_structure
from src.ta import thesis as thesis_mod

DOSSIER_DIR = PROJECT_ROOT / "reports"

#: Cửa sổ đầu mục tin tức trong hồ sơ. 20 phiên ~ một tháng giao dịch: đủ để
#: thấy cả phần "còn trôi tiếp" (cần 10 phiên sau tin) của những tin đầu cửa sổ,
#: mà chưa dài tới mức phần đầu bảng không còn liên quan tới phiên hôm nay.
NEWS_SESSIONS = 20

#: Cửa sổ quét cờ đỏ, tính bằng **ngày lịch** — cố ý dài hơn hẳn 20 phiên đầu
#: mục tin. Một vụ khởi tố bốn tháng trước không còn là "tin" theo nghĩa đầu
#: mục, nhưng nó vẫn là điều kiện mà doanh nghiệp đang vận hành bên trong.
REDFLAG_DAYS = redflag_mod.WINDOW_DAYS


@dataclass
class Dossier:
    """The written file plus the objects it was written from.

    The caller almost always wants both: the path to hand the user, and the
    same numbers as text to answer questions about in the terminal.
    """
    symbol: str
    as_of: str
    snapshot: Snapshot
    structure: Structure
    forecasts: List[Forecast] = field(default_factory=list)
    changes: List[Dict[str, Any]] = field(default_factory=list)
    path: Optional[str] = None
    #: Mốc hồi tưởng đã yêu cầu (rỗng = hồ sơ của phiên mới nhất).
    as_of_requested: str = ""
    #: Đầu mục tin tức của cửa sổ ``NEWS_SESSIONS`` phiên. ``None`` khi kho tin
    #: chưa nạp hoặc đọc hỏng — người gọi phải kiểm tra trước khi tóm tắt.
    news: Optional[Any] = None
    #: Kết luận đã có cho **đúng** phiên này, hoặc ``None``. ``None`` không phải
    #: "trung tính" — nó là *chưa ai đọc*, và file HTML nói thẳng điều đó.
    thesis: Optional[Any] = None
    #: Gói bằng chứng + hướng dẫn viết, chỉ dựng khi ``thesis is None``. Đây là
    #: thứ tầng MCP in ra để model đang gọi tool đọc rồi nộp kết luận lại.
    brief: str = ""
    #: Cờ đỏ trong ``REDFLAG_DAYS`` ngày. ``None`` = **chưa quét được**, khác
    #: hẳn một ``RedFlags`` rỗng (= đã quét, không thấy gì). Người gọi phải giữ
    #: đúng phân biệt đó khi tóm tắt.
    redflags: Optional[Any] = None

    @property
    def needs_thesis(self) -> bool:
        return self.thesis is None

    @property
    def pending_flags(self) -> int:
        """Ứng viên cờ đỏ chưa model nào đọc — vẫn đang mang điểm của máy.

        Độc lập với ``needs_thesis``: một mã đã có kết luận từ phiên trước vẫn
        có thể vừa dính thêm một ứng viên mới trong cửa sổ 180 ngày, và ứng
        viên đó phải được đọc dù không ai viết lại kết luận.
        """
        return self.redflags.n_pending if self.redflags is not None else 0

    @property
    def markdown(self) -> str:
        """What ``/deep-dive`` would print for this symbol."""
        return format_deep_dive(self.snapshot, self.structure)


# ---------------------------------------------------------------------------
# markdown → html
# ---------------------------------------------------------------------------
# Only the subset format.py emits: headings, pipe tables, bullets, **bold**,
# `code`, whole-line _italics_. A real markdown library would accept far more
# than we produce and drag in a dependency for it.
_HEADING_RE = re.compile(r"^(#{1,4})\s+(.*)$")
_BULLET_RE = re.compile(r"^\s*-\s+(.*)$")
_ITALIC_LINE_RE = re.compile(r"^_(.+)_$")


def _esc(text: Any) -> str:
    return html_escape.escape(str(text if text is not None else "—"))


def _inline(text: str) -> str:
    """Escape first, then re-apply the markup — never the other way round."""
    out = _esc(text)
    out = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", out)
    out = re.sub(r"`([^`]+)`", r"<code>\1</code>", out)
    return out


def _cells(row: str) -> List[str]:
    return [c.strip() for c in row.strip().strip("|").split("|")]


def _is_separator(cells: List[str]) -> bool:
    return bool(cells) and all(c and set(c) <= set("-: ") for c in cells)


def _table_html(rows: List[List[str]]) -> str:
    """A pipe table; a trailing colon in the separator means right-aligned."""
    if not rows:
        return ""
    header, rest = rows[0], rows[1:]
    align = [""] * len(header)
    if rest and _is_separator(rest[0]):
        align = ["num" if c.endswith(":") else "" for c in rest[0]]
        rest = rest[1:]

    def klass(i: int) -> str:
        return f' class="{align[i]}"' if i < len(align) and align[i] else ""

    out = ['<div class="scroll"><table>', "<tr>"]
    out += [f"<th{klass(i)}>{_inline(c)}</th>" for i, c in enumerate(header)]
    out.append("</tr>")
    for row in rest:
        out.append("<tr>")
        out += [f"<td{klass(i)}>{_inline(c)}</td>" for i, c in enumerate(row)]
        out.append("</tr>")
    out.append("</table></div>")
    return "".join(out)


def _md_to_html(md: str, headings: Optional[List[Tuple[str, str, int]]] = None) -> str:
    """Render the markdown; append ``(id, title, level)`` per heading, for the nav."""
    lines = md.splitlines()
    out: List[str] = []
    in_list = False
    i = 0

    def close_list() -> None:
        nonlocal in_list
        if in_list:
            out.append("</ul>")
            in_list = False

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        if not stripped:
            close_list()
            i += 1
            continue

        if stripped.startswith("|"):
            close_list()
            rows = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                rows.append(_cells(lines[i]))
                i += 1
            out.append(_table_html(rows))
            continue

        heading = _HEADING_RE.match(stripped)
        if heading:
            close_list()
            level = max(2, len(heading.group(1)))
            title = heading.group(2).strip()
            if level in (2, 3) and headings is not None:
                anchor = f"muc-{len(headings) + 1}"
                headings.append((anchor, title, level))
                out.append(f'<h{level} id="{anchor}">{_inline(title)}</h{level}>')
            else:
                out.append(f"<h{level}>{_inline(title)}</h{level}>")
            i += 1
            continue

        bullet = _BULLET_RE.match(line)
        if bullet:
            if not in_list:
                out.append('<ul class="notes">')
                in_list = True
            out.append(f"<li>{_inline(bullet.group(1))}</li>")
            i += 1
            continue

        if in_list and line.startswith("  "):
            # A continuation line under the previous bullet (forecast notes).
            out[-1] = out[-1][: -len("</li>")] + \
                f'<div class="sub">{_inline(stripped)}</div></li>'
            i += 1
            continue

        close_list()
        italic = _ITALIC_LINE_RE.match(stripped)
        if italic:
            out.append(f'<p class="muted"><em>{_inline(italic.group(1))}</em></p>')
        elif stripped.startswith("→"):
            out.append(f'<p class="verdict">{_inline(stripped)}</p>')
        elif stripped.startswith("⚠️"):
            out.append(f'<p class="warn">{_inline(stripped)}</p>')
        elif stripped.startswith(">"):
            out.append(f'<p class="asof">{_inline(stripped.lstrip("> ").strip())}</p>')
        else:
            out.append(f"<p>{_inline(stripped)}</p>")
        i += 1

    close_list()
    return "\n".join(out)


def _without_disclaimer(md: str) -> str:
    """One disclaimer per document, at the foot — not once per section."""
    return md[: -len(DISCLAIMER)].rstrip() if md.rstrip().endswith(DISCLAIMER) else md


def _without_asof_note(md: str) -> str:
    """Bỏ dải hồi tưởng khỏi phần chữ — file HTML đã in nó ngay trên biểu đồ.

    Bản markdown giữ nguyên dải này (terminal không có phần đầu trang để mang),
    nên chỗ cắt nằm ở đây chứ không ở ``format.py``.
    """
    kept = [line for line in md.splitlines() if not line.lstrip().startswith(">")]
    return "\n".join(kept).strip()


# ---------------------------------------------------------------------------
# page assembly
# ---------------------------------------------------------------------------
_EXTRA_CSS = """
.wrap { max-width: 1280px; margin: 0 auto; display: flex; flex-direction: column; }
body { padding: 20px 24px 64px; }
#header { margin-bottom: 14px; }

/* The shared chart markup puts its read-out panels above the panes. In a
   dossier the chart has to be the first thing on screen — otherwise a page of
   text pushes it below the fold — so the same DOM is reordered here instead of
   being forked into a second skeleton. */
.redflag-banner { order: 0; }
#header { order: 1; } #legend { order: 2; } #charts-container { order: 3; }
.hint { order: 4; } #hover-panel { order: 5; } #structure-panel { order: 6; }
.toc { order: 7; } .sections { order: 8; } .foot { order: 9; }
#header .right { display: flex; flex-wrap: wrap; gap: 8px; justify-content: flex-end; }
.chip { background: #0f1117; border: 1px solid #21262d; border-radius: 999px;
        padding: 5px 12px; font-size: 12px; color: #8b949e; white-space: nowrap; }
.chip b { color: #f0f6fc; font-weight: 600; }
.hint { color: #6e7681; font-size: 12px; margin: -8px 0 14px; }
.toc { display: flex; flex-wrap: wrap; gap: 8px 18px; margin: 0 0 8px;
       padding: 12px 18px; background: #161b22; border: 1px solid #21262d;
       border-radius: 8px; font-size: 13px; }
.toc a { color: #58a6ff; text-decoration: none; }
.toc a.lv2 { color: #f0f6fc; font-weight: 600; }
.toc a:hover { text-decoration: underline; }
.toc a.in-detail { color: #6e7681; font-weight: 400; }
h2, h3 { scroll-margin-top: 12px; }
code { background: #161b22; border: 1px solid #21262d; border-radius: 4px;
       padding: 1px 5px; font-size: 13px; color: #d2a8ff;
       font-family: ui-monospace, SFMono-Regular, Consolas, monospace; }
th code, td code { background: none; border: none; padding: 0; }
ul.notes { margin: 8px 0 8px 20px; }
ul.notes strong { color: #f0f6fc; }
.verdict { color: #f0f6fc; border-left: 3px solid #d2a8ff; padding-left: 12px;
           margin: 10px 0; }
.warn { color: #e3b341; }
.muted { color: #6e7681; font-size: 13px; }

/* Dải cờ đỏ. Nằm trên cả tên mã: nếu chủ tịch vừa bị khởi tố thì đó là thứ
   phải đọc trước khi đọc bất kỳ con số nào của trang này. */
.redflag-banner { border-radius: 8px; padding: 12px 16px; margin: 0 0 14px;
                  border: 1px solid; }
.redflag-banner.rf-critical { background: #2d0f12; border-color: #f85149;
                              box-shadow: inset 3px 0 0 #f85149; }
.redflag-banner.rf-warn { background: #2b220c; border-color: #e3b341;
                          box-shadow: inset 3px 0 0 #e3b341; }
.rf-head { font-size: 15px; font-weight: 700; color: #ffa198;
           display: flex; flex-wrap: wrap; gap: 10px; align-items: baseline; }
.rf-warn .rf-head { color: #e3b341; }
.rf-window { font-size: 12px; font-weight: 400; color: #8b949e; }
.rf-list { margin: 8px 0 0; padding-left: 20px; }
.rf-list li { color: #f0f6fc; font-size: 13px; margin: 5px 0; }
.rf-list b { color: #ffa198; }
.rf-warn .rf-list b { color: #e3b341; }
.rf-meta { display: block; color: #8b949e; font-size: 12px; }
.rf-more { color: #8b949e; font-size: 12px; margin-top: 8px; }
/* Trạng thái đọc. ⏳ phải nổi hơn ✅: một cờ đã được model đọc là chuyện bình
   thường, còn một cờ chưa ai đọc nghĩa là con số điểm trừ bên cạnh nó mới chỉ
   do cụm từ chấm — đó mới là thứ người đọc cần nhận ra ngay. */
.rf-pending { color: #e3b341; }
.rf-judged { color: #7ee787; }

/* Hai tầng của trang. Khác nhau về sắc độ chứ không chỉ về vị trí: tầng trên
   là một ý kiến, tầng dưới là số đo, và người đọc phải thấy được ranh giới đó
   mà không cần đọc chữ. */
.verdict-layer h2 { border-bottom-color: #d2a8ff44; }
.verdict-layer > h2:first-child { margin-top: 8px; font-size: 22px; }
.verdict-layer table { max-width: 640px; }
.verdict-layer table td:first-child { width: 130px; color: #8b949e; }
.verdict-layer h3 { color: #e3b341; font-size: 15px; margin: 20px 0 6px; }

.detail-layer { margin-top: 40px; border: 1px solid #21262d; border-radius: 8px;
                background: #12161d; }
.detail-layer > summary { cursor: pointer; padding: 14px 18px; list-style: none;
                          display: flex; flex-wrap: wrap; align-items: baseline;
                          gap: 4px 12px; border-radius: 8px; }
.detail-layer > summary::-webkit-details-marker { display: none; }
.detail-layer > summary::before { content: '▸'; color: #6e7681; margin-right: 6px; }
.detail-layer[open] > summary::before { content: '▾'; }
.detail-layer > summary:hover { background: #161b22; }
.dg-title { color: #8b949e; font-weight: 600; letter-spacing: .04em; font-size: 14px; }
.dg-hint { color: #6e7681; font-size: 12.5px; }
.dg-body { padding: 0 18px 18px; border-top: 1px solid #21262d; }
.dg-body h2:first-child { margin-top: 20px; }
"""


#: Một liên kết trỏ vào trong khối DIỄN GIẢI đang gập sẽ không cuộn tới đâu cả
#: — trình duyệt không tự mở ``<details>`` để tới một `id` bên trong nó. Mười
#: dòng này vá đúng chỗ đó, cho cả mục lục lẫn liên kết dán từ ngoài vào.
_TOC_SCRIPT = """<script>
(function () {
  function reveal(hash) {
    if (!hash || hash.length < 2) return;
    var el = document.getElementById(hash.slice(1));
    if (!el) return;
    var box = el.closest('details');
    if (box && !box.open) { box.open = true; }
    el.scrollIntoView({ block: 'start' });
  }
  document.querySelectorAll('.toc a').forEach(function (a) {
    a.addEventListener('click', function () { reveal(a.getAttribute('href')); });
  });
  if (location.hash) { setTimeout(function () { reveal(location.hash); }, 0); }
})();
</script>"""


def _read(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def _library_tag() -> str:
    """Inline the vendored chart library; fall back to the CDN if it is gone.

    Inlining is what makes the file self-contained — the fallback only keeps a
    checkout without the vendor directory from producing a blank chart.
    """
    lib = Path(LIB_PATH)
    if lib.is_file():
        return "<script>" + lib.read_text(encoding="utf-8").replace(
            "</script", r"<\/script") + "</script>"
    return f'<script src="{LIB_CDN}"></script>'


def _chips(snap, structure) -> List[str]:
    """The numbers worth seeing before scrolling: price, momentum, the box."""
    chips: List[str] = []
    if snap.bars:
        change = snap.price.get("change_pct")
        css = "pos" if (change or 0) >= 0 else "neg"
        chips.append(f'<span class="chip">Đóng cửa <b>{_n(snap.price["close"])}</b> '
                     f'<span class="{css}">{_signed(change)}</span></span>')
        chips.append(f'<span class="chip">RSI14 <b>{_n(snap.momentum["rsi14"], 1)}</b></span>')
        arrow = {"up": "↑", "down": "↓"}.get(snap.adx.get("direction", ""), "→")
        chips.append(f'<span class="chip">ADX14 <b>{_n(snap.adx.get("adx"), 1)}</b> '
                     f'{arrow}</span>')
        chips.append(f'<span class="chip">ATR14 <b>{_n(snap.momentum["atr14"])}</b> '
                     f'({_n(snap.momentum["atr_pct"], 1)}%)</span>')
        chips.append(f'<span class="chip">RVOL <b>{_n(snap.volume["rvol"])}</b></span>')
    box = structure.box
    if box is not None:
        chips.append(f'<span class="chip">Hộp {_esc(box.id)} '
                     f'<b>{_n(box.bottom)}–{_n(box.top)}</b></span>')
    if structure.pattern is not None and structure.pattern.kind != "none":
        chips.append(f'<span class="chip">{_esc(structure.pattern.name)}</span>')
    return chips


def _thesis_card(thesis) -> Optional[Dict[str, Any]]:
    """Nội dung **rút gọn** cho thẻ ngay dưới biểu đồ.

    Thẻ này trước đây in tên mẫu hình rồi đổ cả danh sách ``brief`` xuống dưới
    — tức là lại một chỗ nữa bắt người đọc tự kết luận, ngay tại chỗ mắt rơi
    vào đầu tiên sau biểu đồ. Giờ nó mang đúng bốn thứ quyết định: nghiêng về
    đâu, vào bằng gì, sai ở đâu, mục tiêu đâu. Phần còn lại đã có cả trang
    bên dưới để nói.

    ``None`` khi chưa có kết luận — JS lùi về hành vi cũ thay vì vẽ một thẻ
    trống trông như một nhận định trung tính.
    """
    if thesis is None:
        return None
    rows = [("Kích hoạt", thesis.trigger), ("Mục tiêu", thesis.target),
            ("Huỷ nếu", thesis.invalidation), ("Tin cậy", thesis.confidence)]
    return {
        "stance_label": thesis.stance_label,
        "tone": thesis.tone,
        "headline": thesis.headline,
        "rows": [{"label": k, "value": v} for k, v in rows if v],
        "source": thesis.source,
        "written_at": thesis.written_at,
    }


def _redflag_banner(symbol: str, redflags: Optional[Any]) -> str:
    """Dải cờ đỏ ở **đỉnh trang**, trên cả tên mã và biểu đồ.

    Chỉ hiện khi có cờ. Đây là ngoại lệ có chủ ý của nguyên tắc "rỗng thì vẫn
    in một ô trống": dải này là *báo động*, và một báo động hiện thường trực ở
    trạng thái "không có gì" thì sau hai tuần không ai còn nhìn nó. Vế "đã quét
    và không thấy gì" vẫn được nói, nhưng nói ở khối chữ bên dưới.
    """
    if redflags is None or redflags.is_empty:
        return ""
    top = redflags.flags[:3]

    def _state(f) -> str:
        """Một cờ chưa ai đọc **phải** nói ra điều đó ngay trên dải báo động.

        Dải này là thứ duy nhất người đọc chắc chắn nhìn thấy. In một con số
        điểm trừ ở đây mà không nói nó do máy hay do người chấm là để một bộ
        lọc cụm từ mượn uy tín của một lượt đọc chưa hề xảy ra.
        """
        r = f.ruling or {}
        if not r:
            return ' · <span class="rf-pending">⏳ chưa ai đọc</span>'
        who = _esc(r.get("source") or "không rõ")
        return f' · <span class="rf-judged">✅ {who} đã đọc</span>'

    items = "".join(
        f'<li><b>[{_esc(f.label)}]</b> {_esc(f.title)}'
        f'<span class="rf-meta">{_esc(f.published[:10])} · '
        f'{f.age_days} ngày trước · −{f.score:.0f} điểm{_state(f)}</span></li>'
        for f in top
    )
    more = ""
    if len(redflags.flags) > len(top):
        more = (f'<div class="rf-more">… còn {len(redflags.flags) - len(top)} '
                f'đầu mục nữa trong khối “Cờ đỏ” ngay dưới biểu đồ.</div>')
    # Số ứng viên đã bị bác đứng ngay trên dải: người đọc phải biết là đã có
    # người gỡ bớt cờ, và gỡ bao nhiêu, chứ không chỉ thấy phần còn lại.
    if redflags.dismissed:
        more += (f'<div class="rf-more">{len(redflags.dismissed)} ứng viên khác '
                 f'đã bị bác sau khi đọc (máy chấm −{redflags.penalty_raw:.0f} '
                 f'trước đó) — lý do nằm trong khối “Cờ đỏ”.</div>')
    cls = "rf-critical" if redflags.level == redflag_mod.LEVEL_CRITICAL else "rf-warn"
    return (
        f'<div class="redflag-banner {cls}">'
        f'<div class="rf-head">🚩 {_esc(redflags.level_label)} — '
        f'{_esc(symbol)} · điểm trừ −{redflags.penalty:.0f}'
        f'<span class="rf-window">{redflags.window_days} ngày gần nhất · '
        f'{len(redflags.flags)} đầu mục</span></div>'
        f'<ul class="rf-list">{items}</ul>{more}'
        f'</div>'
    )


def render_dossier(
    snap,
    structure,
    forecasts: Optional[List[Any]] = None,
    changes: Optional[List[Dict[str, Any]]] = None,
    futures_md: str = "",
    basis: Optional[Dict[str, Dict[str, Any]]] = None,
    news_md: str = "",
    thesis: Optional[Any] = None,
    redflags: Optional[Any] = None,
) -> str:
    """Build the HTML string — no file, no data loading, so it is easy to test.

    Trang có **hai tầng, không trộn vào nhau**:

    * *Trên* — kết luận: thẻ ngay dưới biểu đồ, rồi KẾT LUẬN và LÝ DO. Đây là
      ý kiến của một model, và nó mang tên người viết.
    * *Dưới* — DIỄN GIẢI: đúng những số đo mà mọi phiên bản trước của file này
      vẫn in, không đổi một chữ nào theo phần trên.

    Thứ tự đó là cả điểm của thiết kế: người đọc duyệt một kết luận chứ không
    tự dựng lấy một cái, nhưng vẫn bác được nó bằng số liệu nằm cùng file.
    Khối dưới **gập lại** mặc định — mở ra là việc của người muốn kiểm chứng,
    không phải việc bắt buộc của người đọc.
    """
    recs = structure.records
    behavior = analyze_market_behavior(recs)
    series = build_series(recs, behavior, basis)
    overlays = build_overlays(structure)
    # Thẻ dưới biểu đồ nói kết luận khi đã có; chưa có thì nó lùi về mô tả mẫu
    # hình như trước. JS đọc khoá này để biết đang ở trạng thái nào.
    overlays["thesis"] = _thesis_card(thesis)

    # --- tầng trên: cờ đỏ, rồi mới tới kết luận -----------------------------
    #
    # Cờ đỏ đứng **trước** KẾT LUẬN, không nằm trong DIỄN GIẢI. Lý do không
    # phải thẩm mỹ: một vụ khởi tố lãnh đạo làm mọi con số phía dưới đổi nghĩa,
    # nên nó phải được đọc *trước* khi người ta đọc mẫu hình. Đặt nó sau phần
    # nhận định là mặc định rằng người đọc sẽ cuộn tới cuối — mà người đọc một
    # báo cáo có kết luận sẵn thì thường không cuộn.
    verdict_md = thesis_mod.format_thesis(
        thesis, symbol=structure.symbol, as_of=structure.as_of)
    red_md = news_format.format_redflags(redflags)
    conflict = thesis_mod.redflag_conflict(thesis, redflags)
    verdict_md = "\n\n".join(x for x in (red_md, conflict, verdict_md) if x)

    # --- tầng dưới: số đo gốc ----------------------------------------------
    detail_md = [_without_asof_note(_without_disclaimer(format_snapshot(snap))),
                 _without_asof_note(_without_disclaimer(format_structure(structure)))]
    # Tin tức đi ngay sau cấu trúc giá: cả hai nói về *chính mã này*, còn hai
    # khối dưới là lực nền (phái sinh) và kỳ vọng (forecast). Rỗng khi kho tin
    # chưa nạp — hồ sơ vẫn dựng y hệt như trước khi có tầng này.
    if news_md:
        detail_md.append(news_md)
    # Bối cảnh phái sinh đi *sau* cấu trúc giá, không đi trước: hồ sơ này nói về
    # một mã, phái sinh chỉ là lực nền. Chuỗi rỗng khi chưa nạp dữ liệu VN30 /
    # VN30F1M, nên hồ sơ vẫn dựng được y hệt như trước khi có tầng này.
    if futures_md:
        detail_md.append(futures_md)
    if changes:
        lines = ["## 🔔 Forecast đổi trạng thái", ""]
        for c in changes:
            lines.append(
                f"- **{c['symbol']}** {c['from']} → **{c['to']}** "
                f"ngày {c.get('date') or '—'} · giá {_n(c['close'])} · "
                f"mục tiêu {_n(c['target'])}"
            )
            lines.append(f"  {c['note']}")
        detail_md.append("\n".join(lines))
    if forecasts:
        detail_md.append(_without_disclaimer(
            format_forecast_list(forecasts, title="Forecast đang mở")))

    headings: List[Tuple[str, str, int]] = []
    verdict_html = _md_to_html(verdict_md, headings)
    n_verdict = len(headings)               # chỗ cắt giữa hai tầng, cho mục lục
    detail_html = _md_to_html("\n\n".join(detail_md), headings)
    sections = (
        f'<div class="verdict-layer">{verdict_html}</div>'
        f'<details class="detail-layer" id="dien-giai">'
        f'<summary><span class="dg-title">DIỄN GIẢI — số đo gốc</span>'
        f'<span class="dg-hint">chỉ báo, cấu trúc giá, đầu mục tin, phái sinh · '
        f'mở ra để kiểm chứng kết luận ở trên</span></summary>'
        f'<div class="dg-body">{detail_html}</div></details>'
    )
    # Mục lục phân biệt hai tầng: mục của phần kết luận sáng, mục nằm trong
    # khối DIỄN GIẢI đang gập thì mờ đi — bấm vào vẫn tới nơi (script bên dưới
    # mở khối ra trước khi nhảy), nhưng người đọc biết trước mình đang rời
    # phần nhận định để đi vào phần số liệu.
    toc = "".join(
        f'<a class="{"lv2" if lv == 2 else "lv3"}'
        f'{"" if i < n_verdict else " in-detail"}" href="#{a}">{_inline(t)}</a>'
        for i, (a, t, lv) in enumerate(headings)
    )

    symbol = structure.symbol
    date_from = recs[0].date.strftime("%Y-%m-%d")
    date_to = recs[-1].date.strftime("%Y-%m-%d")

    return "\n".join([
        "<!DOCTYPE html>", '<html lang="vi">', "<head>", '<meta charset="UTF-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        f"<title>{_esc(symbol)} — hồ sơ kỹ thuật {_esc(structure.as_of)}</title>",
        f"<style>{_read(CSS_PATH)}</style>",
        f"<style>{REPORT_CSS}</style>",
        f"<style>{_EXTRA_CSS}</style>",
        _library_tag(),
        "</head>", "<body>", '<div class="wrap">',
        _redflag_banner(symbol, redflags),

        '<div id="header">',
        f'  <div class="left"><h1>[{_esc(symbol)}]</h1>'
        f'  <div class="sub">{date_from} &nbsp;→&nbsp; {date_to} · '
        f'{structure.bars} phiên · dựng lúc {datetime.now():%Y-%m-%d %H:%M}</div></div>',
        f'  <div class="right">{"".join(_chips(snap, structure))}</div>',
        "</div>",

        _asof_html(structure.as_of_requested, structure.as_of),
        chart_body_html(),
        '<div class="hint">Kéo để trượt · lăn chuột để phóng to · rê chuột lên một '
        'đường kẻ để xem vì sao nó được vẽ · bấm vào một phiên để ghim chỉ báo của phiên đó.</div>',

        f'<nav class="toc">{toc}</nav>' if toc else "",
        f'<div class="sections">{sections}</div>',

        f'<div class="foot">{_esc(DISCLAIMER.strip("_"))}</div>',
        "</div>",
        chart_data_script(series, overlays),
        "<script>" + _read(JS_PATH).replace("</script", r"<\/script") + "</script>",
        _TOC_SCRIPT,
        "</body>", "</html>",
    ])


# ---------------------------------------------------------------------------
# entry point
# ---------------------------------------------------------------------------
def build_dossier(
    symbol: str,
    lookback_days: int = 260,
    profile: str = "standard",
    as_of: Optional[datetime] = None,
    out_dir: Optional[str] = None,
    with_forecasts: bool = True,
    open_browser: bool = False,
    with_news: bool = True,
    with_brief: bool = True,
) -> Optional[Dossier]:
    """Write the dossier for one symbol; ``None`` when the symbol has no data.

    Hai lần gọi, hai kết quả khác nhau — và đó là cả ý đồ:

    1. **Lần đầu**, chưa có kết luận cho phiên này. File vẫn ghi ra đầy đủ số
       đo, nhưng chỗ KẾT LUẬN nói thẳng là chưa ai viết, và ``brief`` mang về
       gói bằng chứng kèm hướng dẫn. Model đang gọi tool đọc gói đó, viết kết
       luận, nộp qua ``submit_thesis``.
    2. **Lần sau**, ``load_thesis`` tìm thấy kết luận của đúng phiên đó và
       dựng lại file với kết luận nằm trên cùng.

    ``with_brief=False`` bỏ bước dựng gói bằng chứng (tốn thêm một lượt nạp
    tin + ngành) — dùng khi người gọi chỉ cần file, không định viết gì.
    """
    structure = build_structure(symbol, lookback_days=lookback_days, as_of=as_of)
    if not structure.records:
        return None
    snap = build_snapshot(symbol, as_of=as_of,
                          lookback_days=max(lookback_days, 260), profile=profile)

    forecasts: List[Any] = []
    changes: List[Dict[str, Any]] = []
    if with_forecasts:
        # check_all replays the price history, so the statuses shown are current
        # even if the stored file is stale.
        check = check_all([structure.symbol], open_only=True, as_of=as_of)
        forecasts = [f for f in check.forecasts if f.is_open]
        changes = check.changes

    futures_md = "\n".join(format_futures_brief(
        futures_mod.build_futures_snapshot(as_of),
        futures_mod.symbol_exposure(symbol, as_of),
        ref_date=structure.as_of,
    ))

    # Basis theo phiên, cho pane dưới ADX. Khối chữ phái sinh ở trên chỉ nói
    # phiên gần nhất; cả chuỗi mới trả lời được câu "mức này có lạ không" mà
    # không phải rời file đi tra chỗ khác. Rỗng khi chưa nạp VN30 / VN30F1M —
    # khi đó chart bỏ hẳn pane thay vì vẽ một dải trống.
    basis = {
        p.date: {"pct": p.basis_pct,
                 "sessions": p.sessions_to_expiry,
                 "expiry": p.is_expiry}
        for p in futures_mod.basis_series(as_of, max(lookback_days, 800))
    }

    # Đầu mục tin tức. Cửa sổ phiên lấy thẳng từ ``structure.records`` — chuỗi
    # đó đã bị cắt theo ``as_of``, nên tin cũng không thể vượt mốc hồi tưởng mà
    # không phải kiểm tra lại lần nữa ở đây.
    #
    # Bọc try/except có chủ ý: kho tin nằm ở file khác, nạp bằng lượt khác, và
    # hoàn toàn có thể chưa có trên một máy vừa clone. Hồ sơ kỹ thuật là phần
    # người dùng gọi ``/report`` để lấy — một kho tin hỏng không được phép giết
    # nó. Lỗi đi vào ``note`` để vẫn nhìn thấy được, thay vì im lặng.
    digest = None
    news_md = ""
    if with_news:
        try:
            digest = news_mod.build_digest(
                structure.symbol, sessions=NEWS_SESSIONS, as_of=as_of,
                session_dates=[r.date.strftime("%Y-%m-%d")
                               for r in structure.records],
            )
            if not digest.is_empty:
                # Tin tiêu biểu đứng **trước** bảng 20 phiên: câu đầu tiên ai
                # cũng hỏi là "có tin gì đáng kể, giá phản ứng chưa", và trả lời
                # nó bằng một bảng 20 dòng là bắt người đọc tự quét. Cả hai khối
                # đều là **phép đo**, nên cùng nằm trong DIỄN GIẢI — kết luận về
                # tin là của model và ở tầng trên, không trộn vào đây.
                news_md = "\n\n".join([
                    news_format.format_highlights(digest),
                    _without_disclaimer(news_format.format_digest(digest)),
                ])
        except Exception as exc:                     # noqa: BLE001
            digest = None
            news_md = (f"## 📰 Tin tức {NEWS_SESSIONS} phiên gần nhất\n\n"
                       f"⚠️ Không đọc được kho tin: {exc}")

    # Cờ đỏ. Cửa sổ riêng (``REDFLAG_DAYS`` ngày lịch), không dùng chung với
    # 20 phiên đầu mục — hai câu hỏi khác nhau, hai độ dài trí nhớ khác nhau.
    # Cùng lý do bọc try/except như kho tin: hồ sơ kỹ thuật không được chết vì
    # một lớp phụ, nhưng ``None`` ở đây phải đọc là *chưa quét được*, không
    # phải *không có cờ* — và ``format_redflags`` in ra đúng hai câu khác nhau
    # cho hai trạng thái đó.
    #
    # Lượt quét của máy đi qua ``rulings.apply`` trước khi ra khỏi hàm này:
    # phán quyết khoá theo **bài** chứ không theo phiên, nên một cờ đã được đọc
    # tuần trước vẫn còn hiệu lực hôm nay và không phải đọc lại. Không áp ở đây
    # thì mọi chỗ đọc ``dossier.redflags`` (dải đỏ, gói bằng chứng, câu cảnh báo
    # lệch tầng) lại quay về bản thuần cụm từ, và cả tầng phán quyết thành ra
    # chỉ sửa đúng cái file HTML vừa ghi.
    redflags = None
    if with_news:
        try:
            redflags = rulings_mod.apply(
                redflag_mod.build(structure.symbol, as_of=as_of,
                                  window_days=REDFLAG_DAYS))
        except Exception:                            # noqa: BLE001
            redflags = None

    # Kết luận của **đúng** phiên này. Không rơi về bản gần nhất: một nhận định
    # viết cho phiên tuần trước nói về một cây nến khác và một mốc kích hoạt
    # khác — dùng lại nó ở đây là gán cho người viết một câu họ không nói.
    thesis = thesis_mod.load_thesis(structure.symbol, structure.as_of)

    brief = ""
    if thesis is None and with_brief:
        # Chưa có kết luận → dựng gói bằng chứng để model đang gọi tool đọc.
        # Bọc try/except cùng lý do như kho tin: gói này chạm tới bảng xếp
        # hạng, kho tin, ảnh chụp cơ bản — ba file phụ, ba chỗ có thể chưa có
        # trên một máy vừa clone. Không cái nào được phép giết hồ sơ kỹ thuật.
        try:
            evidence = thesis_mod.build_evidence(
                structure.symbol, as_of=as_of, snapshot=snap, structure=structure,
                futures_md=futures_md, sessions=NEWS_SESSIONS,
                redflags=redflags)
            brief = thesis_mod.format_brief(evidence)
        except Exception as exc:                     # noqa: BLE001
            brief = (f"⚠️ Không dựng được gói bằng chứng: "
                     f"{type(exc).__name__}: {exc}")

    html = render_dossier(snap, structure, forecasts=forecasts, changes=changes,
                          futures_md=futures_md, basis=basis, news_md=news_md,
                          thesis=thesis, redflags=redflags)

    root = asof_mod.out_root(DOSSIER_DIR, as_of, out_dir)
    path = root / f"ho_so_{structure.symbol}_{structure.as_of}.html"
    path.write_text(html, encoding="utf-8")
    if open_browser:
        open_html_in_chrome(str(path))
    return Dossier(
        symbol=structure.symbol, as_of=structure.as_of, snapshot=snap,
        structure=structure, forecasts=forecasts, changes=changes, path=str(path),
        as_of_requested=structure.as_of_requested, news=digest,
        thesis=thesis, brief=brief, redflags=redflags,
    )
