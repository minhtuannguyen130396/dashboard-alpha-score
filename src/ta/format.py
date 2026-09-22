"""Markdown rendering for terminal output.

The MCP tools return text, not JSON blobs — the whole point is that the result
is readable the moment it lands in Claude Code. Data structures stay pure in
``signals`` / ``snapshot`` / ``scan``; all wording lives here.
"""
from typing import Any, Dict, List, Optional

from src.ta.scan import ScanResult
from src.ta.snapshot import Snapshot

RULE_LABELS = {
    "rsi_oversold_reclaim": "RSI chạm lại ngưỡng quá bán",
    "rsi_overbought_loss": "RSI chạm lại ngưỡng quá mua",
    "rsi_turning_up": "RSI đang quay đầu lên (còn trong vùng quá bán)",
    "rsi_turning_down": "RSI đang quay đầu xuống (còn trong vùng quá mua)",
    "adx_momentum": "ADX trên ngưỡng động lực",
}

SIDE_MARK = {"bullish": "▲", "bearish": "▼", "neutral": "•"}
QUALITY_MARK = {"strong": "★★★", "normal": "★★", "weak": "★"}

BOX_STATE_VN = {
    "inside": "còn trong hộp",
    "breakout_up_confirmed": "✅ vượt lên, volume xác nhận",
    "breakout_up_weak": "vượt lên, volume yếu",
    "breakdown_confirmed": "❌ thủng xuống, volume xác nhận",
    "breakdown_weak": "thủng xuống, volume yếu",
    "false_breakout_up": "phá lên giả",
    "false_breakdown": "phá xuống giả",
}

DISCLAIMER = (
    "_Số liệu kỹ thuật thuần tuý, không phải khuyến nghị đầu tư — "
    "quyết định vào lệnh là của bạn._"
)


def asof_note(as_of_requested: str, data_date: str = "") -> str:
    """Một câu nói rõ đây là bản hồi tưởng — rỗng khi chạy trên dữ liệu mới nhất.

    Hai ngày, không phải một: mốc người dùng *yêu cầu* và phiên cuối *có thật*
    trong tầm nhìn đó. Chọn 01/01/2025 là ngày nghỉ thì số liệu thật ra dừng ở
    31/12/2024 — giấu chỗ lệch này đi là để người đọc tự suy ra sai.
    """
    if not as_of_requested:
        return ""
    tail = ""
    if data_date and data_date not in ("-", as_of_requested):
        tail = f" · phiên gần nhất trong tầm nhìn: **{data_date}**"
    return (f"🕰️ **Hồi tưởng — giả định hôm nay là {as_of_requested}**{tail}. "
            "Mọi số liệu dưới đây chỉ đọc dữ liệu tới mốc đó; phiên sau mốc bị cắt bỏ.")


def _asof_lines(as_of_requested: str, data_date: str = "") -> List[str]:
    """Khối markdown chèn ngay dưới tiêu đề, hoặc rỗng."""
    note = asof_note(as_of_requested, data_date)
    return [f"> {note}", ""] if note else []


def _n(value: Optional[float], digits: int = 2, dash: str = "—") -> str:
    if value is None:
        return dash
    return f"{value:,.{digits}f}"


def _signed(value: Optional[float], digits: int = 2) -> str:
    return "—" if value is None else f"{value:+.{digits}f}%"


def _vol(value: Optional[float]) -> str:
    if not value:
        return "—"
    for unit, div in (("M", 1e6), ("K", 1e3)):
        if abs(value) >= div:
            return f"{value / div:.2f}{unit}"
    return f"{value:.0f}"


# ---------------------------------------------------------------------------
# scan
# ---------------------------------------------------------------------------
def format_scan(result: ScanResult, limit: int = 40, show_detail: bool = False) -> str:
    rules = ", ".join(RULE_LABELS.get(r, r) for r in result.rules)
    lines = [
        f"## Quét tín hiệu — {result.as_of}",
        "",
        *_asof_lines(getattr(result, "as_of_requested", ""), result.as_of),
        f"**Luật:** {rules}  ",
        f"**Bộ mã:** {result.scanned} mã · **Profile:** `{result.profile}` · "
        f"**Cửa sổ:** {result.recent_bars} phiên gần nhất",
        "",
    ]

    if not result.hits:
        lines += ["Không mã nào khớp trong cửa sổ này.", ""]
    else:
        shown = result.hits[:limit]
        lines += [
            "| # | Mã | Giá | +/- | Điểm | Tín hiệu | RSI | ADX | Diễn giải |",
            "|---|----|----:|----:|-----:|----------|----:|----:|-----------|",
        ]
        for i, h in enumerate(shown, 1):
            mark = SIDE_MARK.get(h.side, "•")
            quality = QUALITY_MARK.get(h.event_quality or "", "")
            adx_cell = f"{_n(h.adx, 1)}" + (
                f" {'↑' if h.adx_direction == 'up' else '↓' if h.adx_direction == 'down' else '→'}"
                if h.adx is not None else ""
            )
            lines.append(
                f"| {i} | **{h.symbol}** | {_n(h.close)} | {_signed(h.change_pct)} | "
                f"{h.score} | {mark} {quality} | {_n(h.rsi, 1)} | {adx_cell} | {h.note} |"
            )
        lines.append("")
        if len(result.hits) > limit:
            lines.append(f"_… và {len(result.hits) - limit} mã nữa (tăng `limit` để xem thêm)._")
            lines.append("")

        if show_detail:
            lines.append("### Chi tiết")
            lines.append("")
            for h in shown:
                lines.append(f"**{h.symbol}** — {h.note}")
                event = h.detail.get("event")
                if event:
                    lines.append(
                        f"  - Vào vùng: RSI chạm {event['extreme']} ngày {event['extreme_date']}, "
                        f"{event['bars_in_zone']} phiên trong vùng, quay lại ngưỡng "
                        f"{event['threshold']:.0f} ngày {event['date']}"
                    )
                    lines.append(f"  - Đánh giá: {', '.join(event['reasons'])}")
                lines.append(f"  - {h.detail['adx']['label']}")
                lines.append("")

    if result.unknown_symbols:
        lines.append(f"⚠️ Không có dữ liệu: {', '.join(result.unknown_symbols)}")
        lines.append("")
    if result.skipped:
        lines.append(f"⚠️ Bỏ qua do lỗi: {', '.join(result.skipped)}")
        lines.append("")

    lines += ["**Thang điểm:** chất lượng tín hiệu RSI (1–3) + ADX có động lực & cùng chiều (1–2) "
              "+ ADX đang mạnh lên (1) + phân kỳ (1) + giá xác nhận (1).", "", DISCLAIMER]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# snapshot
# ---------------------------------------------------------------------------
def format_snapshot(snap: Snapshot) -> str:
    if not snap.bars:
        return f"## {snap.symbol}\n\n" + "\n".join(f"⚠️ {w}" for w in snap.warnings)

    p, t, m, v, lv = snap.price, snap.trend, snap.momentum, snap.volume, snap.levels
    lines = [
        f"## {snap.symbol} — {snap.as_of}",
        "",
        *_asof_lines(getattr(snap, "as_of_requested", ""), snap.as_of),
        f"**Giá đóng cửa {_n(p['close'])}** ({_signed(p['change_pct'])} phiên) · "
        f"5 phiên {_signed(p.get('change_5d'))} · 20 phiên {_signed(p.get('change_20d'))}",
        "",
        *_last_bar_lines(snap),
        "### Xu hướng",
        f"- {t['label']}",
        f"- EMA20 `{_n(t['ema20'])}` ({_signed(t['vs_ema20_pct'])}) · "
        f"EMA50 `{_n(t['ema50'])}` ({_signed(t['vs_ema50_pct'])}) · EMA100 `{_n(t['ema100'])}`",
        *([f"- Chuỗi swing: {' → '.join(t['swings'])}"] if t.get("swings") else []),
        *([f"- {t['last_event']}"] if t.get("last_event") else []),
        "",
        "### Động lượng",
        f"- {snap.rsi_zone.get('label', '—')}",
        f"- {snap.adx.get('label', '—')}"
        + (f"  (+DI {_n(snap.adx.get('plus_di'), 1)} / -DI {_n(snap.adx.get('minus_di'), 1)})"
           if snap.adx.get("plus_di") is not None else ""),
        f"- MACD `{_n(m['macd_line'], 3)}` / signal `{_n(m['macd_signal'], 3)}` · "
        f"hist `{_n(m['macd_hist'], 3)}` · MFI14 `{_n(m['mfi14'], 1)}`",
        f"- ATR14 `{_n(m['atr14'])}` ({_n(m['atr_pct'], 1)}% giá) — biên độ dao động thường ngày",
        "",
        "### Thanh khoản",
        f"- KL phiên `{_vol(v['volume'])}` · TB20 `{_vol(v['avg20'])}` · "
        f"RVOL `{_n(v['rvol'])}` · Khối ngoại ròng `{_vol(v['foreign_net'])}` cp",
        "",
        "### Vùng giá tham chiếu",
        f"- Đỉnh/đáy 10 phiên: `{_n(lv['swing_high_10'])}` / `{_n(lv['swing_low_10'])}`",
        f"- Đỉnh/đáy 20 phiên: `{_n(lv['swing_high_20'])}` / `{_n(lv['swing_low_20'])}`",
        f"- Bollinger20: `{_n(lv['bb_lower'])}` … `{_n(lv['bb_mid'])}` … `{_n(lv['bb_upper'])}`",
        "",
    ]

    if snap.recent_rsi_events:
        lines += ["### Lịch sử tín hiệu RSI gần đây", ""]
        for e in reversed(snap.recent_rsi_events):
            bullish = e["kind"] == "oversold_reclaim"
            kind = ("chạm lại quá bán ⟶ tín hiệu tăng" if bullish
                    else "chạm lại quá mua ⟶ tín hiệu giảm")
            extreme_word = "đáy RSI" if bullish else "đỉnh RSI"
            star = QUALITY_MARK.get(e["quality"], "")
            div = " · có phân kỳ" if e["divergence"] else ""
            lines.append(
                f"- `{e['date']}` {kind} {star} — {extreme_word} {e['extreme']} "
                f"({e['bars_in_zone']} phiên trong vùng), giá {_n(e['close'])}{div}"
            )
        lines.append("")

    for w in snap.warnings:
        lines.append(f"⚠️ {w}")
    if snap.warnings:
        lines.append("")

    lines.append(DISCLAIMER)
    return "\n".join(lines)


