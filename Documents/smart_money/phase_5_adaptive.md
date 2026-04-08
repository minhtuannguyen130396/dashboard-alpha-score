# Phase 5 — Adaptive & Learning

**Mục tiêu:** thay hard-coded weights bằng calibration dựa trên lịch sử. Weight thay đổi theo regime và symbol class.

**Điều kiện tiên quyết:** Phase 1-4 (hoặc ít nhất Phase 1-3) đã ổn, có lịch sử backtest đủ dài (≥ 2 năm).

**Tinh thần:** giữ simple, không ML phức tạp. Logistic regression + rule-based buckets là đủ.

## 5.1. Weight calibration qua logistic regression

**File:** `src/analysis/smart_money/calibration/weight_calibrator.py`

### Data prep

Với mỗi signal trong lịch sử:
```python
features = {
    "prop": primitive.prop.value,
    "foreign": primitive.foreign.value,
    "divergence": primitive.divergence.value,
    "concentration": primitive.concentration.value,
    # ... các primitive khác
}

target = 1 if forward_return_5d > 0.02 else 0  # binary: đạt 2% trong 5 ngày
```

### Fit

```python
from sklearn.linear_model import LogisticRegression

X = DataFrame(all_features)
y = Series(all_targets)

model = LogisticRegression(
    penalty='l2',
    C=1.0,
    max_iter=1000,
)
model.fit(X, y)

# Weights = coefficients, normalize về tổng 1
raw_weights = dict(zip(X.columns, model.coef_[0]))
positive_weights = {k: max(0, v) for k, v in raw_weights.items()}
total = sum(positive_weights.values())
calibrated = {k: v/total for k, v in positive_weights.items()}
```

### Ghi chú quan trọng
- Chỉ giữ weight dương (signal đúng hướng với return). Weight âm = primitive sai hướng → bỏ luôn.
- Không dùng model prediction runtime — chỉ lấy **weights** để dùng trong composite. Giữ logic composite đơn giản, interpretable.
- Chạy offline, output = `calibrated_weights.json`, composite load từ file.

### Regularization
L2 penalty = 1.0 là default. Nếu dataset nhỏ (< 10k signals) → tăng regularization để tránh overfit.

## 5.2. Regime-dependent weights

**Ý tưởng:** weight trong bull market khác bear market.

### Split training data theo regime

```python
for signal in history:
    regime = compute_vnindex_regime(signal.date)  # bull_trend/bear_trend/sideway
    training_buckets[regime].append(signal)

weights_by_regime = {}
for regime, signals in training_buckets.items():
    weights_by_regime[regime] = calibrate_weights(signals)
```

### Runtime
```python
def _get_weights(cfg, market_regime):
    if cfg.use_regime_weights:
        return cfg.regime_weights.get(market_regime, cfg.default_weights)
    return cfg.default_weights
```

### Ví dụ insight từ real data (hypothesis)
- Bull market: prop + foreign + concentration đều mạnh
- Bear market: divergence có predictive power cao hơn (catch đáy)
- Sideway: OFI intraday quan trọng hơn daily flow

## 5.3. Symbol-class buckets

**Ý tưởng:** large cap, mid cap, small cap có dynamics khác nhau.

### Phân loại

```python
def classify_symbol(symbol, records):
    avg_mcap = compute_avg_marketcap(records)
    if avg_mcap > 10_000e9:      # 10k tỷ
        return "large_cap"
    elif avg_mcap > 2_000e9:     # 2k tỷ
        return "mid_cap"
    else:
        return "small_cap"
```

### Insight (hypothesis)
- **Large cap (VN30):** smart money chủ yếu là foreign. Weight foreign > prop.
- **Mid cap:** cân bằng prop + foreign.
- **Small cap:** prop dominates (foreign ít quan tâm). Foreign signal noise → giảm weight.

### Calibrate per bucket
```python
weights_by_bucket = {}
for bucket, signals in bucketed.items():
    weights_by_bucket[bucket] = calibrate_weights(signals)
```

## 5.4. Combined: regime × symbol_class

```python
def _get_weights(cfg, regime, symbol_class):
    key = (regime, symbol_class)
    if key in cfg.weights_matrix:
        return cfg.weights_matrix[key]
    # Fallback ladder:
    return (
        cfg.weights_by_symbol.get(symbol_class)
        or cfg.weights_by_regime.get(regime)
        or cfg.default_weights
    )
```

