# Signal Scoring V4

> 22 nodes · cohesion 0.20

## Summary

Engine chấm điểm tín hiệu chính của hệ thống. Điểm được tách thành hai cổng độc lập: **setup_score** (xu hướng trung hạn: momentum rolling-rank, trend EMA, volume_setup, structure, regime alignment) và **trigger_score** (điều kiện vào lệnh tức thì: volume_trigger, candle quality, divergence, prop trading flow). Giao dịch chỉ xảy ra khi cả hai gate vượt ngưỡng VÀ không có hard blocker (ADX < 10, RVOL < 0.3).

Hard blockers chặn hoàn toàn. Soft blockers giảm điểm nhỏ (−0.04/blocker). Rolling-rank window 120 bars tránh tình trạng score bị kẹt giữa trên các cổ phiếu trending. Entry gate cuối là 0.52 (setup) × 0.45 (trigger) — thoáng hơn V3 để các setup tốt thực sự trade được.

## Key Concepts

- **signal_scoring_v4.py** (24 connections) — `src\analysis\signal_scoring_v4.py`
- **_build_score_v4()** (15 connections) — `src\analysis\signal_scoring_v4.py`
- **_safe_last()** (9 connections) — `src\analysis\signal_scoring_v4.py`
- **_rolling_rank()** (5 connections) — `src\analysis\signal_scoring_v4.py`
- **_score_candle_v4()** (4 connections) — `src\analysis\signal_scoring_v4.py`
- **_score_momentum_v4()** (4 connections) — `src\analysis\signal_scoring_v4.py`
- **_score_trend_v4()** (4 connections) — `src\analysis\signal_scoring_v4.py`
- **_score_volume_setup_v4()** (4 connections) — `src\analysis\signal_scoring_v4.py`
- **_score_volume_trigger_v4()** (4 connections) — `src\analysis\signal_scoring_v4.py`
- **calculate_signal_score_v4()** (3 connections) — `src\analysis\signal_scoring_v4.py`
- **_detect_blockers_v4()** (3 connections) — `src\analysis\signal_scoring_v4.py`
- **_detect_divergence()** (3 connections) — `src\analysis\signal_scoring_v4.py`
- **_percentile_rank()** (3 connections) — `src\analysis\signal_scoring_v4.py`
- **_score_divergence_v4()** (3 connections) — `src\analysis\signal_scoring_v4.py`
- **_score_prop_trading_v4()** (3 connections) — `src\analysis\signal_scoring_v4.py`
- **_score_regime_align_v4()** (3 connections) — `src\analysis\signal_scoring_v4.py`
- **_score_structure_v4()** (3 connections) — `src\analysis\signal_scoring_v4.py`
- **_candle_quality()** (2 connections) — `src\analysis\signal_scoring_v4.py`
- **_score_confirmation_v4()** (2 connections) — `src\analysis\signal_scoring_v4.py`
- **blockers_text()** (1 connections) — `src\analysis\signal_scoring_v4.py`
- **reason_text()** (1 connections) — `src\analysis\signal_scoring_v4.py`
- **volume_score()** (1 connections) — `src\analysis\signal_scoring_v4.py`

## Relationships

- No strong cross-community connections detected

## Source Files

- `src\analysis\signal_scoring_v4.py`

## Audit Trail

- EXTRACTED: 104 (100%)
- INFERRED: 0 (0%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*