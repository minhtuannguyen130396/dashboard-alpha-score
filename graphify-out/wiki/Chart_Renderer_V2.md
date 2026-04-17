# Chart Renderer V2

> 30 nodes · cohesion 0.12

## Summary

Tạo báo cáo HTML tương tác dùng TradingView Lightweight Charts. `render_backtest_chart()` nhận `MarketBehaviorSnapshot` và xuất một file HTML tự chứa, mở trực tiếp trên Chrome. Python side (`chart_renderer_v2.py`) build data JSON + khung HTML; JavaScript side (`chart_renderer_v2.js`) xử lý render và tương tác.

**Layout chart:** Candlestick chính + volume bars + score strip (màu gradient theo signal_score) + smart money strip (setup_composite và trigger_composite). Crosshair hover kích hoạt `renderHoverPanel()` hiển thị chi tiết điểm số từng thành phần, được tính sẵn trong `hover_payloads` (precomputed — không tính lại khi hover). `redrawStrips()` và `visibleWindow()` đồng bộ scroll giữa các panel.

## Key Concepts

- **chart_renderer_v2.py** (29 connections) — `src\reporting\chart_renderer_v2.py`
- **makeSub()** (6 connections) — `src\reporting\chart_renderer_v2.js`
- **render_backtest_chart()** (6 connections) — `src\reporting\chart_renderer_v2.py`
- **renderHoverPanel()** (5 connections) — `src\reporting\chart_renderer_v2.js`
- **drawSmStrip()** (4 connections) — `src\reporting\chart_renderer_v2.js`
- **_bar()** (3 connections) — `src\reporting\chart_renderer_v2.js`
- **_build_finance_rows()** (3 connections) — `src\reporting\chart_renderer_v2.py`
- **drawScoreStrip()** (3 connections) — `src\reporting\chart_renderer_v2.js`
- **_fmt_date()** (3 connections) — `src\reporting\chart_renderer_v2.py`
- **_n()** (3 connections) — `src\reporting\chart_renderer_v2.js`
- **chart_renderer_v2.py Beautiful HTML chart renderer using TradingView Lightweight** (3 connections) — `src\reporting\chart_renderer_v2.py`
- **redrawStrips()** (3 connections) — `src\reporting\chart_renderer_v2.js`
- **_srow()** (3 connections) — `src\reporting\chart_renderer_v2.js`
- **updateSelectedDay()** (3 connections) — `src\reporting\chart_renderer_v2.js`
- **visibleWindow()** (3 connections) — `src\reporting\chart_renderer_v2.js`
- **_build_html()** (2 connections) — `src\reporting\chart_renderer_v2.py`
- **crosshairOpts()** (2 connections) — `src\reporting\chart_renderer_v2.js`
- **gridOpts()** (2 connections) — `src\reporting\chart_renderer_v2.js`
- **_hexToRgba()** (2 connections) — `src\reporting\chart_renderer_v2.js`
- **layoutOpts()** (2 connections) — `src\reporting\chart_renderer_v2.js`
- **open_html_in_chrome()** (2 connections) — `src\reporting\chart_renderer_v2.py`
- **renderInfoBar()** (2 connections) — `src\reporting\chart_renderer_v2.js`
- **scaleOpts()** (2 connections) — `src\reporting\chart_renderer_v2.js`
- **scrollOpts()** (2 connections) — `src\reporting\chart_renderer_v2.js`
- **_vol()** (2 connections) — `src\reporting\chart_renderer_v2.js`
- *... and 5 more nodes in this community*

## Relationships

- No strong cross-community connections detected

## Source Files

- `src\reporting\chart_renderer_v2.js`
- `src\reporting\chart_renderer_v2.py`

## Audit Trail

- EXTRACTED: 104 (98%)
- INFERRED: 2 (2%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*