# Graph Report - E:\Trader\support_trade_stock_tool  (2026-04-09)

## Corpus Check
- Corpus is ~30,555 words - fits in a single context window. You may not need a graph.

## Summary
- 492 nodes · 834 edges · 62 communities detected
- Extraction: 72% EXTRACTED · 28% INFERRED · 0% AMBIGUOUS · INFERRED: 234 edges (avg confidence: 0.5)
- Token cost: 0 input · 0 output

## God Nodes (most connected - your core abstractions)
1. `FlowPrimitive` - 35 edges
2. `SmartMoneyConfig` - 32 edges
3. `_mk_record()` - 22 edges
4. `IndicatorGroup3` - 19 edges
5. `IntradayPrimitiveTest` - 17 edges
6. `CalibrationTest` - 17 edges
7. `IndicatorGroup4` - 16 edges
8. `_build_score_v4()` - 15 edges
9. `IndicatorGroup1` - 15 edges
10. `IndicatorGroup2` - 15 edges

## Surprising Connections (you probably didn't know these)
- `Persistence detector — multiplier (NOT a bucket primitive).  Returns a ``Persist` --uses--> `SmartMoneyConfig`  [INFERRED]
  src\analysis\smart_money\primitives\persistence.py → src\analysis\smart_money\config.py
- `Unit tests for the smart_money module (Phase 1).` --uses--> `FlowPrimitive`  [INFERRED]
  tests\test_smart_money.py → src\analysis\smart_money\types.py
- `chart_renderer_v2.py Beautiful HTML chart renderer using TradingView Lightweight` --uses--> `MarketBehaviorSnapshot`  [INFERRED]
  src\reporting\chart_renderer_v2.py → src\analysis\market_behavior_analyzer.py
- `TradeConfigV4` --uses--> `IndicatorGroup3`  [INFERRED]
  src\backtesting\trade_simulator.py → src\analysis\technical_indicators.py
- `Trade simulator V4.  Single-position long-only simulator with realistic VN mar` --uses--> `IndicatorGroup3`  [INFERRED]
  src\backtesting\trade_simulator.py → src\analysis\technical_indicators.py

## Hyperedges (group relationships)
- **Score Configuration Stack** — ScoreWeightsV4, ScoreThresholdsV4, ScoreConfigV4 [INFERRED 0.90]
- **Hover Payload Delivery Stack** — MarketBehaviorSnapshot, _build_hover_payloads(), render_backtest_chart() [INFERRED 0.92]

## Communities

### Community 0 - "Intraday Flow Primitives"
Cohesion: 0.06
Nodes (24): AuctionFlowPrimitive, _bar_minutes(), BlockTradePrimitive, _compute_ofi_scalar(), IntradayDivergencePrimitive, OrderFlowImbalancePrimitive, _percentile_rank(), run_intraday_primitives() (+16 more)

### Community 1 - "Smart Money Core"
Cohesion: 0.06
Nodes (44): _deal_value(), Primitive, Protocol that every flow primitive must satisfy., Traded value excluding putthrough (price-impact value).      The smart money doc, _aggregate_bucket(), _assert_bucket_invariants(), _classify_label(), _compute_daily_layer() (+36 more)

### Community 2 - "Technical Indicators"
Cohesion: 0.06
Nodes (26): atr(), average_volume(), bollinger_bands(), chaikin_volatility(), ema(), _extract(), hma(), _impact_volumes() (+18 more)

### Community 3 - "Smart Money Tests"
Cohesion: 0.08
Nodes (8): CompositeTest, ForeignPrimitiveTest, IntegrationV5Test, _mk_record(), NormalizeTest, Phase2Test, PropPrimitiveTest, Unit tests for the smart_money module (Phase 1).

### Community 4 - "Weight Calibration"
Cohesion: 0.08
Nodes (20): CalibratedWeights, DriftMonitor, DriftReport, ExpectedReturnBins, _fit_logistic(), from_dict(), load_calibrated_weights(), _profit_factor() (+12 more)