def format_deep_dive(snap: Snapshot, structure=None) -> str:
    """Everything the deep dive says about one symbol, in one string.

    The snapshot carries the indicators; the structure adds the horizontal
    levels and the reversal formations. Composed here rather than in the MCP
    tool so the terminal answer and the HTML dossier cannot drift apart.
    """
    block = format_snapshot(snap)
    if structure is None or not snap.bars:
        return block

    extra = format_levels_brief(structure.levels, getattr(structure, "profile", None))
    extra += format_formations_brief(getattr(structure, "evidence", []))
    if not extra:
        return block
    # The disclaimer closes the block, so the added sections go in front of it.
    body = block[: -len(DISCLAIMER)].rstrip() if block.endswith(DISCLAIMER) else block
    tail = "\n\n" + DISCLAIMER if block.endswith(DISCLAIMER) else ""
    return body + "\n\n" + "\n".join(extra).rstrip() + tail


def format_symbol_list(rows: List[Dict[str, Any]], title: str) -> str:
    lines = [f"## {title} — {len(rows)} mã", ""]
    if not rows:
        return "\n".join(lines + ["Không có mã nào."])
    lines += ["| Mã | Từ | Đến | Số phiên |", "|----|----|-----|---------:|"]
    for r in rows:
        lines.append(f"| {r['symbol']} | {r['first']} | {r['last']} | {r['bars']:,} |")
    return "\n".join(lines)



def _last_bar_lines(snap) -> List[str]:
    """What the most recent session actually looked like.

    The snapshot tables say where price sits; this says how it got there —
    whether the bar was wide or listless, and which end it closed at.
    """
    bar = getattr(snap, "last_bar", None)
    if not bar:
        return []
    from src.ta.candles import CEILING, FLOOR, LIMIT_LABELS, NORMAL

    limit = bar.get("limit", NORMAL)
    if limit in (CEILING, FLOOR):
        return ["### Phiên gần nhất", "",
                f"- **{LIMIT_LABELS[limit]}** ({_signed(bar.get('change_vs_basic'), 1)}%) "
                f"— dư lệnh chất đống, không đọc được hình nến", ""]

    lines = ["### Phiên gần nhất", ""]
    spread = bar.get("spread_atr")
    if spread is not None:
        if spread >= 1.5:
            width = "biên độ rộng bất thường"
        elif spread >= 1.0:
            width = "biên độ rộng hơn thường ngày"
        elif spread <= 0.5:
            width = "biên độ hẹp, phiên tẻ nhạt"
        else:
            width = "biên độ bình thường"
        lines.append(f"- Biên độ `{spread:g}×` ATR14 — {width}")

    pos = bar.get("close_pos")
    if pos is not None:
        if pos >= 0.75:
            where = "bên mua giữ được phiên"
        elif pos <= 0.25:
            where = "bên bán giữ được phiên"
        else:
            where = "chưa bên nào dứt điểm"
        lines.append(f"- Đóng ở `{pos * 100:.0f}%` biên độ nến — {where}")

    wicks = []
    if (bar.get("upper_wick_pct") or 0) >= 0.4:
        wicks.append("Râu trên dài — bị đánh xuống từ vùng cao")
    if (bar.get("lower_wick_pct") or 0) >= 0.4:
        wicks.append("Râu dưới dài — được đỡ lên từ vùng thấp")
    if wicks:
        lines.append("- " + " · ".join(wicks))
    if limit != NORMAL:
        lines.append(f"- {LIMIT_LABELS[limit]}")

    for signal in getattr(snap, "candles", [])[:3]:
        lines.append(f"- {signal['label']}")
    for signal in getattr(snap, "vsa", [])[:2]:
        lines.append(f"- {signal['label']}")
    lines.append("")
    return lines


def format_levels_brief(levels, profile=None) -> List[str]:
    """Compact horizontal-level block — one bullet per zone, for the deep dive."""
    if not levels:
        return []
    from src.ta.levels import KIND_LABELS, SOURCE_LABELS

    lines = ["### Vùng giá quan trọng", ""]
    for level in levels:
        band = (f"{_n(level.low)}–{_n(level.high)}"
                if level.high > level.low else _n(level.price))
        lines.append(
            f"- **{level.id}** `{band}` — {KIND_LABELS.get(level.kind, level.kind)} "
            f"({SOURCE_LABELS.get(level.source, level.source)}), chạm {level.touches} lần, "
            f"{level.volume_share:g}% volume, giá cách {_signed(level.distance_pct, 1)}"
        )
    if profile is not None:
        lines.append(f"- POC `{_n(profile.poc)}` · 70% khối lượng trong "
                     f"{_n(profile.value_low)}–{_n(profile.value_high)}")
    lines.append("")
    return lines


def format_formations_brief(evidence) -> List[str]:
    """Compact reversal-formation block — one bullet per formation.

    ``format_structure`` prints the full table; the deep dive only has room for
    the verdict, which is the part that carries a level and a condition.
    """
    if not evidence:
        return []
    lines = ["### Mô hình đảo chiều", ""]
    for ev in evidence:
        f = ev.formation
        lines.append(
            f"- {ev.mark} **{f.name}** ({f.start_date} → {f.end_date}) · "
            f"neckline `{_n(f.neckline_now)}` — {ev.conclusion}"
        )
    lines.append("")
    return lines


# ---------------------------------------------------------------------------
# structure
# ---------------------------------------------------------------------------
def format_structure(structure, image_path: Optional[str] = None) -> str:
    """The drawn levels, and what each one means for a decision."""
    from src.ta.confluence import TIER_LABELS
    from src.ta.levels import KIND_LABELS as LEVEL_KIND_VN
    from src.ta.levels import SOURCE_LABELS as LEVEL_SOURCE_VN
    from src.ta.formations import PIVOT_ROLES
    from src.ta.formations import STATE_LABELS as FORMATION_STATE_VN

    if not structure.bars:
        return f"## {structure.symbol}\n\n" + "\n".join(f"⚠️ {w}" for w in structure.warnings)

    lines = [
        f"## {structure.symbol} — cấu trúc giá ({structure.as_of})",
        "",
        *_asof_lines(getattr(structure, "as_of_requested", ""), structure.as_of),
        f"Đóng cửa **{_n(structure.close)}** · ATR14 `{_n(structure.atr14)}` · "
        f"{structure.bars} phiên · {len(structure.pivots)} swing pivot",
        "",
    ]

    box = structure.box
    if box is not None:
        lines += [
            "### Bounding box",
            "",
            "| ID | Cạnh trên | Cạnh dưới | Biên độ | Số phiên | Trạng thái |",
            "|----|----------:|----------:|--------:|---------:|------------|",
            f"| **{box.id}** | {_n(box.top)} | {_n(box.bottom)} | {box.height_pct:.1f}% | "
            f"{box.bars} | {BOX_STATE_VN.get(box.state, box.state)} |",
            "",
        ]
        if box.target is not None:
            hit = " ✓ đã chạm" if box.target_hit else ""
            lines.append(
                f"- Mục tiêu đo được (chiều cao hộp chiếu ra): **{_n(box.target)}**{hit} · "
                f"mất hiệu lực nếu đóng cửa qua {_n(box.invalidation)}"
            )
            lines.append("")

    if structure.trendlines:
        lines += ["### Đường xu hướng", ""]
        for line in structure.trendlines:
            state = "đã phá vỡ" if line.broken else "còn hiệu lực"
            lines.append(
                f"- **{line.name}** "
                f"`{_n(line.value_now)}` ({state}, chạm {line.touches} lần) — "
                f"{line.p1_date} → {line.p2_date}"
            )
        lines.append("")
        lines += ["Hỏi theo ID (ví dụ *\"tại sao nối "
                  f"{structure.trendlines[0].id}?\"*) để xem lý do vẽ và ý nghĩa.", ""]

    if getattr(structure, "evidence", None):
        lines += ["### Mô hình đảo chiều", ""]
        for ev in structure.evidence:
            f = ev.formation
            lines.append(
                f"{ev.mark} **{f.id} {f.name}** ({f.start_date} → {f.end_date}, "
                f"{f.bars} phiên) — {FORMATION_STATE_VN.get(f.state, f.state)}, "
                f"{TIER_LABELS.get(ev.tier, ev.tier)}"
            )
            lines.append("")
            marks = " · ".join(
                f"{role.capitalize()} {_n(p.price)}"
                for role, p in zip(PIVOT_ROLES.get(f.kind, []), f.pivots)
            )
            tilt = ""
            if abs(f.neckline_slope) > 1e-9:
                tilt = " (nghiêng lên)" if f.neckline_slope > 0 else " (nghiêng xuống)"
            lines.append("| Yếu tố | Ghi nhận |")
            lines.append("|---|---|")
            lines.append(f"| Các mốc | {marks} |")
            lines.append(f"| Neckline | `{_n(f.neckline_now)}`{tilt} |")
            lines.append(f"| Hình mẫu | fit {f.fit_atr:g} ATR, cao {_n(f.height)} |")
            lines.append(f"| Nến | {ev.candle_note} |")
            lines.append(f"| Volume | {ev.volume_note} |")
            if f.target is not None:
                hit = " ✓ đã chạm" if f.target_hit else ""
                lines.append(f"| Mục tiêu đo được | `{_n(f.target)}`{hit} |")
            lines.append(f"| Phủ định tại | `{_n(f.invalidation)}` |")
            lines.append("")
            lines.append(f"→ {ev.conclusion}")
            lines.append("")

    if getattr(structure, "levels", None):
        lines += ["### Vùng giá quan trọng", ""]
        lines += ["| ID | Vùng | Vai trò | Nguồn | Chạm | % volume | Cách giá |",
                  "|----|------|---------|-------|-----:|---------:|---------:|"]
        for level in structure.levels:
            band = (f"{_n(level.low)}–{_n(level.high)}"
                    if level.high > level.low else _n(level.price))
            lines.append(
                f"| **{level.id}** | {band} | {LEVEL_KIND_VN.get(level.kind, level.kind)} "
                f"| {LEVEL_SOURCE_VN.get(level.source, level.source)} | {level.touches} "
                f"| {level.volume_share:g}% | {_signed(level.distance_pct, 1)} |"
            )
        lines.append("")
        profile = getattr(structure, "profile", None)
        if profile is not None:
            lines.append(
                f"- Volume tập trung nhiều nhất tại `{_n(profile.poc)}` (POC); "
                f"70% khối lượng nằm trong {_n(profile.value_low)}–{_n(profile.value_high)}"
            )
            lines.append("")

    lines += ["### Diễn giải", ""]
    lines += [f"- {item}" for item in structure.brief]
    lines.append("")

    if image_path:
        lines += [f"📈 Ảnh biểu đồ: `{image_path}`", ""]
    for w in structure.warnings:
        lines.append(f"⚠️ {w}")
    if structure.warnings:
        lines.append("")

    lines.append(DISCLAIMER)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# forecasts
