"""Draw the structure onto a PNG — candles, box, trendlines, RSI and ADX.

Matplotlib only, no extra dependency and no browser: the report needs a picture
it can embed and Claude can look at. Colours mirror the interactive chart in
``chart_renderer_v2`` so the two read as the same product.

Bars are plotted against their integer index, not the date, so weekends and
holidays leave no gaps; the x tick labels carry the real dates.
"""
from datetime import datetime
from typing import Optional

import matplotlib
matplotlib.use("Agg")                                          # headless, no GUI
import matplotlib.pyplot as plt                                 # noqa: E402
from matplotlib.gridspec import GridSpec                        # noqa: E402
from matplotlib.lines import Line2D                             # noqa: E402
from matplotlib.patches import Rectangle                        # noqa: E402

from src.analysis.technical_indicators import IndicatorGroup2   # noqa: E402
from src.ta import asof as asof_mod                              # noqa: E402
from src.ta.config import RsiConfig                             # noqa: E402
from src.ta.indicators_ext import adx_di                        # noqa: E402
from src.ta.loader import PROJECT_ROOT                          # noqa: E402
from src.ta.formations import BEARISH, CONFIRMED, FAILED        # noqa: E402
from src.ta.pivots import HIGH                                  # noqa: E402
from src.ta.signals import detect_rsi_events                    # noqa: E402
from src.ta.structure import Structure, build_structure         # noqa: E402
from src.ta.trendlines import RESISTANCE                        # noqa: E402

BG = "#0f1117"
PANEL = "#161b22"
GRID = "#21262d"
TEXT = "#c9d1d9"
MUTED = "#6e7681"
UP = "#26a69a"
DOWN = "#ef5350"
EMA20 = "#58a6ff"
EMA50 = "#f0883e"
RES = "#f85149"
SUP = "#3fb950"
BOX = "#e3b341"
ZONE = "#8b949e"
NECK = "#d2a8ff"      # distinct from the box amber it often crosses
ADX_C = "#bc8cff"
RSI_C = "#e3b341"


def _style(ax, *, bottom_labels: bool = False):
    ax.set_facecolor(BG)
    ax.grid(color=GRID, linewidth=0.6, alpha=0.8)
    ax.set_axisbelow(True)
    for spine in ax.spines.values():
        spine.set_color(GRID)
    ax.tick_params(colors=MUTED, labelsize=8,
                   labelbottom=bottom_labels, length=3)
    ax.yaxis.set_label_position("right")
    ax.yaxis.tick_right()


