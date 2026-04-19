# Market Behavior Scoring

> 29 nodes · cohesion 0.24

## Summary

Tầng quyết định cuối cùng — kết hợp `SignalScoreV4` + `SmartMoneySignal` + candle patterns để xác định BUY/SELL tại mỗi bar. `MarketBehaviorSnapshot` lưu toàn bộ chuỗi dữ liệu theo ngày (buy/sell points, scores, smart money composites, hover payloads) để chart renderer tiêu thụ mà không cần tính lại.

Logic mua (`_is_buy_signal`) chỉ kích hoạt trong các regime được phép (`bull_trend`, `mild_bull`, `bullish_reversal`) và yêu cầu cả hai gate (setup + trigger) đủ điểm, không có hard blocker. Logic bán (`_is_sale_signal`) dùng ngưỡng thấp hơn nhưng bị tắt trong bull regime — exit trong xu hướng mạnh nên để ATR/trailing stop xử lý, không phải tín hiệu bán.

## Key Concepts

- **IndicatorGroup3** (19 connections) — `src\analysis\technical_indicators.py`
- **IndicatorGroup4** (16 connections) — `src\analysis\technical_indicators.py`
- **IndicatorGroup1** (15 connections) — `src\analysis\technical_indicators.py`
- **IndicatorGroup2** (15 connections) — `src\analysis\technical_indicators.py`
- **SignalScoreV4** (14 connections) — `src\analysis\signal_scoring_v4.py`
- **BearishPatterns** (10 connections) — `src\analysis\candle_patterns.py`
- **BullishPatterns** (10 connections) — `src\analysis\candle_patterns.py`
- **MarketBehaviorSnapshot** (10 connections) — `src\analysis\market_behavior_analyzer.py`
- **Blocker** (9 connections) — `src\analysis\signal_scoring_v4.py`
- **Signal Score V4 — sole supported scoring engine.  Carries forward V3's dedicat** (7 connections) — `src\analysis\signal_scoring_v4.py`
- **Slow-moving accumulation/distribution view.** (7 connections) — `src\analysis\signal_scoring_v4.py`
- **Intraday-only trigger: RVOL, wide range, close position.** (7 connections) — `src\analysis\signal_scoring_v4.py`
- **True if price makes new low/high but indicator doesn't confirm.** (7 connections) — `src\analysis\signal_scoring_v4.py`
- **Score domestic proprietary trading (tự doanh) net flow.      Positive ``propTr** (7 connections) — `src\analysis\signal_scoring_v4.py`
- **Return 0..1 rank of ``value`` within ``window``.** (7 connections) — `src\analysis\signal_scoring_v4.py`
- **Percentile rank of the latest value within the last ``window`` values.** (7 connections) — `src\analysis\signal_scoring_v4.py`
- **market_behavior_analyzer.py** (6 connections) — `src\analysis\market_behavior_analyzer.py`
- **Buy when setup is solid, both gates clear and no hard blocker.      Three-stag** (6 connections) — `src\analysis\market_behavior_analyzer.py`
- **Asymmetric sell: looser thresholds, but suppressed in bull regimes.      Ratio** (6 connections) — `src\analysis\market_behavior_analyzer.py`
- **Container for derived market behavior signals and overlays.** (6 connections) — `src\analysis\market_behavior_analyzer.py`
- **Compute one hover payload per trading day.      All indicators are calculated** (6 connections) — `src\analysis\market_behavior_analyzer.py`
- **analyze_market_behavior()** (5 connections) — `src\analysis\market_behavior_analyzer.py`
- **_is_buy_signal()** (4 connections) — `src\analysis\market_behavior_analyzer.py`
- **_is_sale_signal()** (4 connections) — `src\analysis\market_behavior_analyzer.py`
- **_build_hover_payloads()** (3 connections) — `src\analysis\market_behavior_analyzer.py`
- *... and 4 more nodes in this community*

## Relationships

- No strong cross-community connections detected

## Source Files

- `src\analysis\candle_patterns.py`
- `src\analysis\market_behavior_analyzer.py`
- `src\analysis\signal_scoring_v4.py`
- `src\analysis\technical_indicators.py`

## Audit Trail

- EXTRACTED: 56 (26%)
- INFERRED: 163 (74%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*