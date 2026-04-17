# Technical Indicators

> 46 nodes · cohesion 0.06

## Summary

Thư viện tính toán ~30+ chỉ báo kỹ thuật thuần túy — không có logic quyết định, chỉ transform dữ liệu giá/khối lượng thành số. Kết quả được đóng gói vào 4 nhóm `IndicatorGroup1-4` dùng cho các mục đích khác nhau trong scoring engine.

**Phân nhóm chỉ báo:**
- **Trend/MA:** SMA, EMA, WMA, VWMA, HMA, KAMA — xác định xu hướng và dynamic support
- **Momentum:** RSI, MACD, Stochastic %K/%D, ROC, CCI, Williams %R, Ultimate Oscillator — đo sức mạnh và quá mua/bán
- **Volatility:** ATR, Bollinger Bands, Keltner Channel, Donchian Channel, Chaikin Volatility, StdDev, Mass Index — đo biên độ dao động
- **Volume:** OBV, ADL, CMF, MFI, VROC, VWAP, average_volume — xác nhận xu hướng bằng dòng tiền
- **Breadth:** ADL, McClellan Oscillator, TRIN, Bullish Percent Index — đo sức rộng thị trường
- **Pattern signals:** `is_large_buyer_accumulation()`, `is_fomo_by_retail()` — tín hiệu hành vi thị trường

**Lưu ý về volume:** VN sử dụng "deal volume" (khối lượng khớp lệnh) thay vì total volume cho các chỉ báo liên quan đến price movement. Xem [[Volume Convention]].

*Các file đơn lẻ SMA/EMA/RSI... trong index là artifact fragmentation — tất cả đều nằm trong `technical_indicators.py` và được community này bao phủ.*

## Key Concepts

- **technical_indicators.py** (47 connections) — `src\analysis\technical_indicators.py`
- **_extract()** (11 connections) — `src\analysis\technical_indicators.py`
- **ema()** (6 connections) — `src\analysis\technical_indicators.py`
- **_impact_volumes()** (4 connections) — `src\analysis\technical_indicators.py`
- **average_volume()** (3 connections) — `src\analysis\technical_indicators.py`
- **bollinger_bands()** (3 connections) — `src\analysis\technical_indicators.py`
- **keltner_channel()** (3 connections) — `src\analysis\technical_indicators.py`
- **sma()** (3 connections) — `src\analysis\technical_indicators.py`
- **vwma()** (3 connections) — `src\analysis\technical_indicators.py`
- **atr()** (2 connections) — `src\analysis\technical_indicators.py`
- **chaikin_volatility()** (2 connections) — `src\analysis\technical_indicators.py`
- **hma()** (2 connections) — `src\analysis\technical_indicators.py`
- **is_fomo_by_retail()** (2 connections) — `src\analysis\technical_indicators.py`
- **kama()** (2 connections) — `src\analysis\technical_indicators.py`
- **macd()** (2 connections) — `src\analysis\technical_indicators.py`
- **momentum()** (2 connections) — `src\analysis\technical_indicators.py`
- **roc()** (2 connections) — `src\analysis\technical_indicators.py`
- **rsi()** (2 connections) — `src\analysis\technical_indicators.py`
- **std_dev()** (2 connections) — `src\analysis\technical_indicators.py`
- **stochastic_d()** (2 connections) — `src\analysis\technical_indicators.py`
- **stochastic_k()** (2 connections) — `src\analysis\technical_indicators.py`
- **vroc_score()** (2 connections) — `src\analysis\technical_indicators.py`
- **wma()** (2 connections) — `src\analysis\technical_indicators.py`
- **ad_signals()** (1 connections) — `src\analysis\technical_indicators.py`
- **adv_decline_line()** (1 connections) — `src\analysis\technical_indicators.py`
- *... and 21 more nodes in this community*

## Relationships

- No strong cross-community connections detected

## Source Files

- `src\analysis\technical_indicators.py`

## Audit Trail

- EXTRACTED: 134 (100%)
- INFERRED: 0 (0%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*