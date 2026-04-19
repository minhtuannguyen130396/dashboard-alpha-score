# Architecture — Gộp hay Tách?

## Quyết định: Gộp vào app, tách module trong cùng repo

### Vì sao gộp

1. **Smart money không đứng một mình.** Chỉ có giá trị khi kết hợp với price action, volume, structure. Tách = user phải tra cứu 2 nơi rồi mental merge.
2. **Data chung.** Cùng `StockRecord`, cùng loader, cùng pipeline backtest. Tách = duplicate hoặc cross-repo import.
3. **Backtest cần chung environment.** Muốn đo "smart money có cải thiện PF không" phải chạy trong cùng simulator.
4. **Maintenance 1 repo rẻ hơn 2.**

### Khi nào mới tách (hiện tại chưa)

- Smart money module có user base riêng (bán API flow data)
- Tick data pipeline quá nặng (storage TB, Kafka) làm app chậm khởi động
- Team khác maintain, release cycle khác

## Module layout

```
src/
  analysis/
    smart_money/              ← module độc lập về mặt logic
      __init__.py             ← export public API
      types.py                ← FlowPrimitive, SmartMoneySignal dataclasses
      normalize.py            ← z-score, winsorize, rank helpers
      primitives/
        __init__.py
        base.py               ← Primitive protocol
        prop_flow.py          ← Tự doanh primitive
        foreign_flow.py       ← Khối ngoại primitive
        divergence.py         ← Phase 2
        concentration.py      ← Phase 2
        persistence.py        ← Phase 2
        toxic_flow.py         ← Phase 2 (penalty-type)
        # Phase 4:
        block_trade.py
        order_flow_imbalance.py
        vwap_relationship.py
        auction_flow.py
      composite.py            ← Aggregator với confidence weighting
      narrative.py            ← Tự sinh câu mô tả cho UI
    signal_scoring_v5.py      ← Import smart_money, không chứa logic flow
    score_config.py           ← ScoreConfigV5 có setup_smartmoney weight
```

### Nguyên tắc module boundary

- `smart_money/` **không** import từ `signal_scoring_*`. Một chiều: scoring → smart_money.
- `smart_money/` chạy độc lập: `compute_smart_money(records)` trả `SmartMoneySignal` đầy đủ mà không cần biết gì về V5 scoring.
- Có CLI/notebook inspect smart money cho 1 mã mà không cần chạy scoring.
- Logic **tách**, deployment **gộp**.

## Public API contract

```python
from src.analysis.smart_money import (
    compute_smart_money,
    SmartMoneySignal,
    FlowPrimitive,
)

signal: SmartMoneySignal = compute_smart_money(records, config=None)

# SmartMoneySignal có gì:
signal.setup_composite    # float [-1..+1] — dùng trong setup_score
signal.setup_confidence   # float [0..1]
signal.trigger_composite  # float [-1..+1] — dùng trong trigger_score
signal.trigger_confidence # float [0..1]
signal.composite          # float [-1..+1] — weighted avg 2 bucket, CHỈ cho UI/display
signal.confidence         # float [0..1]  — CHỈ cho UI/display
signal.label              # "strong_bull" | "bull" | "neutral" | "bear" | "strong_bear" | "toxic"
signal.is_toxic           # bool — giá và flow lệch pha mạnh (hard blocker, không vào bucket)
signal.trend              # "strengthening" | "stable" | "weakening"
signal.primitives         # Dict[str, FlowPrimitive]
signal.narrative          # str — câu mô tả tự sinh cho UI
```

**Quy tắc cứng về bucket (chốt một lần, không đổi):**

- `setup_composite` và `trigger_composite` là **hai kênh tách biệt**. Scoring V5 map `setup_composite` vào `setup_score`, `trigger_composite` vào `trigger_score`. **Không bao giờ** cộng cùng 1 primitive vào cả hai bucket.
- Trường `composite` ở top-level chỉ phục vụ UI (hiển thị 1 con số tổng). Scoring engine **không được đọc** trường này.
- `is_toxic` là **hard blocker**, không phải primitive đóng điểm. Không chiếm slot bucket nào.
- `persistence` không phải primitive đóng điểm — là **confidence multiplier** áp lên setup bucket (xem Phase 2).

## FlowPrimitive contract

```python
from typing import Literal

Bucket = Literal["setup", "trigger"]

@dataclass
class FlowPrimitive:
    name: str                     # "prop", "foreign", "divergence", ...
    bucket: Bucket                # "setup" hoặc "trigger" — KHÔNG optional
    value: float                  # [-1..+1], dấu = hướng, độ lớn = độ mạnh
    confidence: float             # [0..1], đủ data để tin không
    components: Dict[str, float]  # sub-metrics để debug (prop_5d, prop_10d, ...)
    reasons: List[str]            # human-readable, vd "prop accumulating 8/10 days"
```

### Bucket assignment table (chốt)

| Primitive | Bucket | Lý do |
|---|---|---|
| `prop` | `setup` | Flow tích luỹ 10-20 phiên = điều kiện nền |
| `foreign` | `setup` | Tương tự prop |
| `divergence` | `trigger` | Leading signal về đảo chiều — hành động ngày mai |
| `concentration` | `trigger` | "Load-up day" = sự kiện xảy ra hôm nay |
| `persistence` | *(multiplier)* | Không đóng điểm, scale confidence của setup |
| `toxic_flow` | *(blocker)* | Hard blocker, không đóng điểm |
| `ofi` (Phase 4) | `trigger` | Intraday order flow của phiên hôm nay |
| `block_trade` (Phase 4) | `trigger` | Event-based, hôm nay |
| `vwap_relationship` (Phase 4) | `trigger` | Intraday position, hôm nay |
| `auction_flow` (Phase 4) | `trigger` | ATO/ATC của phiên hôm nay |
| `intraday_divergence` (Phase 4) | `trigger` | Divergence trong phiên |
| `cross_section` (Phase 2, optional) | `setup` | Vị thế tương đối so với sector |

