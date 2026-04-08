# Phase 2 — Nâng chất lượng primitives daily

**Mục tiêu:** vẫn chỉ dùng daily data, nhưng khai thác sâu hơn. Thêm 4 primitives mới + toxic flow detection. **Đây là phase đầu tiên bật `trigger_smartmoney` > 0.**

**Điều kiện tiên quyết:** Phase 1 done, backtest xác nhận Phase 1 ≥ V4.

## Bucket assignment (chốt một lần cho Phase 2)

Tất cả primitive Phase 2 **phải khai báo `bucket`** ở class level, composite sẽ dispatch đúng bucket:

| Primitive | `bucket` | Ghi chú |
|---|---|---|
| `divergence` | `trigger` | Leading signal, đóng góp vào `trigger_smartmoney` |
| `concentration` | `trigger` | Load-up day là sự kiện hôm nay |
| `persistence` | *(không phải bucket — là multiplier)* | Scale `setup_confidence`, không đóng điểm |
| `toxic_flow` | *(không phải bucket — là blocker)* | Hard blocker, bypass toàn bộ bucket aggregation |
| `cross_section` (optional) | `setup` | Nếu bật, vào setup bucket cùng prop/foreign |

Phase 2 **không** thêm primitive bucket `setup` mới (trừ cross_section nếu bật). Setup bucket vẫn giữ prop + foreign như Phase 1, chỉ được scale bởi persistence multiplier.

## 2.1. Divergence primitive

**File:** `primitives/divergence.py`

**Ý tưởng:** giá và smart money lệch pha = tín hiệu đảo chiều sớm (leading indicator).

### Logic bullish divergence
- Giá tạo lower low trong 20 phiên
- Cumulative `(prop_net + foreign_net)` tạo higher low trong cùng window
- → Smart money âm thầm gom khi retail bán ra

### Logic bearish divergence
- Giá tạo higher high
- Cumulative flow tạo lower high
- → Smart money đang xả khi giá vẫn còn đẩy

### Output
- `value` = độ mạnh divergence (magnitude-weighted, không binary):
  ```
  price_delta_pct = (price_pivot_2 - price_pivot_1) / price_pivot_1
  flow_delta_norm = (flow_pivot_2 - flow_pivot_1) / avg_traded_value
  divergence_strength = clamp(flow_delta_norm - price_delta_pct, -1, 1)
  ```
- `confidence` = phụ thuộc có đủ pivot rõ ràng không. Nếu giá đi ngang → confidence thấp.

### Ghi chú quan trọng
- `DivergencePrimitive.bucket = "trigger"` — composite tự động map vào `trigger_composite`, scoring engine map tiếp vào `trigger_score` qua `w.trigger_smartmoney`. **Không** đi vào `setup_score`.
- Primitive class phải set `bucket = "trigger"` ở class-level, và `FlowPrimitive` trả ra cũng phải có `bucket="trigger"`.
- Kiểm tra false positive: divergence chỉ valid khi có ít nhất 8-10 phiên giữa 2 pivot.

## 2.2. Concentration primitive

**File:** `primitives/concentration.py`

**Ý tưởng:** 1 ngày smart money đánh chiếm tỷ trọng lớn của tổng flow → "load-up day" = dấu hiệu institutional entry.

### Logic

```python
flow_series = [prop_net[i] + foreign_net[i] for i in range(long_window)]
today_flow = flow_series[-1]
total_abs = sum(abs(f) for f in flow_series)

concentration_ratio = abs(today_flow) / total_abs if total_abs > 0 else 0

# Chỉ có ý nghĩa khi kết hợp với giá + volume
is_load_up = (
    concentration_ratio >= 0.25       # chiếm ≥ 25% tổng 20 phiên
    and today_flow > 0                # hướng accumulate
    and records[-1].priceClose > records[-1].priceOpen  # giá xanh
    and rvol_today >= 1.3             # volume cao
)
```

### Output
- `bucket = "trigger"` — đi vào `trigger_composite`
- `value` dương nếu load-up bull, âm nếu load-down bear
- `confidence` = `concentration_ratio` (càng tập trung càng tin)

### Cảnh báo
Concentration **không có giá trị riêng** — nó khuếch đại tín hiệu khác. Nếu flow concentration cao nhưng giá đỏ và volume thấp → có thể là prop thoái vốn chứ không phải gom. Kết hợp rule `is_load_up` phía trên.

## 2.3. Persistence primitive

**File:** `primitives/persistence.py`

**Ý tưởng:** % số ngày smart money cùng chiều trong 20 phiên. Flow ổn định = niềm tin; nhiễu = noise.

### Logic

```python
combined = [prop_net[i] + foreign_net[i] for i in range(20)]
positive_days = sum(1 for x in combined if x > 0)
negative_days = sum(1 for x in combined if x < 0)
net_days = positive_days - negative_days

persistence = net_days / 20  # [-1..+1]
```

### Cách dùng — đã chốt: multiplier cho setup bucket

Persistence **không phải primitive đóng điểm** — nó không có `bucket`. Implementation trả về một dataclass riêng (`PersistenceSignal`), không phải `FlowPrimitive`, để composite không nhầm lẫn aggregate nó vào bucket nào.