### Cảnh báo
Matrix càng chi tiết → mỗi bucket cần càng nhiều data để fit ổn. Rule of thumb: ≥ 500 signals/bucket. Nếu thiếu → gộp buckets.

## 5.5. Expected value output

Thay vì chỉ output `composite ∈ [-1..+1]`, bonus: output **expected forward return** dựa trên historical bins.

### Calibration bins

```python
# Group historical signals by composite bin
bins = np.linspace(-1, 1, 21)  # 20 bins
expected_return_per_bin = {}
for bin_idx in range(20):
    signals_in_bin = [s for s in history if bins[bin_idx] <= s.composite < bins[bin_idx+1]]
    if len(signals_in_bin) >= 30:
        expected_return_per_bin[bin_idx] = mean(s.forward_return_5d for s in signals_in_bin)
```

### Runtime
```python
signal.expected_return_5d = lookup_bin(signal.composite, expected_return_per_bin)
```

Xuất ra UI: **"Smart Money +0.72 → historical avg +3.2% / 5d"** — user trực quan hơn nhiều so với con số trừu tượng.

## 5.6. Monitoring & drift detection

Calibrated weights **không phải fixed mãi mãi**. Market regime thay đổi → calibration cũ mất tác dụng.

### Drift metrics
- **Rolling PF của smart money component:** so sánh 90 ngày gần nhất vs 90-180 ngày trước. Nếu drop > 20% → cảnh báo re-calibrate.
- **Feature importance stability:** re-fit trên window gần nhất, nếu top features khác xa với production weights → re-calibrate.

### Auto-recalibration
- **Cronjob hàng tháng:** re-calibrate trên data mới nhất, output vào `calibrated_weights_candidate.json`
- **Không tự động deploy** — yêu cầu human approve sau khi xem diff

## 5.7. Config

```python
@dataclass
class SmartMoneyCalibration:
    use_calibrated_weights: bool = False    # start False, bật khi có weights
    weights_file: str = "calibrated_weights.json"
    use_regime_weights: bool = False
    use_symbol_class_weights: bool = False
    expected_return_bins_file: str = "expected_returns.json"
```

## 5.8. Calibration pipeline

**File:** `scripts/calibrate_smart_money.py`

```python
def main():
    # 1. Load historical signals (2+ năm)
    signals = load_signals_from_backtest("output/backtest_signals.parquet")

    # 2. Compute features + target
    df = prepare_features(signals)

    # 3. Split by regime + symbol class
    buckets = split_by_bucket(df)

    # 4. Calibrate each bucket
    weights_matrix = {}
    for key, bucket_df in buckets.items():
        if len(bucket_df) >= 500:
            weights_matrix[key] = calibrate(bucket_df)

    # 5. Compute expected return bins
    bins = compute_expected_return_bins(df)

    # 6. Save
    save_json("calibrated_weights.json", weights_matrix)
    save_json("expected_returns.json", bins)

    # 7. Report
    print_calibration_report(weights_matrix, bins)
```

## 5.9. Testing

- `test_calibrator.py` — synthetic data với known ground truth → weights output đúng hướng
- `test_calibration_loading.py` — composite load weights file đúng
- `test_drift_detection.py` — detect khi PF drop

## 5.10. Backtest protocol

Với calibrated weights, **phải dùng walk-forward**:
- Train trên 2020-2023
- Test out-of-sample 2024
- Re-calibrate cuối 2024
- Test out-of-sample 2025
- Không bao giờ dùng future data để calibrate past weights

## Deliverable Phase 5

- [ ] Weight calibrator + script
- [ ] Regime-dependent weights support
- [ ] Symbol-class bucket support
- [ ] Expected return bins + UI hiển thị
- [ ] Drift monitoring
- [ ] Walk-forward backtest report

## Ước lượng scope

~400-500 LOC + script calibration + data pipeline để chuẩn bị dataset training.

## Điều kiện nghiệm thu

- Calibrated weights trên 2 năm data → out-of-sample PF ≥ hard-coded weights × 1.1
- Không có overfitting rõ rệt (train vs test PF gap < 20%)
- Drift monitoring chạy tự động, có alert

---

**Cảnh báo cuối:** Phase 5 dễ rơi vào bẫy over-engineering. Nếu hard-coded weights của Phase 1-4 đã cho kết quả tốt, **không bắt buộc phải làm Phase 5**. Chỉ làm khi:
1. Đã có ≥ 2 năm signal history
2. Có bằng chứng hard-coded weights bị drift
3. Có thời gian maintain calibration pipeline
