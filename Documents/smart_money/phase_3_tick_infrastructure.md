# Phase 3 — Hạ tầng cho tick data

**Mục tiêu:** refactor abstraction để Phase 4 chỉ cần plug primitives mới, không phải viết lại. **Không thêm logic scoring mới.**

**Điều kiện tiên quyết:** Phase 2 done.

**Lý do quan trọng:** skip phase này sẽ khiến Phase 4 đau đớn. Tick data bar-size khác daily, khối lượng gấp 1000x. Nếu primitives hard-code `List[StockRecord]` daily, phải viết lại toàn bộ.

## 3.1. Abstract `FlowSource`

**File mới:** `src/data/flow_source.py`

```python
from typing import Protocol, Optional
from datetime import date

class FlowSource(Protocol):
    """Nguồn data flow, agnostic về bar-size."""

    def get_daily_flow(self, symbol: str, start: date, end: date) -> List[DailyFlowRecord]:
        ...

    def get_intraday_flow(
        self, symbol: str, day: date, bar_size: str = "1m"
    ) -> Optional[List[IntradayFlowRecord]]:
        """Return None nếu source không hỗ trợ intraday."""
        ...

    def supports_intraday(self) -> bool: ...
```

### Implementations

- `DailyFlowSource` — wrap `StockDataLoader` hiện tại, `supports_intraday() = False`
- `TickFlowSource` — Phase 4 sẽ viết, đọc từ parquet tick storage

## 3.2. Unified record types

**File:** `src/data/flow_records.py`

```python
@dataclass
class DailyFlowRecord:
    date: date
    close: float
    volume: float
    traded_value: float              # = priceImpactValue
    prop_net_value: Optional[float]
    foreign_buy_value: Optional[float]
    foreign_sell_value: Optional[float]
    # fields cần cho primitives

@dataclass
class IntradayFlowRecord:
    timestamp: datetime
    bar_size: str                    # "1m", "5m", "15m", ...
    open: float
    high: float
    low: float
    close: float
    volume: float
    traded_value: float
    # Tick-derived fields (None nếu data không đủ):
    buy_volume: Optional[float]      # classified via Lee-Ready / tick rule
    sell_volume: Optional[float]
    block_buy_count: Optional[int]
    block_sell_count: Optional[int]
    vwap: Optional[float]
    ofi: Optional[float]             # order flow imbalance
```

**Quyết định quan trọng:** primitives Phase 1-2 nhận `List[DailyFlowRecord]` chứ không phải `List[StockRecord]`. Có adapter:

```python
def stock_record_to_daily_flow(r: StockRecord) -> DailyFlowRecord:
    return DailyFlowRecord(
        date=r.date,
        close=r.priceClose,
        volume=r.priceImpactVolume,
        traded_value=r.priceImpactValue,
        prop_net_value=r.propTradingNetValue,
        foreign_buy_value=r.buyForeignValue,
        foreign_sell_value=r.sellForeignValue,
    )
```

## 3.3. Primitive base protocol update

**File:** `smart_money/primitives/base.py`

```python
class Primitive(Protocol):
    name: str
    applicable_bar_sizes: List[str]      # ["1d"] cho daily-only, ["1m","5m","1d"] cho agnostic

    def compute(
        self,
        records: List[FlowRecord],        # DailyFlowRecord hoặc IntradayFlowRecord
        cfg: SmartMoneyConfig,
    ) -> FlowPrimitive: ...

    def min_records(self) -> int: ...
```

### Refactor primitives Phase 1-2
- Prop và foreign: `applicable_bar_sizes = ["1d"]` (chỉ daily có field prop/foreign)
- Divergence: có thể agnostic (dùng price + flow bất kỳ bar size nào)
- Concentration: daily-only
- Persistence: daily-only

Composite skip primitive nào không applicable cho bar size đang compute.

## 3.4. Multi-timeframe composite

**Update:** `composite.py`

```python
def compute_smart_money(
    daily_records: List[DailyFlowRecord],
    intraday_records: Optional[List[IntradayFlowRecord]] = None,
    cfg: SmartMoneyConfig = None,
) -> SmartMoneySignal:

    # Daily primitives
    daily_sm = _compute_layer(daily_records, "1d", cfg)

    # Intraday primitives (Phase 4 mới có)
    intraday_sm = None
    if intraday_records and cfg.use_intraday:
        intraday_sm = _compute_layer(intraday_records, cfg.intraday_bar_size, cfg)

    # Combine
    if intraday_sm is None:
        return daily_sm
    else:
        return _combine_timeframes(daily_sm, intraday_sm, cfg)
```

### Combine logic

```python
def _combine_timeframes(daily, intraday, cfg):
    w_daily = cfg.weight_daily       # default 0.7
    w_intraday = cfg.weight_intraday # default 0.3

    composite = (
        daily.composite * daily.confidence * w_daily
        + intraday.composite * intraday.confidence * w_intraday
    ) / (daily.confidence * w_daily + intraday.confidence * w_intraday)

    # Divergence giữa daily và intraday là tín hiệu valuable:
    # daily bull nhưng intraday bear → có thể là distribution ngày hôm nay
    timeframe_divergence = daily.composite - intraday.composite
    ...
```

