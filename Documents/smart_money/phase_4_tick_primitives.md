# Phase 4 — Tick data primitives

**Mục tiêu:** thêm các primitives tận dụng tick-level data (order flow imbalance, block trades, VWAP, auction flow).

**Điều kiện tiên quyết:**
- Phase 3 done (infrastructure sẵn sàng)
- **Đã có nguồn tick data ổn định** — đây là blocker cứng

## Bucket assignment (chốt cho Phase 4)

Tất cả primitive intraday Phase 4 có `bucket = "trigger"` — chúng mô tả hành vi **trong phiên hôm nay**, không phải flow tích luỹ nhiều phiên:

| Primitive | `bucket` | Ghi chú |
|---|---|---|
| `ofi` (Order Flow Imbalance) | `trigger` | Intraday buy/sell pressure |
| `block_trade` | `trigger` | Events xảy ra hôm nay |
| `vwap_relationship` | `trigger` | Vị thế close vs VWAP hôm nay |
| `auction_flow` | `trigger` | ATO/ATC của phiên hôm nay |
| `intraday_divergence` | `trigger` | Divergence trong phiên |
| `iceberg` (optional) | `trigger` | Events trong phiên |

Phase 4 **không** thêm primitive bucket `setup` nào. Nếu sau này có ý tưởng (ví dụ "multi-day OFI accumulation") → phải được thảo luận và cập nhật bảng này trong `architecture.md` trước khi code.

Phase 4 sẽ làm `trigger_smartmoney` weight tăng nữa. Rebalance lần cuối khi ship.

## 4.0. Nguồn tick data — quyết định trước

Các option cho VN market:

| Nguồn | Ưu | Nhược |
|---|---|---|
| SSI FastConnect / SSI iBoard API | Chính thống, real-time | Phải có account, rate limit |
| VPS SmartOne API | Tương tự | Tương tự |
| Fiinquant / FiinTrade | Data quality tốt, lịch sử đầy đủ | Trả phí |
| Scrape từ app broker | Miễn phí | Fragile, vi phạm ToS |
| SSI/HNX historical tick CSV | Cho backtest | Không real-time |

**Quyết định:** chọn 1 nguồn primary + (tùy chọn) 1 fallback. Cần xác định **trước** khi bắt đầu phase này.

### Data yêu cầu tối thiểu
- Timestamp chính xác (≤ 100ms)
- Price, volume mỗi trade
- Bid/ask tốt nhất (nice-to-have, giúp Lee-Ready)
- Phân biệt được continuous / ATO / ATC

## 4.1. Trade classification (cái khó nhất)

**File:** `src/analysis/smart_money/tick/trade_classifier.py`

Tick data VN **thường không có side flag trực tiếp**. Phải suy luận.

### Ba phương pháp

**a) Tick rule (đơn giản nhất, fallback)**
```python
def tick_rule(trades):
    prev_price = trades[0].price
    prev_side = 0
    for t in trades:
        if t.price > prev_price:
            t.side = +1
        elif t.price < prev_price:
            t.side = -1
        else:
            t.side = prev_side  # giữ nguyên
        prev_price = t.price
        prev_side = t.side
```
Cần data tối thiểu: price + volume. Accuracy ~70%.

**b) Lee-Ready (nếu có bid/ask)**
```python
def lee_ready(trades):
    for t in trades:
        mid = (t.bid + t.ask) / 2
        if t.price > mid:
            t.side = +1
        elif t.price < mid:
            t.side = -1
        else:
            # Tie-breaker: dùng tick rule
            t.side = tick_rule_single(t, prev)
```
Accuracy ~85%.

**c) Bulk volume classification (BVC)**
Cho trường hợp chỉ có OHLCV theo phút (không có tick-level):
```python
def bvc(bar):
    """
    buy_volume = total * Φ((close - open) / σ)
    sell_volume = total - buy_volume
    """
    z = (bar.close - bar.open) / bar_volatility
    buy_fraction = normal_cdf(z)
    return bar.volume * buy_fraction, bar.volume * (1 - buy_fraction)
```
Không chính xác bằng tick-level nhưng robust và không cần data bid/ask.