# ---------------------------------------------------------------------------
def format_forecast_check(result, include_closed: bool = False) -> str:
    """Status of every stored forecast, changes first — this is the 'thông báo'."""
    from src.ta.forecast import BASIS_VN, STATUS_VN

    requested = getattr(result, "as_of_requested", "")
    scope = (f"Đã kiểm tra {result.checked} forecast tạo trước mốc — đánh giá lại tại chỗ, "
             "không ghi đè trạng thái thật." if requested
             else f"Đã kiểm tra {result.checked} forecast.")
    lines = [f"## Theo dõi forecast — {result.as_of}", "",
             *_asof_lines(requested, result.as_of), scope, ""]

    if result.changes:
        lines += [f"### 🔔 {len(result.changes)} forecast đổi trạng thái", ""]
        for c in result.changes:
            lines.append(
                f"- **{c['symbol']}** — {STATUS_VN.get(c['from'], c['from'])} → "
                f"**{STATUS_VN.get(c['to'], c['to'])}**"
                + (f" ngày {c['date']}" if c.get("date") else "")
                + f" · giá {_n(c['close'])} · mục tiêu {_n(c['target'])}"
            )
            lines.append(f"  {c['note']}")
        lines.append("")
    else:
        lines += ["_Không có forecast nào đổi trạng thái từ lần kiểm tra trước._", ""]

    open_list = [f for f in result.forecasts if f.is_open]
    if open_list:
        lines += ["### Đang mở", "",
                  "| Mã | Cơ sở | Trạng thái | Giá | Kích hoạt khi | Mục tiêu | Huỷ nếu | Phiên |",
                  "|----|-------|------------|----:|--------------:|---------:|--------:|------:|"]
        for f in open_list:
            arrow = ">" if f.trigger_type == "close_above" else "<"
            vol = f" @{f.confirm_volume_x:g}×" if f.confirm_volume_x else ""
            gap = ""
            if f.current_close and f.status == "pending":
                past = (f.current_close > f.trigger_level if f.trigger_type == "close_above"
                        else f.current_close < f.trigger_level)
                if past and f.confirm_volume_x:
                    # Price is there but the volume filter held it back — say so,
                    # otherwise the distance column reads like a contradiction.
                    gap = f" · giá đã vượt, chờ volume ({_n(f.current_volume_x, 2)}×)"
                elif past:
                    gap = " · giá đã vượt"
                else:
                    gap = f" (còn {abs(f.trigger_level / f.current_close - 1) * 100:.1f}%)"
            left = max(0, f.deadline_bars - f.bars_elapsed)
            lines.append(
                f"| **{f.symbol}** | {BASIS_VN.get(f.basis, f.basis)} | "
                f"{STATUS_VN.get(f.status, f.status)} | {_n(f.current_close)} | "
                f"{arrow} {_n(f.trigger_level)}{vol}{gap} | {_n(f.target)} | "
                f"{_n(f.invalidation)} | còn {left} |"
            )
        lines.append("")

    if include_closed:
        closed = [f for f in result.forecasts if not f.is_open]
        if closed:
            lines += ["### Đã đóng", "",
                      "| Mã | Cơ sở | Kết quả | Ngày | Giá chốt | Mục tiêu |",
                      "|----|-------|---------|------|---------:|---------:|"]
            for f in closed:
                lines.append(
                    f"| {f.symbol} | {BASIS_VN.get(f.basis, f.basis)} | "
                    f"{STATUS_VN.get(f.status, f.status)} | {f.resolved_date or '—'} | "
                    f"{_n(f.resolved_close)} | {_n(f.target)} |"
                )
            lines.append("")

    if not open_list and not include_closed:
        lines += ["_Chưa có forecast nào đang mở. Dùng `create_forecasts` để tạo._", ""]
    for err in result.errors:
        lines.append(f"⚠️ {err}")
    if result.errors:
        lines.append("")
    lines.append(DISCLAIMER)
    return "\n".join(lines)


def format_forecast_list(forecasts, title: str = "Forecast vừa tạo") -> str:
    from src.ta.forecast import BASIS_VN

    if not forecasts:
        return ("Không có setup nào đủ điều kiện để đặt forecast — "
                "cần hộp tích luỹ, đường nối đỉnh gần giá, hoặc tín hiệu RSI mới.")
    lines = [f"## {title} — {len(forecasts)}", "",
             "| Mã | Cơ sở | Kích hoạt khi | Mục tiêu | Huỷ nếu | Hạn | Diễn giải |",
             "|----|-------|--------------:|---------:|--------:|----:|-----------|"]
    for f in forecasts:
        arrow = ">" if f.trigger_type == "close_above" else "<"
        vol = f" @{f.confirm_volume_x:g}×" if f.confirm_volume_x else ""
        upside = (f.target / f.created_close - 1) * 100 if f.created_close else 0
        lines.append(
            f"| **{f.symbol}** | {BASIS_VN.get(f.basis, f.basis)} | "
            f"{arrow} {_n(f.trigger_level)}{vol} | {_n(f.target)} ({upside:+.1f}%) | "
            f"{_n(f.invalidation)} | {f.deadline_bars} phiên | {f.note} |"
        )
    lines += ["", DISCLAIMER]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# data update
# ---------------------------------------------------------------------------
def format_update(result, limit: int = 40) -> str:
    """What the fetch actually changed — new bars first, problems last."""
    from src.ta.update import MODE_VN

    if result.fatal:
        return f"## Cập nhật giá — thất bại\n\n⚠️ {result.fatal}"

    changed, unchanged, failed = result.changed, result.unchanged, result.failed
    lines = [
        f"## Cập nhật giá — {result.started}",
        "",
        f"**Phạm vi:** {MODE_VN.get(result.mode, result.mode)} · "
        f"{result.requested} mã · {result.duration_s}s",
        "",
        f"- ✅ {len(changed)} mã có dữ liệu mới (**{result.new_bars} phiên**)",
        f"- ⏸ {len(unchanged)} mã không đổi",
    ]
    if failed:
        lines.append(f"- ⚠️ {len(failed)} mã lỗi")
    if result.latest_date:
        lines.append(f"- 📅 Phiên mới nhất trên đĩa: **{result.latest_date}**")
    lines.append("")

    if changed:
        shown = sorted(changed, key=lambda r: (-r.new_bars, r.symbol))[:limit]
        lines += ["| Mã | Trước | Sau | Phiên mới |",
                  "|----|-------|-----|----------:|"]
        for r in shown:
            lines.append(
                f"| **{r.symbol}** | {r.before or '—'} | {r.after or '—'} | {r.new_bars} |"
            )
        lines.append("")
        if len(changed) > limit:
            lines.append(f"_… và {len(changed) - limit} mã nữa._")
            lines.append("")

    gaps = result.gaps
    if gaps:
        lines += [
            f"### ⚠️ {len(gaps)} mã còn thiếu dữ liệu",
            "",
            "Phiên cuối trên đĩa cách xa mốc bắt đầu tải, nghĩa là còn khoảng trống "
            "`mode` này không lấp được. Chỉ báo tính trên chuỗi bị hở sẽ sai.",
            "",
            "| Mã | Phiên cuối cũ | Tải từ | Thiếu ~ngày |",
            "|----|---------------|--------|------------:|",
        ]
        for r in gaps[:20]:
            lines.append(f"| **{r.symbol}** | {r.before} | {r.fetch_from} | {r.gap_days} |")
        widest = gaps[0].gap_days
        suggested = "full" if widest > 120 else "quarter" if widest > 40 else "recent"
        lines += [
            "",
            f"→ Chạy lại các mã này với `mode=\"{suggested}\"` để lấp: "
            f"`{','.join(r.symbol for r in gaps[:20])}`",
            "",
        ]

    warned = [r for r in result.results if r.warnings]
    if warned:
        lines += ["### Ghi chú", ""]
        for r in warned[:10]:
            for w in r.warnings:
                lines.append(f"- {r.symbol}: {w}")
        lines.append("")

    if failed:
        lines += ["### Lỗi", ""]
        for r in failed[:15]:
            lines.append(f"- **{r.symbol}**: {r.error}")
        if len(failed) > 15:
            lines.append(f"- _… và {len(failed) - 15} mã nữa._")
        lines.append("")

    if changed:
        lines.append("_Cache đã được xoá — mọi tool đọc dữ liệu mới ngay, không cần khởi động lại._")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# ranking