```python
# types.py
@dataclass
class PersistenceSignal:
    value: float               # [-1..+1]
    confidence: float
    components: Dict[str, float]

# composite.py
def compute_smart_money(records, cfg):
    setup_prims = {...}
    trigger_prims = {...}

    setup_composite, setup_confidence = _aggregate_bucket(setup_prims, cfg.setup_weights)
    trigger_composite, trigger_confidence = _aggregate_bucket(trigger_prims, cfg.trigger_weights)

    if cfg.use_persistence:
        persistence = PersistenceDetector().compute(records, cfg)
        # Multiplier CHỈ áp lên setup_confidence — persistence đo sự ổn định flow
        # dài hạn, chỉ có nghĩa với setup bucket
        persistence_factor = 0.5 + 0.5 * abs(persistence.value)  # [0.5..1.0]
        setup_confidence *= persistence_factor
```

Flow dao động (persistence gần 0) → `setup_confidence` giảm xuống 0.5×, setup bucket của smart money đóng ít vào score. Flow nhất quán (|persistence| gần 1) → giữ nguyên.

### Quyết định chốt
Persistence **không** được dùng như một option component điểm. Lý do: nếu làm vậy sẽ cần gán `bucket`, nhưng persistence 20 phiên không phải event trigger hôm nay → buộc phải vào setup bucket → trùng ý nghĩa với prop/foreign đã có → double-counting. Dùng làm multiplier là nhất quán nhất.

## 2.4. Toxic flow detection

**File:** `primitives/toxic_flow.py`

**Đây là primitive quan trọng nhất của Phase 2.** Case: "retail FOMO, smart money thoát".

### Logic bullish toxic (= toxic cho bullish signal)

```python
price_change_5d = (close[-1] - close[-6]) / close[-6]
smart_money_5d = sum(prop_net[-5:]) + sum(foreign_net[-5:])
smart_money_normalized = smart_money_5d / (avg_traded * 5)

# Giá tăng mạnh (retail FOMO) nhưng smart money bán ròng
is_toxic_bullish = (
    price_change_5d > 0.03                # giá +3% trong 5 ngày
    and smart_money_normalized < -0.3     # smart money bán ròng mạnh
)
```

### Logic bearish toxic
Giá giảm mạnh nhưng smart money mua ròng → thường là đáy (có thể là setup bullish tốt, không phải toxic).

### Hành động

Toxic **không phải component điểm** và **không có `bucket`**. Nó bypass toàn bộ bucket aggregation. Composite chỉ set `signal.is_toxic = True`. Scoring engine dùng flag này để append hard blocker:

```python
# trong signal_scoring_v5._build_score_v5
if sm.is_toxic and bullish:
    blockers.append(Blocker(
        "toxic_flow",
        "hard",
        "Price rising but smart money exiting — likely retail trap"
    ))
```

Tách biệt rõ ràng: toxic **không giảm `setup_composite` hoặc `trigger_composite`** (để trường hợp V5 tắt blocker thì các giá trị bucket vẫn intact). Toxic chỉ là một output flag riêng.

### Hiển thị
Toxic mã **phải nổi bật đỏ** trong UI (xem `ui_display_guide.md` lớp 1).

## 2.5. Cross-section normalize (optional)

**File:** `primitives/cross_section.py`

**Ý tưởng:** Z-score flow của mã so với **sector** cùng phiên. Mã có smart money inflow mạnh nhất sector = signal ưu tiên.

### Điều kiện
- Cần mapping mã → sector. Nếu chưa có → skip Phase 2, để sau.

### Logic

```python
sector_flows = {}
for symbol in sector_members:
    flow = compute_combined_flow(load_records(symbol))
    sector_flows[symbol] = flow

mean_flow = mean(sector_flows.values())
std_flow = stdev(sector_flows.values())
my_zscore = (sector_flows[target] - mean_flow) / std_flow

cross_section_score = clamp(tanh(my_zscore), -1, 1)
```

### Cảnh báo
Sector normalize đòi hỏi load toàn bộ sector mỗi lần scoring 1 mã. Nên **pre-compute** cho toàn bộ universe theo batch ở đầu pipeline, cache vào dict `{symbol: cross_section_score}`.

## 2.6. Update composite.py

