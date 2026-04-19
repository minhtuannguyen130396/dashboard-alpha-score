# FlowPrimitive

> God node · 35 connections · `src\analysis\smart_money\types.py`

## What It Is

Dataclass cốt lõi của toàn bộ hệ thống Smart Money — là "atom" mà mọi primitive đều trả về.

```python
@dataclass
class FlowPrimitive:
    name: str
    bucket: Bucket          # "setup" | "trigger"
    value: float            # [-1..+1]  âm=bearish, dương=bullish
    confidence: float       # [0..1]    độ tin cậy của tín hiệu
    components: Dict[str, float]   # chi tiết từng thành phần (cho UI/debug)
    reasons: List[str]             # text giải thích (cho hover panel)
```

**Tại sao là god node:** Mọi primitive (PropFlow, ForeignFlow, OFI, BlockTrade, Divergence...) đều tạo ra `FlowPrimitive`. Composite aggregator chỉ đọc `bucket + value + confidence` để tổng hợp — không biết gì về logic bên trong primitive. Đây là interface contract giữa các primitives và engine tổng hợp.

**Invariant quan trọng:** `bucket` phải được set đúng trong primitive (không đổi sau khi tạo). Scoring engine đọc `setup_composite` / `trigger_composite` của `SmartMoneySignal` — không đọc merged `composite` (UI-only).

## Connections by Relation

### contains
- [[types.py]] `EXTRACTED`

### uses
- [[OrderFlowImbalancePrimitive]] `INFERRED`
- [[BlockTradePrimitive]] `INFERRED`
- [[VWAPRelationshipPrimitive]] `INFERRED`
- [[AuctionFlowPrimitive]] `INFERRED`
- [[IntradayDivergencePrimitive]] `INFERRED`
- [[Phase2Test]] `INFERRED`
- [[CompositeTest]] `INFERRED`
- [[Tick-level helpers (Phase 4): trade classification + feature cache.  The intrada]] `INFERRED`
- [[Primitive]] `INFERRED`
- [[NormalizeTest]] `INFERRED`
- [[PropPrimitiveTest]] `INFERRED`
- [[ConcentrationPrimitive]] `INFERRED`
- [[DivergencePrimitive]] `INFERRED`
- [[ForeignFlowPrimitive]] `INFERRED`
- [[PropFlowPrimitive]] `INFERRED`
- [[Composite aggregator for smart money primitives.  Splits primitives into two ind]] `INFERRED`
- [[Weighted average over primitives, weighted by configured weight × confidence.]] `INFERRED`
- [[Pick (setup_weights, trigger_weights), honoring Phase 5 calibration.]] `INFERRED`
- [[Run all daily primitives over ``records`` and return bucket outputs.      Return]] `INFERRED`
- [[Compute the daily smart money signal for a single symbol.      ``records`` is a]] `INFERRED`

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*