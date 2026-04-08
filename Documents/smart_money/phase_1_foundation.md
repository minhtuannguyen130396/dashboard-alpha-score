# Phase 1 — Foundation

**Mục tiêu:** dựng abstraction đúng + 2 primitives đầu tiên (prop, foreign) + composite + tích hợp V5 scoring. Không cần data mới.

**Điều kiện tiên quyết:** không có. Phase này chạy được ngay trên data hiện tại.

## 1.1. Tạo module `src/analysis/smart_money/`

Tạo đúng skeleton theo [architecture.md](architecture.md). Các file cần có (rỗng/stub ban đầu):

- `__init__.py` — export `compute_smart_money`, `SmartMoneySignal`, `FlowPrimitive`
- `types.py`
- `normalize.py`
- `primitives/__init__.py`
- `primitives/base.py`
- `primitives/prop_flow.py`
- `primitives/foreign_flow.py`
- `composite.py`
- `narrative.py`

## 1.2. `normalize.py`

Helpers dùng chung cho tất cả primitives.

```python
def rolling_zscore(series: List[float], window: int = 60) -> float: ...
def winsorize(series: List[float], p: float = 0.02) -> List[float]: ...
def rank_to_signed(rank: float) -> float:
    """[0..1] → [-1..+1]"""
    return 2 * rank - 1
def clamp(x: float, lo: float = -1.0, hi: float = 1.0) -> float: ...
def safe_ratio(num: float, denom: float, fallback: float = 0.0) -> float: ...
```

**Quan trọng:**
- `winsorize` trước khi z-score, chống 1 block trade phá scale
- `safe_ratio` để tránh div-by-zero khắp nơi

## 1.3. `types.py`

```python
from typing import Literal

Bucket = Literal["setup", "trigger"]

@dataclass
class FlowPrimitive:
    name: str
    bucket: Bucket                # REQUIRED — "setup" hoặc "trigger"
    value: float                  # [-1..+1]
    confidence: float             # [0..1]
    components: Dict[str, float]
    reasons: List[str]

@dataclass
class SmartMoneySignal:
    # Bucket outputs — scoring engine đọc từ đây
    setup_composite: float        # [-1..+1] từ primitives bucket="setup"
    setup_confidence: float       # [0..1]
    trigger_composite: float      # [-1..+1] từ primitives bucket="trigger"
    trigger_confidence: float     # [0..1]

    # UI-only composite (weighted avg 2 bucket) — scoring không đọc
    composite: float
    confidence: float

    label: str                    # strong_bull | bull | neutral | bear | strong_bear | toxic
    is_toxic: bool
    trend: str                    # strengthening | stable | weakening
    primitives: Dict[str, FlowPrimitive]
    narrative: str
```

**Phase 1 chỉ có 2 primitives (prop, foreign) — cả hai đều `bucket="setup"`. `trigger_composite` và `trigger_confidence` sẽ = 0 cho đến khi Phase 2 thêm divergence/concentration.** Điều này là đúng và mong đợi — Phase 1 chưa tác động tới trigger_score của V5.

## 1.4. Prop flow primitive

**File:** `primitives/prop_flow.py`

Di chuyển `_score_prop_trading_v4` thành `PropFlowPrimitive`, nhưng fix các bug của V4:

### Bug cần fix
V4 hiện normalize theo `avg(|prop_net|)` 20 phiên. Sai ở chỗ: mã nào prop ít giao dịch thì `avg_abs` thấp → tín hiệu bị khuếch đại giả.

**Fix:** normalize theo `avg(priceImpactValue)` của chính mã đó (giá trị giao dịch trung bình). Prop net 10 tỷ trên mã giao dịch 1000 tỷ/ngày ≠ prop net 10 tỷ trên mã 50 tỷ/ngày.

### Logic

