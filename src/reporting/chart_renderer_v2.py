"""
chart_renderer_v2.py
Beautiful HTML chart renderer using TradingView Lightweight Charts.
Price + volume + technical indicator panes — no trading signals.
"""
import json
import os
import shutil
import webbrowser
from datetime import datetime
from typing import Any, Dict, List, Optional

from src.data.stock_data_loader import StockRecord
from src.analysis.market_behavior_analyzer import MarketBehaviorSnapshot


REPORTING_DIR = os.path.dirname(__file__)
CSS_PATH = os.path.join(REPORTING_DIR, "chart_renderer_v2.css")
JS_PATH = os.path.join(REPORTING_DIR, "chart_renderer_v2.js")

#: Vendored copy of Lightweight Charts. A chart written to disk has to keep
#: working offline and after being emailed, so the library ships with the repo;
#: the CDN URL is only the fallback for the linked-asset chart below.
LIB_PATH = os.path.join(REPORTING_DIR, "vendor",
                        "lightweight-charts.standalone.production.js")
LIB_CDN = ("https://unpkg.com/lightweight-charts@4.2.0/dist/"
           "lightweight-charts.standalone.production.js")


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


# ---------------------------------------------------------------------------
# HTML assembly — only the dynamic parts use f-strings
# ---------------------------------------------------------------------------
def chart_body_html() -> str:
    """The markup the chart JS expects — legend, read-outs, one div per pane.

    The ids here are what ``chart_renderer_v2.js`` looks up; keeping the
    skeleton in one function means the standalone chart page and the report
    dossier can never drift into two different DOMs.
    """
    return "\n".join([
        # Legend
        '<div id="legend">',
        '  <span class="li"><span class="line line-ema20"></span>EMA20</span>',
        '  <span class="li"><span class="line line-ema50"></span>EMA50</span>',
        '  <span class="legend-separator">│</span>',
        '  <span class="li"><span class="dot dot-vol-big-buyer"></span>Vol: Big Buyer</span>',
        '  <span class="li"><span class="dot dot-vol-fomo-retail"></span>Vol: Fomo Retail</span>',
        '  <span class="li"><span class="dot dot-vol-both"></span>Vol: Cả hai</span>',
        '  <span class="li"><span class="dot dot-vol-other"></span>Vol: Khác</span>',
        '</div>',

        # Structure read-out — pattern name + why each overlay is drawn
        '<div id="structure-panel"></div>',

        # Full hover panel — shows price + indicators for the selected day
        '<div id="hover-panel"></div>',

        # Floating tooltip for hovering a trendline / box edge — positioned via
        # fixed coords in JS so it never fights Lightweight Charts' own DOM.
        '<div id="overlay-tooltip"></div>',

        '<div id="charts-container">',
        '  <div id="price-chart"></div>',
        '  <div id="volume-chart"></div>',
        '  <div id="rsi-chart"></div>',
        '  <div id="macd-chart"></div>',
        '  <div id="adx-chart"></div>',
        '</div>',
    ])


def chart_data_script(series: Dict[str, List[Any]],
                      overlays: Optional[dict] = None) -> str:
    """The globals the chart JS reads, as one ``<script>`` block."""
    return "\n".join([
        '<script>',
        f'const CANDLE_DATA          = {json.dumps(series["candles"])};',
        f'const EMA20_DATA           = {json.dumps(series["ema20"])};',
        f'const EMA50_DATA           = {json.dumps(series["ema50"])};',
        f'const VOLUME_DATA          = {json.dumps(series["volume"])};',
        f'const EMA_VOLUME_DATA      = {json.dumps(series["ema_volume"])};',
        f'const HOVER_DATA           = {json.dumps(series["hover"])};',
        f'const OVERLAY_DATA         = {json.dumps(overlays or {}, ensure_ascii=False)};',
        '</script>',
    ])


