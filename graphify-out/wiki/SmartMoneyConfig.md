# SmartMoneyConfig

> God node · 32 connections · `src\analysis\smart_money\config.py`

## What It Is

Dataclass duy nhất kiểm soát toàn bộ hành vi của hệ thống Smart Money. Được truyền vào `compute_smart_money()` và phân phối xuống tất cả các lớp.

**Ba tầng cấu hình:**

1. **Feature flags theo phase** — bật/tắt từng primitive: `use_prop`, `use_foreign` (Phase 1), `use_divergence`, `use_concentration`, `use_persistence`, `use_toxic_flow` (Phase 2), `use_intraday`, `use_ofi`, `use_block_trades`... (Phase 3+). Khi một primitive bị tắt, nó không xuất hiện trong bucket → `_aggregate_bucket` tự rebalance trọng số còn lại.

2. **Bucket weights** — `setup_weights` (chỉ primitives có `bucket="setup"`) và `trigger_weights` (chỉ `bucket="trigger"`). Phase 5 calibration có thể override bằng weights học từ dữ liệu.

3. **Calibration mode** (Phase 5) — `use_calibrated_weights`, `use_regime_weights`, `use_symbol_class_weights`. Khi tắt, dùng weights tĩnh ở trên.

**Lưu ý:** `weight_daily` / `weight_intraday` và UI weights merge không được scoring engine đọc — chỉ dùng cho display.

## Connections by Relation

### contains
- [[config.py]] `EXTRACTED`

### uses
- [[OrderFlowImbalancePrimitive]] `INFERRED`
- [[BlockTradePrimitive]] `INFERRED`
- [[VWAPRelationshipPrimitive]] `INFERRED`
- [[AuctionFlowPrimitive]] `INFERRED`
- [[IntradayDivergencePrimitive]] `INFERRED`
- [[Tick-level helpers (Phase 4): trade classification + feature cache.  The intrada]] `INFERRED`
- [[Primitive]] `INFERRED`
- [[ConcentrationPrimitive]] `INFERRED`
- [[DivergencePrimitive]] `INFERRED`
- [[ForeignFlowPrimitive]] `INFERRED`
- [[PropFlowPrimitive]] `INFERRED`
- [[Composite aggregator for smart money primitives.  Splits primitives into two ind]] `INFERRED`
- [[Weighted average over primitives, weighted by configured weight × confidence.]] `INFERRED`
- [[Pick (setup_weights, trigger_weights), honoring Phase 5 calibration.]] `INFERRED`
- [[Run all daily primitives over ``records`` and return bucket outputs.      Return]] `INFERRED`
- [[Compute the daily smart money signal for a single symbol.      ``records`` is a]] `INFERRED`
- [[Multi-timeframe smart money compute (Phase 3+).      Daily layer is always compu]] `INFERRED`
- [[PersistenceDetector]] `INFERRED`
- [[Intraday flow primitives (Phase 4) — all bucket="trigger".  Each primitive consu]] `INFERRED`
- [[Composite OFI: 0.4 × rolling-30min OFI + 0.6 × end-of-day 15-min OFI.]] `INFERRED`

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*