## 3.5. Storage design cho tick data

**Quyết định trước khi Phase 4:**

### Format
**Parquet** (không phải JSON). Vì sao:
- Columnar → read chọn lọc field rất nhanh
- Compression tốt (tick data redundant cao)
- Ecosystem tốt với pandas/polars/duckdb

### Layout

```
data_tick/
  <SYMBOL>/
    2026-04-01.parquet
    2026-04-02.parquet
    ...
```

- Partition theo ngày: load 1 ngày không phải scan cả năm
- Partition theo mã: mỗi worker backtest chỉ load mã đang test

### Schema tối thiểu

```
time: timestamp
price: float
volume: int
side: int8  (-1 sell, 0 unknown, +1 buy)  — None nếu chưa classified
bid: float  (nullable)
ask: float  (nullable)
trade_type: str  (continuous / ATO / ATC / lunch)
```

Side có thể để None trong raw file, classify lúc load (cache classified version riêng).

### Helper

**File:** `src/data/tick_storage.py`

```python
def write_tick_day(symbol: str, day: date, trades: pd.DataFrame): ...
def read_tick_day(symbol: str, day: date) -> Optional[pd.DataFrame]: ...
def read_tick_range(symbol: str, start: date, end: date) -> pd.DataFrame: ...
def resample_to_bars(ticks: pd.DataFrame, bar_size: str) -> List[IntradayFlowRecord]: ...
```

### Runtime access rule (chốt từ Phase 3, enforce ở Phase 4)

Phase 3 chỉ định nghĩa API, Phase 4 mới có nightly job và primitives. Nhưng quy tắc sau phải ghi rõ từ bây giờ để Phase 4 không lệch:

- **Scoring engine chỉ được gọi `read_tick_day(symbol, signal_date)`** — đọc tick raw của đúng 1 ngày (phiên đang score).
- **Không** gọi `read_tick_range()` ở runtime (chỉ dùng cho backfill / nightly job).
- Mọi nhu cầu so sánh với history → đi qua `IntradayFeatureCache` (xem Phase 4 section 4.10).

Lý do: tick data 20 ngày của 1 mã có thể nặng hàng GB; load runtime = không khả thi. Feature cache giữ scalar per day per symbol (~10 numbers), load 20 ngày chỉ tốn ms.

## 3.6. Configuration update

```python
@dataclass
class SmartMoneyConfig:
    # ... existing fields

    # Phase 3 additions
    use_intraday: bool = False           # bật khi có tick data
    intraday_bar_size: str = "5m"
    weight_daily: float = 0.7
    weight_intraday: float = 0.3
    tick_storage_path: str = "data_tick"
```

## 3.7. Adapter layer trong scoring

**Update:** `signal_scoring_v5.py`

```python
def _build_score_v5(records: List[StockRecord], bullish, cfg):
    # Adapt StockRecord → DailyFlowRecord
    daily_flow = [stock_record_to_daily_flow(r) for r in records]

    # Nếu tick data có sẵn:
    intraday_flow = None
    if cfg.smart_money.use_intraday:
        today = records[-1].date
        source = TickFlowSource(cfg.smart_money.tick_storage_path)
        raw = source.get_intraday_flow(symbol, today, cfg.smart_money.intraday_bar_size)
        if raw:
            intraday_flow = raw

    sm_signal = compute_smart_money(daily_flow, intraday_flow, cfg.smart_money)
    ...
```

## 3.8. Testing

- `test_flow_source.py` — DailyFlowSource wrap StockDataLoader đúng
- `test_flow_records_adapter.py` — StockRecord → DailyFlowRecord round-trip
- `test_primitives_phase3_compat.py` — Phase 1-2 primitives chạy được trên DailyFlowRecord (không regression)
- `test_composite_multi_timeframe.py` — với intraday=None, behavior giữ nguyên Phase 2

## 3.9. Migration checklist

- [ ] Tạo `DailyFlowRecord`, `IntradayFlowRecord`
- [ ] Tạo adapter `stock_record_to_daily_flow`
- [ ] Refactor Phase 1-2 primitives sang `DailyFlowRecord`
- [ ] Update composite accept cả 2 timeframes
- [ ] `FlowSource` protocol + `DailyFlowSource` implementation
- [ ] Tick storage helpers (chỉ API, chưa có data)
- [ ] Scoring adapter layer
- [ ] Tất cả tests Phase 1-2 vẫn pass
- [ ] **Smoke test:** chạy V5 scoring trên 1 mã → output giống hệt Phase 2 (byte-for-byte)

## Deliverable Phase 3

- [ ] `src/data/flow_source.py` + `flow_records.py` + `tick_storage.py`
- [ ] Refactored primitives sang FlowRecord base
- [ ] Multi-timeframe composite
- [ ] Zero regression trên Phase 2 tests

## Ước lượng scope

~400-600 LOC refactor + ~200 LOC mới.

**Đây là phase ít visible nhất nhưng quan trọng nhất cho long-term.**
