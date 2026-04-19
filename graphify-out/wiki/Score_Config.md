# Score Config

> Community · `src\analysis\score_config.py`

## Summary

Tập trung toàn bộ số magic (weights, thresholds, penalties) của scoring engine vào một chỗ duy nhất — tách rõ "cấu hình" ra khỏi "logic". Cho phép tuning mà không cần đụng vào code scoring.

**Các dataclasses:**

- **`ScoreWeightsV4`** — trọng số từng component trong setup và trigger. Setup components: candle (0.15), trend (0.22), momentum (0.13), volume (0.13), structure (0.17), regime (0.10), prop (0.10). Trigger: confirmation (0.35), volume (0.25), candle (0.20), momentum (0.10), divergence (0.10). Final: setup×0.55 + trigger×0.45.

- **`ScoreThresholdsV4`** — ngưỡng quyết định: entry gates (final 0.48, trigger 0.43), sell gates (final 0.50, trigger 0.42 — thoáng hơn entry vì ATR stop quản lý risk), hard blockers (ADX<10, RVOL<0.3), soft blocker penalties.

- **`ScoreConfigV4`** — bundle weights + thresholds + rolling window (120 bars). `DEFAULT_SCORE_CONFIG_V4` là instance mặc định dùng toàn hệ thống.

- **`ScoreConfigV5`** — mở rộng V4, thêm `smart_money_weight` để blend smart money score vào setup. `.v4_compat()` trả về V4-compatible config cho backward compatibility.

## Source Files

- `src\analysis\score_config.py`

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*