### Community 5 - "Chart Renderer V2"
Cohesion: 0.12
Nodes (25): _bar(), _build_finance_rows(), _build_html(), crosshairOpts(), drawScoreStrip(), drawSmStrip(), _fmt_date(), gridOpts() (+17 more)

### Community 6 - "Market Behavior Scoring"
Cohesion: 0.24
Nodes (26): BearishPatterns, BullishPatterns, _LegacyIndicatorGroup4, analyze_market_behavior(), _build_hover_payloads(), _has_hard_blocker(), _is_buy_signal(), _is_sale_signal() (+18 more)

### Community 7 - "Backtest Engine"
Cohesion: 0.1
Nodes (13): compute_stats(), PerformanceStats, Performance metrics for backtest trade lists.  Computes the set called out in, _std(), BacktestReportRow, TradeRecord, _build_trade_record(), Trade simulator V4.  Single-position long-only simulator with realistic VN mar (+5 more)

### Community 8 - "Candlestick Patterns"
Cohesion: 0.13
Nodes (9): _candle_features(), _extract(), hammer(), hanging_man(), inverted_hammer(), _is_downtrend(), _is_uptrend(), NeutralPatterns (+1 more)

### Community 9 - "Signal Scoring V4"
Cohesion: 0.2
Nodes (18): _build_score_v4(), calculate_signal_score_v4(), _candle_quality(), _detect_blockers_v4(), _detect_divergence(), _percentile_rank(), _rolling_rank(), _safe_last() (+10 more)

### Community 10 - "Stock Selector App"
Cohesion: 0.23
Nodes (13): _action_btn(), _apply_theme(), _card(), create_stock_selector_app(), _field_label(), get_all_stock_records(), get_all_symbols(), _load_records() (+5 more)

### Community 11 - "Numeric Normalization"
Cohesion: 0.18
Nodes (10): clamp(), rank_to_signed(), Shared numeric helpers for smart money primitives., Cap the lowest/highest p fraction of values to reduce outlier impact., Z-score of the latest value within the last ``window`` entries.      Winsorizes, Map a [0..1] percentile rank to the [-1..+1] range., Smooth bounded mapping to [-1..+1] via tanh., rolling_zscore() (+2 more)

### Community 12 - "Trade Classification"
Cohesion: 0.21
Nodes (10): bvc_classify(), lee_ready_classify(), _normal_cdf(), Trade classification (tick rule, Lee-Ready, BVC).  VN tick feeds rarely include, Mark each tick +1/-1/0 based on price change vs previous tick.      Equal price, Quote-rule + tick-rule fallback (Lee-Ready 1991). Needs bid/ask., Bulk Volume Classification — splits each bar's volume into buy/sell.      Doesn', _resolve_for_bars() (+2 more)

### Community 13 - "Persistence Detector"
Cohesion: 0.47
Nodes (3): PersistenceDetector, PersistenceSignal, Persistence detector — multiplier (NOT a bucket primitive).  Returns a ``Persist

### Community 14 - "Chart Renderer"
Cohesion: 0.6
Nodes (3): draw_candlestick_plotly(), open_html_in_chrome(), render_backtest_chart()

### Community 15 - "Volume Convention Tests"
Cohesion: 0.6
Nodes (2): _record(), VolumeConventionTest

### Community 16 - "Volume Convention"
Cohesion: 0.5
Nodes (4): Deal Volume as Price-Movement Source, Price Impact Volume, Total Volume Raw Reference, Volume Convention

### Community 17 - "Adjusted Price Loader"
Cohesion: 0.67
Nodes (1): LoadStockHistoryAdjustmentTest

### Community 18 - "Score V2 Validation"
Cohesion: 0.67
Nodes (3): A/B Backtest Comparison, Regime-Based Validation, Score V2 Validation Checklist

### Community 19 - "CLI Entry Point"
Cohesion: 1.0
Nodes (0): 

### Community 20 - "Score V2 Notes"
Cohesion: 1.0
Nodes (2): Score V2 Implementation Notes, Setup / Trigger Scoring Split

