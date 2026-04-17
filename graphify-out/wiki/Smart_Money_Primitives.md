# Smart Money Primitives

> 72 nodes · cohesion 0.05

## Summary

Community lớn nhất (72 nodes, cohesion thấp 0.05 — nhiều file kết hợp). Đây là view tổng thể của toàn bộ Smart Money module: primitives + composite + config + types + score_config — bao gồm cả `score_config.py` mà Smart_Money_Core.md không có.

Điểm khác biệt với [[Smart Money Core]]: Smart_Money_Primitives còn bao gồm `score_config.py` (`ScoreConfigV5`, `.v4_compat()`) và nhiều intraday primitives hơn. Cohesion thấp vì graphify cluster này gom nhiều file không liên quan chặt chẽ. Đọc [[Smart Money Core]] để hiểu kiến trúc cốt lõi, đọc [[Score Config]] cho cấu hình weights/thresholds.

## Key Concepts

- **SmartMoneyConfig** (42 connections) — `src\analysis\smart_money\config.py`
- **FlowPrimitive** (35 connections) — `src\analysis\smart_money\types.py`
- **composite.py** (10 connections) — `src\analysis\smart_money\composite.py`
- **Tick-level helpers (Phase 4): trade classification + feature cache.  The intrada** (9 connections) — `src\analysis\smart_money\tick\__init__.py`
- **score_config.py** (9 connections) — `src\analysis\score_config.py`
- **compute_smart_money_mtf()** (8 connections) — `src\analysis\smart_money\composite.py`
- **SmartMoneySignal** (8 connections) — `src\analysis\smart_money\types.py`
- **_compute_daily_layer()** (7 connections) — `src\analysis\smart_money\composite.py`
- **Primitive** (6 connections) — `src\analysis\smart_money\primitives\base.py`
- **compute_smart_money()** (6 connections) — `src\analysis\smart_money\composite.py`
- **ScoreConfigV5** (6 connections) — `src\analysis\score_config.py`
- **ConcentrationPrimitive** (5 connections) — `src\analysis\smart_money\primitives\concentration.py`
- **DivergencePrimitive** (5 connections) — `src\analysis\smart_money\primitives\divergence.py`
- **ForeignFlowPrimitive** (5 connections) — `src\analysis\smart_money\primitives\foreign_flow.py`
- **PropFlowPrimitive** (5 connections) — `src\analysis\smart_money\primitives\prop_flow.py`
- **.v4_compat()** (5 connections) — `src\analysis\score_config.py`
- **_aggregate_bucket()** (4 connections) — `src\analysis\smart_money\composite.py`
- **Composite aggregator for smart money primitives.  Splits primitives into two ind** (4 connections) — `src\analysis\smart_money\composite.py`
- **Pick (setup_weights, trigger_weights), honoring Phase 5 calibration.** (4 connections) — `src\analysis\smart_money\composite.py`
- **Run all daily primitives over ``records`` and return bucket outputs.      Return** (4 connections) — `src\analysis\smart_money\composite.py`
- **Compute the daily smart money signal for a single symbol.      ``records`` is a** (4 connections) — `src\analysis\smart_money\composite.py`
- **Multi-timeframe smart money compute (Phase 3+).      Daily layer is always compu** (4 connections) — `src\analysis\smart_money\composite.py`
- **Weighted average over primitives, weighted by configured weight × confidence.** (4 connections) — `src\analysis\smart_money\composite.py`
- **_resolve_weights()** (4 connections) — `src\analysis\smart_money\composite.py`
- **divergence.py** (4 connections) — `src\analysis\smart_money\primitives\divergence.py`
- *... and 47 more nodes in this community*

## Relationships

- No strong cross-community connections detected

## Source Files

- `src\analysis\score_config.py`
- `src\analysis\smart_money\composite.py`
- `src\analysis\smart_money\config.py`
- `src\analysis\smart_money\primitives\base.py`
- `src\analysis\smart_money\primitives\concentration.py`
- `src\analysis\smart_money\primitives\divergence.py`
- `src\analysis\smart_money\primitives\foreign_flow.py`
- `src\analysis\smart_money\primitives\prop_flow.py`
- `src\analysis\smart_money\primitives\toxic_flow.py`
- `src\analysis\smart_money\primitives_intraday.py`
- `src\analysis\smart_money\tick\__init__.py`
- `src\analysis\smart_money\types.py`

## Audit Trail

- EXTRACTED: 160 (52%)
- INFERRED: 148 (48%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*