### Implementation plan
- Implement cả 3
- Config `cfg.trade_classification_method` = `tick_rule | lee_ready | bvc | auto`
- `auto` detect data có bid/ask không → chọn phù hợp

### Xử lý đặc biệt
- **ATO/ATC auction:** không phải continuous trading → tick rule không áp dụng. Classify toàn bộ auction volume theo direction của auction price vs last close.
- **Lunch break:** bỏ qua window 11:30-13:00
- **Phiên ATC giờ cuối (14:30-14:45):** auction, xử lý riêng

## 4.2. Order Flow Imbalance (OFI) primitive

**File:** `primitives/order_flow_imbalance.py`

**Ý tưởng:** tỷ lệ buy volume vs sell volume trong mỗi time window.

```python
def compute(intraday_records):
    buy_vol = sum(r.buy_volume for r in intraday_records)
    sell_vol = sum(r.sell_volume for r in intraday_records)
    total = buy_vol + sell_vol
    ofi = (buy_vol - sell_vol) / total if total > 0 else 0

    # Rolling 30 phút + end-of-day
    ofi_30min = _rolling_ofi(intraday_records, window_minutes=30)
    ofi_eod = _last_n_minutes_ofi(intraday_records, minutes=15)

    # End-of-day weight cao hơn (institutional thường gom cuối phiên)
    value = 0.4 * ofi_30min + 0.6 * ofi_eod
```

### Normalize
Percentile của OFI hôm nay so với 20 ngày gần nhất của chính mã → tránh bias.

**Không recompute 20 ngày tick mỗi lần scoring.** Runtime chỉ tính OFI raw cho phiên hiện tại, sau đó **load scalar OFI history từ Intraday Feature Cache** (section 4.10) để tính percentile:

```python
def compute(intraday_records_today, symbol, signal_date, cfg) -> FlowPrimitive:
    # 1. Raw compute cho phiên hôm nay (từ intraday bars / ticks của signal_date)
    ofi_today = _compute_ofi_scalar(intraday_records_today)

    # 2. Load scalar history từ cache — KHÔNG load lại tick data
    cache = IntradayFeatureCache(cfg.cache_path)
    history = cache.load_feature(
        symbol=symbol,
        feature="ofi_composite",
        end_date=signal_date - 1,
        lookback=20,
    )   # → list[float] ≤ 20 phần tử

    # 3. Percentile rank
    rank = percentile_rank(history, ofi_today) if len(history) >= 10 else 0.5
    value = rank_to_signed(rank)

    return FlowPrimitive(
        name="ofi",
        bucket="trigger",
        value=value,
        confidence=_confidence(intraday_records_today, history),
        components={"ofi_today": ofi_today, "history_len": len(history)},
        reasons=[...],
    )
```

### Confidence
- Data đủ (>= 80% phiên hôm nay có trade) **và** cache có ≥ 15/20 ngày history → 1.0
- Cache history < 10 ngày → confidence ≤ 0.3 (không đủ baseline cho percentile tin cậy)
- Mã thanh khoản thấp, nhiều gap không trade trong phiên hôm nay → giảm xuống

## 4.3. Block trade primitive

**File:** `primitives/block_trade.py`

**Ý tưởng:** trades có volume >> median = proxy institutional mạnh nhất.

### Logic

