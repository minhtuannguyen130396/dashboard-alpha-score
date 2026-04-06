"""
chart_renderer_v2.py
Beautiful HTML chart renderer using TradingView Lightweight Charts.
Drop-in replacement for chart_renderer.py — identical function signatures.
"""
import json
import os
import webbrowser
from datetime import datetime
from typing import List

from src.models.trade_record import TradeRecord
from src.data.stock_data_loader import StockRecord
from src.analysis.market_behavior_analyzer import MarketBehaviorSnapshot


# ---------------------------------------------------------------------------
# Static CSS — plain string, no f-string escaping needed
# ---------------------------------------------------------------------------
_CSS = """
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

body {
  background: #0f1117;
  color: #c9d1d9;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Trebuchet MS', sans-serif;
  padding: 20px 24px 40px;
  min-width: 800px;
}

/* ---- Header ---- */
#header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
  margin-bottom: 14px;
  padding: 14px 20px;
  background: #161b22;
  border-radius: 10px;
  border: 1px solid #21262d;
  border-left: 4px solid #2962ff;
}
#header .left h1 {
  font-size: 24px;
  font-weight: 700;
  color: #f0f6fc;
  letter-spacing: 0.5px;
}
#header .left .sub {
  font-size: 12px;
  color: #6e7681;
  margin-top: 4px;
  letter-spacing: 0.3px;
}
.pnl {
  padding: 8px 18px;
  border-radius: 8px;
  font-size: 15px;
  font-weight: 700;
  white-space: nowrap;
  align-self: center;
}
.pnl-pos { background: rgba(63,185,80,.12); color: #3fb950; border: 1px solid rgba(63,185,80,.3); }
.pnl-neg { background: rgba(248,81,73,.12); color: #f85149; border: 1px solid rgba(248,81,73,.3); }

/* ---- Legend ---- */
#legend {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 18px;
  margin-bottom: 12px;
  padding: 9px 14px;
  background: #161b22;
  border: 1px solid #21262d;
  border-radius: 8px;
  font-size: 12px;
  color: #8b949e;
}
.li { display: flex; align-items: center; gap: 6px; }
.dot  { width: 10px; height: 10px; border-radius: 50%; flex-shrink: 0; }
.line { width: 20px; height: 3px;  border-radius: 2px; flex-shrink: 0; }
.arr-up {
  width: 0; height: 0; flex-shrink: 0;
  border-left: 5px solid transparent;
  border-right: 5px solid transparent;
  border-bottom: 9px solid;
}
.arr-dn {
  width: 0; height: 0; flex-shrink: 0;
  border-left: 5px solid transparent;
  border-right: 5px solid transparent;
  border-top: 9px solid;
}

/* ---- Charts ---- */
#charts-container { margin-bottom: 18px; }
#price-chart  { width: 100%; height: 520px; border-radius: 10px 10px 0 0; overflow: hidden; }
#volume-chart { width: 100%; height: 170px; border-radius: 0 0 10px 10px; overflow: hidden; margin-top: 2px; }

/* ---- Finance table ---- */
#finance-section {}
#finance-section h2 {
  font-size: 11px;
  font-weight: 600;
  color: #6e7681;
  text-transform: uppercase;
  letter-spacing: 1.2px;
  margin-bottom: 8px;
}
.table-wrap {
  border-radius: 10px;
  overflow: hidden;
  border: 1px solid #21262d;
}
table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
  background: #161b22;
}
thead tr { background: #1c2128; }
th {
  padding: 10px 14px;
  color: #6e7681;
  font-weight: 600;
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.6px;
  text-align: right;
  border-bottom: 1px solid #21262d;
  white-space: nowrap;
}
th:first-child, th:nth-child(2), th:nth-child(3) { text-align: left; }
td {
  padding: 8px 14px;
  border-bottom: 1px solid #0d1117;
  text-align: right;
  color: #c9d1d9;
  white-space: nowrap;
}
td:first-child, td:nth-child(2), td:nth-child(3) { text-align: left; color: #8b949e; }
tbody tr:hover td { background: #1c2128; }
tbody tr:last-child td { border-bottom: none; }
tfoot tr { background: #1c2128; }
tfoot td {
  border-top: 1px solid #30363d;
  border-bottom: none;
  font-weight: 700;
  font-size: 13px;
}
.pos { color: #3fb950; font-weight: 600; }
.neg { color: #f85149; font-weight: 600; }
"""