# ---------------------------------------------------------------------------
def _clip(text: str, limit: int = 150) -> str:
    """Table cells have to stay one screen wide; the full sentence is in the HTML."""
    text = (text or "").strip()
    return text if len(text) <= limit else text[:limit].rstrip(" ,.;—-") + "…"


def _futures_why(row) -> str:
    """Vì sao mã này phơi nhiễm tới mức đó — kênh trước, rồi mới tới các số.

    Kênh đứng đầu câu vì nó không phải một mức độ mà là một *loại*: mã trong rổ
    VN30 nhận lệnh chênh lệch giá thẳng vào, mã ngoài rổ thì không — cùng một
    con số beta ở hai bên không có cùng nghĩa.
    """
    e = getattr(row, "futures", None)
    if e is None or e.beta is None:
        return _clip((e.note if e else "") or row.headline)
    # Câu kênh đầy đủ nằm ở dòng `explain` ngay trên bảng; lặp lại nguyên văn ở
    # mỗi dòng chỉ đẩy các con số ra khỏi tầm mắt.
    bits = ["trong rổ VN30" if e.in_vn30 else "ngoài rổ VN30",
            f"β {e.beta:.2f}" + (f" (R² {e.r2:.2f})" if e.r2 is not None else "")]
    if e.liquidity_share_pct is not None:
        bits.append(f"{e.liquidity_share_pct:.2f}% thanh khoản rổ")
    if e.expiry_move_ratio is not None:
        bits.append(f"biên độ phiên đáo hạn {e.expiry_move_ratio:.2f}× phiên thường")
    return _clip(" · ".join(bits), 190)


def _rank_why(row, criterion_key: str) -> str:
    """The sentence that explains this row's number, not a restatement of it."""
    if criterion_key in ("trend", "trend_abs", "adx", "vs_ema20", "vs_ema50"):
        return _clip(row.trend.note, 190)
    if criterion_key in ("pattern", "confidence", "target_pct", "risk_reward"):
        return _clip(row.pattern.note or row.headline)
    if criterion_key in ("futures", "beta"):
        return _futures_why(row)
    return _clip(row.headline)


def format_rank_list(
    rows,
    criterion,
    descending: bool = True,
    total: Optional[int] = None,
    filters: Optional[List[str]] = None,
    as_of: str = "",
    as_of_requested: str = "",
) -> str:
    """One ordered list, with the reason each row sits where it sits.

    This is the answer to "xếp cho tôi theo <tiêu chí>" — the numbers alone
    would be a leaderboard; the `Vì sao` column is what makes it readable.
    """
    from src.ta.ranking import CONFIDENCE_VN, SIDE_MARK

    arrow = "cao → thấp" if descending else "thấp → cao"
    lines = [f"## Xếp hạng theo {criterion.label} — {arrow}", "",
             *_asof_lines(as_of_requested, as_of)]
    head = []
    if as_of:
        head.append(f"Dữ liệu tới phiên **{as_of}**")
    head.append(f"**{len(rows)}**"
                + (f"/{total}" if total and total != len(rows) else "") + " mã")
    if filters:
        head.append("lọc: " + " · ".join(filters))
    lines += [" · ".join(head), "", f"_{criterion.explain}_", ""]

    if not rows:
        lines += ["", "Không có mã nào khớp bộ lọc."]
        return "\n".join(lines)

    # The criterion column is the only place its number appears — no point
    # printing "Cường độ" twice when the sort already is the trend score.
    show_trend = criterion.key not in ("trend", "trend_abs")
    show_pattern = criterion.key not in ("confidence", "pattern")
    unit = f" ({criterion.unit})" if criterion.unit else ""

    header = ["#", "Mã", f"{criterion.label}{unit}", "Giá", "+/-"]
    align = ["--:", "----", "------:", "----:", "----:"]
    if show_trend:
        header.append("Cường độ")
        align.append("-------:")
    if show_pattern:
        header.append("Mẫu hình")
        align.append("--------")
    header.append("Vì sao")
    align.append("--------")
    lines += ["| " + " | ".join(header) + " |", "|" + "|".join(align) + "|"]

    for i, row in enumerate(rows, 1):
        value = criterion.value(row)
        shown = _n(value, criterion.digits) if value is not None else "—"
        if not show_trend:
            shown = f"{SIDE_MARK[row.trend.side]} {shown}"
        cells = [str(i), f"**{row.symbol}**", shown, _n(row.close), _signed(row.change_pct)]
        if show_trend:
            cells.append(f"{SIDE_MARK[row.trend.side]} {row.trend.score:+.1f}")
        if show_pattern:
            cells.append(f"{CONFIDENCE_VN[row.pattern.state]} {row.pattern.confidence:.0f}"
                         if row.pattern.state != "none" else "—")
        else:
            shown_state = CONFIDENCE_VN[row.pattern.state]
            cells[2] = f"{shown} · {shown_state}"
        cells.append(_rank_why(row, criterion.key))
        lines.append("| " + " | ".join(cells) + " |")
    lines += ["", DISCLAIMER]
    return "\n".join(lines)


def _rank_block(title: str, rows, kind: str) -> List[str]:
    from src.ta.ranking import BIAS_MARK, CONFIDENCE_VN, SIDE_MARK

    lines = [f"### {title}", ""]
    if not rows:
        return lines + ["_Không có mã nào._", ""]
    if kind == "trend":
        lines += ["| # | Mã | Cường độ | ADX | Giá | +/- | Điểm đến từ đâu |",
                  "|--:|----|--------:|----:|----:|----:|------------------|"]
        for i, r in enumerate(rows, 1):
            warn = " ⚠️" if r.trend.conflict else ""
            lines.append(
                f"| {i} | **{r.symbol}** | {SIDE_MARK[r.trend.side]} {r.trend.score:+.1f} | "
                f"{_n(r.trend.adx, 1)} | {_n(r.close)} | {_signed(r.change_pct)} | "
                f"{r.trend.note}{warn} |"
            )
    elif kind == "futures":
        lines += ["| # | Mã | Kênh | β VN30 | % thanh khoản rổ | Biên độ đáo hạn | "
                  "RS 20p | Điểm |",
                  "|--:|----|------|-------:|-----------------:|----------------:|"
                  "-------:|-----:|"]
        for i, r in enumerate(rows, 1):
            e = r.futures
            if e is None or e.beta is None:
                continue
            lines.append(
                f"| {i} | **{r.symbol}** | {'trong rổ' if e.in_vn30 else 'ngoài rổ'} | "
                f"{_n(e.beta)} | "
                f"{_n(e.liquidity_share_pct) if e.liquidity_share_pct is not None else '—'} | "
                f"{_n(e.expiry_move_ratio)}× | {_signed(e.rs_20)} | **{e.score:.0f}** |"
            )
        return lines + [""]
    else:
        lines += ["| # | Mã | Mẫu hình | Độ tin cậy | Mốc | Mục tiêu | Huỷ nếu |",
                  "|--:|----|----------|-----------|----:|--------:|--------:|"]
        for i, r in enumerate(rows, 1):
            p = r.pattern
            lines.append(
                f"| {i} | **{r.symbol}** | {BIAS_MARK.get(p.bias, '•')} {p.name} | "
                f"{CONFIDENCE_VN[p.state]} {p.confidence:.0f} | {_n(p.trigger)} | "
                f"{_n(p.target)} | {_n(p.invalidation)} |"
            )
    return lines + [""]


