# Score V2 Implementation Notes

Tai lieu nay dung cho luc bat dau code `score v2`.

## File uu tien sua

- `src/analysis/signal_scoring.py`
- `src/analysis/technical_indicators.py`
- `src/analysis/market_behavior_analyzer.py`

## Chien luoc nang cap

1. Khong xoa `v1` ngay lap tuc.
2. Them `SignalScoreV2`.
3. Them config rieng cho weight va threshold.
4. Giu duong lui de A/B test.

## De xuat ham moi

Trong `signal_scoring.py`:
- `_score_trend_v2`
- `_score_momentum_v2`
- `_score_volume_quality_v2`
- `_score_structure_v2`
- `_score_confirmation_v2`
- `_build_signal_score_v2`
- `calculate_signal_score_v2`

Trong `technical_indicators.py`:
- `IndicatorGroup2.rsi` neu chua co ban on dinh
- `IndicatorGroup2.macd` review lai output va tail handling
- `IndicatorGroup2.adx`
- helper swing high / swing low
- helper rolling zscore hoac percentile ranking

## Nguyen tac coding

- Moi ham score tra ve:
  - score
  - reason
  - raw metrics
- Tach bullish va bearish, nhung dung chung helper khi co the.
- Neu khong du du lieu, tra ve score trung tinh hoac score 0 kem reason.

## Dieu can tranh

- Khong hard-code weight trong nhieu noi.
- Khong de 1 indicator quyet dinh toan bo score.
- Khong dung du lieu tuong lai de xac nhan breakout.
- Khong tron setup voi trigger trong cung 1 bien ma khong giai thich.

## Muc tieu kha thi cho iteration dau

- V2 phai chay duoc tren luong backtest hien tai.
- V2 phai ghi ra:
  - `final_score`
  - `setup_score`
  - `trigger_score`
  - `label`
  - `reasons`
  - `blockers`
- Chart va report chi can hien thi `final_score` o buoc dau.