```python
def compute(raw_ticks_today, symbol, signal_date, cfg) -> FlowPrimitive:
    # Threshold không lấy từ median phiên hôm nay (sẽ dao động, 1 ngày ít trade
    # sẽ khiến threshold quá thấp). Lấy từ cache — baseline median
    # của 20 ngày gần nhất, ổn định hơn nhiều.
    cache = IntradayFeatureCache(cfg.cache_path)
    baseline_median = cache.load_scalar(
        symbol=symbol,
        feature="median_trade_size_20d",
        as_of=signal_date - 1,
    )
    if baseline_median is None:
        # Cold start: dùng median phiên hôm nay, confidence giảm
        baseline_median = median(t.volume for t in raw_ticks_today)
        cold_start = True
    else:
        cold_start = False

    threshold = baseline_median * cfg.block_threshold_multiplier  # default 30
    blocks = [t for t in raw_ticks_today if t.volume >= threshold]

    block_buy = sum(t.volume for t in blocks if t.side > 0)
    block_sell = sum(t.volume for t in blocks if t.side < 0)
    total_block = block_buy + block_sell
    if total_block == 0:
        return FlowPrimitive(name="block_trade", bucket="trigger",
                             value=0, confidence=0, ...)

    value = clamp(2 * (block_buy - block_sell) / total_block, -1, 1)
    confidence = min(1.0, len(blocks) / 5)
    if cold_start:
        confidence *= 0.5
    return FlowPrimitive(name="block_trade", bucket="trigger",
                         value=value, confidence=confidence, ...)
```

### Ngưỡng threshold
- `threshold = baseline_median × block_threshold_multiplier` (default 30)
- **Baseline median** đến từ cache (20 ngày gần nhất) — ổn định, không phụ thuộc 1 phiên cá biệt
- Mã thanh khoản cao (VN30): baseline median cao → threshold tự động cao
- Mã nhỏ: baseline median thấp → threshold thấp
- Cold start (mã mới, cache trống) → fallback sang median phiên hôm nay nhưng confidence x 0.5
- Tune qua config `block_threshold_multiplier`

## 4.4. VWAP relationship primitive

**File:** `primitives/vwap_relationship.py`

**Ý tưởng:** Close > VWAP với volume dồn above VWAP → accumulation.

```python
def compute(intraday_records):
    total_volume = sum(r.volume for r in intraday_records)
    total_vp = sum(r.close * r.volume for r in intraday_records)
    vwap = total_vp / total_volume

    close = intraday_records[-1].close
    above_volume = sum(r.volume for r in intraday_records if r.close > vwap)
    up_vol_ratio = above_volume / total_volume

    # Value = combination
    position_score = (close - vwap) / vwap  # % distance from vwap
    value = clamp(
        0.5 * tanh(position_score * 100)
        + 0.5 * (2 * up_vol_ratio - 1),
        -1, 1,
    )
```

## 4.5. Auction flow primitive

**File:** `primitives/auction_flow.py`

**Ý tưởng:** ATO/ATC trên HOSE có meaning riêng — institutional hay đặt lệnh lớn ở auction.

```python
def compute(intraday_records):
    ato_trades = [r for r in raw_ticks if r.trade_type == "ATO"]
    atc_trades = [r for r in raw_ticks if r.trade_type == "ATC"]

    ato_net = sum(t.side * t.volume for t in ato_trades)
    atc_net = sum(t.side * t.volume for t in atc_trades)

    total_session_volume = sum(r.volume for r in intraday_records)
    ato_ratio = ato_net / total_session_volume
    atc_ratio = atc_net / total_session_volume

    # ATC quan trọng hơn ATO
    value = clamp(tanh(30 * (0.4 * ato_ratio + 0.6 * atc_ratio)), -1, 1)
```

### Ghi chú
ATC mua ròng mạnh + đóng cửa cao hơn giá phiên continuous = dấu hiệu institutional chốt mua cuối phiên → bullish mạnh cho phiên sau.

## 4.6. Intraday divergence primitive

**File:** `primitives/intraday_divergence.py`

**Ý tưởng:** giá tạo high mới trong phiên nhưng cumulative OFI không tạo high → intraday bearish divergence.

Tương tự `divergence.py` Phase 2 nhưng chạy trên intraday bars thay vì daily.

### Output
Rất mạnh cho trigger ngày (khác với daily divergence là leading cho setup).

## 4.7. Iceberg detection (nâng cao, optional)

**File:** `primitives/iceberg.py`

**Ý tưởng:** lệnh mua/bán nhiều lần cùng 1 mức giá với size đều = iceberg order (institutional che lệnh lớn).

### Cần level-2 data
Data bid/ask per tick + order book depth. Nhiều nguồn VN không cung cấp. Chỉ làm khi data cho phép.

