# Hover Score Details Prompt

Use the prompt below when implementing the hover-details feature for the backtest chart and dashboard score bar.

## Prompt

You are a senior Python developer and data-visualization engineer working in this repository.

Your task is to add a feature that shows the full calculated metrics for a specific candle/day when the user hovers over that day on the chart, and also updates the score bar/panel on the dashboard at the same time.

### Goal

When the user hovers over a candle, date column, or chart point:
- show the full computed metrics for that exact trading day
- render that information in the hover tooltip or hover side panel
- update the score bar / score panel on the dashboard to match the hovered day

The user should be able to inspect one candle/day and immediately see:
- raw market data
- indicator values
- score breakdown
- reasons
- blockers
- signal classification

### Relevant files

Primary files to inspect and modify:
- `src/reporting/chart_renderer_v2.py`
- `src/analysis/market_behavior_analyzer.py`
- `src/analysis/signal_scoring.py`
- `src/backtesting/backtest_runner.py`

Potentially relevant supporting files:
- `src/analysis/technical_indicators.py`
- `dashboard.html`
- `symbol-analysis.html`

### Existing context

The codebase already has:
- `StockRecord`
- `SignalScore`
- `SignalScoreV2`
- `MarketBehaviorSnapshot`
- backtest chart rendering
- per-day score generation during backtest

Do not recompute indicators on every hover in the frontend.
Prepare the full hover payload ahead of time in Python and pass it into the rendered chart/dashboard.

### Feature requirements

For every candle/day, prepare a metadata payload that includes as much of the available calculated data as possible.

When hovering a day, display:
- Date
- Symbol
- Open
- High
- Low
- Close
- Average price
- Volume
- EMA20
- EMA50
- EMA100 if available
- ATR14
- RSI14
- MACD line
- MACD signal
- MACD histogram
- ADX
- RVOL
- MFI
- OBV or OBV slope if available
- swing high / swing low values if available
- score label
- regime
- signal strength if available
- setup score
- trigger score
- final score
- candle score
- trend score
- momentum score
- volume score
- structure score
- confirmation score
- reasons
- blockers
- whether this day is a buy point or sale point

### Dashboard behavior

The dashboard score bar/panel must update when hovering a day.
It should not remain fixed only on the latest candle.

When hover ends, choose one consistent behavior:
- either keep the last hovered state
- or reset to the latest trading day

Explain the choice briefly in code comments only if needed.

### Data model requirement

Design a clear per-day payload structure, for example:

```python
{
    "date": "...",
    "symbol": "...",
    "price": {...},
    "indicators": {...},
    "scores": {...},
    "signals": {...},
    "reasons": [...],
    "blockers": [...]
}
```

You may use a dataclass, dict, or renderer-ready JSON structure, but it must:
- be generated once during chart/report preparation
- be attached to each plotted day/candle
- be easy for the frontend to render
- support both score v1 and score v2

### Technical constraints

- Do not recalculate heavy indicators in frontend JavaScript.
- Reuse already computed data where possible.
- Avoid breaking the existing chart.
- Handle missing data safely with `None`, `null`, or `N/A`.
- Keep the implementation extensible for future score fields.
- Keep backward compatibility as much as possible.

### Expected implementation plan

1. Inspect how chart data is built in `src/reporting/chart_renderer_v2.py`.
2. Extend the market behavior / score payload so each day has full hover metadata.
3. Pass the payload into the chart renderer output.
4. Implement hover handling so the visible score panel updates with the hovered day.
5. Show a readable tooltip / hover details block.
6. Keep the UI performant with larger datasets.

### Deliverables

Implement the feature end to end.

At the end, hovering a single day on the chart should let the user inspect:
- all important calculated values for that day
- the full score decomposition
- the reasons and blockers behind the signal
- synchronized score details in the dashboard panel

### Coding style

- Write clear Python and JavaScript.
- Prefer small helpers over one large function.
- Add short comments only where logic is not obvious.
- Do not duplicate existing indicator calculations if the values already exist elsewhere in the pipeline.

