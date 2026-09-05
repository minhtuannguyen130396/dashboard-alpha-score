"""Assemble the technical overview report for one or many symbols.

Two outputs from one pass: a self-contained HTML file on disk (charts embedded
as data URIs so it can be opened or sent anywhere), and a compact markdown
summary returned to the terminal. The HTML is the artefact; the markdown is
what the user actually reads first.
"""
import base64
import html as html_escape
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.ta import asof as asof_mod
from src.ta.boxes import INSIDE
from src.ta.formations import CONFIRMED as FORMATION_CONFIRMED
from src.ta.formations import PIVOT_ROLES
from src.ta.formations import STATE_LABELS as FORMATION_STATE_VN
from src.ta.forecast import BASIS_VN, STATUS_VN, Forecast, check_all, load_all
from src.ta.format import BOX_STATE_VN, DISCLAIMER, _n, _signed, asof_note
from src.ta.loader import PROJECT_ROOT, resolve_universe
from src.ta.render import render_structure_chart
from src.ta.snapshot import Snapshot, build_snapshot
from src.ta.structure import Structure, build_structure

REPORT_DIR = PROJECT_ROOT / "reports"
#: Charts dominate both runtime and file size — keep a report readable.
MAX_SYMBOLS = 12


@dataclass
class SymbolSection:
    symbol: str
    snapshot: Snapshot
    structure: Structure
    chart_path: Optional[str] = None
    forecasts: List[Forecast] = field(default_factory=list)

    @property
    def headline(self) -> str:
        """The single most decision-relevant sentence for this symbol.

        A confirmed reversal formation outranks the box and the oscillators: it
        carries a level, a target and a condition, which none of them do.
        """
        for ev in getattr(self.structure, "evidence", []):
            if ev.formation.state == FORMATION_CONFIRMED:
                return (f"{ev.mark} {ev.formation.name} đã phá neckline "
                        f"{ev.formation.neckline_now}, mục tiêu {ev.formation.target}")
        box = self.structure.box
        if box is not None and box.state != INSIDE:
            return BOX_STATE_VN.get(box.state, box.state)
        zone = self.snapshot.rsi_zone.get("state")
        if zone in ("turning_up", "turning_down"):
            return self.snapshot.rsi_zone.get("label", "")
        if box is not None and box.position_pct is not None:
            return f"trong hộp {box.bottom}–{box.top}, ở {box.position_pct:.0f}% chiều cao"
        return self.snapshot.trend.get("label", "")


@dataclass
class Report:
    as_of: str
    generated: str
    #: Mốc hồi tưởng đã yêu cầu (rỗng = báo cáo trên dữ liệu mới nhất).
    as_of_requested: str = ""
    sections: List[SymbolSection] = field(default_factory=list)
    forecast_changes: List[Dict[str, Any]] = field(default_factory=list)
    html_path: Optional[str] = None
    skipped: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# building
# ---------------------------------------------------------------------------
def build(
    symbols: str,
    lookback_days: int = 180,
    profile: str = "standard",
    with_charts: bool = True,
    with_forecasts: bool = True,
    as_of: Optional[datetime] = None,
    out_dir: Optional[str] = None,
) -> Report:
    wanted = resolve_universe(symbols)
    report = Report(
        as_of="-",
        generated=datetime.now().strftime("%Y-%m-%d %H:%M"),
        as_of_requested=asof_mod.label(as_of),
    )
    if not wanted:
        report.skipped.append(f"Không tìm thấy dữ liệu cho {symbols!r}")
        return report

    if with_forecasts:
        # Hồi tưởng: chỉ forecast tạo trước mốc, replay tới mốc, không ghi đĩa.
        check = check_all(wanted, open_only=True, as_of=as_of)
        report.forecast_changes = check.changes

    for sym in wanted[:MAX_SYMBOLS]:
        try:
            snapshot = build_snapshot(sym, as_of=as_of, lookback_days=max(lookback_days, 260),
                                      profile=profile)
            structure = build_structure(sym, lookback_days=lookback_days, as_of=as_of)
            chart = None
            if with_charts and structure.bars:
                chart = render_structure_chart(structure)
            report.sections.append(SymbolSection(
                symbol=sym, snapshot=snapshot, structure=structure, chart_path=chart,
                forecasts=load_all([sym], as_of=as_of) if with_forecasts else [],
            ))
        except Exception as exc:
            report.skipped.append(f"{sym}: {type(exc).__name__}: {exc}")

    if len(wanted) > MAX_SYMBOLS:
        report.skipped.append(
            f"Đã giới hạn {MAX_SYMBOLS} mã đầu trong {len(wanted)} mã yêu cầu"
        )
    if report.sections:
        report.as_of = max(s.snapshot.as_of for s in report.sections if s.snapshot.bars)

    report.html_path = write_html(report, out_dir=out_dir)
    return report


