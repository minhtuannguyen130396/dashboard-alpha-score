# Persistence Detector

> 6 nodes · cohesion 0.47

## Summary

Phát hiện tín hiệu Smart Money bền vững qua nhiều ngày liên tiếp. **Không phải bucket primitive** — hoạt động như multiplier độc lập tác động lên `setup_confidence` sau khi các primitive khác đã tính xong.

Nếu `setup_composite` vượt threshold liên tục ≥ N ngày, `PersistenceDetector.compute()` trả về `PersistenceSignal` với multiplier > 1 để boost confidence. Mục đích: tránh phản ứng với tín hiệu one-off ngắn hạn và tăng độ tin cậy cho những đợt tích lũy dài hạn thực sự. Khi tín hiệu yếu hoặc gián đoạn, multiplier về 1.0 (neutral). Kích hoạt bởi `SmartMoneyConfig.use_persistence=True` (Phase 2+).

## Key Concepts

- **PersistenceDetector** (4 connections) — `src\analysis\smart_money\primitives\persistence.py`
- **persistence.py** (3 connections) — `src\analysis\smart_money\primitives\persistence.py`
- **.compute()** (3 connections) — `src\analysis\smart_money\primitives\persistence.py`
- **PersistenceSignal** (3 connections) — `src\analysis\smart_money\primitives\persistence.py`
- **.min_records()** (2 connections) — `src\analysis\smart_money\primitives\persistence.py`
- **Persistence detector — multiplier (NOT a bucket primitive).  Returns a ``Persist** (2 connections) — `src\analysis\smart_money\primitives\persistence.py`

## Relationships

- No strong cross-community connections detected

## Source Files

- `src\analysis\smart_money\primitives\persistence.py`

## Audit Trail

- EXTRACTED: 14 (82%)
- INFERRED: 3 (18%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*