def _build_html(
    symbol: str,
    date_from: str,
    date_to: str,
    css_href: str,
    js_href: str,
    data_script: str,
) -> str:
    return "\n".join([
        '<!DOCTYPE html>',
        '<html lang="vi">',
        '<head>',
        '<meta charset="UTF-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1.0">',
        f'<title>[{symbol}] {date_from} → {date_to}</title>',
        f'<script src="{LIB_CDN}"></script>',
        f'<link rel="stylesheet" href="{css_href}">',
        '</head>',
        '<body>',

        # Header
        '<div id="header">',
        f'  <div class="left"><h1>[{symbol}]</h1><div class="sub">{date_from} &nbsp;→&nbsp; {date_to}</div></div>',
        '</div>',

        chart_body_html(),

        # Inject data
        data_script,

        # Chart logic (plain string — no brace escaping needed)
        f'<script src="{js_href}"></script>',

        '</body>',
        '</html>',
    ])


# ---------------------------------------------------------------------------
# Series payload — shared by every renderer that draws this chart
# ---------------------------------------------------------------------------
#: Volume bar colour by (big buyer, fomo retail).
_VOLUME_COLOR = {
    (True,  False): "#26a69a",
    (False, True):  "#ef5350",
    (True,  True):  "#2962ff",
    (False, False): "#9c27b0",
}


def build_series(
    stock_records: List[StockRecord],
    market_behavior: MarketBehaviorSnapshot,
) -> Dict[str, List[Any]]:
    """The data the chart JS reads, built once.

    Both the standalone chart file and the report dossier inject these under the
    same global names, so a change in how a series is shaped lands on both.
    """
    mb = market_behavior
    return {
        "candles": [
            {
                "time": _fmt_date(r.date),
                "open": r.priceOpen, "high": r.priceHigh,
                "low": r.priceLow,   "close": r.priceClose,
            }
            for r in stock_records
        ],
        "ema20": [
            {"time": _fmt_date(r.date), "value": v}
            for r, v in zip(stock_records, mb.ema20) if v is not None
        ],
        "ema50": [
            {"time": _fmt_date(r.date), "value": v}
            for r, v in zip(stock_records, mb.ema50) if v is not None
        ],
        "volume": [
            {
                "time": _fmt_date(r.date),
                "value": mb.total_volume[i],
                "color": _VOLUME_COLOR[(bool(mb.big_buyer[i]), bool(mb.fomo_retail[i]))],
            }
            for i, r in enumerate(stock_records)
        ],
        "ema_volume": [
            {"time": _fmt_date(r.date), "value": v}
            for r, v in zip(stock_records, mb.ema_volume) if v is not None
        ],
        "hover": mb.hover_payloads,
    }


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------
def render_chart(
    stock_records: List[StockRecord],
    market_behavior: MarketBehaviorSnapshot,
    overlays: Optional[dict] = None,
    open_browser: bool = True,
    out_dir: Optional[str] = None,
) -> str:
    series = build_series(stock_records, market_behavior)

    symbol      = stock_records[-1].symbol
    date_from   = _fmt_date(stock_records[0].date)
    date_to     = _fmt_date(stock_records[-1].date)

    # Chart hồi tưởng đi vào thư mục riêng của mốc (`out_dir`), chứ không nằm
    # lẫn với chart của phiên thật — xem `src/ta/asof.py`.
    output_dir = out_dir or os.path.join("chart", datetime.now().strftime("%Y-%m-%d"))
    os.makedirs(output_dir, exist_ok=True)
    css_href = _write_static_asset(CSS_PATH, output_dir)
    js_href = _write_static_asset(JS_PATH, output_dir)

    html = _build_html(
        symbol=symbol,
        date_from=date_from,
        date_to=date_to,
        css_href=css_href,
        js_href=js_href,
        data_script=chart_data_script(series, overlays),
    )

    file_name = f"{symbol}_{date_from}_{date_to}.html"
    output_path = os.path.join(output_dir, file_name)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    if open_browser:
        open_html_in_chrome(output_path)
    return output_path


draw_chart = render_chart
