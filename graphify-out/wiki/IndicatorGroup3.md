# IndicatorGroup3

> God node · 19 connections · `src\analysis\technical_indicators.py`

## What It Is

Xem [[IndicatorGroup1]] — cùng pattern, khác tập indicators. IndicatorGroup3 có nhiều connections nhất (19) vì nó được dùng trong cả `market_behavior_analyzer.py` lẫn `trade_simulator.py`, không chỉ trong scoring engine. Đây là bundle có scope rộng nhất trong 4 group.

## Connections by Relation

### contains
- [[technical_indicators.py]] `EXTRACTED`

### uses
- [[SignalScoreV4]] `INFERRED`
- [[MarketBehaviorSnapshot]] `INFERRED`
- [[Blocker]] `INFERRED`
- [[Signal Score V4 — sole supported scoring engine.  Carries forward V3's dedicat]] `INFERRED`
- [[Return 0..1 rank of ``value`` within ``window``.]] `INFERRED`
- [[Percentile rank of the latest value within the last ``window`` values.]] `INFERRED`
- [[Slow-moving accumulation/distribution view.]] `INFERRED`
- [[Intraday-only trigger: RVOL, wide range, close position.]] `INFERRED`
- [[True if price makes new low/high but indicator doesn't confirm.]] `INFERRED`
- [[Score domestic proprietary trading (tự doanh) net flow.      Positive ``propTr]] `INFERRED`
- [[Container for derived market behavior signals and overlays.]] `INFERRED`
- [[Compute one hover payload per trading day.      All indicators are calculated]] `INFERRED`
- [[Buy when setup is solid, both gates clear and no hard blocker.      Three-stag]] `INFERRED`
- [[Asymmetric sell: looser thresholds, but suppressed in bull regimes.      Ratio]] `INFERRED`
- [[TradeConfigV4]] `INFERRED`
- [[Trade simulator V4.  Single-position long-only simulator with realistic VN mar]] `INFERRED`
- [[Emit a TradeRecord for ``fraction`` of a unit position.      ``profit`` is sca]] `INFERRED`
- [[Single-position simulator. Returns trades, sale-marker list, buy-marker list.]] `INFERRED`

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*