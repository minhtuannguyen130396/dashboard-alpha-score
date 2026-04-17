# Intraday Flow Primitives

> 69 nodes · cohesion 0.06

## Summary

Các primitive intraday cho Smart Money (Phase 3+), tất cả xếp vào bucket="trigger". Gồm 5 primitive chính: **OrderFlowImbalance** (OFI — chênh lệch buy vs sell volume trong bar, composite 30min + 15min cuối ngày), **BlockTrade** (lô lớn ≥ 30× average tick — dấu hiệu tổ chức), **VWAPRelationship** (giá đóng cửa so với VWAP — vị thế xu hướng trong ngày), **AuctionFlow** (áp lực bên mua/bán trong phiên ATO/ATC), **IntradayDivergence** (giá và OFI diverge).

`TradeClassifier` phân loại từng tick thành buyer/seller-initiated theo 3 phương pháp: tick_rule (so sánh giá vs tick trước — mặc định cho VN vì hiếm có bid/ask), Lee-Ready (quote-rule + tick-rule fallback), BVC (Bulk Volume Classification — chia volume bar theo phân phối chuẩn). Community này chiếm phần lớn test coverage (Phase 3-5 tests).

## Key Concepts

- **CalibrationTest** (17 connections) — `tests\test_smart_money_phases345.py`
- **IntradayPrimitiveTest** (17 connections) — `tests\test_smart_money_phases345.py`
- **OrderFlowImbalancePrimitive** (15 connections) — `src\analysis\smart_money\primitives_intraday.py`
- **TradeClassifier** (15 connections) — `src\analysis\smart_money\tick\trade_classifier.py`
- **AuctionFlowPrimitive** (14 connections) — `src\analysis\smart_money\primitives_intraday.py`
- **BlockTradePrimitive** (14 connections) — `src\analysis\smart_money\primitives_intraday.py`
- **IntradayDivergencePrimitive** (14 connections) — `src\analysis\smart_money\primitives_intraday.py`
- **VWAPRelationshipPrimitive** (14 connections) — `src\analysis\smart_money\primitives_intraday.py`
- **IntradayFeatureCacheTest** (13 connections) — `tests\test_smart_money_phases345.py`
- **TradeClassifierTest** (13 connections) — `tests\test_smart_money_phases345.py`
- **TickStorageTest** (12 connections) — `tests\test_smart_money_phases345.py`
- **TrainingSignal** (11 connections) — `src\analysis\smart_money\calibration\weight_calibrator.py`
- **primitives_intraday.py** (10 connections) — `src\analysis\smart_money\primitives_intraday.py`
- **test_smart_money_phases345.py** (10 connections) — `tests\test_smart_money_phases345.py`
- **CompositeMTFTest** (10 connections) — `tests\test_smart_money_phases345.py`
- **FlowRecordAdapterTest** (10 connections) — `tests\test_smart_money_phases345.py`
- **run_intraday_primitives()** (8 connections) — `src\analysis\smart_money\primitives_intraday.py`
- **Tests for smart_money Phase 3-5 (FlowRecord adapter, intraday, calibration).** (8 connections) — `tests\test_smart_money_phases345.py`
- **Synthetic data: useful_feature predicts hit, others are noise.** (8 connections) — `tests\test_smart_money_phases345.py`
- **_stock_record()** (6 connections) — `tests\test_smart_money_phases345.py`
- **_make_bars()** (5 connections) — `tests\test_smart_money_phases345.py`
- **_compute_ofi_scalar()** (4 connections) — `src\analysis\smart_money\primitives_intraday.py`
- **.compute()** (4 connections) — `src\analysis\smart_money\primitives_intraday.py`
- **._synth_signals()** (4 connections) — `tests\test_smart_money_phases345.py`
- **._make_ticks()** (4 connections) — `tests\test_smart_money_phases345.py`
- *... and 44 more nodes in this community*

## Relationships

- No strong cross-community connections detected

## Source Files

- `src\analysis\smart_money\calibration\weight_calibrator.py`
- `src\analysis\smart_money\primitives_intraday.py`
- `src\analysis\smart_money\tick\trade_classifier.py`
- `tests\test_smart_money_phases345.py`

## Audit Trail

- EXTRACTED: 185 (57%)
- INFERRED: 137 (43%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*