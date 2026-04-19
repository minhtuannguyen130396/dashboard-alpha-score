# Trade Classification

> 13 nodes · cohesion 0.21

## Summary

Phân loại từng tick hoặc bar thành buyer-initiated (+1) / seller-initiated (-1) / neutral (0). Kết quả dùng để tính OFI và các intraday primitive khác trong Smart Money.

Ba phương pháp, chọn qua `SmartMoneyConfig.trade_classification_method`:
- **tick_rule** — so sánh giá trade với giá trade trước đó (+1 nếu tăng, -1 nếu giảm, 0 nếu bằng). Đơn giản nhất, phù hợp VN vì tick feed hiếm có bid/ask.
- **Lee-Ready** (1991) — ưu tiên quote rule (so giá vs midpoint) khi có bid/ask, fallback về tick rule. Chính xác hơn nhưng cần bid/ask.
- **BVC** (Bulk Volume Classification) — chia volume cả bar thành buy/sell theo xác suất dựa trên price change vs std, không cần tick level. Dùng khi chỉ có bar data.

`TradeClassifier` bọc cả 3 method, expose `.classify_ticks()` và `.classify_bars()`.

## Key Concepts

- **trade_classifier.py** (8 connections) — `src\analysis\smart_money\tick\trade_classifier.py`
- **bvc_classify()** (4 connections) — `src\analysis\smart_money\tick\trade_classifier.py`
- **.classify_ticks()** (4 connections) — `src\analysis\smart_money\tick\trade_classifier.py`
- **lee_ready_classify()** (3 connections) — `src\analysis\smart_money\tick\trade_classifier.py`
- **tick_rule_classify()** (3 connections) — `src\analysis\smart_money\tick\trade_classifier.py`
- **.classify_bars()** (3 connections) — `src\analysis\smart_money\tick\trade_classifier.py`
- **_normal_cdf()** (2 connections) — `src\analysis\smart_money\tick\trade_classifier.py`
- **_resolve_for_bars()** (2 connections) — `src\analysis\smart_money\tick\trade_classifier.py`
- **_resolve_for_ticks()** (2 connections) — `src\analysis\smart_money\tick\trade_classifier.py`
- **Trade classification (tick rule, Lee-Ready, BVC).  VN tick feeds rarely include** (1 connections) — `src\analysis\smart_money\tick\trade_classifier.py`
- **Mark each tick +1/-1/0 based on price change vs previous tick.      Equal price** (1 connections) — `src\analysis\smart_money\tick\trade_classifier.py`
- **Quote-rule + tick-rule fallback (Lee-Ready 1991). Needs bid/ask.** (1 connections) — `src\analysis\smart_money\tick\trade_classifier.py`
- **Bulk Volume Classification — splits each bar's volume into buy/sell.      Doesn'** (1 connections) — `src\analysis\smart_money\tick\trade_classifier.py`

## Relationships

- No strong cross-community connections detected

## Source Files

- `src\analysis\smart_money\tick\trade_classifier.py`

## Audit Trail

- EXTRACTED: 35 (100%)
- INFERRED: 0 (0%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*