# ---------------------------------------------------------------------------
# markdown (terminal)
# ---------------------------------------------------------------------------
def to_markdown(report: Report, detail: bool = True) -> str:
    if not report.sections:
        return "## Báo cáo kỹ thuật\n\n" + "\n".join(f"⚠️ {s}" for s in report.skipped)

    note = asof_note(report.as_of_requested, report.as_of)
    lines = [
        f"# Báo cáo kỹ thuật — {report.as_of}",
        "",
        *([f"> {note}", ""] if note else []),
        f"{len(report.sections)} mã · dựng lúc {report.generated}",
        "",
        "## Tổng quan",
        "",
        "| Mã | Giá | +/- | Xu hướng | RSI | ADX | Hộp | Nổi bật |",
        "|----|----:|----:|----------|----:|----:|-----|---------|",
    ]
    for s in report.sections:
        snap, box = s.snapshot, s.structure.box
        if not snap.bars:
            continue
        adx = snap.adx
        arrow = {"up": "↑", "down": "↓"}.get(adx.get("direction", ""), "→")
        box_cell = f"{_n(box.bottom)}–{_n(box.top)}" if box else "—"
        lines.append(
            f"| **{s.symbol}** | {_n(snap.price['close'])} | {_signed(snap.price['change_pct'])} | "
            f"{snap.trend['label'].split('—')[0].strip()} | {_n(snap.momentum['rsi14'], 1)} | "
            f"{_n(adx.get('adx'), 1)} {arrow} | {box_cell} | {s.headline} |"
        )
    lines.append("")

    if report.forecast_changes:
        lines += ["## 🔔 Forecast đổi trạng thái", ""]
        for c in report.forecast_changes:
            lines.append(
                f"- **{c['symbol']}** `{STATUS_VN.get(c['from'], c['from'])}` → "
                f"**{STATUS_VN.get(c['to'], c['to'])}** ngày {c.get('date') or '—'} "
                f"(giá {_n(c['close'])}, mục tiêu {_n(c['target'])}) — {c['note']}"
            )
        lines.append("")

    open_forecasts = [f for s in report.sections for f in s.forecasts if f.is_open]
    if open_forecasts:
        lines += ["## Forecast đang mở", "",
                  "| Mã | Cơ sở | Trạng thái | Kích hoạt khi | Mục tiêu | Huỷ nếu |",
                  "|----|-------|------------|--------------:|---------:|--------:|"]
        for f in open_forecasts:
            trigger = ("đóng cửa > " if f.trigger_type == "close_above" else "đóng cửa < ")
            vol = f" (vol ≥ {f.confirm_volume_x:g}×)" if f.confirm_volume_x else ""
            lines.append(
                f"| {f.symbol} | {BASIS_VN.get(f.basis, f.basis)} | "
                f"{STATUS_VN.get(f.status, f.status)} | {trigger}{_n(f.trigger_level)}{vol} | "
                f"{_n(f.target)} | {_n(f.invalidation)} |"
            )
        lines.append("")

    if detail:
        lines += ["## Chi tiết từng mã", ""]
        for s in report.sections:
            if not s.snapshot.bars:
                continue
            lines.append(f"### {s.symbol} — {s.snapshot.as_of}")
            lines.append("")
            for item in s.structure.brief:
                lines.append(f"- {item}")
            lines.append(f"- {s.snapshot.rsi_zone.get('label', '')}")
            lines.append(f"- {s.snapshot.adx.get('label', '')}")
            if s.chart_path:
                lines.append(f"- 📈 `{s.chart_path}`")
            lines.append("")

    if report.html_path:
        lines += [f"📄 Báo cáo đầy đủ (có ảnh): `{report.html_path}`", ""]
    for note in report.skipped:
        lines.append(f"⚠️ {note}")
    if report.skipped:
        lines.append("")
    lines.append(DISCLAIMER)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# html (file on disk)
