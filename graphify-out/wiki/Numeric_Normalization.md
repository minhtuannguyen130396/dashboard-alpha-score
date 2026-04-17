# Numeric Normalization

> 13 nodes · cohesion 0.18

## Summary

Bộ hàm tiện ích chuẩn hóa số dùng chung cho tất cả smart money primitives (`src/analysis/smart_money/normalize.py`). Đảm bảo mọi primitive output nằm trong miền chuẩn trước khi đưa vào composite aggregator.

**Các hàm chính:**
- `winsorize(arr, p)` — cắt p% outlier ở hai đuôi, giảm ảnh hưởng của spike bất thường
- `rolling_zscore(arr, window)` — z-score cửa sổ trượt, có winsorize trước khi tính
- `rank_to_signed(rank)` — ánh xạ [0..1] percentile rank → [-1..+1] tuyến tính
- `tanh_scale(x)` — ánh xạ smooth [-1..+1] qua tanh, tránh saturation đột ngột
- `clamp(x, lo, hi)` — giới hạn cứng
- `safe_ratio(a, b)` — tránh chia cho zero

## Key Concepts

- **normalize.py** (8 connections) — `src\analysis\smart_money\normalize.py`
- **rank_to_signed()** (3 connections) — `src\analysis\smart_money\normalize.py`
- **rolling_zscore()** (3 connections) — `src\analysis\smart_money\normalize.py`
- **winsorize()** (3 connections) — `src\analysis\smart_money\normalize.py`
- **clamp()** (2 connections) — `src\analysis\smart_money\normalize.py`
- **tanh_scale()** (2 connections) — `src\analysis\smart_money\normalize.py`
- **mean()** (1 connections) — `src\analysis\smart_money\normalize.py`
- **Shared numeric helpers for smart money primitives.** (1 connections) — `src\analysis\smart_money\normalize.py`
- **Cap the lowest/highest p fraction of values to reduce outlier impact.** (1 connections) — `src\analysis\smart_money\normalize.py`
- **Z-score of the latest value within the last ``window`` entries.      Winsorizes** (1 connections) — `src\analysis\smart_money\normalize.py`
- **Map a [0..1] percentile rank to the [-1..+1] range.** (1 connections) — `src\analysis\smart_money\normalize.py`
- **Smooth bounded mapping to [-1..+1] via tanh.** (1 connections) — `src\analysis\smart_money\normalize.py`
- **safe_ratio()** (1 connections) — `src\analysis\smart_money\normalize.py`

## Relationships

- No strong cross-community connections detected

## Source Files

- `src\analysis\smart_money\normalize.py`

## Audit Trail

- EXTRACTED: 28 (100%)
- INFERRED: 0 (0%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*