def format_ranking(ranking, top: int = 8) -> str:
    """The summary printed right after a board is built."""
    from collections import Counter

    from src.ta.ranking import (
        BEARISH, BULLISH, CONFIDENCE_RANK, CONFIDENCE_VN, CRITERIA, DOWN, SIDE_VN,
        UP, sort_rows,
    )

    if not ranking.rows:
        return ("## Bảng xếp hạng kỹ thuật\n\n"
                + "\n".join(f"⚠️ {s}" for s in ranking.skipped))

    lines = [
        f"# Bảng xếp hạng kỹ thuật — {ranking.as_of}",
        "",
        *_asof_lines(getattr(ranking, "as_of_requested", ""), ranking.as_of),
        f"{len(ranking.rows)} mã · nhóm `{ranking.universe}` · dựng lúc {ranking.generated}",
        "",
    ]
    if ranking.html_path:
        lines.append(f"📄 Bảng HTML (bấm tiêu đề cột để tự sắp xếp): `{ranking.html_path}`")
    if ranking.json_path:
        requested = getattr(ranking, "as_of_requested", "")
        again = (f"gọi `rank_list` với `as_of={requested}` để xếp lại theo tiêu chí khác "
                 "(bảng hồi tưởng không đụng tới bảng của phiên thật)" if requested
                 else "gọi `rank_list` để xếp lại theo tiêu chí khác, không phải dựng lại từ đầu")
        lines.append(f"🗂 Dữ liệu xếp hạng: `{ranking.json_path}` — {again}.")
    lines.append("")
    # Lực nền chung của cả bảng, đứng trước các danh sách xếp hạng: đọc "mã nào
    # mạnh nhất" mà không biết phái sinh đang ở tư thế nào là đọc thiếu một vế.
    lines += format_futures_brief(getattr(ranking, "futures", None), None,
                                  ref_date=ranking.as_of)

    up_rows, _ = sort_rows(ranking.rows, "trend", True, side=UP, limit=top)
    down_rows, _ = sort_rows(ranking.rows, "trend", False, side=DOWN, limit=top)
    bull, _ = sort_rows(ranking.rows, "confidence", True, bias=BULLISH, limit=top)
    bear, _ = sort_rows(ranking.rows, "confidence", True, bias=BEARISH, limit=top)

    lines += ["## Xu hướng — xếp theo cường độ", ""]
    lines += _rank_block(f"▲ Tăng mạnh nhất ({top} mã đầu)", up_rows, "trend")
    lines += _rank_block(f"▼ Giảm mạnh nhất ({top} mã đầu)", down_rows, "trend")
    lines += ["## Mẫu hình — xếp theo độ tin cậy", ""]
    lines += _rank_block("▲ Mẫu hình tăng", bull, "pattern")
    lines += _rank_block("▼ Mẫu hình giảm", bear, "pattern")

    fut_rows, _ = sort_rows(ranking.rows, "futures", True, limit=top)
    if any(getattr(r, "futures", None) and r.futures.beta is not None for r in fut_rows):
        lines += ["## Phái sinh — mã nào nằm gần dòng tiền hợp đồng nhất", ""]
        lines += _rank_block(f"⚙️ Phơi nhiễm cao nhất ({top} mã đầu)", fut_rows, "futures")

    sides = Counter(r.trend.side for r in ranking.rows)
    states = Counter(r.pattern.state for r in ranking.rows)
    lines += [
        "## Phân bố",
        "",
        "- Xu hướng: " + " · ".join(
            f"**{sides.get(k, 0)}** {SIDE_VN[k]}" for k in (UP, DOWN, "flat")),
        "- Mẫu hình: " + " · ".join(
            f"**{states.get(k, 0)}** {CONFIDENCE_VN[k]}"
            for k in sorted(states, key=lambda s: -CONFIDENCE_RANK.get(s, 0))),
        "",
        "## Sắp xếp lại được theo",
        "",
        " · ".join(f"`{k}`" for k in CRITERIA),
        "",
    ]
    if ranking.skipped:
        lines += [f"⚠️ Bỏ qua {len(ranking.skipped)} mã: "
                  + ", ".join(ranking.skipped[:8])
                  + (" …" if len(ranking.skipped) > 8 else ""), ""]
    lines.append(DISCLAIMER)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# phái sinh
# ---------------------------------------------------------------------------
#: Cơ chế lan truyền, viết một lần ở đây.
#:
#: Đây là phần **không** đo được từ ``data/`` — nó là luật chơi của sản phẩm,
#: không phải một con số suy ra từ giá. Để nó nằm cạnh các con số, trong cùng
#: một file, thì người đọc mới nối được "basis chiết khấu" với "vì sao điều đó
#: chạm tới cổ phiếu tôi đang cầm".
FUTURES_MECHANISM = [
    "**Hợp đồng thanh toán theo VN30, không phải VNINDEX.** Chỉ 30 mã trong rổ "
    "nằm trên đường lan truyền cơ học; phần còn lại của sàn chịu ảnh hưởng qua "
    "tâm lý chung, tức là qua beta.",
    "**Phái sinh phản ứng trước.** T+0, đòn bẩy ~7 lần, bán khống không cần vay "
    "hàng — nên một kỳ vọng đổi chiều hiện ra ở basis trước khi hiện ra ở giá "
    "cổ phiếu. Đó là lý do để đọc basis, chứ không phải vì basis dự báo được "
    "điều gì.",
    "**Chênh lệch giá kéo theo lệnh rổ.** Basis lệch xa thì bên kinh doanh "
    "chênh lệch mua/bán *cả rổ cơ sở* để khoá lời — lệnh đó rơi vào đúng các mã "
    "vốn hoá lớn, thanh khoản cao trong VN30.",
    "**Phiên đáo hạn (thứ Năm thứ ba hằng tháng) là ngày đặc biệt.** Giá thanh "
    "toán cuối cùng tính theo chính chỉ số VN30 lúc đóng cửa, nên vị thế lớn có "
    "động cơ tác động vào ATC của vài mã trọng số cao. Biên độ phiên đó thường "
    "rộng bất thường và **không phản ánh cung cầu của riêng mã**.",
]


def format_futures(snap, mechanism: bool = True) -> str:
    """Bức tranh phái sinh của phiên gần nhất, kèm phần cơ chế lan truyền."""
    if not snap.bars:
        return ("## Thị trường phái sinh VN30\n\n"
                + "\n".join(f"⚠️ {w}" for w in snap.warnings))

    s, f, b, e, fl = snap.spot, snap.front, snap.basis, snap.expiry, snap.flow
    lines = [
        f"## Phái sinh VN30 — {snap.as_of}",
        "",
        *_asof_lines(getattr(snap, "as_of_requested", ""), snap.as_of),
        f"**VN30 {_n(s['close'])}** ({_signed(s.get('change_pct'))} phiên · "
        f"5 phiên {_signed(s.get('change_5d'))}) — "
        f"**{f['symbol']} {_n(f['close'])}**"
        + (f" ({_signed(f.get('change_pct'))})" if f.get("change_pct") is not None
           else " (phiên nối hợp đồng — % không có nghĩa)"),
        "",
        "### Chênh lệch phái sinh − cơ sở (basis)",
        "",
        f"- **{b['points']:+.2f} điểm** ({b['pct']:+.3f}% chỉ số) · "
        f"trung vị 5 phiên `{_n(b.get('median_5'))}` · 20 phiên `{_n(b.get('median_20'))}`",
        f"- Phân vị `{_n(b.get('percentile'), 0)}%` trên {b.get('window')} phiên gần nhất · "
        f"`{_n(b.get('percentile_same_maturity'), 0)}%` nếu chỉ so với "
        f"{b.get('n_same_maturity')} phiên **cùng quãng đường tới đáo hạn**",
        f"- Đáo hạn `{e.get('date')}` — còn **{e.get('sessions_left')} phiên** "
        f"({e.get('days_left')} ngày)"
        + (" · *ước lượng, chưa trừ ngày lễ*" if e.get("estimated") else ""),
    ]
    if snap.term:
        # Tháng kế tiếp thường mỏng tới mức chỉ đọc được hướng — nhưng **sát đáo
        # hạn thì không**: thanh khoản dịch dần sang nó, và đúng những phiên đó
        # dán nhãn "mỏng" là nói sai về chính con số vừa in ra. Nên để tỷ lệ so
        # với tháng hiện tại tự quyết định câu chữ.
        share = (snap.term["contracts"] / f["contracts"] * 100
                 if f.get("contracts") else 0.0)
        weight = ("mỏng, chỉ đọc hướng" if share < 10
                  else "thanh khoản đang chuyển sang tháng sau")
        lines.append(
            f"- Cấu trúc kỳ hạn: VN30F2M `{_n(snap.term['f2m'])}`, "
            f"chênh so với tháng hiện tại **{snap.term['spread']:+.2f} điểm** "
            f"({snap.term['contracts']:,} HĐ = {share:.0f}% tháng hiện tại — {weight})")

    lines += [
        "",
        "### Dòng tiền",
        "",
        f"- Khối lượng `{f['contracts']:,}` HĐ · TB20 `{f['avg_contracts_20']:,}` · "
        f"RVOL `{_n(f.get('rvol'))}` · giá trị danh nghĩa `{_n(f.get('notional_bn'), 0)}` tỷ",
        f"- Giá trị khớp lệnh rổ VN30 `{_n(s.get('value_bn'), 0)}` tỷ → "
        f"**đòn bẩy phái sinh/cơ sở {_n(fl.get('leverage_ratio'))}×** "
        f"(TB20 {_n(fl.get('leverage_avg20'))}×)",
        f"- Tự doanh trên phái sinh: phiên `{(fl.get('prop_net_bn') or 0):+,.1f}` tỷ · "
        f"5 phiên `{(fl.get('prop_net_5d_bn') or 0):+,.1f}` tỷ",
        f"- Khối ngoại trên phái sinh: phiên `{fl.get('foreign_net_contracts', 0):+,}` HĐ · "
        f"5 phiên `{fl.get('foreign_net_contracts_5d', 0):+,}` HĐ · "
        f"khối ngoại trên cơ sở `{(s.get('foreign_net_bn') or 0):+,.0f}` tỷ",
        "",
    ]

    if snap.readings:
        lines += ["### Đọc ra gì", ""] + [f"- {r}" for r in snap.readings] + [""]

    if mechanism:
        lines += ["### Ảnh hưởng tới cổ phiếu đi qua đường nào", ""]
        lines += [f"{i}. {m}" for i, m in enumerate(FUTURES_MECHANISM, 1)]
        lines += ["",
                  "Muốn biết **mã cụ thể** nằm ở đâu trên các đường đó: "
                  "`futures_exposure`.", ""]

    for w in snap.warnings:
        lines.append(f"⚠️ {w}")
    if snap.warnings:
        lines.append("")
    lines.append(DISCLAIMER)
    return "\n".join(lines)


