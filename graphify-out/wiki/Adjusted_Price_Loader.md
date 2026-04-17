# Adjusted Price Loader

> 3 nodes · cohesion 0.67

## Summary

Test coverage cho `stock_data_loader.py` (không phải wiki của module đó). `LoadStockHistoryAdjustmentTest` kiểm tra rằng OHLC prices được nhân với `adjRatio` đúng cách — quan trọng vì VN có các sự kiện corporate action (chia cổ tức, phát hành thêm) làm gap giá lịch sử. Xem [[Data Layer]] để hiểu `StockRecord` và toàn bộ data layer.

## Key Concepts

- **LoadStockHistoryAdjustmentTest** (2 connections) — `tests\test_stock_data_loader.py`
- **test_stock_data_loader.py** (1 connections) — `tests\test_stock_data_loader.py`
- **.test_ohlc_prices_are_adjusted_by_adj_ratio()** (1 connections) — `tests\test_stock_data_loader.py`

## Relationships

- No strong cross-community connections detected

## Source Files

- `tests\test_stock_data_loader.py`

## Audit Trail

- EXTRACTED: 4 (100%)
- INFERRED: 0 (0%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*