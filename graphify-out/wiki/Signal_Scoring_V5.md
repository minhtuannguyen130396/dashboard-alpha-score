# Signal Scoring V5

> Community · `src\analysis\signal_scoring_v5.py`

## Summary

V5 là lớp mỏng trên V4 — thay thế duy nhất một thành phần: `setup_prop` (tự doanh net flow cứng) được thay bằng Smart Money module đầy đủ (`compute_smart_money()`). Tất cả sub-scorers còn lại (candle, trend, momentum, volume, structure, confirmation, divergence, regime, blockers) được import trực tiếp từ V4 để đảm bảo lock-step và dễ trace behavioral diff giữa hai version.

**Điểm khác biệt V5 vs V4:**
1. `setup_prop` → Smart Money `setup_composite` (tổng hợp prop + foreign flow có trọng số và confidence)
2. Cả hai bucket (setup + trigger) đều có slot smart money riêng, cho phép intraday primitives (Phase 2+) plug in mà không refactor lại structure

**Khi nào dùng V5:** Khi `SmartMoneyConfig` được cấu hình và truyền vào scorer — V5 tận dụng toàn bộ Smart Money layer. V4 vẫn hoạt động standalone không cần smart money data.

## Key Concepts

- **signal_scoring_v5.py** — `src\analysis\signal_scoring_v5.py`
- **ScoreConfigV5** — cấu hình riêng cho V5 (mở rộng từ V4, thêm smart_money_weight)
- **calculate_signal_score_v5()** — public API, nhận thêm `SmartMoneySignal` parameter
- **_build_score_v5()** — core builder, gọi V4 sub-scorers + smart money slot
- Imports từ V4: `Blocker`, `_score_candle_v4`, `_score_trend_v4`, `_score_momentum_v4`, `_score_volume_setup_v4`, `_score_volume_trigger_v4`, `_score_structure_v4`, `_score_confirmation_v4`, `_score_divergence_v4`, `_score_regime_align_v4`, `_detect_blockers_v4`

## Source Files

- `src\analysis\signal_scoring_v5.py`

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*
