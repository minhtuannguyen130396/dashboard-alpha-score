# Volume Convention

> 4 nodes · cohesion 0.50

## Summary

Quy ước volume cho thị trường chứng khoán Việt Nam — tài liệu tại `src/analysis/README_volume_convention.md`.

VN có 3 loại volume khác nhau. Quy tắc cốt lõi: **dùng "deal volume" (khối lượng khớp lệnh) cho mọi chỉ báo liên quan đến price movement** — không dùng total volume. Deal volume phản ánh giao dịch thực sự tác động đến giá; total volume bao gồm cả putthrough (giao dịch thỏa thuận) không ảnh hưởng giá. "Price Impact Volume" là alias của deal volume trong codebase. Xem `_impact_volumes()` trong `technical_indicators.py`.

## Key Concepts

- **Price Impact Volume** (3 connections) — `src/analysis/README_volume_convention.md`
- **Deal Volume as Price-Movement Source** (1 connections) — `src/analysis/README_volume_convention.md`
- **Total Volume Raw Reference** (1 connections) — `src/analysis/README_volume_convention.md`
- **Volume Convention** (1 connections) — `src/analysis/README_volume_convention.md`

## Relationships

- No strong cross-community connections detected

## Source Files

- `src/analysis/README_volume_convention.md`

## Audit Trail

- EXTRACTED: 2 (33%)
- INFERRED: 4 (67%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*