def format_futures_exposure(rows,
                            title: str = "Mức chịu ảnh hưởng của dòng tiền phái sinh",
                            limit: int = 40) -> str:
    """Bảng phơi nhiễm. Điểm đứng cạnh **cả bốn** thành phần đẻ ra nó.

    Gộp bốn thành phần thành một con số rồi giấu chúng đi thì một mã ngoài rổ
    beta cao trông y hệt một mã trong rổ beta thấp — hai trường hợp chịu ảnh
    hưởng qua hai đường khác hẳn nhau.
    """
    usable = [r for r in rows if r.beta is not None]
    skipped = [r for r in rows if r.beta is None]
    lines = [f"## {title} — {len(rows)} mã", ""]
    if not usable:
        notes = list(dict.fromkeys(r.note for r in rows if r.note))
        return "\n".join(lines + ([f"⚠️ {n}" for n in notes]
                                  or ["Không có mã nào đo được."]))

    lines += [
        "| Mã | Rổ VN30 | Beta vs VN30 | R² | % thanh khoản rổ | "
        "Biên độ phiên đáo hạn | Vol phiên đáo hạn | RS 20p | Điểm |",
        "|----|:-------:|-------------:|---:|-----------------:|"
        "----------------------:|------------------:|-------:|-----:|",
    ]
    for r in usable[:max(1, limit)]:
        lines.append(
            f"| {r.symbol} | {'✅' if r.in_vn30 else '—'} | {_n(r.beta)} | {_n(r.r2)} | "
            f"{_n(r.liquidity_share_pct) if r.liquidity_share_pct is not None else '—'} | "
            f"{_n(r.expiry_move_ratio)}× | {_n(r.expiry_vol_ratio)}× | "
            f"{_signed(r.rs_20)} | **{r.score:.0f}** |"
        )
    if skipped:
        lines += ["", "⚠️ Bỏ qua: "
                  + ", ".join(f"{r.symbol} ({r.note})" for r in skipped[:8])]
    lines += [
        "",
        "- **Beta vs VN30** — mã đi bao nhiêu khi rổ cơ sở đi 1%. R² nói phần "
        "biến động thật sự do thị trường giải thích; R² thấp nghĩa là beta có "
        "đó nhưng phần lớn câu chuyện của mã nằm ở chỗ khác.",
        "- **% thanh khoản rổ** là tỷ trọng giá trị khớp lệnh trong VN30, "
        "**không phải trọng số chỉ số** (trọng số tính theo vốn hoá free-float "
        "có trần 10%, dữ liệu đó không nằm trong `data/`). Nó trả lời câu khác: "
        "lệnh mua/bán cả rổ rơi vào đâu nhiều nhất.",
        "- **Biên độ / Vol phiên đáo hạn** — trung vị các phiên đáo hạn chia cho "
        "trung vị phiên thường, đo trên ~5 năm. Trên 1× là phiên đáo hạn thường "
        "động hơn ngày thường với mã này; dưới 1× là mã đứng ngoài cuộc.",
        "- **Điểm** chỉ để **sắp thứ tự** — trong rổ (40) + beta (30) + thanh "
        "khoản rổ (20) + hành vi đáo hạn (10). Không phải xác suất, không phải "
        "dự báo.",
        "",
        DISCLAIMER,
    ]
    return "\n".join(lines)


def format_futures_stats(buckets, note: str) -> str:
    """Bảng base rate: sau mỗi mức basis, VN30 thật sự đi đâu."""
    lines = ["## Basis rồi thì VN30 đi đâu — thống kê nền", ""]
    if not buckets:
        return "\n".join(lines + [f"⚠️ {note}"])
    lines += [
        f"_{note}_",
        "",
        "| Nhóm basis | n | Trung vị 1p | %tăng 1p | Trung vị 3p | %tăng 3p | "
        "Trung vị 5p | %tăng 5p |",
        "|------------|--:|------------:|---------:|------------:|---------:|"
        "------------:|---------:|",
    ]
    for b in buckets:
        cells = []
        for h in ("1p", "3p", "5p"):
            med, up = b.median_fwd.get(h), b.share_up.get(h)
            cells.append(f"{med:+.2f}%" if med is not None else "—")
            cells.append(f"{up:.0f}%" if up is not None else "—")
        lines.append(f"| {b.label} | {b.n:,} | " + " | ".join(cells) + " |")
    lines += [
        "",
        "**Cách đọc — ba chỗ dễ sai:**",
        "",
        "- Các quan sát **chồng lấn** nhau: cửa sổ 5 phiên của hôm nay và của "
        "ngày mai dùng chung 4 phiên. `n` vì thế không phải số quan sát độc lập, "
        "nó lớn hơn con số thật nhiều lần — đừng đọc chênh lệch nhỏ giữa các "
        "nhóm như thể đã có ý nghĩa thống kê.",
        "- Trung vị chứ không phải trung bình: một phiên sập 5% kéo trung bình đi "
        "xa hơn mức nó thật sự đại diện.",
        "- Nền chung **dương** ở mọi nhóm vì VN30 tăng trong giai đoạn lấy mẫu. "
        "Cái đáng đọc là **chênh lệch giữa các nhóm**, không phải dấu của từng ô.",
        "",
        DISCLAIMER,
    ]
    return "\n".join(lines)


def format_futures_brief(fsnap, exposure, ref_date: str = "") -> List[str]:
    """Bối cảnh phái sinh gói gọn cho hồ sơ **một mã**.

    Bản đầy đủ (``format_futures``) là bức tranh cả thị trường; nhét nguyên nó
    vào hồ sơ một mã thì phần thị trường dài hơn phần cổ phiếu. Ở đây chỉ giữ
    hai câu về tư thế phái sinh, rồi lập tức trả lời câu duy nhất người đọc hồ
    sơ này cần: *mã tôi đang xem nằm ở đâu trên đường lan truyền đó.*

    Trả về danh sách dòng markdown, rỗng khi chưa có dữ liệu phái sinh — đúng
    kiểu ``format_levels_brief``, để chỗ gọi chỉ phải kiểm tra một điều kiện.
    """
    if fsnap is None or not getattr(fsnap, "bars", 0):
        return []

    b, e, fl, f = fsnap.basis, fsnap.expiry, fsnap.flow, fsnap.front
    pct = b.get("percentile_same_maturity")
    scope = "phiên cùng quãng đường tới đáo hạn"
    if pct is None:
        pct, scope = b.get("percentile"), "phiên gần nhất"

    lines = [
        f"## Bối cảnh phái sinh — {fsnap.as_of}",
        "",
        f"- Basis **{b['points']:+.2f} điểm** ({b['pct']:+.3f}%) — phân vị "
        f"`{_n(pct, 0)}%` so với {scope}. Đáo hạn `{e.get('date')}`, còn "
        f"**{e.get('sessions_left')} phiên**"
        + (" · *ước lượng*" if e.get("estimated") else ""),
        f"- Hợp đồng `{f['contracts']:,}` HĐ (RVOL {_n(f.get('rvol'))}) — giá trị danh "
        f"nghĩa gấp **{_n(fl.get('leverage_ratio'))}×** khớp lệnh rổ VN30 · tự doanh "
        f"5 phiên `{(fl.get('prop_net_5d_bn') or 0):+,.0f}` tỷ · khối ngoại 5 phiên "
        f"`{(fl.get('foreign_net_contracts_5d') or 0):+,}` HĐ",
    ]

    # Phái sinh và cổ phiếu được nạp bằng hai lượt khác nhau, nên hai bên có thể
    # dừng ở hai phiên khác nhau. Im lặng ở đây là để người đọc ghép một tư thế
    # phái sinh của hôm nay vào một bảng giá của tuần trước mà không hay biết.
    if ref_date and fsnap.as_of != ref_date:
        lines.append(
            f"- ⚠️ Phái sinh đã có phiên **{fsnap.as_of}**, phần còn lại của báo cáo "
            f"dừng ở **{ref_date}** — chạy `/update` để hai bên khớp nhau."
        )

    if exposure is not None and exposure.beta is not None:
        where = ("**trong rổ VN30** — lệnh arbitrage rơi thẳng vào"
                 if exposure.in_vn30
                 else "**ngoài rổ VN30** — chỉ chịu ảnh hưởng qua tâm lý chung")
        share = (f" · chiếm `{_n(exposure.liquidity_share_pct)}%` thanh khoản rổ"
                 if exposure.liquidity_share_pct is not None else "")
        lines.append(
            f"- {exposure.symbol} {where}. Beta so với VN30 **{_n(exposure.beta)}** "
            f"(R² {_n(exposure.r2)}){share}"
        )
        if exposure.expiry_move_ratio is not None:
            verdict = ("rộng hơn" if exposure.expiry_move_ratio > 1.1
                       else "hẹp hơn" if exposure.expiry_move_ratio < 0.9
                       else "ngang")
            lines.append(
                f"- Phiên đáo hạn: biên độ **{_n(exposure.expiry_move_ratio)}×** phiên "
                f"thường ({verdict}), volume {_n(exposure.expiry_vol_ratio)}× — đo trên "
                f"{exposure.n_expiries} kỳ"
            )
        if exposure.rs_20 is not None:
            lines.append(
                f"- Sức mạnh tương đối so với VN30: 20 phiên {_signed(exposure.rs_20)} · "
                f"60 phiên {_signed(exposure.rs_60)}"
            )
    elif exposure is not None and exposure.note:
        lines.append(f"- ⚠️ {exposure.symbol}: {exposure.note}")

    lines.append("")
    return lines