### Community 21 - "Hover Payload Pipeline"
Cohesion: 1.0
Nodes (2): Hover Score Details Prompt, Precomputed Hover Payload Pipeline

### Community 22 - "Simple Moving Average"
Cohesion: 1.0
Nodes (1): Calculate the Simple Moving Average.

### Community 23 - "Exponential Moving Average"
Cohesion: 1.0
Nodes (1): Calculate the Exponential Moving Average.

### Community 24 - "Weighted Moving Average"
Cohesion: 1.0
Nodes (1): Calculate the Weighted Moving Average.

### Community 25 - "Volume Weighted MA"
Cohesion: 1.0
Nodes (1): Calculate the Volume Weighted Moving Average.

### Community 26 - "Hull Moving Average"
Cohesion: 1.0
Nodes (1): Calculate the Hull Moving Average.

### Community 27 - "Kaufman Adaptive MA"
Cohesion: 1.0
Nodes (1): Calculate the Kaufman Adaptive Moving Average.

### Community 28 - "Price Momentum"
Cohesion: 1.0
Nodes (1): Measure momentum using the close versus the close N periods ago.

### Community 29 - "Percent Momentum"
Cohesion: 1.0
Nodes (1): Measure momentum as a percentage change instead of an absolute delta.

### Community 30 - "Rate of Change"
Cohesion: 1.0
Nodes (1): Calculate the Rate of Change.

### Community 31 - "Commodity Channel Index"
Cohesion: 1.0
Nodes (1): Calculate the Commodity Channel Index.

### Community 32 - "Stochastic %K"
Cohesion: 1.0
Nodes (1): Calculate Stochastic %K.

### Community 33 - "Stochastic %D"
Cohesion: 1.0
Nodes (1): Calculate Stochastic %D.

### Community 34 - "Williams %R"
Cohesion: 1.0
Nodes (1): Calculate Williams %R.

### Community 35 - "Ultimate Oscillator"
Cohesion: 1.0
Nodes (1): Calculate the Ultimate Oscillator.

### Community 36 - "MACD Histogram"
Cohesion: 1.0
Nodes (1): Calculate MACD, the signal line, and the histogram.