### Logic sơ bộ
```python
def detect_iceberg(trades_at_price):
    # Same price, similar size, repeated within short window
    if len(trades_at_price) < 5:
        return None
    sizes = [t.volume for t in trades_at_price]
    if stdev(sizes) / mean(sizes) < 0.2:  # rất đều
        return {
            "price": trades_at_price[0].price,
            "total_volume": sum(sizes),
            "side": majority_side(trades_at_price),
        }
```

## 4.8. Update composite cho intraday layer

Tất cả intraday primitives có `bucket = "trigger"` → composite dispatch chúng vào `trigger_composite` cùng với divergence/concentration từ Phase 2. **Không tạo bucket mới** ("intraday" không phải một bucket — nó chỉ là nguồn data).

```python
def compute_smart_money(daily_records, intraday_records=None, raw_ticks=None, cfg=None):
    primitives: Dict[str, FlowPrimitive] = {}

    # Daily primitives (Phase 1-2)
    if cfg.use_prop:
        primitives["prop"] = PropFlowPrimitive().compute(daily_records, cfg)
    if cfg.use_foreign:
        primitives["foreign"] = ForeignFlowPrimitive().compute(daily_records, cfg)
    if cfg.use_divergence:
        primitives["divergence"] = DivergencePrimitive().compute(daily_records, cfg)
    if cfg.use_concentration:
        primitives["concentration"] = ConcentrationPrimitive().compute(daily_records, cfg)

    # Intraday primitives (Phase 4) — tất cả bucket="trigger"
    if intraday_records is not None and cfg.use_intraday:
        if cfg.use_ofi:
            primitives["ofi"] = OrderFlowImbalancePrimitive().compute(intraday_records, cfg)
        if cfg.use_block_trades:
            primitives["block_trade"] = BlockTradePrimitive().compute(raw_ticks, cfg)
        if cfg.use_vwap_relationship:
            primitives["vwap_relationship"] = VWAPRelationshipPrimitive().compute(intraday_records, cfg)
        if cfg.use_auction_flow:
            primitives["auction_flow"] = AuctionFlowPrimitive().compute(raw_ticks, cfg)
        if cfg.use_intraday_divergence:
            primitives["intraday_divergence"] = IntradayDivergencePrimitive().compute(intraday_records, cfg)

    # Bucket split như Phase 1-2 — composite code KHÔNG đổi logic, chỉ cần
    # cfg.trigger_weights biết thêm 5 keys mới
    setup_prims = {k: p for k, p in primitives.items() if p.bucket == "setup"}
    trigger_prims = {k: p for k, p in primitives.items() if p.bucket == "trigger"}

    setup_composite, setup_confidence = _aggregate_bucket(setup_prims, cfg.setup_weights)
    trigger_composite, trigger_confidence = _aggregate_bucket(trigger_prims, cfg.trigger_weights)
    # ... rest giống Phase 2
```

### Trigger weights sau Phase 4

```python
# SmartMoneyConfig.trigger_weights sau khi ship Phase 4
trigger_weights = {
    # Phase 2 (daily)
    "divergence":         0.20,
    "concentration":      0.15,
    # Phase 4 (intraday) — tổng ~0.65 để dominate khi có tick data
    "ofi":                0.20,
    "block_trade":        0.15,
    "vwap_relationship":  0.10,
    "auction_flow":       0.10,
    "intraday_divergence":0.10,
}
# Tổng = 1.00
```

Khi không có tick data (`intraday_records=None`), 5 key intraday không có primitive tương ứng → `_aggregate_bucket` tự rebalance dựa trên `confidence=0` → chỉ divergence + concentration đóng góp. Không cần code đặc biệt.

### V5 scoring weight sau Phase 4

```python
trigger_smartmoney: float = 0.18   # 0.12 → 0.18 khi có intraday
```