def _date_ticks(ax, records, count: int = 10):
    n = len(records)
    step = max(1, n // count)
    ticks = list(range(0, n, step))
    ax.set_xticks(ticks)
    ax.set_xticklabels([records[i].date.strftime("%d/%m") for i in ticks],
                       rotation=0, fontsize=8)


def _candles(ax, records):
    for i, r in enumerate(records):
        rising = r.priceClose >= r.priceOpen
        color = UP if rising else DOWN
        ax.vlines(i, r.priceLow, r.priceHigh, color=color, linewidth=0.8, zorder=2)
        bottom = min(r.priceOpen, r.priceClose)
        height = abs(r.priceClose - r.priceOpen) or (r.priceHigh - r.priceLow) * 0.02
        ax.add_patch(Rectangle((i - 0.32, bottom), 0.64, height,
                               facecolor=color, edgecolor=color, linewidth=0.5, zorder=3))


def _draw_box(ax, box, n: int):
    """Filled rectangle over the box's own span, edges extended to the right."""
    left, right = box.start_index, box.end_index
    ax.add_patch(Rectangle((left - 0.5, box.bottom), right - left + 1, box.height,
                           facecolor=BOX, alpha=0.16, edgecolor=BOX,
                           linewidth=1.4, zorder=1))
    for level in (box.top, box.bottom):
        ax.plot([right, n - 1], [level, level], color=BOX, linewidth=1.0,
                linestyle=(0, (4, 3)), alpha=0.85, zorder=4)
    ax.annotate(box.id, xy=(left - 0.5, box.top), xytext=(3, 4),
                textcoords="offset points", color=BOX, fontsize=9,
                fontweight="bold", va="bottom", ha="left", zorder=7)
    ax.annotate(f"{box.top:g}", xy=(n - 1, box.top), xytext=(4, 0),
                textcoords="offset points", color=BOX, fontsize=8, va="center")
    ax.annotate(f"{box.bottom:g}", xy=(n - 1, box.bottom), xytext=(4, 0),
                textcoords="offset points", color=BOX, fontsize=8, va="center")

    if box.breakout_index is not None:
        i = box.breakout_index
        up = "up" in box.state or box.state == "false_breakout_up"
        ax.annotate(
            "", xy=(i, box.breakout_close), xytext=(i, box.top if up else box.bottom),
            arrowprops=dict(arrowstyle="-|>", color=UP if up else DOWN, linewidth=1.4),
            zorder=6,
        )
    if box.target is not None:
        color = UP if box.target > box.top else DOWN
        ax.axhline(box.target, color=color, linewidth=0.9, linestyle=":",
                   alpha=0.8, zorder=4)
        ax.annotate(f"mục tiêu {box.target:g}", xy=(n - 1, box.target), xytext=(4, 0),
                    textcoords="offset points", color=color, fontsize=8, va="center")
    if box.invalidation is not None:
        ax.axhline(box.invalidation, color=MUTED, linewidth=0.8,
                   linestyle=":", alpha=0.7, zorder=4)
        ax.annotate(f"huỷ {box.invalidation:g}", xy=(n - 1, box.invalidation),
                    xytext=(4, 0), textcoords="offset points",
                    color=MUTED, fontsize=8, va="center")


def _draw_trendlines(ax, lines, n: int):
    for line in lines:
        color = RES if line.kind == RESISTANCE else SUP
        alpha = 0.45 if line.broken else 0.95
        xs_solid = [line.p1_index, line.p2_index]
        ax.plot(xs_solid, [line.value_at(x) for x in xs_solid],
                color=color, linewidth=1.6, alpha=alpha, zorder=5)
        # Projection past the second anchor is where the level is actually used.
        ax.plot([line.p2_index, n - 1], [line.value_at(line.p2_index), line.value_at(n - 1)],
                color=color, linewidth=1.2, alpha=alpha * 0.8,
                linestyle=(0, (5, 3)), zorder=5)
        # Label at the midpoint of the anchored segment: the right edge is
        # already crowded with box levels and price callouts.
        mid = (line.p1_index + line.p2_index) / 2
        above = line.kind == RESISTANCE
        ax.annotate(line.id, xy=(mid, line.value_at(mid)),
                    xytext=(0, 6 if above else -6), textcoords="offset points",
                    color=color, fontsize=9, fontweight="bold",
                    ha="center", va="bottom" if above else "top", zorder=7)
        if line.broken and line.break_index is not None:
            ax.plot(line.break_index, line.value_at(line.break_index), marker="x",
                    color=color, markersize=7, markeredgewidth=1.6, zorder=6)


def _draw_pivots(ax, pivots, market=None, labelled: int = 6):
    """Every swing as a small marker; the most recent few also named.

    Labelling all of them would bury the chart — on a 260-bar series there
    are usually 40+ pivots. The last handful is what the current structure
    is made of, and that is the part worth reading off the picture.
    """
    for p in pivots:
        if p.kind == HIGH:
            ax.plot(p.index, p.price, marker="v", color=MUTED, markersize=4, zorder=6)
        else:
            ax.plot(p.index, p.price, marker="^", color=MUTED, markersize=4, zorder=6)

    for swing in (market.swings[-labelled:] if market else []):
        top = swing.kind == HIGH
        color = SUP if swing.short in ("HH", "HL") else (
            MUTED if swing.short in ("EQH", "EQL") else RES)
        ax.annotate(swing.short, xy=(swing.index, swing.price),
                    xytext=(0, 9 if top else -9), textcoords="offset points",
                    color=color, fontsize=7, fontweight="bold", ha="center",
                    va="bottom" if top else "top", zorder=7)


def _draw_structure_events(ax, market, n: int, recent: int = 3):
    """The last few BOS / CHoCH levels, as the horizontal lines they are."""
    if market is None:
        return
    for event in market.events[-recent:]:
        color = SUP if event.direction == "up" else RES
        style = "-" if event.kind == "bos" else (0, (2, 2))
        ax.plot([event.index, min(n - 1, event.index + 12)],
                [event.level, event.level], color=color, linewidth=1.0,
                linestyle=style, alpha=0.7, zorder=4)
        ax.annotate("BOS" if event.kind == "bos" else "CHoCH",
                    xy=(event.index, event.level), xytext=(2, 3),
                    textcoords="offset points", color=color, fontsize=7,
                    alpha=0.85, zorder=7)


def _draw_levels(ax, levels, n: int):
    """Horizontal zones as shaded bands across the whole chart."""
    for level in levels:
        height = max(level.high - level.low, 1e-9)
        ax.add_patch(Rectangle((-1, level.low), n + 4, height,
                               facecolor=ZONE, alpha=0.10, edgecolor="none",
                               zorder=0))
        ax.plot([-1, n - 1], [level.price, level.price], color=ZONE,
                linewidth=0.7, linestyle=(0, (2, 4)), alpha=0.6, zorder=1)
        ax.annotate(level.id, xy=(0, level.price), xytext=(2, 2),
                    textcoords="offset points", color=ZONE, fontsize=7,
                    fontweight="bold", zorder=6)


def _draw_formations(ax, evidence, n: int):
    """Neckline, the pivots that define it, and the measured target.

    The defining pivots get filled markers so they stand out from the ordinary
    swing pivots already dotted along the series — the point of the drawing is
    to show *which* turns made the shape.
    """
    for ev in evidence:
        f = ev.formation
        color = RES if f.bias == BEARISH else SUP
        alpha = 0.35 if f.state == FAILED else 0.95
        start, end = f.pivots[1].index, n - 1
        ax.plot([start, end], [f.neckline_at(start), f.neckline_at(end)],
                color=NECK, linewidth=1.6, alpha=alpha,
                linestyle="-" if f.state == CONFIRMED else (0, (6, 3)), zorder=5)
        ax.annotate(f"{f.id} {f.name}".strip(),
                    xy=(start, f.neckline_at(start)), xytext=(2, -10),
                    textcoords="offset points", color=NECK, fontsize=8,
                    fontweight="bold", alpha=alpha, zorder=7)

        top = f.bias == BEARISH
        for pivot in f.pivots:
            ax.plot(pivot.index, pivot.price, marker="o", color=color,
                    markersize=5, alpha=alpha, zorder=7)
        pick = max if top else min
        peak = pick(f.pivots, key=lambda p: p.price)
        ax.annotate(f"{peak.price:g}", xy=(peak.index, peak.price),
                    xytext=(0, 8 if top else -8), textcoords="offset points",
                    color=color, fontsize=8, ha="center",
                    va="bottom" if top else "top", alpha=alpha, zorder=7)

        if f.break_index is not None:
            ax.plot(f.break_index, f.break_close, marker="D", color=color,
                    markersize=5, alpha=alpha, zorder=7)
        if f.target is not None and f.state != FAILED:
            ax.axhline(f.target, color=color, linewidth=0.9, linestyle=":",
                       alpha=0.7, zorder=4)
            ax.annotate(f"mục tiêu {f.id} {f.target:g}".strip(),
                        xy=(n - 1, f.target), xytext=(4, 0),
                        textcoords="offset points", color=color, fontsize=8,
                        va="center", zorder=7)


def render_structure_chart(
    structure: Structure,
    out_dir: Optional[str] = None,
    rsi_cfg: RsiConfig = RsiConfig(),
    dpi: int = 110,
) -> Optional[str]:
    """Write the annotated chart and return its path, or ``None`` if no data."""
    recs = structure.records
    if not recs:
        return None
    n = len(recs)

    fig = plt.figure(figsize=(14, 10), facecolor=BG)
    gs = GridSpec(4, 1, height_ratios=[4.2, 1.0, 1.3, 1.3], hspace=0.08, figure=fig)
    ax_p, ax_v, ax_r, ax_a = (fig.add_subplot(gs[i]) for i in range(4))
    for ax in (ax_p, ax_v, ax_r):
        _style(ax)
    _style(ax_a, bottom_labels=True)

    # ---- price ------------------------------------------------------------
    _draw_levels(ax_p, getattr(structure, "levels", []), n)
    _candles(ax_p, recs)
    for series, color, name in ((structure.ema20, EMA20, "EMA20"),
                                (structure.ema50, EMA50, "EMA50")):
        xs = [i for i, v in enumerate(series) if v is not None]
        ax_p.plot(xs, [series[i] for i in xs], color=color, linewidth=1.1,
                  label=name, zorder=4)
    _draw_pivots(ax_p, structure.pivots, getattr(structure, "market", None))
    _draw_structure_events(ax_p, getattr(structure, "market", None), n)
    _draw_trendlines(ax_p, structure.trendlines, n)
    if structure.box is not None:
        _draw_box(ax_p, structure.box, n)
    _draw_formations(ax_p, getattr(structure, "evidence", []), n)

    lows = min(r.priceLow for r in recs)
    highs = max(r.priceHigh for r in recs)
    pad = (highs - lows) * 0.08
    floor = lows - pad
    ceiling = highs + pad
    targets = []
    if structure.box is not None and structure.box.target is not None:
        targets.append(structure.box.target)
    targets += [ev.formation.target for ev in getattr(structure, "evidence", [])
                if ev.formation.target is not None and ev.formation.state != FAILED]
    for target in targets:
        floor = min(floor, target - pad * 0.5)
        ceiling = max(ceiling, target + pad * 0.5)
    ax_p.set_ylim(floor, ceiling)
    ax_p.set_xlim(-1, n + max(4, n * 0.03))

    pattern = (f" · {structure.pattern.name}"
               if structure.pattern and structure.pattern.kind != "none" else "")
    ax_p.set_title(
        f"{structure.symbol}   {recs[0].date:%d/%m/%Y} → {recs[-1].date:%d/%m/%Y}   "
        f"đóng cửa {structure.close}{pattern}",
        color=TEXT, fontsize=13, loc="left", pad=28,
    )
    handles = [
        Line2D([], [], color=EMA20, lw=1.4, label="EMA20"),
        Line2D([], [], color=EMA50, lw=1.4, label="EMA50"),
        Line2D([], [], color=RES, lw=1.6, label="Đường nối đỉnh"),
        Line2D([], [], color=SUP, lw=1.6, label="Đường nối đáy"),
        Line2D([], [], color=BOX, lw=1.6, label="Hộp tích luỹ"),
        Line2D([], [], color=NECK, lw=1.6, label="Neckline"),
    ]
    legend = ax_p.legend(handles=handles, loc="lower left", fontsize=8, ncol=6,
                         bbox_to_anchor=(0, 1.005), facecolor=PANEL,
                         edgecolor=GRID, framealpha=0.9)
    for text in legend.get_texts():
        text.set_color(TEXT)

    # ---- volume -----------------------------------------------------------
    vols = [r.priceImpactVolume / 1e6 for r in recs]
    colors = [UP if r.priceClose >= r.priceOpen else DOWN for r in recs]
    ax_v.bar(range(n), vols, color=colors, width=0.64, alpha=0.75)
    avg = sum(vols) / n if n else 0
    ax_v.axhline(avg, color=MUTED, linewidth=0.8, linestyle=":")
    ax_v.set_ylabel("KL (triệu)", color=MUTED, fontsize=8)
    ax_v.set_xlim(*ax_p.get_xlim())

    # ---- RSI --------------------------------------------------------------
    rsi = IndicatorGroup2.rsi(recs, rsi_cfg.period)
    xs = [i for i, v in enumerate(rsi) if v is not None]
    ax_r.plot(xs, [rsi[i] for i in xs], color=RSI_C, linewidth=1.2)
    ax_r.axhline(rsi_cfg.overbought, color=RES, linewidth=0.8, linestyle=":")
    ax_r.axhline(rsi_cfg.oversold, color=SUP, linewidth=0.8, linestyle=":")
    ax_r.axhspan(rsi_cfg.overbought, 100, color=RES, alpha=0.06)
    ax_r.axhspan(0, rsi_cfg.oversold, color=SUP, alpha=0.06)
    for event in detect_rsi_events(recs, rsi_cfg, rsi):
        bullish = event.side == "bullish"
        ax_r.plot(event.index, event.rsi, marker="o", markersize=5,
                  color=SUP if bullish else RES, zorder=6)
        ax_p.axvline(event.index, color=SUP if bullish else RES,
                     linewidth=0.7, alpha=0.25, zorder=0)
    ax_r.set_ylim(0, 100)
    ax_r.set_yticks([0, 30, 50, 70, 100])
    ax_r.set_ylabel(f"RSI{rsi_cfg.period}", color=MUTED, fontsize=8)
    ax_r.set_xlim(*ax_p.get_xlim())

    # ---- ADX --------------------------------------------------------------
    adx, pdi, mdi = adx_di(recs, 14)
    for series, color, width, label in ((adx, ADX_C, 1.4, "ADX14"),
                                        (pdi, UP, 0.9, "+DI"),
                                        (mdi, DOWN, 0.9, "-DI")):
        pts = [i for i, v in enumerate(series) if v is not None]
        if pts:
            ax_a.plot(pts, [series[i] for i in pts], color=color,
                      linewidth=width, label=label)
    ax_a.axhline(20, color=MUTED, linewidth=0.8, linestyle=":")
    ax_a.set_ylabel("ADX / DI", color=MUTED, fontsize=8)
    ax_a.set_xlim(*ax_p.get_xlim())
    adx_legend = ax_a.legend(loc="upper left", fontsize=7, ncol=3,
                             facecolor=PANEL, edgecolor=GRID, framealpha=0.9)
    for text in adx_legend.get_texts():
        text.set_color(TEXT)
    _date_ticks(ax_a, recs)

    out_root = asof_mod.out_root(PROJECT_ROOT / "chart",
                                 asof_mod.parse(structure.as_of_requested), out_dir)
    path = out_root / f"{structure.symbol}_structure_{structure.as_of}.png"
    fig.savefig(path, dpi=dpi, facecolor=BG, bbox_inches="tight")
    plt.close(fig)
    return str(path)


def render_symbol(
    symbol: str,
    lookback_days: int = 180,
    as_of: Optional[datetime] = None,
    out_dir: Optional[str] = None,
):
    """Convenience: build the structure and draw it. Returns ``(path, structure)``."""
    structure = build_structure(symbol, lookback_days=lookback_days, as_of=as_of)
    return render_structure_chart(structure, out_dir=out_dir), structure


def render_interactive(
    symbol: str,
    lookback_days: int = 260,
    as_of: Optional[datetime] = None,
    open_browser: bool = False,
) -> Optional[str]:
    """Write the TradingView-style HTML chart with the structure drawn on it.

    Same renderer the desktop app uses, plus trendlines, box edges and the
    measured target. Returns the file path.
    """
    from src.analysis.market_behavior_analyzer import analyze_market_behavior
    from src.reporting.chart_renderer_v2 import render_chart
    from src.ta.overlays import build_overlays

    structure = build_structure(symbol, lookback_days=lookback_days, as_of=as_of)
    if not structure.records:
        return None
    behavior = analyze_market_behavior(structure.records)
    out_dir = (str(asof_mod.out_root(PROJECT_ROOT / "chart", as_of))
               if as_of is not None else None)
    return render_chart(structure.records, behavior, out_dir=out_dir,
                        overlays=build_overlays(structure), open_browser=open_browser)
