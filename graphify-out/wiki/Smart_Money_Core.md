# Smart Money Core

> 66 nodes · cohesion 0.06

## Key Concepts

- **FlowPrimitive** (35 connections) — `src\analysis\smart_money\types.py`
- **SmartMoneyConfig** (32 connections) — `src\analysis\smart_money\config.py`
- **composite.py** (10 connections) — `src\analysis\smart_money\composite.py`
- **Tick-level helpers (Phase 4): trade classification + feature cache.  The intrada** (9 connections) — `src\analysis\smart_money\tick\__init__.py`
- **compute_smart_money_mtf()** (8 connections) — `src\analysis\smart_money\composite.py`
- **SmartMoneySignal** (8 connections) — `src\analysis\smart_money\types.py`
- **_compute_daily_layer()** (7 connections) — `src\analysis\smart_money\composite.py`
- **Primitive** (6 connections) — `src\analysis\smart_money\primitives\base.py`
- **compute_smart_money()** (6 connections) — `src\analysis\smart_money\composite.py`
- **ConcentrationPrimitive** (5 connections) — `src\analysis\smart_money\primitives\concentration.py`
- **DivergencePrimitive** (5 connections) — `src\analysis\smart_money\primitives\divergence.py`
- **ForeignFlowPrimitive** (5 connections) — `src\analysis\smart_money\primitives\foreign_flow.py`
- **PropFlowPrimitive** (5 connections) — `src\analysis\smart_money\primitives\prop_flow.py`
- **_aggregate_bucket()** (4 connections) — `src\analysis\smart_money\composite.py`
- **Composite aggregator for smart money primitives.  Splits primitives into two ind** (4 connections) — `src\analysis\smart_money\composite.py`
- **Pick (setup_weights, trigger_weights), honoring Phase 5 calibration.** (4 connections) — `src\analysis\smart_money\composite.py`
- **Run all daily primitives over ``records`` and return bucket outputs.      Return** (4 connections) — `src\analysis\smart_money\composite.py`
- **Compute the daily smart money signal for a single symbol.      ``records`` is a** (4 connections) — `src\analysis\smart_money\composite.py`
- **Multi-timeframe smart money compute (Phase 3+).      Daily layer is always compu** (4 connections) — `src\analysis\smart_money\composite.py`
- **Weighted average over primitives, weighted by configured weight × confidence.** (4 connections) — `src\analysis\smart_money\composite.py`
- **_resolve_weights()** (4 connections) — `src\analysis\smart_money\composite.py`
- **divergence.py** (4 connections) — `src\analysis\smart_money\primitives\divergence.py`
- **.compute()** (4 connections) — `src\analysis\smart_money\primitives\divergence.py`
- **base.py** (3 connections) — `src\analysis\smart_money\primitives\base.py`
- **Protocol that every flow primitive must satisfy.** (3 connections) — `src\analysis\smart_money\primitives\base.py`
- *... and 41 more nodes in this community*

## Relationships

- No strong cross-community connections detected

## Source Files

- `src\analysis\smart_money\composite.py`
- `src\analysis\smart_money\config.py`
- `src\analysis\smart_money\narrative.py`
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

- EXTRACTED: 143 (53%)
- INFERRED: 129 (47%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*