# Smart Money Tests

> 38 nodes · cohesion 0.08

## Summary

Test suite cho Smart Money Phase 1-2 (`tests/test_smart_money.py`). `_mk_record()` là factory tạo synthetic `StockRecord` dùng chung trong tất cả test cases — node kết nối nhiều nhất vì mọi test đều gọi nó.

**Bao phủ:** PropPrimitiveTest (prop flow direction), ForeignPrimitiveTest (zero confidence khi no foreign activity), NormalizeTest (normalize helpers), CompositeTest (bucket aggregation, opposing signals cancel, disabled phase2 = no trigger), Phase2Test (divergence, concentration, persistence multiplier, toxic flow detection), IntegrationV5Test (end-to-end V5 run + warmup). Test suite cho Phase 3-5 (intraday, calibration) nằm trong community [[Intraday Flow Primitives]].

## Key Concepts

- **_mk_record()** (22 connections) — `tests\test_smart_money.py`
- **Phase2Test** (11 connections) — `tests\test_smart_money.py`
- **CompositeTest** (10 connections) — `tests\test_smart_money.py`
- **test_smart_money.py** (8 connections) — `tests\test_smart_money.py`
- **NormalizeTest** (6 connections) — `tests\test_smart_money.py`
- **PropPrimitiveTest** (6 connections) — `tests\test_smart_money.py`
- **ForeignPrimitiveTest** (4 connections) — `tests\test_smart_money.py`
- **IntegrationV5Test** (4 connections) — `tests\test_smart_money.py`
- **.test_label_classification()** (2 connections) — `tests\test_smart_money.py`
- **.test_opposite_signs_cancel()** (2 connections) — `tests\test_smart_money.py`
- **.test_primitive_bucket_matches_class_attribute()** (2 connections) — `tests\test_smart_money.py`
- **.test_trigger_zero_when_phase2_disabled()** (2 connections) — `tests\test_smart_money.py`
- **.test_buy_dominates()** (2 connections) — `tests\test_smart_money.py`
- **.test_no_foreign_activity_zero_confidence()** (2 connections) — `tests\test_smart_money.py`
- **.test_v5_runs_end_to_end()** (2 connections) — `tests\test_smart_money.py`
- **.test_v5_warmup()** (2 connections) — `tests\test_smart_money.py`
- **.test_concentration_load_up_day()** (2 connections) — `tests\test_smart_money.py`
- **.test_concentration_no_signal_low_rvol()** (2 connections) — `tests\test_smart_money.py`
- **.test_persistence_high_when_consistent()** (2 connections) — `tests\test_smart_money.py`
- **.test_persistence_low_when_noisy()** (2 connections) — `tests\test_smart_money.py`
- **.test_persistence_multiplier_lowers_setup_confidence()** (2 connections) — `tests\test_smart_money.py`
- **.test_phase2_disabled_matches_phase1_setup()** (2 connections) — `tests\test_smart_money.py`
- **.test_toxic_flow_detection()** (2 connections) — `tests\test_smart_money.py`
- **.test_toxic_flow_not_triggered_normal()** (2 connections) — `tests\test_smart_money.py`
- **.test_toxic_label_overrides()** (2 connections) — `tests\test_smart_money.py`
- *... and 13 more nodes in this community*

## Relationships

- No strong cross-community connections detected

## Source Files

- `tests\test_smart_money.py`

## Audit Trail

- EXTRACTED: 116 (94%)
- INFERRED: 7 (6%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*