# ---------------------------------------------------------------------------
# Static JS — plain string, JS braces are NOT f-string expressions
# ---------------------------------------------------------------------------
_JS = """
(function () {
  'use strict';

  const BG     = '#0f1117';
  const GRID   = '#161b22';
  const BORDER = '#21262d';
  const TXT    = '#6e7681';
  const LS     = LightweightCharts.LineStyle;

  // Shared option factories — avoids spread so Lightweight Charts receives
  // plain objects without prototype chain surprises.
  function layoutOpts() {
    return {
      background: { type: 'solid', color: BG },
      textColor: TXT,
      fontSize: 12,
      fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif",
    };
  }
  function gridOpts()  { return { vertLines: { color: GRID }, horzLines: { color: GRID } }; }
  function crosshairOpts() {
    return {
      mode: LightweightCharts.CrosshairMode.Normal,
      vertLine: { color: '#3c4153', width: 1, style: LS.Dashed, labelBackgroundColor: '#2962ff' },
      horzLine: { color: '#3c4153', width: 1, style: LS.Dashed, labelBackgroundColor: '#2962ff' },
    };
  }
  // Drag on chart body  = pan  (pressedMouseMove)
  // Drag on axis        = disabled (axisPressedMouseMove: false)
  // Scroll wheel        = zoom
  function scrollOpts() { return { pressedMouseMove: true, mouseWheel: false, horzTouchDrag: true }; }
  function scaleOpts()  { return { mouseWheel: true, pinch: true, axisPressedMouseMove: false }; }

  const priceEl = document.getElementById('price-chart');
  const volEl   = document.getElementById('volume-chart');

  // ── Price chart ──────────────────────────────────────────────────────────
  const pc = LightweightCharts.createChart(priceEl, {
    layout:          layoutOpts(),
    grid:            gridOpts(),
    crosshair:       crosshairOpts(),
    handleScroll:    scrollOpts(),
    handleScale:     scaleOpts(),
    rightPriceScale: { borderColor: BORDER },
    timeScale:       { borderColor: BORDER, timeVisible: false },
    height: 520,
    width:  priceEl.offsetWidth,
  });

  const cs = pc.addCandlestickSeries({
    upColor:         '#26a69a',
    downColor:       '#ef5350',
    borderUpColor:   '#26a69a',
    borderDownColor: '#ef5350',
    wickUpColor:     '#26a69a',
    wickDownColor:   '#ef5350',
  });
  cs.setData(CANDLE_DATA);

  pc.addLineSeries({
    color: '#58a6ff', lineWidth: 1.5,
    priceLineVisible: false, lastValueVisible: true, title: 'EMA20',
  }).setData(EMA20_DATA);

  pc.addLineSeries({
    color: '#f0883e', lineWidth: 1.5,
    priceLineVisible: false, lastValueVisible: true, title: 'EMA50',
  }).setData(EMA50_DATA);

  // Markers (all types merged and sorted by time)
  const markers = [
    ...BUY_MARKERS.map(m => ({
      time: m.time, position: 'belowBar', color: '#3fb950',
      shape: 'arrowUp', size: 1, text: m.score.toFixed(1),
    })),
    ...SELL_MARKERS.map(m => ({
      time: m.time, position: 'aboveBar', color: '#f85149',
      shape: 'arrowDown', size: 1, text: m.score.toFixed(1),
    })),
    ...ACTUAL_BUY_MARKERS.map(m => ({
      time: m.time, position: 'belowBar', color: '#2962ff',
      shape: 'circle', size: 0.8, text: '',
    })),
    ...ACTUAL_SELL_MARKERS.map(m => ({
      time: m.time, position: 'aboveBar', color: '#e3b341',
      shape: 'circle', size: 0.8, text: '',
    })),
  ].sort((a, b) => (a.time < b.time ? -1 : a.time > b.time ? 1 : 0));
  cs.setMarkers(markers);

  // ── Volume chart ─────────────────────────────────────────────────────────
  const vc = LightweightCharts.createChart(volEl, {
    layout:          layoutOpts(),
    grid:            gridOpts(),
    crosshair:       crosshairOpts(),
    handleScroll:    scrollOpts(),
    handleScale:     scaleOpts(),
    rightPriceScale: { borderColor: BORDER, scaleMargins: { top: 0.05, bottom: 0 } },
    timeScale:       { borderColor: BORDER, timeVisible: true },
    height: 170,
    width:  volEl.offsetWidth,
  });

  vc.addHistogramSeries({
    priceFormat: { type: 'volume' },
    priceScaleId: 'right',
  }).setData(VOLUME_DATA);

  vc.addLineSeries({
    color: '#bc8cff', lineWidth: 2,
    lineStyle: LS.Dashed,
    priceLineVisible: false, lastValueVisible: false,
  }).setData(EMA_VOLUME_DATA);

  // ── Sync via logical range (bar-index based, more stable than time range) ─
  let _lock = false;
  function syncRange(src, dst) {
    src.timeScale().subscribeVisibleLogicalRangeChange(r => {
      if (_lock || !r) return;
      _lock = true;
      dst.timeScale().setVisibleLogicalRange(r);
      _lock = false;
    });
  }
  syncRange(pc, vc);
  syncRange(vc, pc);

  // ── Info bar (always visible, updates on crosshair hover over signal) ──────
  const infoBar = document.getElementById('info-bar');
  const MARKER_MAP = {};
  BUY_MARKERS.forEach(m  => { MARKER_MAP[m.time + '_b'] = { label: '▲ Mua',  score: m.score, reason: m.reason, cls: 'pos' }; });
  SELL_MARKERS.forEach(m => { MARKER_MAP[m.time + '_s'] = { label: '▼ Bán',  score: m.score, reason: m.reason, cls: 'neg' }; });

  function renderInfoBar(info) {
    infoBar.innerHTML =
      '<span class="' + info.cls + '">' + info.label + '</span>' +
      '&nbsp;&nbsp;Score: <b>' + info.score.toFixed(2) + '</b>' +
      (info.reason ? '&nbsp;&nbsp;·&nbsp;&nbsp;<span style="color:#8b949e">' + info.reason + '</span>' : '');
  }

  // Default: last signal (buy or sell) by time
  const allSignals = [
    ...BUY_MARKERS.map(m  => ({ time: m.time, info: MARKER_MAP[m.time + '_b'] })),
    ...SELL_MARKERS.map(m => ({ time: m.time, info: MARKER_MAP[m.time + '_s'] })),
  ].sort((a, b) => (a.time < b.time ? -1 : a.time > b.time ? 1 : 0));
  if (allSignals.length > 0) renderInfoBar(allSignals[allSignals.length - 1].info);

  pc.subscribeCrosshairMove(param => {
    if (!param.time) return;
    const info = MARKER_MAP[param.time + '_b'] || MARKER_MAP[param.time + '_s'];
    if (info) renderInfoBar(info);
    // no else — keep showing last info when hovering over non-signal candles
  });

  // ── Responsive resize ────────────────────────────────────────────────────
  new ResizeObserver(() => {
    const w = document.getElementById('charts-container').clientWidth;
    pc.resize(w, 520);
    vc.resize(w, 170);
  }).observe(document.getElementById('charts-container'));

  // ── Initial fit + sync ───────────────────────────────────────────────────
  pc.timeScale().fitContent();
  pc.timeScale().applyOptions({ rightOffset: 12 });
  requestAnimationFrame(() => {
    const r = pc.timeScale().getVisibleLogicalRange();
    if (r) vc.timeScale().setVisibleLogicalRange(r);
  });
})();
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def open_html_in_chrome(path_to_html: str):
    chrome_path = r'"C:\Program Files\Google\Chrome\Application\chrome.exe" %s'
    webbrowser.get(chrome_path).open("file://" + os.path.realpath(path_to_html))


def _fmt_date(dt) -> str:
    return dt.strftime('%Y-%m-%d') if hasattr(dt, 'strftime') else str(dt)


def _build_finance_rows(records: List[TradeRecord]) -> str:
    rows = []
    total_profit = 0.0
    for i, r in enumerate(records, 1):
        cls = "pos" if r.profit >= 0 else "neg"
        pct = getattr(r, 'profit_pct', 0.0)
        total_profit += r.profit
        rows.append(
            f"<tr>"
            f"<td>{i}</td>"
            f"<td>{_fmt_date(r.date_buy)}</td>"
            f"<td>{_fmt_date(r.date_sale)}</td>"
            f"<td style='text-align:center'>{getattr(r, 'hoding_day', '-')}</td>"
            f"<td>{r.buy_volume:,.0f}</td>"
            f"<td>{r.buy_value:,.0f}</td>"
            f"<td>{r.sale_value:,.0f}</td>"
            f"<td class='{cls}'>{r.profit:+,.2f}</td>"
            f"<td class='{cls}'>{pct:+.2f}%</td>"
            f"<td>{r.cash:,.0f}</td>"
            f"</tr>"
        )
    tcls = "pos" if total_profit >= 0 else "neg"
    rows.append(
        f"<tr>"
        f"<td colspan='7' style='text-align:right;color:#6e7681;font-size:11px;text-transform:uppercase;letter-spacing:.6px'>Tổng lợi nhuận</td>"
        f"<td class='{tcls}'>{total_profit:+,.2f}</td>"
        f"<td colspan='2'></td>"
        f"</tr>"
    )
    return "\n".join(rows)


# ---------------------------------------------------------------------------
# HTML assembly — only the dynamic parts use f-strings
# ---------------------------------------------------------------------------
def _build_html(
    symbol: str,
    date_from: str,
    date_to: str,
    total_profit: float,
    pnl_class: str,
    finance_rows_html: str,
    candle_data_json: str,
    ema20_data_json: str,
    ema50_data_json: str,
    volume_data_json: str,
    ema_volume_data_json: str,
    buy_markers_json: str,
    sell_markers_json: str,
    actual_buy_markers_json: str,
    actual_sell_markers_json: str,
) -> str:
    sign = "+" if total_profit >= 0 else ""
    return "\n".join([
        '<!DOCTYPE html>',
        '<html lang="vi">',
        '<head>',
        '<meta charset="UTF-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1.0">',
        f'<title>[{symbol}] {date_from} → {date_to}</title>',
        '<script src="https://unpkg.com/lightweight-charts@4.2.0/dist/lightweight-charts.standalone.production.js"></script>',
        f'<style>{_CSS}</style>',
        '</head>',
        '<body>',

        # Header
        '<div id="header">',
        f'  <div class="left"><h1>[{symbol}]</h1><div class="sub">{date_from} &nbsp;→&nbsp; {date_to}</div></div>',
        f'  <div class="pnl {pnl_class}">Realized PnL &nbsp; {sign}{total_profit:,.2f}</div>',
        '</div>',

        # Legend
        '<div id="legend">',
        '  <span class="li"><span class="line" style="background:#58a6ff"></span>EMA20</span>',
        '  <span class="li"><span class="line" style="background:#f0883e"></span>EMA50</span>',
        '  <span class="li"><span class="arr-up" style="border-bottom-color:#3fb950"></span>Tín hiệu Mua</span>',
        '  <span class="li"><span class="arr-dn" style="border-top-color:#f85149"></span>Tín hiệu Bán</span>',
        '  <span class="li"><span class="dot" style="background:#2962ff"></span>Mua Thực Tế</span>',
        '  <span class="li"><span class="dot" style="background:#e3b341"></span>Bán Thực Tế</span>',
        '  <span style="color:#30363d">│</span>',
        '  <span class="li"><span class="dot" style="background:#26a69a"></span>Vol: Big Buyer</span>',
        '  <span class="li"><span class="dot" style="background:#ef5350"></span>Vol: Fomo Retail</span>',
        '  <span class="li"><span class="dot" style="background:#2962ff"></span>Vol: Cả hai</span>',
        '  <span class="li"><span class="dot" style="background:#9c27b0"></span>Vol: Khác</span>',
        '</div>',

        # Info bar (shown on marker hover)
        '<div id="info-bar" style="display:flex;align-items:center;gap:6px;padding:6px 14px;'
        'margin-bottom:8px;background:#1c2128;border-radius:6px;font-size:13px;'
        'border:1px solid #30363d;min-height:32px;"></div>',

        # Charts
        '<div id="charts-container">',
        '  <div id="price-chart"></div>',
        '  <div id="volume-chart"></div>',
        '</div>',

        # Finance table
        '<div id="finance-section">',
        '  <h2>Lịch sử giao dịch</h2>',
        '  <div class="table-wrap">',
        '  <table>',
        '    <thead><tr>',
        '      <th>#</th><th>Ngày Mua</th><th>Ngày Bán</th><th style="text-align:center">Ngày nắm</th>',
        '      <th>KL Mua</th><th>GT Mua</th><th>GT Bán</th>',
        '      <th>Lợi nhuận</th><th>% Lãi</th><th>Tiền mặt</th>',
        '    </tr></thead>',
        f'   <tbody>{finance_rows_html}</tbody>',
        '  </table>',
        '  </div>',
        '</div>',

        # Inject data
        '<script>',
        f'const CANDLE_DATA          = {candle_data_json};',
        f'const EMA20_DATA           = {ema20_data_json};',
        f'const EMA50_DATA           = {ema50_data_json};',
        f'const VOLUME_DATA          = {volume_data_json};',
        f'const EMA_VOLUME_DATA      = {ema_volume_data_json};',
        f'const BUY_MARKERS          = {buy_markers_json};',
        f'const SELL_MARKERS         = {sell_markers_json};',
        f'const ACTUAL_BUY_MARKERS   = {actual_buy_markers_json};',
        f'const ACTUAL_SELL_MARKERS  = {actual_sell_markers_json};',
        '</script>',

        # Chart logic (plain string — no brace escaping needed)
        f'<script>{_JS}</script>',

        '</body>',
        '</html>',
    ])


# ---------------------------------------------------------------------------
# Main entry point — same signature as chart_renderer.render_backtest_chart
# ---------------------------------------------------------------------------
def render_backtest_chart(
    stock_records: List[StockRecord],
    market_behavior: MarketBehaviorSnapshot,
    actual_sale_point: List[int],
    actual_buy_point: List[int],
    list_fynance: List[TradeRecord],
) -> None:
    mb = market_behavior

    candle_data = [
        {
            "time": _fmt_date(r.date),
            "open": r.priceOpen, "high": r.priceHigh,
            "low": r.priceLow,   "close": r.priceClose,
        }
        for r in stock_records
    ]

    ema20_data = [
        {"time": _fmt_date(r.date), "value": v}
        for r, v in zip(stock_records, mb.ema20) if v is not None
    ]
    ema50_data = [
        {"time": _fmt_date(r.date), "value": v}
        for r, v in zip(stock_records, mb.ema50) if v is not None
    ]

    _COLOR = {
        (True,  False): "#26a69a",
        (False, True):  "#ef5350",
        (True,  True):  "#2962ff",
        (False, False): "#9c27b0",
    }
    volume_data = [
        {
            "time": _fmt_date(r.date),
            "value": mb.total_volume[i],
            "color": _COLOR[(bool(mb.big_buyer[i]), bool(mb.fomo_retail[i]))],
        }
        for i, r in enumerate(stock_records)
    ]
    ema_volume_data = [
        {"time": _fmt_date(r.date), "value": v}
        for r, v in zip(stock_records, mb.ema_volume) if v is not None
    ]

    def _score(i):  return mb.signal_scores[i]  if i < len(mb.signal_scores)  else 0.0
    def _reason(i): return mb.signal_reasons[i] if i < len(mb.signal_reasons) else ""

    buy_markers = [
        {"time": _fmt_date(r.date), "score": _score(i), "reason": _reason(i)}
        for i, (r, flag) in enumerate(zip(stock_records, mb.buy_point)) if flag
    ]
    sell_markers = [
        {"time": _fmt_date(r.date), "score": _score(i), "reason": _reason(i)}
        for i, (r, flag) in enumerate(zip(stock_records, mb.sale_point)) if flag
    ]
    actual_buy_markers = [
        {"time": _fmt_date(r.date)}
        for r, flag in zip(stock_records, actual_buy_point) if flag == 1
    ]
    actual_sell_markers = [
        {"time": _fmt_date(r.date)}
        for r, flag in zip(stock_records, actual_sale_point) if flag in (1, -1)
    ]

    symbol      = stock_records[-1].symbol
    date_from   = _fmt_date(stock_records[0].date)
    date_to     = _fmt_date(stock_records[-1].date)
    total_profit = sum(r.profit for r in list_fynance)
    pnl_class   = "pnl-pos" if total_profit >= 0 else "pnl-neg"

    html = _build_html(
        symbol=symbol,
        date_from=date_from,
        date_to=date_to,
        total_profit=total_profit,
        pnl_class=pnl_class,
        finance_rows_html=_build_finance_rows(list_fynance),
        candle_data_json=json.dumps(candle_data),
        ema20_data_json=json.dumps(ema20_data),
        ema50_data_json=json.dumps(ema50_data),
        volume_data_json=json.dumps(volume_data),
        ema_volume_data_json=json.dumps(ema_volume_data),
        buy_markers_json=json.dumps(buy_markers),
        sell_markers_json=json.dumps(sell_markers),
        actual_buy_markers_json=json.dumps(actual_buy_markers),
        actual_sell_markers_json=json.dumps(actual_sell_markers),
    )

    current_date_str = datetime.now().strftime("%Y-%m-%d")
    output_dir = os.path.join("chart", current_date_str)
    os.makedirs(output_dir, exist_ok=True)
    file_name = f"{symbol}_{date_from}_{date_to}.html"
    output_path = os.path.join(output_dir, file_name)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    open_html_in_chrome(output_path)


draw_chart = render_backtest_chart