# ---------------------------------------------------------------------------
# usage guide
# ---------------------------------------------------------------------------
#: (slash command, tool, what it answers). Kept next to the tools it names so a
#: renamed tool shows up here as an obviously wrong row, not silent rot.
_COMMAND_MAP = [
    ("/update", "update_prices_tool + update_news",
     "Tải giá mới nhất về `data/` **và** nạp tin tức về `news/index.db` — "
     "cùng một `universe` + `mode` cho cả hai bước"),
    ("/scan", "scan_signals", "Quét cả rổ tìm tín hiệu RSI14 / ADX14"),
    ("/structure", "analyze_structure",
     "Trendline + hộp tích luỹ + hình mẫu + mô hình đảo chiều, kèm ảnh biểu đồ"),
    ("/deep-dive", "technical_report",
     "Toàn bộ chỉ báo + mô hình đảo chiều của 1 hoặc nhiều mã"),
    ("/report MÃ", "build_dossier",
     "Hồ sơ 1 mã ra file HTML: biểu đồ TradingView tương tác đã kẻ trendline + "
     "hộp tích luỹ, kèm toàn bộ nội dung deep-dive"),
    ("/report nhóm", "build_report",
     "Bảng tổng hợp nhiều mã, xuất file HTML có ảnh biểu đồ"),
    ("/rank", "build_ranking",
     "Xếp hạng cả rổ theo cường độ xu hướng + độ tin cậy mẫu hình, "
     "ra file HTML sắp xếp được và file JSON tổng hợp"),
    ("/rank <tiêu chí>", "rank_list",
     "Đọc lại bảng vừa dựng và sắp xếp theo tiêu chí khác, cao→thấp hoặc ngược lại"),
    ("/prospect", "build_prospect",
     "Danh sách **triển vọng cao**: lọc cả rổ xuống ứng viên có tư thế tăng giá rồi "
     "chấm điểm = phần đo được (mẫu hình 30 + breakout/volume 25 + RSI 15 + sức mạnh "
     "tương đối 12 + định giá so ngành 12 + nội bộ 6) cộng phần tin (−25…+25)"),
    ("—", "prospect_evidence",
     "Gói bằng chứng để chính model đọc: tin của mã theo phiên kèm phản ứng đã đo, "
     "tin ngành, chỉ số cơ bản so trung bình ngành, giao dịch nội bộ"),
    ("—", "prospect_score_news",
     "Nộp điểm tin vừa chấm, ghi vào kho nhận định rồi trộn vào bảng triển vọng"),
    ("—", "score_news_gemini",
     "Chấm điểm tin cả loạt bằng Gemini (chạy nền, cần GEMINI_API_KEY)"),
    ("—", "update_fundamentals",
     "Nạp và **đóng băng** chỉ số cơ bản theo ngày — FireAnt chỉ trả trạng thái hôm "
     "nay, ngày nào không chạy là ngày đó mất vĩnh viễn"),
    ("/watch", "check_forecasts", "Forecast nào đổi trạng thái từ lần kiểm tra trước"),
    ("/futures", "futures_snapshot",
     "Thị trường phái sinh VN30: basis, đòn bẩy, tự doanh/khối ngoại trên hợp đồng, "
     "đếm ngược tới phiên đáo hạn"),
    ("/futures <mã|nhóm>", "futures_exposure",
     "Mã nào chịu ảnh hưởng của dòng tiền phái sinh, qua đường nào: trong rổ VN30, "
     "beta, tỷ trọng thanh khoản rổ, hành vi phiên đáo hạn"),
    ("—", "futures_stats",
     "Base rate: sau mỗi mức basis thì VN30 thật sự đi đâu trong 1/3/5 phiên"),
    ("/news <MÃ>", "news_digest",
     "Đầu mục tin tức 20 phiên gần nhất, gom theo phiên, mỗi phiên kèm trạng thái "
     "đo được: đã vào giá / giá chạy trước tin / còn trôi tiếp / chưa phản ứng"),
    ("—", "news_transactions",
     "Giao dịch của người nội bộ và cổ đông lớn: chiều mua/bán, khối lượng đăng ký "
     "so với khối lượng thực hiện"),
    ("—", "news_impact",
     "Event study đầy đủ quanh vài giao dịch nội bộ gần nhất — ba cửa sổ tách rời"),
    ("—", "news_stats",
     "Base rate: loại giao dịch nội bộ này thường đi kèm mức giá chạy bao nhiêu"),
    ("—", "update_news",
     "Riêng phần tin: đầu mục tin, giao dịch nội bộ, mốc BCTC/cổ tức về "
     "`news/index.db`. Mốc lùi nối tiếp chỗ kho đang dừng nên `latest` vẫn lấp "
     "kín quãng bỏ bê"),
    ("<lệnh> + ngày", "tham số `as_of`",
     "Mọi lệnh báo cáo nhận thêm một mốc thời gian: `/deep-dive FPT 01/01/2025` "
     "chạy như thể hôm nay là ngày đó"),
    ("—", "create_forecasts", "Đặt kỳ vọng có thể kiểm chứng cho một mã"),
    ("—", "list_symbols", "Mã nào có dữ liệu, phủ sóng từ ngày nào"),
    ("—", "list_presets", "Các nhóm mã, profile ngưỡng, luật quét"),
    ("/ta", "usage_guide", "Chính bảng này"),
]