```python
def compute(records) -> FlowPrimitive:
    short_n, long_n = 10, 20
    prop_net = [r.propTradingNetValue or 0 for r in records]

    short_sum = sum(prop_net[-short_n:])
    long_sum = sum(prop_net[-long_n:])
    today = prop_net[-1]

    # Normalize theo traded value của chính mã
    traded_values = [r.priceImpactValue for r in records[-long_n:]]
    avg_traded = mean(traded_values) or 1.0

    short_ratio = short_sum / (avg_traded * short_n)
    long_ratio = long_sum / (avg_traded * long_n)
    today_ratio = today / avg_traded

    # Map sang [-1..+1] qua tanh hoặc clip
    value = clamp(
        0.5 * tanh(short_ratio * 20)
        + 0.3 * tanh(long_ratio * 20)
        + 0.2 * tanh(today_ratio * 20)
    )

    # Confidence: số phiên có prop data / tổng phiên
    has_data = sum(1 for v in prop_net[-long_n:] if v != 0)
    confidence = has_data / long_n

    return FlowPrimitive(
        name="prop",
        bucket="setup",
        value=value,
        confidence=confidence,
        components={
            "short_ratio": short_ratio,
            "long_ratio": long_ratio,
            "today_ratio": today_ratio,
            "short_sum": short_sum,
            "long_sum": long_sum,
        },
        reasons=[...]  # tự sinh từ components
    )
```

## 1.5. Foreign flow primitive

**File:** `primitives/foreign_flow.py`

Dùng `buyForeignValue - sellForeignValue` (value, không phải quantity — tránh skew giữa mã giá khác nhau).

### Logic tương tự prop

```python
foreign_net = [(r.buyForeignValue or 0) - (r.sellForeignValue or 0) for r in records]
# ... giống prop pattern
```

### Confidence adjustment

Nếu có data foreign room (ownership ceiling): mã đang **full room** → foreign không mua được dù muốn → confidence giảm (vì signal méo). Để field `foreign_room_confidence_factor` = 1.0 nếu chưa có data room.

## 1.6. Composite v1

**File:** `composite.py`

Composite phải sinh ra **hai output độc lập**: `setup_composite` từ primitives `bucket="setup"`, `trigger_composite` từ primitives `bucket="trigger"`. Phase 1 chỉ có setup primitives nên trigger side = 0.

```python
def compute_smart_money(records, cfg=None) -> SmartMoneySignal:
    cfg = cfg or DEFAULT_SMART_MONEY_CONFIG
    primitives: Dict[str, FlowPrimitive] = {}

    if cfg.use_prop:
        primitives["prop"] = PropFlowPrimitive().compute(records, cfg)
    if cfg.use_foreign:
        primitives["foreign"] = ForeignFlowPrimitive().compute(records, cfg)

    # Split theo bucket — assert primitive.bucket khớp class attribute
    setup_prims = {k: p for k, p in primitives.items() if p.bucket == "setup"}
    trigger_prims = {k: p for k, p in primitives.items() if p.bucket == "trigger"}

    setup_composite, setup_confidence = _aggregate_bucket(
        setup_prims, cfg.setup_weights
    )
    trigger_composite, trigger_confidence = _aggregate_bucket(
        trigger_prims, cfg.trigger_weights
    )

    # UI-only composite — weighted avg của 2 bucket, scoring KHÔNG đọc trường này
    ui_composite, ui_confidence = _ui_merge(
        setup_composite, setup_confidence,
        trigger_composite, trigger_confidence,
        cfg.ui_weight_setup, cfg.ui_weight_trigger,
    )

    label = _classify_label(ui_composite, ui_confidence)
    trend = _detect_trend(records, primitives)

    return SmartMoneySignal(
        setup_composite=setup_composite,
        setup_confidence=setup_confidence,
        trigger_composite=trigger_composite,
        trigger_confidence=trigger_confidence,
        composite=ui_composite,
        confidence=ui_confidence,
        label=label,
        is_toxic=False,    # Phase 2 sẽ fill
        trend=trend,
        primitives=primitives,
        narrative=generate_narrative(primitives, ui_composite, label),
    )


def _aggregate_bucket(
    primitives: Dict[str, FlowPrimitive],
    weights: Dict[str, float],
) -> Tuple[float, float]:
    """Weighted by configured weight × primitive.confidence."""
    if not primitives:
        return 0.0, 0.0

    total_weight = 0.0
    weighted_sum = 0.0
    for name, prim in primitives.items():
        w = weights.get(name, 0.0) * prim.confidence
        weighted_sum += prim.value * w
        total_weight += w

    if total_weight <= 0:
        return 0.0, 0.0

    composite = weighted_sum / total_weight
    # Confidence = tổng weight hiệu dụng / tổng weight cấu hình
    max_weight = sum(weights.get(n, 0.0) for n in primitives.keys())
    confidence = total_weight / max_weight if max_weight > 0 else 0.0
    return composite, confidence
```