```python
def compute_smart_money(records, cfg):
    primitives: Dict[str, FlowPrimitive] = {}

    # Phase 1 primitives — bucket="setup"
    primitives["prop"] = PropFlowPrimitive().compute(records, cfg)
    primitives["foreign"] = ForeignFlowPrimitive().compute(records, cfg)

    # Phase 2 primitives — bucket="trigger"
    if cfg.use_divergence:
        primitives["divergence"] = DivergencePrimitive().compute(records, cfg)
    if cfg.use_concentration:
        primitives["concentration"] = ConcentrationPrimitive().compute(records, cfg)

    # Split theo bucket — source of truth là primitive.bucket, không phải tên
    setup_prims = {k: p for k, p in primitives.items() if p.bucket == "setup"}
    trigger_prims = {k: p for k, p in primitives.items() if p.bucket == "trigger"}

    setup_composite, setup_confidence = _aggregate_bucket(setup_prims, cfg.setup_weights)
    trigger_composite, trigger_confidence = _aggregate_bucket(trigger_prims, cfg.trigger_weights)

    # Persistence = multiplier CHỈ cho setup_confidence (không phải primitive,
    # không vào bucket nào)
    if cfg.use_persistence:
        persistence = PersistenceDetector().compute(records, cfg)
        setup_confidence *= (0.5 + 0.5 * abs(persistence.value))

    # Toxic = hard flag, không modify composite/confidence
    is_toxic = False
    if cfg.use_toxic_flow:
        is_toxic = ToxicFlowDetector().detect(records, primitives)

    # UI-only merge cho display
    ui_composite, ui_confidence = _ui_merge(
        setup_composite, setup_confidence,
        trigger_composite, trigger_confidence,
        cfg.ui_weight_setup, cfg.ui_weight_trigger,
    )

    # Label: toxic overrides
    label = "toxic" if is_toxic else _classify_label(ui_composite, ui_confidence)

    return SmartMoneySignal(
        setup_composite=setup_composite,
        setup_confidence=setup_confidence,
        trigger_composite=trigger_composite,
        trigger_confidence=trigger_confidence,
        composite=ui_composite,
        confidence=ui_confidence,
        label=label,
        is_toxic=is_toxic,
        trend=_detect_trend(records, primitives),
        primitives=primitives,
        narrative=generate_narrative(primitives, ui_composite, label, is_toxic),
    )
```

### V5 scoring weight update cho Phase 2

Phase 2 bật `trigger_smartmoney` > 0. Cần rebalance trigger weights của V5:

```python
# score_config.py sau khi Phase 2 ship
@dataclass
class ScoreWeightsV5:
    # Setup — giữ nguyên từ Phase 1
    setup_smartmoney: float = 0.10

    # Trigger — rebalance để tổng = 1.0
    trigger_confirmation: float = 0.30   # 0.35 → 0.30
    trigger_volume:       float = 0.22   # 0.25 → 0.22
    trigger_candle:       float = 0.18   # 0.20 → 0.18
    trigger_momentum:     float = 0.08   # 0.10 → 0.08
    trigger_divergence:   float = 0.10   # price/indicator div của V4, giữ
    trigger_smartmoney:   float = 0.12   # 0 → 0.12
```

**Quan trọng:** `trigger_divergence` (V4 — price vs RSI/MACD/OBV) khác với `trigger_smartmoney` (Phase 2 — price vs prop/foreign flow). Đây là hai tín hiệu khác nhau, không trùng, giữ cả hai.

## 2.7. Testing

- `test_divergence_primitive.py`
  - Fixture: giá lower low + flow higher low → value > 0.3
  - Fixture: giá và flow cùng hướng → value ≈ 0
- `test_concentration_primitive.py`
  - 1 ngày chiếm 40% tổng flow, giá xanh, volume cao → is_load_up = True
- `test_persistence_primitive.py`
  - 18/20 ngày cùng chiều → value ≈ 0.8
- `test_toxic_flow.py`
  - Giá +5%, smart money -40% → is_toxic = True
  - Giá +5%, smart money +10% → is_toxic = False
- `test_composite_phase2.py`
  - Persistence thấp → **setup_confidence** giảm (không phải trigger_confidence, không phải ui_confidence trực tiếp)
  - Toxic flag → label = "toxic", `setup_composite` và `trigger_composite` giữ nguyên giá trị (không bị zero-out)
  - Invariant: `divergence` và `concentration` chỉ xuất hiện trong `cfg.trigger_weights`, không có trong `cfg.setup_weights`
  - Invariant: `prop` và `foreign` chỉ xuất hiện trong `cfg.setup_weights`
  - Regression test Phase 1: tắt toàn bộ Phase 2 features (`use_divergence=False`, etc.) → output phải giống hệt Phase 1 (byte-for-byte trên các trường setup_*)
  - `trigger_composite` chỉ ≠ 0 khi ít nhất một trong `use_divergence`/`use_concentration` được bật

## 2.8. Backtest checkpoint

Sau Phase 2, chạy lại backtest:
- V4 vs V5-phase1 vs V5-phase2
- Metric đặc biệt: **số toxic trade bị block** (giảm drawdown bao nhiêu?)
- Nếu toxic detection block ≥ 5% tổng trade và drawdown cải thiện ≥ 10% → keep
- Nếu block nhưng PF giảm → tune threshold cao hơn (conservative hơn)

## Deliverable Phase 2

- [ ] `divergence.py` primitive + tests
- [ ] `concentration.py` primitive + tests
- [ ] `persistence.py` primitive + tests
- [ ] `toxic_flow.py` detector + tests (hard blocker integration)
- [ ] Updated `composite.py` với persistence multiplier + toxic label
- [ ] Updated narrative generator để mention toxic/divergence/concentration
- [ ] Backtest report Phase 1 vs Phase 2

## Ước lượng scope

~500-700 LOC thêm (bao gồm test).
