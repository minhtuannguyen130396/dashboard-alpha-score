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

DOSSIER_DIR = PROJECT_ROOT / "reports"


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
"""


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


def render_dossier(
    snap,
    structure,
    forecasts: Optional[List[Any]] = None,
    changes: Optional[List[Dict[str, Any]]] = None,
    futures_md: str = "",
) -> str:
    """Build the HTML string — no file, no data loading, so it is easy to test."""
    recs = structure.records
    behavior = analyze_market_behavior(recs)
    series = build_series(recs, behavior)
    overlays = build_overlays(structure)

    body_md = [_without_asof_note(_without_disclaimer(format_snapshot(snap))),
               _without_asof_note(_without_disclaimer(format_structure(structure)))]
    # Bối cảnh phái sinh đi *sau* cấu trúc giá, không đi trước: hồ sơ này nói về
    # một mã, phái sinh chỉ là lực nền. Chuỗi rỗng khi chưa nạp dữ liệu VN30 /
    # VN30F1M, nên hồ sơ vẫn dựng được y hệt như trước khi có tầng này.
    if futures_md:
        body_md.append(futures_md)
    if changes:
        lines = ["## 🔔 Forecast đổi trạng thái", ""]
        for c in changes:
            lines.append(
                f"- **{c['symbol']}** {c['from']} → **{c['to']}** "
                f"ngày {c.get('date') or '—'} · giá {_n(c['close'])} · "
                f"mục tiêu {_n(c['target'])}"
            )
            lines.append(f"  {c['note']}")
        body_md.append("\n".join(lines))
    if forecasts:
        body_md.append(_without_disclaimer(
            format_forecast_list(forecasts, title="Forecast đang mở")))

    headings: List[Tuple[str, str, int]] = []
    sections = _md_to_html("\n\n".join(body_md), headings)
    toc = "".join(
        f'<a class="{"lv2" if lv == 2 else "lv3"}" href="#{a}">{_inline(t)}</a>'
        for a, t, lv in headings
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
) -> Optional[Dossier]:
    """Write the dossier for one symbol; ``None`` when the symbol has no data."""
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
    ))

    html = render_dossier(snap, structure, forecasts=forecasts, changes=changes,
                          futures_md=futures_md)

    root = asof_mod.out_root(DOSSIER_DIR, as_of, out_dir)
    path = root / f"ho_so_{structure.symbol}_{structure.as_of}.html"
    path.write_text(html, encoding="utf-8")
    if open_browser:
        open_html_in_chrome(str(path))
    return Dossier(
        symbol=structure.symbol, as_of=structure.as_of, snapshot=snap,
        structure=structure, forecasts=forecasts, changes=changes, path=str(path),
        as_of_requested=structure.as_of_requested,
    )