### Community 37 - "Relative Strength Index"
Cohesion: 1.0
Nodes (1): Calculate the Relative Strength Index (Wilder's smoothing).

### Community 38 - "Average True Range"
Cohesion: 1.0
Nodes (1): Calculate the Average True Range.

### Community 39 - "Average Directional Index"
Cohesion: 1.0
Nodes (1): Calculate the Average Directional Index (Wilder's method).

### Community 40 - "Bollinger Bands"
Cohesion: 1.0
Nodes (1): Calculate Bollinger Bands.

### Community 41 - "Keltner Channel"
Cohesion: 1.0
Nodes (1): Calculate the Keltner Channel.

### Community 42 - "Donchian Channel"
Cohesion: 1.0
Nodes (1): Calculate the Donchian Channel.

### Community 43 - "Standard Deviation"
Cohesion: 1.0
Nodes (1): Calculate standard deviation.

### Community 44 - "Mass Index"
Cohesion: 1.0
Nodes (1): Calculate the Mass Index.

### Community 45 - "Chaikin Volatility"
Cohesion: 1.0
Nodes (1): Calculate Chaikin Volatility.

### Community 46 - "On Balance Volume"
Cohesion: 1.0
Nodes (1): Calculate On-Balance Volume.

### Community 47 - "ADL Divergence Signals"
Cohesion: 1.0
Nodes (1): Generate divergence signals from the ADL:         +1: bullish divergence (price

### Community 48 - "Chaikin Money Flow"
Cohesion: 1.0
Nodes (1): Calculate Chaikin Money Flow             This has been tested, but the hit rate

### Community 49 - "Money Flow Index"
Cohesion: 1.0
Nodes (1): Calculate the Money Flow Index.

### Community 50 - "VROC Score"
Cohesion: 1.0
Nodes (1): Calculate the VROC score:         - Return 1 if current volume change versus N

### Community 51 - "VWAP"
Cohesion: 1.0
Nodes (1): Calculate the Volume-Weighted Average Price.

### Community 52 - "Large Buyer Signals"
Cohesion: 1.0
Nodes (1): Check whether there is evidence of large-buyer accumulation.

### Community 53 - "Retail FOMO Signals"
Cohesion: 1.0
Nodes (1): Check whether retail FOMO behavior is likely present.

### Community 54 - "Advance Decline Line"
Cohesion: 1.0
Nodes (1): Calculate the Advance/Decline Line as the cumulative net advances.

### Community 55 - "McClellan Oscillator"
Cohesion: 1.0
Nodes (1): Calculate the McClellan Oscillator as short EMA minus long EMA of net advances.

### Community 56 - "TRIN Index"
Cohesion: 1.0
Nodes (1): Calculate TRIN (Arms Index): (adv/dec) / (vol_adv/vol_dec).

### Community 57 - "Bullish Percent Index"
Cohesion: 1.0
Nodes (1): Calculate the Bullish Percent Index as the percentage of bullish stocks.

### Community 58 - "Pivot Support Levels"
Cohesion: 1.0
Nodes (1): Calculate pivot points and support/resistance levels (S1-S3, R1-R3).

### Community 59 - "Fibonacci Levels"
Cohesion: 1.0
Nodes (1): Calculate Fibonacci retracement and extension levels.

### Community 60 - "Rolling Correlation"
Cohesion: 1.0
Nodes (1): Calculate the rolling Pearson correlation coefficient.

### Community 61 - "Workspace Rules"
Cohesion: 1.0
Nodes (1): Graphify Workspace Rules

## Knowledge Gaps
- **79 isolated node(s):** `NeutralPatterns`, `IndicatorGroup5`, `IndicatorGroup6`, `Use deal volume for any indicator intended to explain price movement.`, `Calculate average volume over the most recent N sessions.` (+74 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **Thin community `CLI Entry Point`** (2 nodes): `main.py`, `main()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Score V2 Notes`** (2 nodes): `Score V2 Implementation Notes`, `Setup / Trigger Scoring Split`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Hover Payload Pipeline`** (2 nodes): `Hover Score Details Prompt`, `Precomputed Hover Payload Pipeline`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Simple Moving Average`** (1 nodes): `Calculate the Simple Moving Average.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Exponential Moving Average`** (1 nodes): `Calculate the Exponential Moving Average.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Weighted Moving Average`** (1 nodes): `Calculate the Weighted Moving Average.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Volume Weighted MA`** (1 nodes): `Calculate the Volume Weighted Moving Average.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Hull Moving Average`** (1 nodes): `Calculate the Hull Moving Average.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Kaufman Adaptive MA`** (1 nodes): `Calculate the Kaufman Adaptive Moving Average.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Price Momentum`** (1 nodes): `Measure momentum using the close versus the close N periods ago.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Percent Momentum`** (1 nodes): `Measure momentum as a percentage change instead of an absolute delta.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Rate of Change`** (1 nodes): `Calculate the Rate of Change.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Commodity Channel Index`** (1 nodes): `Calculate the Commodity Channel Index.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Stochastic %K`** (1 nodes): `Calculate Stochastic %K.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Stochastic %D`** (1 nodes): `Calculate Stochastic %D.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Williams %R`** (1 nodes): `Calculate Williams %R.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Ultimate Oscillator`** (1 nodes): `Calculate the Ultimate Oscillator.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `MACD Histogram`** (1 nodes): `Calculate MACD, the signal line, and the histogram.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Relative Strength Index`** (1 nodes): `Calculate the Relative Strength Index (Wilder's smoothing).`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Average True Range`** (1 nodes): `Calculate the Average True Range.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Average Directional Index`** (1 nodes): `Calculate the Average Directional Index (Wilder's method).`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Bollinger Bands`** (1 nodes): `Calculate Bollinger Bands.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Keltner Channel`** (1 nodes): `Calculate the Keltner Channel.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Donchian Channel`** (1 nodes): `Calculate the Donchian Channel.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Standard Deviation`** (1 nodes): `Calculate standard deviation.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Mass Index`** (1 nodes): `Calculate the Mass Index.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Chaikin Volatility`** (1 nodes): `Calculate Chaikin Volatility.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `On Balance Volume`** (1 nodes): `Calculate On-Balance Volume.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `ADL Divergence Signals`** (1 nodes): `Generate divergence signals from the ADL:         +1: bullish divergence (price`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Chaikin Money Flow`** (1 nodes): `Calculate Chaikin Money Flow             This has been tested, but the hit rate`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Money Flow Index`** (1 nodes): `Calculate the Money Flow Index.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `VROC Score`** (1 nodes): `Calculate the VROC score:         - Return 1 if current volume change versus N`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `VWAP`** (1 nodes): `Calculate the Volume-Weighted Average Price.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Large Buyer Signals`** (1 nodes): `Check whether there is evidence of large-buyer accumulation.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Retail FOMO Signals`** (1 nodes): `Check whether retail FOMO behavior is likely present.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Advance Decline Line`** (1 nodes): `Calculate the Advance/Decline Line as the cumulative net advances.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `McClellan Oscillator`** (1 nodes): `Calculate the McClellan Oscillator as short EMA minus long EMA of net advances.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `TRIN Index`** (1 nodes): `Calculate TRIN (Arms Index): (adv/dec) / (vol_adv/vol_dec).`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Bullish Percent Index`** (1 nodes): `Calculate the Bullish Percent Index as the percentage of bullish stocks.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Pivot Support Levels`** (1 nodes): `Calculate pivot points and support/resistance levels (S1-S3, R1-R3).`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Fibonacci Levels`** (1 nodes): `Calculate Fibonacci retracement and extension levels.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Rolling Correlation`** (1 nodes): `Calculate the rolling Pearson correlation coefficient.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Workspace Rules`** (1 nodes): `Graphify Workspace Rules`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `FlowPrimitive` connect `Smart Money Core` to `Intraday Flow Primitives`, `Smart Money Tests`?**
  _High betweenness centrality (0.095) - this node is a cross-community bridge._
- **Why does `Tick-level helpers (Phase 4): trade classification + feature cache.  The intrada` connect `Smart Money Core` to `Intraday Flow Primitives`, `Weight Calibration`?**
  _High betweenness centrality (0.055) - this node is a cross-community bridge._
- **Why does `SmartMoneyConfig` connect `Smart Money Core` to `Intraday Flow Primitives`, `Persistence Detector`?**
  _High betweenness centrality (0.049) - this node is a cross-community bridge._
- **Are the 34 inferred relationships involving `FlowPrimitive` (e.g. with `Composite aggregator for smart money primitives.  Splits primitives into two ind` and `Weighted average over primitives, weighted by configured weight × confidence.`) actually correct?**
  _`FlowPrimitive` has 34 INFERRED edges - model-reasoned connections that need verification._
- **Are the 31 inferred relationships involving `SmartMoneyConfig` (e.g. with `Composite aggregator for smart money primitives.  Splits primitives into two ind` and `Weighted average over primitives, weighted by configured weight × confidence.`) actually correct?**
  _`SmartMoneyConfig` has 31 INFERRED edges - model-reasoned connections that need verification._
- **Are the 18 inferred relationships involving `IndicatorGroup3` (e.g. with `MarketBehaviorSnapshot` and `Container for derived market behavior signals and overlays.`) actually correct?**
  _`IndicatorGroup3` has 18 INFERRED edges - model-reasoned connections that need verification._
- **Are the 7 inferred relationships involving `IntradayPrimitiveTest` (e.g. with `TrainingSignal` and `AuctionFlowPrimitive`) actually correct?**
  _`IntradayPrimitiveTest` has 7 INFERRED edges - model-reasoned connections that need verification._