### Runtime invariants (đưa vào test)

```python
# 1. Không primitive dùng chung 2 bucket
assert not (set(cfg.setup_weights) & set(cfg.trigger_weights)), \
    "Primitive không được có mặt ở cả 2 bucket"

# 2. Primitive.bucket khớp với bucket nó được aggregate
for name, p in primitives.items():
    if name in cfg.setup_weights:
        assert p.bucket == "setup"
    if name in cfg.trigger_weights:
        assert p.bucket == "trigger"
```

### Label thresholds

- `|composite| ≥ 0.6` và `confidence ≥ 0.5` → `strong_bull` / `strong_bear`
- `|composite| ≥ 0.3` → `bull` / `bear`
- Otherwise → `neutral`
- Phase 2 sẽ thêm `toxic`

## 1.7. Narrative generator v1

**File:** `narrative.py`

Tự sinh câu mô tả **không dùng LLM** (deterministic, cheap).

```python
def generate_narrative(primitives, composite, label) -> str:
    parts = []
    prop = primitives.get("prop")
    foreign = primitives.get("foreign")

    if prop and prop.confidence > 0.3:
        if prop.value > 0.3:
            parts.append(f"Tự doanh mua ròng mạnh ({prop.components['short_sum']/1e9:.0f} tỷ/10 phiên)")
        elif prop.value < -0.3:
            parts.append(f"Tự doanh bán ròng ({prop.components['short_sum']/1e9:.0f} tỷ/10 phiên)")

    if foreign and foreign.confidence > 0.3:
        # Tương tự

    if prop and foreign and prop.value * foreign.value > 0.09:
        parts.append("Tự doanh và khối ngoại cùng chiều")
    elif prop and foreign and prop.value * foreign.value < -0.09:
        parts.append("Tự doanh và khối ngoại ngược chiều")

    return ". ".join(parts) + "."
```

## 1.8. Tích hợp V5 scoring

**File mới:** `src/analysis/signal_scoring_v5.py` (copy V4, đổi tên).

### Thay đổi config

```python
# score_config.py
@dataclass
class ScoreWeightsV5:
    # Setup
    setup_candle:     float = 0.15
    setup_trend:      float = 0.22
    setup_momentum:   float = 0.13
    setup_volume:     float = 0.13
    setup_structure:  float = 0.17
    setup_regime:     float = 0.10
    setup_smartmoney: float = 0.10    # prop + foreign (Phase 1)

    # Trigger — giữ nguyên V4, Phase 1 chưa thêm trigger_smartmoney
    trigger_confirmation: float = 0.35
    trigger_volume:       float = 0.25
    trigger_candle:       float = 0.20
    trigger_momentum:     float = 0.10
    trigger_divergence:   float = 0.10
    trigger_smartmoney:   float = 0.00   # Phase 1: chưa có primitive trigger → để 0
```

Phase 2 sẽ bật `trigger_smartmoney` sau khi thêm divergence/concentration primitives. Phase 1 không đụng tới trigger bucket để giảm blast radius.

