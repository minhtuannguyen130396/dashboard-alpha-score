# _build_score_v4()

> God node · 15 connections · `src\analysis\signal_scoring_v4.py`

## What It Is

Hàm nội bộ cốt lõi của scoring engine — được `calculate_signal_score_v4()` gọi để tính toán đầy đủ một `SignalScoreV4`. Là god node vì nó gọi tất cả 11 sub-scorers và assembler:

**Chuỗi gọi:** `calculate_signal_score_v4()` → `_build_score_v4()` → mỗi sub-scorer:
- `_score_trend_v4()` — EMA alignment, ADX strength
- `_score_momentum_v4()` — RSI, MACD rolling-rank (window 120)
- `_score_volume_setup_v4()` — volume trend, accumulation signals
- `_score_volume_trigger_v4()` — RVOL, intraday volume spike
- `_score_candle_v4()` + `_candle_quality()` — pattern + body/shadow ratio
- `_score_structure_v4()` — support/resistance, pivot levels
- `_score_divergence_v4()` — price/indicator divergence
- `_score_regime_align_v4()` — score alignment với regime thị trường
- `_score_prop_trading_v4()` — tự doanh net flow
- `_score_confirmation_v4()` — cross-confirmation giữa các signals
- `_detect_blockers_v4()` — xác định hard/soft blockers

## Connections by Relation

### calls
- [[SignalScoreV4]] `EXTRACTED`
- [[_safe_last()]] `EXTRACTED`
- [[_score_candle_v4()]] `EXTRACTED`
- [[_score_trend_v4()]] `EXTRACTED`
- [[_score_momentum_v4()]] `EXTRACTED`
- [[_score_volume_setup_v4()]] `EXTRACTED`
- [[_score_volume_trigger_v4()]] `EXTRACTED`
- [[_score_structure_v4()]] `EXTRACTED`
- [[_score_divergence_v4()]] `EXTRACTED`
- [[_score_regime_align_v4()]] `EXTRACTED`
- [[_score_prop_trading_v4()]] `EXTRACTED`
- [[_detect_blockers_v4()]] `EXTRACTED`
- [[calculate_signal_score_v4()]] `EXTRACTED`
- [[_score_confirmation_v4()]] `EXTRACTED`

### contains
- [[signal_scoring_v4.py]] `EXTRACTED`

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*