Lưu ý: tổng `setup_smartmoney (0.10) + trigger_smartmoney (0.18) = 0.28` — **vượt invariant 0.25 đã chốt ở architecture**. Cần đánh giá lại khi ship Phase 4:
- Option A: giảm `setup_smartmoney` xuống 0.08 → tổng 0.26, vẫn vượt → bump invariant lên 0.30
- Option B: giữ invariant 0.25, `trigger_smartmoney` max = 0.15
- Backtest sẽ quyết định.

## 4.9. Testing

- Fixtures: synthetic tick data (đủ để test logic, không cần data thật)
- `test_trade_classifier.py` — tick rule, Lee-Ready, BVC accuracy trên synthetic
- Mỗi primitive intraday có test riêng với fixture rõ ràng
- `test_combine_timeframes.py` — daily + intraday merge đúng với các edge case
- `test_intraday_feature_cache.py` — write/read round-trip, cold start fallback, cache miss behavior
- `test_ofi_normalize_with_cache.py` — OFI percentile khớp khi đưa vào fixture cache có 20 ngày

## 4.10. Intraday Feature Cache

**Đây là layer nối giữa "normalize theo 20 ngày" (cần history) và "lazy load ngày signal" (không load tick 20 ngày).**

### Nguyên tắc

Tick data **raw** rất nặng (trăm ngàn → triệu dòng/ngày/mã). Nhưng các primitive intraday chỉ cần **một vài scalar per day** khi so sánh với history:
- `ofi_composite` (1 float)
- `median_trade_size` (1 float)
- `block_count`, `block_buy_vol`, `block_sell_vol` (3 numbers)
- `vwap`, `upvol_ratio` (2 floats)
- `auction_ato_net`, `auction_atc_net` (2 floats)
- `data_quality_score` (1 float)

~10 số/mã/ngày × 1000 mã × 500 ngày ≈ 5M cells → dưới 100MB Parquet. Load 20 ngày history chỉ là mấy chục row scalar, O(ms).

**Quy tắc cứng:**
- Primitive **không bao giờ** load tick raw của ngày khác ngày signal
- History dùng để normalize **luôn** đến từ feature cache
- Feature cache populated bởi **nightly batch job**, không phải runtime

### Schema cache

**File:** `src/data/intraday_feature_cache.py`

```python
@dataclass
class IntradayFeatureRow:
    symbol: str
    date: date
    # OFI
    ofi_composite: float
    ofi_30min: float
    ofi_eod: float
    # Block trades
    median_trade_size: float
    block_count: int
    block_buy_volume: float
    block_sell_volume: float
    # VWAP
    vwap: float
    close_vs_vwap_pct: float
    upvol_ratio: float
    # Auction
    auction_ato_net: float
    auction_atc_net: float
    # Data quality
    bars_with_trades: int
    total_bars: int
    data_quality_score: float    # bars_with_trades / total_bars
    # Metadata
    classifier_method: str        # "tick_rule" | "lee_ready" | "bvc"
    computed_at: datetime
```

### Storage layout

**Single table partitioned by month** — đơn giản hơn per-symbol:

```
data_tick_features/
  2026-01.parquet
  2026-02.parquet
  2026-03.parquet
  2026-04.parquet
```

- Mỗi file ~30 ngày × 1000 mã × ~15 cột ≈ 450k rows, vài MB
- Truy vấn `WHERE symbol=X AND date BETWEEN A AND B` rất nhanh với pyarrow/polars
- Append-only: mỗi ngày nightly job thêm 1 batch rows vào file tháng hiện hành
- Không rewrite file cũ

### API

```python
class IntradayFeatureCache:
    def __init__(self, base_path: str): ...

    # Runtime (scoring engine)
    def load_feature(
        self, symbol: str, feature: str,
        end_date: date, lookback: int,
    ) -> List[float]:
        """Return up to `lookback` values ending at end_date (inclusive)."""

    def load_scalar(
        self, symbol: str, feature: str, as_of: date,
    ) -> Optional[float]:
        """Return cached scalar (vd 20d median) AS OF a date. None nếu chưa tính."""

    def load_row(self, symbol: str, date: date) -> Optional[IntradayFeatureRow]: ...

    # Nightly job
    def write_day(self, rows: List[IntradayFeatureRow]) -> None:
        """Append rows cho 1 ngày. Idempotent: gọi lại ghi đè."""

    # Maintenance
    def rebuild_scalars(self, symbol: str, as_of: date) -> None:
        """Recompute derived scalars như median_trade_size_20d từ raw rows."""
```