# ---------------------------------------------------------------------------
REPORT_CSS = """
:root { color-scheme: dark; }
* { box-sizing: border-box; }
body { margin: 0; padding: 32px 24px 64px; background: #0f1117; color: #c9d1d9;
       font: 15px/1.6 -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; }
.wrap { max-width: 1180px; margin: 0 auto; }
h1 { font-size: 26px; margin: 0 0 4px; color: #f0f6fc; }
h2 { font-size: 19px; margin: 40px 0 12px; color: #f0f6fc;
     border-bottom: 1px solid #21262d; padding-bottom: 8px; }
h3 { font-size: 17px; margin: 28px 0 8px; color: #58a6ff; }
.sub { color: #6e7681; font-size: 13px; margin-bottom: 8px; }
table { border-collapse: collapse; width: 100%; margin: 12px 0; font-size: 14px; }
th, td { border: 1px solid #21262d; padding: 7px 10px; text-align: left; }
th { background: #161b22; color: #8b949e; font-weight: 600; }
td.num, th.num { text-align: right; font-variant-numeric: tabular-nums; }
tr:nth-child(even) td { background: #12161d; }
.pos { color: #3fb950; } .neg { color: #f85149; }
ul { margin: 8px 0 8px 20px; padding: 0; }
li { margin: 4px 0; }
img { max-width: 100%; height: auto; border: 1px solid #21262d; border-radius: 6px;
      margin: 12px 0; display: block; }
.card { background: #161b22; border: 1px solid #21262d; border-radius: 8px;
        padding: 16px 20px; margin: 16px 0; }
.change { border-left: 3px solid #e3b341; padding-left: 12px; margin: 10px 0; }
.form { border-left: 3px solid #6e7681; }
.form.full { border-left-color: #f85149; }
.form.partial { border-left-color: #e3b341; }
.form.conflict { border-left-color: #6e7681; }
.form .marks { color: #8b949e; font-size: 13px; margin: 4px 0 10px; }
.form .verdict { margin-top: 10px; color: #f0f6fc; }
.foot { color: #6e7681; font-size: 13px; margin-top: 48px;
        border-top: 1px solid #21262d; padding-top: 16px; }
.scroll { overflow-x: auto; }
.asof { background: #1c1a10; border: 1px solid #6a5a1e; border-left: 3px solid #e3b341;
        border-radius: 6px; padding: 10px 14px; margin: 14px 0; color: #e6d9a8;
        font-size: 14px; }
.asof b { color: #f2d675; }
"""


def _esc(text: Any) -> str:
    return html_escape.escape(str(text if text is not None else "—"))


def _asof_html(as_of_requested: str, data_date: str = "") -> str:
    """Dải cảnh báo hồi tưởng trong file HTML — cùng câu chữ với bản terminal.

    File HTML sống lâu hơn phiên chat và thường được gửi đi nơi khác; mở ra mà
    không có dòng này thì không cách nào biết đây là ảnh chụp của quá khứ.
    """
    note = asof_note(as_of_requested, data_date)
    return f'<div class="asof">{_esc_md(note)}</div>' if note else ""


