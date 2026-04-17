# Stock Selector App

> 14 nodes · cohesion 0.23

## Summary

UI desktop tkinter — entry point của toàn bộ ứng dụng (`main.py` → `create_stock_selector_app()`). Dark theme (#0F172A base). Cho phép user chọn mã cổ phiếu từ danh sách JSON, đặt date range, rồi trigger 3 action chính:

1. **Fetch history** — gọi FireAnt API để tải OHLCV về local
2. **Backtest report** — chạy toàn bộ pipeline (indicators → scoring → simulation) và xuất CSV
3. **Backtest chart** — tương tự nhưng mở HTML chart trong Chrome

Tất cả action chạy trong daemon thread (`_run_in_thread`) để không block UI. `get_all_stock_records()` load metadata cổ phiếu (tên, nhóm ngành) để hỗ trợ filter sau này.

## Key Concepts

- **stock_selector_app.py** (11 connections) — `src\app\stock_selector_app.py`
- **create_stock_selector_app()** (7 connections) — `src\app\stock_selector_app.py`
- **get_all_stock_records()** (5 connections) — `src\app\stock_selector_app.py`
- **_action_btn()** (2 connections) — `src\app\stock_selector_app.py`
- **_apply_theme()** (2 connections) — `src\app\stock_selector_app.py`
- **_card()** (2 connections) — `src\app\stock_selector_app.py`
- **_field_label()** (2 connections) — `src\app\stock_selector_app.py`
- **get_all_symbols()** (2 connections) — `src\app\stock_selector_app.py`
- **_load_records()** (2 connections) — `src\app\stock_selector_app.py`
- **_run_in_thread()** (2 connections) — `src\app\stock_selector_app.py`
- **_section_header()** (2 connections) — `src\app\stock_selector_app.py`
- **Stock Selector App - v2 Modern tkinter UI for backtesting and data management.** (1 connections) — `src\app\stock_selector_app.py`
- **Return the full stock dataset, including group metadata for later filters.** (1 connections) — `src\app\stock_selector_app.py`
- **Run *task* in a daemon thread; call optional callbacks on main thread.** (1 connections) — `src\app\stock_selector_app.py`

## Relationships

- No strong cross-community connections detected

## Source Files

- `src\app\stock_selector_app.py`

## Audit Trail

- EXTRACTED: 42 (100%)
- INFERRED: 0 (0%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*