### Derived scalars

Một số "feature" không phải 1 số của 1 ngày mà là aggregate qua window (`median_trade_size_20d`, `ofi_baseline_60d`). Lưu riêng để primitive khỏi tính lại:

```
data_tick_features/
  daily/          ← scalar per day
    2026-04.parquet
  derived/        ← rolling aggregates per (symbol, as_of)
    median_trade_size_20d.parquet
    ofi_baseline_60d.parquet
```

Derived recompute sau mỗi lần daily update, trong cùng nightly job.

### Nightly batch pipeline

**File:** `scripts/compute_intraday_features.py`

```
for day in missing_days(cache, today):
    for symbol in universe:
        ticks = tick_storage.read_tick_day(symbol, day)
        if not ticks:
            continue
        classified = TradeClassifier(method=cfg.classifier_method).classify(ticks)
        bars = resample_to_bars(classified, "5m")
        row = compute_intraday_feature_row(symbol, day, bars, classified)
        batch.append(row)
    cache.write_day(batch)
    cache.rebuild_scalars_for_day(day)   # update 20d/60d rollups
```

Chạy sau 15:30 mỗi ngày giao dịch. Idempotent — chạy lại ngày cũ không làm hỏng data.

### Cold start protocol

- Cache trống cho 1 mã → primitive fallback với confidence giảm (xem block_trade section 4.3)
- Cache có < 10/20 ngày history → primitive trả confidence ≤ 0.3
- Không bao giờ làm "on-demand backfill tại runtime" — quá chậm, blast radius lớn, dễ race condition. Backfill đi qua nightly job hoặc CLI manual.

### Invariant

- Primitive ở runtime **chỉ** đọc cache + tick raw của 1 ngày signal.
- Không primitive nào được gọi `tick_storage.read_tick_range()` với range > 1 ngày.
- Unit test assert: mock `tick_storage` với spy, verify `read_tick_day` được gọi đúng 1 lần với đúng signal_date.

## 4.11. Performance consideration

Tick data nặng → chú ý:
- Cache classified trades (classify 1 lần, lưu parquet riêng)
- **Runtime chỉ load:** (a) tick raw của ngày signal, (b) scalar features từ `IntradayFeatureCache` cho 20 ngày lookback. KHÔNG load tick raw của các ngày khác.
- Precompute heavy: mọi thứ cần history đều đi qua nightly `compute_intraday_features.py` + cache. Runtime chỉ là lookup + aggregate của ngày hôm nay.
- Numpy/polars thay vì pure Python cho aggregation
- Benchmark: scoring 1 mã không được > 500ms kể cả với intraday
- Benchmark riêng: `load_feature(symbol, "ofi_composite", lookback=20)` phải < 5ms khi cache ấm

## Deliverable Phase 4

- [ ] Trade classifier (3 methods) + tests
- [ ] 5-6 intraday primitives
- [ ] Tick storage pipeline functional (raw ticks per day)
- [ ] **Intraday Feature Cache** module (`src/data/intraday_feature_cache.py`)
- [ ] **Nightly batch job** `scripts/compute_intraday_features.py` + idempotency tests
- [ ] Derived scalar rollups (20d median, 60d baselines) auto-recompute
- [ ] Multi-timeframe composite fully operational
- [ ] Invariant test: runtime scoring chỉ load tick raw của 1 ngày signal
- [ ] Backtest so sánh Phase 3 (daily only) vs Phase 4 (daily + intraday)
- [ ] Performance benchmark đạt target (scoring < 500ms, feature cache lookup < 5ms)

## Ước lượng scope

~1000-1500 LOC (phase lớn nhất). Đòi hỏi data pipeline + classification + multiple primitives + performance tuning.