Nếu sau này thêm primitive mới, **phải khai báo bucket trong bảng này** trước khi implement.

### Protocol mỗi primitive phải implement

```python
class Primitive(Protocol):
    name: str
    bucket: Bucket                      # class-level attribute, immutable
    def compute(self, records: List[FlowRecord], cfg: SmartMoneyConfig) -> FlowPrimitive: ...
    def min_records(self) -> int: ...   # số bar tối thiểu, composite skip nếu thiếu
```

Primitive sinh ra `FlowPrimitive` phải set `bucket` trùng với class attribute (composite assert điều này khi aggregate).

## Config

```python
@dataclass
class SmartMoneyConfig:
    # Primitives bật/tắt
    use_prop: bool = True
    use_foreign: bool = True
    use_divergence: bool = False        # Phase 2
    use_concentration: bool = False     # Phase 2
    use_persistence: bool = False       # Phase 2
    use_toxic_flow: bool = False        # Phase 2

    # Weights trong setup bucket (renormalize theo confidence runtime,
    # chỉ primitive có bucket="setup" được phép có mặt ở đây)
    setup_weights: Dict[str, float] = field(default_factory=lambda: {
        "prop": 0.50,
        "foreign": 0.50,
        # Phase 2+: "cross_section": 0.20 (rebalance lại nếu bật)
    })

    # Weights trong trigger bucket
    trigger_weights: Dict[str, float] = field(default_factory=lambda: {
        "divergence": 0.50,       # Phase 2
        "concentration": 0.50,    # Phase 2
        # Phase 4: "ofi": 0.30, "block_trade": 0.25, "vwap": 0.15,
        #         "auction": 0.15, "intraday_divergence": 0.15
    })

    # Weight giữa 2 bucket chỉ dùng để tính UI-only signal.composite.
    # Scoring engine KHÔNG dùng 2 con này — nó map setup/trigger vào
    # setup_score/trigger_score của V5 qua setup_smartmoney / trigger_smartmoney.
    ui_weight_setup: float = 0.6
    ui_weight_trigger: float = 0.4

    # Windows
    short_window: int = 10
    long_window: int = 20
    normalize_window: int = 60

    # Toxic detection
    toxic_price_change_threshold: float = 0.03
    toxic_flow_opposite_threshold: float = -0.3
```

## Tích hợp với V5 scoring

`ScoreWeightsV5` có **hai** field smart money, không phải một:

```python
@dataclass
class ScoreWeightsV5:
    # Setup bucket
    setup_candle:     float = 0.15
    setup_trend:      float = 0.22
    setup_momentum:   float = 0.13
    setup_volume:     float = 0.13
    setup_structure:  float = 0.17
    setup_regime:     float = 0.10
    setup_smartmoney: float = 0.10    # ← prop + foreign (+ cross_section)

    # Trigger bucket
    trigger_confirmation: float = 0.30
    trigger_volume:       float = 0.20
    trigger_candle:       float = 0.15
    trigger_momentum:     float = 0.10
    trigger_divergence:   float = 0.10    # price/indicator divergence của V4 (giữ)
    trigger_smartmoney:   float = 0.15    # ← divergence + concentration (+ Phase 4 intraday)
```

`signal_scoring_v5._build_score_v5` gọi `compute_smart_money(records)` **một lần**, map **hai** output vào **hai** bucket:

```python
sm = compute_smart_money(records, cfg.smart_money)

# Setup bucket
if bullish:
    sm_setup_score = max(0.0, sm.setup_composite) * sm.setup_confidence
else:
    sm_setup_score = max(0.0, -sm.setup_composite) * sm.setup_confidence

# Trigger bucket — tách biệt hoàn toàn
if bullish:
    sm_trigger_score = max(0.0, sm.trigger_composite) * sm.trigger_confidence
else:
    sm_trigger_score = max(0.0, -sm.trigger_composite) * sm.trigger_confidence

setup_score += w.setup_smartmoney * sm_setup_score
trigger_score += w.trigger_smartmoney * sm_trigger_score

# Toxic flow — hard blocker, không bao giờ cộng điểm
if sm.is_toxic and bullish:
    blockers.append(Blocker("toxic_flow", "hard", "retail FOMO, smart money exiting"))
```

**Invariant phải assert trong test:**
1. Không primitive nào xuất hiện trong cả `setup_weights` và `trigger_weights`.
2. `setup_composite` chỉ aggregate từ primitives có `bucket="setup"`.
3. `trigger_composite` chỉ aggregate từ primitives có `bucket="trigger"`.
4. Tổng scoring weight smart money (`setup_smartmoney + trigger_smartmoney`) ≤ 0.25 để tránh overweight.

## Testing strategy

- Unit tests mỗi primitive độc lập với fixture `StockRecord` giả
- Confidence calculation tests (missing data, partial data)
- Composite tests — đảm bảo rebalance khi 1 primitive confidence = 0
- Integration test: V5 scoring với smart money vs V4 trên cùng 1 dataset nhỏ

## Migration từ V4

V4 hiện có `_score_prop_trading_v4` inline. Kế hoạch:

1. Tạo `smart_money/primitives/prop_flow.py` kế thừa logic V4 nhưng fix bug normalize (dùng `priceImpactValue` thay vì `avg_abs`)
2. Giữ V4 nguyên vẹn — V5 là file mới `signal_scoring_v5.py`
3. App cho phép chọn engine V4 hoặc V5 qua config để A/B test
4. Sau khi backtest xác nhận V5 ≥ V4, depreciate V4
