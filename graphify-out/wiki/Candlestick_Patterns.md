# Candlestick Patterns

> 23 nodes · cohesion 0.13

## Summary

Thư viện nhận dạng mẫu nến Nhật. Mỗi hàm nhận danh sách `StockRecord` và trả về boolean array đánh dấu các bar khớp pattern. Kết quả được `SignalScoreV4` dùng để tính thành phần candle_score.

`_candle_features()` trích xuất đặc điểm hình học của từng candle (body size, upper/lower shadow, tỷ lệ body/range). `_is_uptrend()` / `_is_downtrend()` kiểm tra ngữ cảnh xu hướng trước đó — nhiều mẫu chỉ có ý nghĩa khi xuất hiện ở đúng bối cảnh (ví dụ: hammer chỉ có giá trị sau downtrend).

**Phân loại:** `BullishPatterns` (hammer, bullish_engulfing, morning_star, piercing_pattern, inverted_hammer, three_white_soldiers, rising_three_methods, doji_dragonfly) · `BearishPatterns` (hanging_man, bearish_engulfing, dark_cloud_cover, evening_star, shooting_star, three_black_crows, doji_gravestone) · `NeutralPatterns` (doji, spinning_top).

## Key Concepts

- **candle_patterns.py** (24 connections) — `src\analysis\candle_patterns.py`
- **_candle_features()** (5 connections) — `src\analysis\candle_patterns.py`
- **_is_downtrend()** (4 connections) — `src\analysis\candle_patterns.py`
- **_is_uptrend()** (4 connections) — `src\analysis\candle_patterns.py`
- **_extract()** (3 connections) — `src\analysis\candle_patterns.py`
- **hammer()** (3 connections) — `src\analysis\candle_patterns.py`
- **hanging_man()** (3 connections) — `src\analysis\candle_patterns.py`
- **inverted_hammer()** (3 connections) — `src\analysis\candle_patterns.py`
- **shooting_star()** (3 connections) — `src\analysis\candle_patterns.py`
- **bearish_engulfing()** (1 connections) — `src\analysis\candle_patterns.py`
- **bullish_engulfing()** (1 connections) — `src\analysis\candle_patterns.py`
- **dark_cloud_cover()** (1 connections) — `src\analysis\candle_patterns.py`
- **doji()** (1 connections) — `src\analysis\candle_patterns.py`
- **doji_dragonfly()** (1 connections) — `src\analysis\candle_patterns.py`
- **doji_gravestone()** (1 connections) — `src\analysis\candle_patterns.py`
- **evening_star()** (1 connections) — `src\analysis\candle_patterns.py`
- **morning_star()** (1 connections) — `src\analysis\candle_patterns.py`
- **NeutralPatterns** (1 connections) — `src\analysis\candle_patterns.py`
- **piercing_pattern()** (1 connections) — `src\analysis\candle_patterns.py`
- **rising_three_methods()** (1 connections) — `src\analysis\candle_patterns.py`
- **spinning_top()** (1 connections) — `src\analysis\candle_patterns.py`
- **three_black_crows()** (1 connections) — `src\analysis\candle_patterns.py`
- **three_white_soldiers()** (1 connections) — `src\analysis\candle_patterns.py`

## Relationships

- No strong cross-community connections detected

## Source Files

- `src\analysis\candle_patterns.py`

## Audit Trail

- EXTRACTED: 66 (100%)
- INFERRED: 0 (0%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*