### Thay đổi trong `_build_score_v5`

```python
from src.analysis.smart_money import compute_smart_money

sm = compute_smart_money(records, cfg.smart_money)

# Setup bucket
if bullish:
    sm_setup_score = max(0.0, sm.setup_composite) * sm.setup_confidence
else:
    sm_setup_score = max(0.0, -sm.setup_composite) * sm.setup_confidence

# Trigger bucket (Phase 1: luôn = 0 vì chưa có primitive trigger)
if bullish:
    sm_trigger_score = max(0.0, sm.trigger_composite) * sm.trigger_confidence
else:
    sm_trigger_score = max(0.0, -sm.trigger_composite) * sm.trigger_confidence

setup_score = (
    ...
    + w.setup_smartmoney * sm_setup_score
)
trigger_score = (
    ...
    + w.trigger_smartmoney * sm_trigger_score   # = 0 trong Phase 1
)
```

**Lưu ý:** scoring engine **không bao giờ** đọc `sm.composite` hay `sm.confidence` (đó là UI-only fields). Chỉ đọc `sm.setup_*` và `sm.trigger_*`.

### Expose thông tin smart money ra `SignalScoreV5`

```python
# Tách 2 bucket để UI và debug có thể thấy đóng góp riêng:
smart_money_setup_score: float = 0.0      # sau khi nhân confidence, trước khi nhân weight
smart_money_trigger_score: float = 0.0
smart_money_setup_composite: float = 0.0  # raw [-1..+1]
smart_money_trigger_composite: float = 0.0
smart_money_confidence: float = 0.0       # UI-only merge
smart_money_label: str = "neutral"
smart_money_narrative: str = ""
```

Để app hiển thị lớp card/glance trực tiếp từ score object. Phase 1 trường `trigger_*` sẽ luôn = 0 (hợp lệ).

## 1.9. Testing

### Unit tests cần có

- `tests/test_smart_money_prop_primitive.py`
  - Mã prop mua ròng 10 ngày liên tục → value > 0.5
  - Mã không có prop data → confidence = 0
  - Mã prop mua 1 ngày siêu lớn rồi im lặng → winsorize hoạt động
- `tests/test_smart_money_foreign_primitive.py` — tương tự
- `tests/test_smart_money_composite.py`
  - Prop + foreign cùng chiều → `setup_composite` mạnh
  - Prop bull, foreign bear → `setup_composite` gần 0
  - Foreign confidence = 0 → `setup_composite` = prop value
  - `trigger_composite` = 0 và `trigger_confidence` = 0 ở Phase 1 (invariant)
  - Assert: không primitive nào có mặt ở cả `setup_weights` và `trigger_weights`
  - Assert: `primitive.bucket` khớp với bucket được aggregate vào
- `tests/test_smart_money_integration_v5.py`
  - V5 với smart money weight = 0 → giống V4 prop removed
  - V5 với smart money weight cao → score thay đổi đúng hướng

## 1.10. Backtest & validation

**Trước khi deploy:**

1. Chạy backtest `V4` vs `V5-phase1` trên cùng universe + period
2. So sánh metrics: win rate, profit factor, max drawdown, trade count
3. Chấp nhận V5 nếu: PF ≥ V4 × 1.05 **hoặc** drawdown giảm ≥ 10% mà PF không giảm > 3%

## Deliverable Phase 1

- [ ] Module `src/analysis/smart_money/` đầy đủ theo layout
- [ ] 2 primitives (prop, foreign) hoạt động + unit tests pass
- [ ] Composite v1 với confidence weighting
- [ ] Narrative generator v1
- [ ] `signal_scoring_v5.py` + `ScoreConfigV5` tích hợp smart money
- [ ] Backtest report so sánh V4 vs V5
- [ ] Updated `score_config.py` với V5 weights

## Ước lượng scope

~600-800 LOC mới (bao gồm test).
