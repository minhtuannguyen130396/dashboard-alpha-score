# SignalScoreV4

> God node · 15 connections · `src\analysis\signal_scoring_v4.py`

## What It Is

Dataclass kết quả của engine chấm điểm. Được `calculate_signal_score_v4()` tạo ra và `MarketBehaviorAnalyzer` tiêu thụ để ra quyết định BUY/SELL.

**Các trường chính:**
- `setup_score` / `trigger_score` — điểm hai cổng, [0..1], scoring engine tính độc lập
- `final_score` — weighted combination của hai cổng
- `regime` — chế độ thị trường hiện tại: `bull_trend`, `mild_bull`, `bullish_reversal`, `bear_trend`...
- `label` — tóm tắt: `"buy"`, `"sell"`, `"hold"`, `"none"`
- `blockers` — danh sách `Blocker` (hard/soft) giải thích lý do không trade

**Tại sao là god node:** `SignalScoreV4` kết nối scoring engine với analyzer (IndicatorGroup1-4, BullishPatterns, BearishPatterns, ScoreConfigV4) và với output layer (MarketBehaviorSnapshot, hover_payloads). Nó là interface contract giữa tầng tính điểm và tầng quyết định.

## Connections by Relation

### calls
- [[_build_score_v4()]] `EXTRACTED`
- [[calculate_signal_score_v4()]] `EXTRACTED`

### contains
- [[signal_scoring_v4.py]] `EXTRACTED`

### uses
- [[IndicatorGroup3]] `INFERRED`
- [[IndicatorGroup2]] `INFERRED`
- [[IndicatorGroup4]] `INFERRED`
- [[IndicatorGroup1]] `INFERRED`
- [[ScoreConfigV4]] `INFERRED`
- [[MarketBehaviorSnapshot]] `INFERRED`
- [[BearishPatterns]] `INFERRED`
- [[BullishPatterns]] `INFERRED`
- [[Container for derived market behavior signals and overlays.]] `INFERRED`
- [[Compute one hover payload per trading day.
 
     All indicators are calculated]] `INFERRED`
- [[Buy when setup is solid, both gates clear and no hard blocker.
 
     Three-stag]] `INFERRED`
- [[Asymmetric sell: looser thresholds, but suppressed in bull regimes.
 
     Ratio]] `INFERRED`

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*