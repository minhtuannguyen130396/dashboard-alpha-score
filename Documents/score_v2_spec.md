# Score V2 Specification

## Muc tieu

Score v2 can sua 3 van de cua v1:
- Qua phu thuoc vao mo hinh nen dao chieu.
- Context va pivot con tho, de bi nhieu trong sideway.
- Chua tach ro giai doan "co setup" va "du dieu kien kich hoat".

## Nguyen tac

- Khong look-ahead bias.
- Moi score ngay `t` chi duoc dung du lieu `<= t`.
- Score phai giai thich duoc bang cac thanh phan nho.
- Uu tien config hoa threshold va weight.

## Cau truc de xuat

```python
@dataclass
class SignalScoreV2:
    label: str
    regime: str
    setup_score: float
    trigger_score: float
    final_score: float
    candle_score: float
    trend_score: float
    momentum_score: float
    volume_score: float
    structure_score: float
    confirmation_score: float
    blockers: List[str]
    reasons: List[str]
```

## Nhom score

### 1. Candle score

Muc dich:
- Van giu vai tro cua mo hinh nen, nhung khong de no chi phoi qua manh.

Thanh phan:
- reversal pattern strength
- continuation pattern strength
- body/range quality
- wick asymmetry

Goi y scale:
- `0.0` = khong co mo hinh dang chu y
- `0.5` = co dau hieu nhung trung binh
- `1.0` = mo hinh ro va dep

Weight goi y:
- `0.15`

### 2. Trend score

Muc dich:
- Do suc manh va huong cua xu huong nen.

Thanh phan:
- vi tri gia so voi EMA20, EMA50, EMA100
- do doc EMA20 va EMA50
- khoang cach EMA20-EMA50
- ADX14

Huong bullish:
- continuation bullish: uu tien `close > EMA20 > EMA50`
- reversal bullish: chap nhan downtrend nhung can co dau hieu giam luc ban

Huong bearish lam nguoc lai.

Weight goi y:
- `0.20`

### 3. Momentum score

Thanh phan:
- RSI14
- MACD histogram
- ROC hoac momentum ngan han

Goi y:
- reversal bullish manh khi RSI thoat oversold va MACD histogram cai thien
- continuation bullish manh khi RSI nam tren trung tinh va MACD > signal

Weight goi y:
- `0.15`

### 4. Volume score

Thanh phan:
- relative volume 20 phien
- range / ATR14
- OBV slope hoac MFI / CMF
- volume expansion di cung huong gia

Weight goi y:
- `0.20`

### 5. Structure score

Thanh phan:
- swing low / swing high 10 phien
- swing low / swing high 20 phien
- khoang cach toi support / resistance
- false break hay giu duoc vung

Weight goi y:
- `0.15`

### 6. Confirmation score

Thanh phan:
- close vuot high/low cua 1-3 phien truoc
- breakout khoi sideway ngan
- follow-through o phien tiep theo
- retest giu duoc muc vua vuot

Luu y:
- Neu score dang tinh tai cuoi ngay, confirmation co the chia 2 muc:
  - immediate confirmation tai ngay hien tai
  - delayed confirmation tai ngay ke tiep trong backtest

Weight goi y:
- `0.15`

## Tong hop score

### Setup score

Dung de danh dau phien "dang theo doi", chua chac da vao lenh.

Cong thuc goi y:

```text
setup_score =
  0.20 * candle_score +
  0.25 * trend_score +
  0.20 * momentum_score +
  0.20 * volume_score +
  0.15 * structure_score
```

### Trigger score

Dung de kich hoat diem mua/ban.

Cong thuc goi y:

```text
trigger_score =
  0.35 * confirmation_score +
  0.25 * volume_score +
  0.20 * candle_score +
  0.10 * momentum_score +
  0.10 * structure_score
```

### Final score

```text
final_score = 0.55 * setup_score + 0.45 * trigger_score
```

## Threshold goi y

- `setup_watch_threshold = 0.55`
- `setup_good_threshold = 0.65`
- `trigger_threshold = 0.70`
- `strong_signal_threshold = 0.80`

## Blockers goi y

Vi du blockers:
- ADX qua thap, sideway nhieu
- volume yeu
- close dang nam sat resistance
- MACD va RSI phan ky nguoc
- mo hinh nen dep nhung khong co breakout

Neu co blocker manh:
- co the tru diem truc tiep
- hoac van giu score nhung chan `buy_point` / `sale_point`

## Config hoa

Nen tao file:

`src/analysis/score_config.py`

Noi dung goi y:
- thresholds
- weights
- indicator periods
- feature toggles

## Tich hop voi he thong hien tai

- `signal_scoring.py`
  - them `calculate_signal_score_v2`
  - giu lai `calculate_signal_score` de so sanh A/B
- `market_behavior_analyzer.py`
  - them logic su dung `setup_score`, `trigger_score`, `blockers`
- `backtest_runner.py`
  - cho phep chon `score_version="v1" | "v2"`

## Backtest toi thieu

- Backtest toan bo danh sach hien co.
- Tach theo nhom:
  - VN30
  - Large Cap
  - Mid Cap
  - Other
- So sanh v1 va v2 theo:
  - win rate
  - avg gain
  - avg loss
  - expectancy
  - max drawdown
  - profit factor
  - number of trades