def format_usage_guide() -> str:
    """Cheat sheet built from the live constants, so it cannot drift out of date."""
    from src.ta.config import PROFILES
    from src.ta.loader import GROUP_FILES
    from src.ta.ranking import CRITERIA
    from src.ta.scan import RULES
    from src.ta.update import MODE_VN, MODES

    lines = [
        "# Plugin `vn-ta` — phân tích kỹ thuật cổ phiếu VN",
        "",
        "Dữ liệu giá đọc local từ `data/`, không cần mạng (trừ `/update`).",
        "**Không nhớ command cũng được — cứ nói bằng tiếng Việt bạn muốn gì.**",
        "",
        "## Command",
        "",
        "| Command | Tool | Trả lời câu hỏi gì |",
        "|---------|------|--------------------|",
    ]
    for command, tool, purpose in _COMMAND_MAP:
        lines.append(f"| `{command}` | `{tool}` | {purpose} |")

    lines += [
        "",
        "## Nhịp dùng hàng ngày",
        "",
        "```",
        "/update              # phiên mới nhất (80 mã + VNINDEX) + tin cả rổ",
        "/update no-news      # chỉ giá, ~15s",
        "/watch               # forecast nào đổi trạng thái",
        "/scan                # tín hiệu mới trong 5 phiên gần nhất",
        "/structure ANV       # xem kỹ mã đáng chú ý",
        "```",
        "",
        "## Tham số hay dùng",
        "",
        f"**Nhóm mã (`universe`):** {', '.join(f'`{g}`' for g in GROUP_FILES)}, "
        "`disk` (mọi mã có dữ liệu), hoặc danh sách `ANV,HPG,ACB`",
        "",
        f"**Luật quét (`rules`):** {', '.join(f'`{r}`' for r in RULES)}",
        "",
        "**Mốc thời gian (`as_of`):** thêm một ngày vào bất kỳ lệnh báo cáo nào để "
        "*giả định hôm nay là ngày đó* — `01/01/2025` (ngày/tháng/năm) hoặc `2025-01-01`. "
        "Mọi phiên sau mốc bị cắt bỏ, kể cả forecast, nên kết quả đúng bằng những gì "
        "biết được tại ngày đó. File hồi tưởng ghi riêng vào `reports/asof_<ngày>/` và "
        "không đụng tới báo cáo của phiên thật.",
        "",
        "**Tiêu chí xếp hạng (`criterion` của `rank_list`):** "
        + " · ".join(f"`{key}` = {c.label}" for key, c in CRITERIA.items()),
        "",
        "**Profile ngưỡng:** " + " · ".join(
            f"`{name}` (RSI {cfg.rsi.oversold:.0f}/{cfg.rsi.overbought:.0f}, "
            f"ADX ≥ {cfg.adx.trend_threshold:.0f})"
            for name, cfg in PROFILES.items()
        ),
        "",
        "**Phạm vi cập nhật (`mode`):** " + " · ".join(
            f"`{m}` = {MODE_VN.get(m, m)}" for m in MODES
        ),
        "",
        "## Ví dụ",
        "",
        "```",
        "/scan vn30 10                 # VN30, tín hiệu trong 10 phiên gần nhất",
        "/structure GAS,HPG 260        # 2 mã, 260 ngày lịch sử",
        "/report FPT                   # hồ sơ FPT: chart tương tác + deep-dive, 1 file HTML",
        "/report vn30                  # bảng tổng hợp VN30 ra file HTML",
        "/rank                         # xếp hạng toàn bộ mã có dữ liệu ra file HTML + JSON",
        "/rank độ tin cậy giảm dần     # sắp xếp lại bảng vừa dựng theo tiêu chí khác",
        "/update ANV,HPG recent        # 2 mã, tháng này + tháng trước",
        "/watch closed                 # gồm cả forecast đã đóng",
        "",
        "/deep-dive FPT 01/01/2025     # giả định hôm nay là 01/01/2025",
        "/report FPT ngày 15/06/2024   # hồ sơ HTML dựng bằng dữ liệu tới 15/06/2024",
        "/rank vn30 01/01/2025         # xếp hạng VN30 như thể đang đứng ở ngày đó",
        "/rank độ tin cậy 01/01/2025   # xếp lại chính bảng hồi tưởng đó",
        "```",
        "",
        DISCLAIMER,
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# triển vọng cao
# ---------------------------------------------------------------------------
def _prospect_score_cell(row) -> str:
    """Tổng điểm, **luôn kèm hai vế đã tạo ra nó**.

    Không bao giờ in một mình: ``72`` không nói gì, ``72 (đo 61 + tin +11)``
    nói rằng một phần ba số đó là nhận định của một model chứ không phải phép
    đo. Đó là điều kiện để cột này không thành cái "điểm cổ phiếu" mà
    ``CLAUDE.md`` cấm.
    """
    if row.news is None:
        return f"**{row.base_score:.0f}** (đo, chưa chấm tin)"
    return f"**{row.total:.0f}** (đo {row.base_score:.0f} · tin {row.news.score:+.0f})"


def format_prospect(board, top: int = 12, show_excluded: bool = True) -> str:
    """Bảng triển vọng cao — danh sách ứng viên, kèm mọi thành phần điểm."""
    from src.ta.prospect import EXCLUDE_VN, MAX_NEWS

    if not board.rows and not board.excluded:
        return ("## Triển vọng cao\n\n"
                + "\n".join(f"⚠️ {n}" for n in board.notes)
                + "\n\nChưa có bảng xếp hạng nào để lọc — chạy `build_ranking` trước.")

    lines = [
        f"# Triển vọng cao — {board.as_of}",
        "",
        *_asof_lines(getattr(board, "as_of_requested", ""), board.as_of),
        f"{len(board.rows)} ứng viên trên {len(board.rows) + len(board.excluded)} mã "
        f"· nhóm `{board.universe}` · dựng lúc {board.generated}",
        "",
    ]
    if board.html_path:
        lines.append(f"📄 Bảng HTML: `{board.html_path}`")
    if board.json_path:
        lines.append(f"🗂 Dữ liệu: `{board.json_path}`")
    lines.append("")

    scored = board.scored_rows[:max(1, top)]
    lines += [
        "## Danh sách",
        "",
        "| # | Mã | Ngành | Điểm | 🚩 Cờ đỏ | Mẫu hình | Break | RSI | RS | Định giá | Nội bộ | Tin |",
        "|--:|----|-------|-----:|--------:|--------:|------:|----:|---:|--------:|------:|----:|",
    ]
    for i, r in enumerate(scored, 1):
        def pts(key):
            c = r.component(key)
            return f"{c.points:+.0f}" if c else "—"
        news = f"{r.news.score:+.0f}" if r.news else "·"
        # Ba trạng thái, ba ký hiệu khác nhau: `?` là chưa quét được, `—` là đã
        # quét và sạch, một con số âm là có cờ. Gộp hai cái đầu thành một ô
        # trống là đúng lỗi mà quy ước "chưa đo được ≠ đã đo và thấy phẳng" cấm.
        rf = r.redflags
        flag = "?" if rf is None else ("—" if rf.is_empty else f"**{-rf.penalty:.0f}**")
        lines.append(
            f"| {i} | **{r.symbol}** | {r.sector_label} | {_prospect_score_cell(r)} | "
            f"{flag} | "
            f"{pts('pattern')} | {pts('breakout')} | {pts('rsi')} | {pts('rs')} | "
            f"{pts('value')} | {pts('insider')} | {news} |"
        )
    lines.append("")

    lines += ["## Vì sao từng mã vào danh sách", ""]
    for i, r in enumerate(scored, 1):
        lines.append(f"### {i}. {r.symbol} — {_prospect_score_cell(r)}")
        lines.append("")
        lines.append(
            f"Giá {_n(r.close)} · RSI {_n(r.rsi, 1)} · RVOL {_n(r.rvol)}× · "
            f"thanh khoản {_n(r.liquidity_bn, 0)} tỷ/phiên · 20 phiên {_signed(r.change_20d)}"
        )
        lines.append("")
        # Cờ đỏ in **trước** mọi thành phần khác, kể cả khi nó bằng 0: thứ tự
        # đọc là thứ tự ưu tiên, và một điểm trừ 50 nằm lẫn giữa sáu dòng điểm
        # cộng thì không còn là cảnh báo nữa.
        rf_comp = r.component("redflag")
        if rf_comp is not None:
            lines.append(f"- **🚩 {rf_comp.label} {rf_comp.points:+.1f}/"
                         f"−{rf_comp.max_points:.0f}** — {rf_comp.note}")
        if r.redflags is not None and not r.redflags.is_empty:
            for f in r.redflags.flags[:4]:
                lines.append(f"  - [{f.label}] {f.title.strip()} "
                             f"_({f.published[:10]} · −{f.score:.0f})_")
        for c in r.components:
            if c.key == "redflag":
                continue
            if abs(c.points) < 0.05 and not c.note:
                continue
            lines.append(f"- **{c.label} {c.points:+.1f}/{c.max_points:.0f}** — {c.note}")
        if r.trigger or r.target or r.invalidation:
            lines.append(
                f"- **Mốc giá** — kích hoạt {_n(r.trigger)} · mục tiêu {_n(r.target)} "
                f"· huỷ nếu mất {_n(r.invalidation)}"
            )
        if r.sector is not None and r.sector.comparable:
            v = r.sector
            lines.append(
                f"- **Ngành {v.label}** — {v.n_rows} mã, {v.breadth_up:.0f}% đang tăng, "
                f"trung vị 20 phiên {_signed(v.median_change_20d)}"
                + (f", mã này đứng thứ {v.rank_in_sector}/{v.n_rows}"
                   if v.rank_in_sector else "")
                + (f", dẫn đầu {v.leader}" if v.leader else "")
            )
        if r.news is not None:
            n = r.news
            lines.append(
                f"- **Tin {n.score:+.0f}/{MAX_NEWS:.0f}** ({n.label or 'không nhãn'}, "
                f"độ chắc chắn {n.confidence or '—'}, chấm bởi `{n.source or '?'}`) — "
                f"{n.summary}"
            )
            for good in n.good[:3]:
                lines.append(f"  - ✅ {good}")
            for bad in n.bad[:3]:
                lines.append(f"  - ⚠️ {bad}")
            if n.sector_outlook:
                lines.append(f"  - 🔭 Triển vọng ngành: {n.sector_outlook}")
        else:
            lines.append("- **Tin** — chưa chấm. Gọi `prospect_evidence` để đọc "
                         "gói bằng chứng, rồi `prospect_score_news` để nộp điểm.")
        for w in r.warnings:
            lines.append(f"- ⚠️ {w}")
        lines.append("")

    if show_excluded and board.excluded:
        from itertools import groupby
        lines += ["## Bị loại khỏi danh sách", ""]
        keyed = sorted(board.excluded, key=lambda r: r.excluded)
        for reason, group in groupby(keyed, key=lambda r: r.excluded):
            items = list(group)
            lines.append(f"**{EXCLUDE_VN.get(reason, reason)}** ({len(items)} mã): "
                         + ", ".join(f"{r.symbol} ({r.excluded_note})"
                                     for r in items[:6])
                         + (" …" if len(items) > 6 else ""))
        lines.append("")

    n_news = board.n_news_scored
    lines += [
        "## Cách đọc bảng này",
        "",
        f"- Cột **Điểm** là hai vế cộng lại và **luôn in cả hai**: phần *đo được* "
        f"(0–100, từ giá và sổ sách) cộng phần *tin* (−{MAX_NEWS:.0f}…+{MAX_NEWS:.0f}, "
        f"nhận định của model ngôn ngữ). Đã chấm tin: {n_news}/{len(board.rows)} mã.",
        "- Ba cột điểm của `/rank` (cường độ xu hướng, độ tin cậy mẫu hình, phơi nhiễm "
        "phái sinh) **không** nằm trong con số này và không bị nó thay thế — bảng xếp "
        "hạng vẫn là bảng xếp hạng.",
        f"- Thanh khoản là **cửa vào**, không phải điểm: dưới "
        f"{board.min_liquidity_bn:.0f} tỷ/phiên thì loại thẳng, vì một mẫu hình đẹp "
        "trên mã không giao dịch được là mẫu hình không dùng được.",
        "- RSI đủ điểm ở **40–60** như yêu cầu, rồi giảm dần chứ không cắt phựt: một mã "
        "vừa breakout bằng volume gần như luôn có RSI 62–72, cắt cứng ở 60 là loại đúng "
        "những mã hai tiêu chí đầu vừa chọn ra. Trên 75 thành điểm âm.",
        "",
    ]
    if board.notes:
        lines += ["**Khoảng trống trong bảng này:**"] + [f"- {n}" for n in board.notes] + [""]
    lines.append(DISCLAIMER)
    return "\n".join(lines)
