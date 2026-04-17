"""
chart_renderer_v2.py
Beautiful HTML chart renderer using TradingView Lightweight Charts.
Drop-in replacement for chart_renderer.py — identical function signatures.
"""
import json
import os
import shutil
import webbrowser
from datetime import datetime
from typing import List

from src.models.trade_record import TradeRecord
from src.data.stock_data_loader import StockRecord
from src.analysis.market_behavior_analyzer import MarketBehaviorSnapshot


_REPORTING_DIR = os.path.dirname(__file__)
_CSS_SOURCE_FILENAME = "chart_renderer_v2.css"
_CSS_SOURCE_PATH = os.path.join(_REPORTING_DIR, _CSS_SOURCE_FILENAME)

_JS_SOURCE_FILENAME = "chart_renderer_v2.js"
_JS_SOURCE_PATH = os.path.join(_REPORTING_DIR, _JS_SOURCE_FILENAME)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def open_html_in_chrome(path_to_html: str):
    chrome_path = r'"C:\Program Files\Google\Chrome\Application\chrome.exe" %s'
    webbrowser.get(chrome_path).open("file://" + os.path.realpath(path_to_html))


def _write_static_asset(source_path: str, output_dir: str) -> str:
    asset_name = os.path.basename(source_path)
    asset_output_path = os.path.join(output_dir, asset_name)
    shutil.copyfile(source_path, asset_output_path)
    return os.path.basename(asset_output_path)


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
            f"<td class='cell-center'>{getattr(r, 'hoding_day', '-')}</td>"
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
        f"<td colspan='7' class='total-label'>Tổng lợi nhuận</td>"
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
    css_href: str,
    js_href: str,
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
    hover_data_json: str = "[]",
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
        f'<link rel="stylesheet" href="{css_href}">',
        '</head>',
        '<body>',

        # Header
        '<div id="header">',
        f'  <div class="left"><h1>[{symbol}]</h1><div class="sub">{date_from} &nbsp;→&nbsp; {date_to}</div></div>',
        f'  <div class="pnl {pnl_class}">Realized PnL &nbsp; {sign}{total_profit:,.2f}</div>',
        '</div>',

        # Legend
        '<div id="legend">',
        '  <span class="li"><span class="line line-ema20"></span>EMA20</span>',
        '  <span class="li"><span class="line line-ema50"></span>EMA50</span>',
        '  <span class="li"><span class="arr-up arr-up-buy"></span>Tín hiệu Mua</span>',
        '  <span class="li"><span class="arr-dn arr-dn-sell"></span>Tín hiệu Bán</span>',
        '  <span class="li"><span class="dot dot-actual-buy"></span>Mua Thực Tế</span>',
        '  <span class="li"><span class="dot dot-actual-sell"></span>Bán Thực Tế</span>',
        '  <span class="legend-separator">│</span>',
        '  <span class="li"><span class="dot dot-vol-big-buyer"></span>Vol: Big Buyer</span>',
        '  <span class="li"><span class="dot dot-vol-fomo-retail"></span>Vol: Fomo Retail</span>',
        '  <span class="li"><span class="dot dot-vol-both"></span>Vol: Cả hai</span>',
        '  <span class="li"><span class="dot dot-vol-other"></span>Vol: Khác</span>',
        '  <span class="legend-separator">│</span>',
        '  <span class="li"><span class="line line-sm-setup"></span>SM Setup</span>',
        '  <span class="li"><span class="line line-sm-trigger"></span>SM Trigger</span>',
        '</div>',

        # Compact signal info bar (latest/hovered signal)
        '<div id="info-bar"></div>',

        # Full hover panel — hidden until first hover; shows all metrics for the hovered day
        '<div id="hover-panel"></div>',

        # Charts
        '<div id="charts-container">',
        '  <div id="price-chart"></div>',
        '  <div id="volume-chart"></div>',
        '  <div id="score-strip"><span class="score-strip-label">Score</span>'
        '<canvas id="score-strip-canvas"></canvas></div>',
        '  <div id="smartmoney-chart"></div>',
        '  <div id="smartmoney-strip"><span class="sm-strip-label">Smart Money</span>'
        '<canvas id="smartmoney-strip-canvas"></canvas></div>',
        '  <div id="rsi-chart"></div>',
        '  <div id="macd-chart"></div>',
        '  <div id="adx-chart"></div>',
        '</div>',

        # Finance table
        '<div id="finance-section">',
        '  <h2>Lịch sử giao dịch</h2>',
        '  <div class="table-wrap">',
        '  <table>',
        '    <thead><tr>',
        '      <th>#</th><th>Ngày Mua</th><th>Ngày Bán</th><th class="col-center">Ngày nắm</th>',
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
        f'const HOVER_DATA           = {hover_data_json};',
        '</script>',

        # Chart logic (plain string — no brace escaping needed)
        f'<script src="{js_href}"></script>',

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

    current_date_str = datetime.now().strftime("%Y-%m-%d")
    output_dir = os.path.join("chart", current_date_str)
    os.makedirs(output_dir, exist_ok=True)
    css_href = _write_static_asset(_CSS_SOURCE_PATH, output_dir)
    js_href = _write_static_asset(_JS_SOURCE_PATH, output_dir)

    html = _build_html(
        symbol=symbol,
        date_from=date_from,
        date_to=date_to,
        css_href=css_href,
        js_href=js_href,
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
        hover_data_json=json.dumps(mb.hover_payloads),
    )

    file_name = f"{symbol}_{date_from}_{date_to}.html"
    output_path = os.path.join(output_dir, file_name)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    open_html_in_chrome(output_path)


draw_chart = render_backtest_chart