def _esc_md(text: Any) -> str:
    """Structure notes carry markdown; **bold** is the only markup used."""
    return re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", _esc(text))


def _img_tag(path: Optional[str]) -> str:
    """Embed the PNG so the report survives being moved or emailed."""
    if not path or not Path(path).is_file():
        return ""
    data = base64.b64encode(Path(path).read_bytes()).decode("ascii")
    return f'<img src="data:image/png;base64,{data}" alt="biểu đồ">'


def _signed_html(value: Optional[float]) -> str:
    if value is None:
        return "—"
    css = "pos" if value >= 0 else "neg"
    return f'<span class="{css}">{value:+.2f}%</span>'


def write_html(report: Report, out_dir: Optional[str] = None) -> Optional[str]:
    if not report.sections:
        return None

    parts: List[str] = [
        "<!DOCTYPE html>", '<html lang="vi">', "<head>", '<meta charset="UTF-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        f"<title>Báo cáo kỹ thuật {report.as_of}</title>",
        f"<style>{REPORT_CSS}</style>", "</head>", "<body>", '<div class="wrap">',
        f"<h1>Báo cáo kỹ thuật — {_esc(report.as_of)}</h1>",
        f'<div class="sub">{len(report.sections)} mã · dựng lúc {_esc(report.generated)}</div>',
        _asof_html(report.as_of_requested, report.as_of),
        "<h2>Tổng quan</h2>", '<div class="scroll">', "<table>",
        "<tr><th>Mã</th><th class='num'>Giá</th><th class='num'>+/-</th><th>Xu hướng</th>"
        "<th class='num'>RSI14</th><th class='num'>ADX14</th><th>Hộp</th><th>Nổi bật</th></tr>",
    ]
    for s in report.sections:
        snap, box = s.snapshot, s.structure.box
        if not snap.bars:
            continue
        arrow = {"up": "↑", "down": "↓"}.get(snap.adx.get("direction", ""), "→")
        box_cell = f"{box.bottom}–{box.top}" if box else "—"
        parts.append(
            f"<tr><td><b>{_esc(s.symbol)}</b></td>"
            f"<td class='num'>{_n(snap.price['close'])}</td>"
            f"<td class='num'>{_signed_html(snap.price['change_pct'])}</td>"
            f"<td>{_esc(snap.trend['label'])}</td>"
            f"<td class='num'>{_n(snap.momentum['rsi14'], 1)}</td>"
            f"<td class='num'>{_n(snap.adx.get('adx'), 1)} {arrow}</td>"
            f"<td>{_esc(box_cell)}</td><td>{_esc(s.headline)}</td></tr>"
        )
    parts += ["</table>", "</div>"]

    if report.forecast_changes:
        parts.append("<h2>🔔 Forecast đổi trạng thái</h2>")
        for c in report.forecast_changes:
            parts.append(
                f'<div class="change"><b>{_esc(c["symbol"])}</b>: '
                f'{_esc(STATUS_VN.get(c["from"], c["from"]))} → '
                f'<b>{_esc(STATUS_VN.get(c["to"], c["to"]))}</b> '
                f'ngày {_esc(c.get("date"))} — giá {_n(c["close"])}, '
                f'mục tiêu {_n(c["target"])}<br><span class="sub">{_esc(c["note"])}</span></div>'
            )

    open_forecasts = [f for s in report.sections for f in s.forecasts if f.is_open]
    if open_forecasts:
        parts += ["<h2>Forecast đang mở</h2>", '<div class="scroll">', "<table>",
                  "<tr><th>Mã</th><th>Cơ sở</th><th>Trạng thái</th><th class='num'>Kích hoạt khi</th>"
                  "<th class='num'>Mục tiêu</th><th class='num'>Huỷ nếu</th></tr>"]
        for f in open_forecasts:
            trigger = "> " if f.trigger_type == "close_above" else "< "
            vol = f" (vol ≥ {f.confirm_volume_x:g}×)" if f.confirm_volume_x else ""
            parts.append(
                f"<tr><td>{_esc(f.symbol)}</td><td>{_esc(BASIS_VN.get(f.basis, f.basis))}</td>"
                f"<td>{_esc(STATUS_VN.get(f.status, f.status))}</td>"
                f"<td class='num'>{trigger}{_n(f.trigger_level)}{_esc(vol)}</td>"
                f"<td class='num'>{_n(f.target)}</td>"
                f"<td class='num'>{_n(f.invalidation)}</td></tr>"
            )
        parts += ["</table>", "</div>"]

    parts.append("<h2>Chi tiết từng mã</h2>")
    for s in report.sections:
        if not s.snapshot.bars:
            continue
        snap = s.snapshot
        parts.append(f"<h3>{_esc(s.symbol)} — {_esc(snap.as_of)}</h3>")
        parts.append(_img_tag(s.chart_path))
        for ev in getattr(s.structure, "evidence", []):
            f = ev.formation
            marks = " · ".join(
                f"{role.capitalize()} {_n(p.price)}"
                for role, p in zip(PIVOT_ROLES.get(f.kind, []), f.pivots)
            )
            parts.append(f'<div class="card form {_esc(ev.tier)}">')
            parts.append(
                f"<strong>{_esc(ev.mark)} {_esc(f.id)} {_esc(f.name)}</strong> "
                f"<span class=\"sub\">{_esc(f.start_date)} → {_esc(f.end_date)} · "
                f"{_esc(FORMATION_STATE_VN.get(f.state, f.state))}</span>"
            )
            parts.append(f'<div class="marks">{_esc(marks)} · '
                         f'Neckline {_n(f.neckline_now)}</div>')
            parts.append("<ul>")
            parts.append(f"<li>Nến: {_esc(ev.candle_note)}</li>")
            parts.append(f"<li>Volume: {_esc(ev.volume_note)}</li>")
            if f.target is not None:
                hit = " ✓ đã chạm" if f.target_hit else ""
                parts.append(f"<li>Mục tiêu đo được: <strong>{_n(f.target)}</strong>{hit} · "
                             f"phủ định tại {_n(f.invalidation)}</li>")
            else:
                parts.append(f"<li>Phủ định tại {_n(f.invalidation)}</li>")
            parts.append("</ul>")
            parts.append(f'<div class="verdict">→ {_esc(ev.conclusion)}</div>')
            parts.append("</div>")
        parts.append('<div class="card"><ul>')
        for item in s.structure.brief:
            parts.append(f"<li>{_esc_md(item)}</li>")
        parts.append(f"<li>{_esc(snap.rsi_zone.get('label', ''))}</li>")
        parts.append(f"<li>{_esc(snap.adx.get('label', ''))}</li>")
        parts.append(
            f"<li>ATR14 {_n(snap.momentum['atr14'])} "
            f"({_n(snap.momentum['atr_pct'], 1)}% giá) · "
            f"RVOL {_n(snap.volume['rvol'])} · "
            f"EMA20 {_n(snap.trend['ema20'])} / EMA50 {_n(snap.trend['ema50'])}</li>"
        )
        parts.append("</ul></div>")

    parts += [
        f'<div class="foot">{_esc(DISCLAIMER.strip("_"))}</div>',
        "</div>", "</body>", "</html>",
    ]

    cutoff = asof_mod.parse(report.as_of_requested)
    root = asof_mod.out_root(REPORT_DIR, cutoff, out_dir)
    name = "_".join(s.symbol for s in report.sections[:3])
    if len(report.sections) > 3:
        name += f"_va_{len(report.sections) - 3}_ma"
    path = root / f"bao_cao_{name}_{asof_mod.file_tag(cutoff)}.html"
    path.write_text("\n".join(parts), encoding="utf-8")
    return str(path)
