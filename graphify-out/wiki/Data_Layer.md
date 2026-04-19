# Data Layer

> Community · `src\data\`

## Summary

Tầng data của hệ thống — tải, lưu trữ và cung cấp dữ liệu giá/tick cho tất cả các module phía trên. Gồm 6 module, chia thành 3 nhóm:

---

### 1. Dữ liệu giá lịch sử (daily OHLCV)

**`stock_data_loader.py`** — `StockRecord` là dataclass trung tâm của toàn hệ thống. Mỗi record là một ngày giao dịch với đầy đủ: OHLCV, deal volume, putthrough volume, foreign buy/sell, prop trading net value, adjRatio. Property `priceImpactVolume` = dealVolume (quy ước VN volume). Loader đọc từ JSON files on-disk (fetch sẵn, không query API realtime).

**`fireant_history_fetcher.py`** — Fetch lịch sử giá từ FireAnt REST API (`restv2.fireant.vn`). Đọc bearer token từ env var `FIREANT_BEARER_TOKEN` hoặc file `access_token.txt`. Fetch song song 8 workers; lưu kết quả thành JSON per-symbol. Entry: `fetch_all_stock_history()` được gọi từ Stock Selector App UI.

---

### 2. Dữ liệu flow record (daily + intraday abstraction)

**`flow_records.py`** — `DailyFlowRecord` và `IntradayFlowRecord` — bar-size agnostic wrapper cho Smart Money primitives (Phase 3+). Cùng interface hoạt động cho daily, intraday, hoặc pre-aggregated bars. `stock_records_to_daily_flows()` convert `StockRecord` → `DailyFlowRecord` để các primitives không phụ thuộc trực tiếp vào `StockRecord`.

**`flow_source.py`** — `FlowSource` Protocol định nghĩa interface: `get_daily_flow()` và `get_intraday_flow()`. `DailyFlowSource` wrap JSON-on-disk, từ chối serve intraday. `TickFlowSource` (Phase 4) phục vụ từ tick storage khi tick data có sẵn.

---

### 3. Tick data (intraday, Phase 3+)

**`tick_storage.py`** — Lưu tick data theo layout `data_tick/<SYMBOL>/YYYY-MM-DD.parquet`. Schema: time, price, volume, side (+1/-1/0), bid, ask, trade_type (continuous/ATO/ATC/lunch). Phase 3 dùng JSON fallback cho unit tests; Phase 4 chuyển sang parquet qua `write_tick_day(..., format='parquet')`.

**`intraday_feature_cache.py`** — Cache ~10 scalar features per (symbol, day) để primitives normalize against history mà không cần load toàn bộ tick history. Layout: `data_tick_features/daily/YYYY-MM.json`. Có thể swap sang parquet mà không thay đổi public API.

## Source Files

- `src\data\stock_data_loader.py`
- `src\data\fireant_history_fetcher.py`
- `src\data\flow_records.py`
- `src\data\flow_source.py`
- `src\data\tick_storage.py`
- `src\data\intraday_feature_cache.py`

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*
