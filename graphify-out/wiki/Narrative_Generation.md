# Narrative Generation

> 4 nodes · cohesion 0.67

## Summary

Sinh text giải thích tín hiệu Smart Money bằng tiếng Anh — deterministic, không dùng LLM. `generate_narrative()` nhận `SmartMoneySignal` và trả về string mô tả label, composite score, confidence, và lý do từ các primitives. `_fmt_billion()` format số tiền VND thành dạng đọc được (B/M). Output được lưu vào `SmartMoneySignal.narrative` để hover panel hiển thị.

## Key Concepts

- **narrative.py** (3 connections) — `src\analysis\smart_money\narrative.py`
- **_fmt_billion()** (2 connections) — `src\analysis\smart_money\narrative.py`
- **generate_narrative()** (2 connections) — `src\analysis\smart_money\narrative.py`
- **Deterministic narrative generation for smart money signals (no LLM).** (2 connections) — `src\analysis\smart_money\narrative.py`

## Relationships

- No strong cross-community connections detected

## Source Files

- `src\analysis\smart_money\narrative.py`

## Audit Trail

- EXTRACTED: 8 (89%)
- INFERRED: 1 (11%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*