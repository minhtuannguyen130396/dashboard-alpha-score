# UI Display Guide — Smart Money

**Nguyên tắc cốt lõi:** progressive disclosure — 3 lớp từ ngoài vào trong. Nếu hiển thị 30 cột một lúc, user bỏ qua toàn bộ.

## Lớp 1 — Glance (bảng danh sách mã)

**Không gian:** 1 cột, < 6 ký tự hiển thị.
**Mục đích:** liếc qua là hiểu; dùng để filter/sort nhanh.

### Format

```
Mã    Score  SM     ...
FPT   0.72   ●●●↑   ← composite strong bullish + đang accelerate
HPG   0.68   ●●○    ← medium bullish, stable
VIC   0.55   ●○○↓   ← weak, đang xấu đi
MWG   0.60   ✕      ← TOXIC FLOW (giá tăng nhưng SM bán)
ABC   0.45   ─      ← neutral / confidence thấp
DEF   0.50   ●●●↑*  ← strong với divergence (bonus marker)
```

### Ký hiệu

| Ký hiệu | Nghĩa |
|---|---|
| `●●●` | Strong (`\|composite\| ≥ 0.6`) |
| `●●○` | Medium (`\|composite\| ≥ 0.3`) |
| `●○○` | Weak (`\|composite\| > 0`) |
| `─` | Neutral hoặc confidence < 0.3 |
| `✕` | Toxic flow — cảnh báo đỏ |
| `↑` | Composite acceleration (tuần này > tuần trước) |
| `↓` | Composite deceleration |
| `*` | Bonus marker: divergence hoặc load-up day detected |

### Màu

- **Xanh lá** — composite dương (bullish SM)
- **Đỏ** — composite âm (bearish SM)
- **Xám** — neutral / low confidence
- **Đỏ đậm + bold** — toxic

**Nguyên tắc:** màu theo **hướng**, độ đậm/số chấm theo **strength**. Không đổi màu theo strength.

### Tooltip on hover

1 câu tóm tắt:
```
"Smart Money +0.72 • prop mua 8/10 phiên • foreign cùng chiều"
```

## Lớp 2 — Card chi tiết (khi click 1 mã)

**Không gian:** half-screen panel hoặc modal.
**Mục đích:** hiểu rõ lý do score, chuẩn bị quyết định trade.

### 4 block chính

#### Block A — Composite (top, lớn nhất)

```
┌─────────────────────────────────────────┐
│  SMART MONEY                            │
│                                         │
│  +0.72  Strong Bullish                  │
│  ████████████████░░░░░░  (gauge -1→+1)  │
│                                         │
│  Confidence: ●●●●○  (0.85 — good)       │
│  Trend: ↑ strengthening (5d)            │
│                                         │
│  Expected: +3.2% / 5d (from history)    │ ← Phase 5
└─────────────────────────────────────────┘
```

Gauge horizontal rõ ràng, kim chỉ vào 0.72. Không dùng circular gauge — khó đọc nhanh.

#### Block B — Breakdown theo primitive (tách theo bucket)

Quan trọng: Block B **phản chiếu đúng contract backend**. Chỉ primitive đóng điểm (có `bucket="setup"` hoặc `bucket="trigger"`) mới xuất hiện dưới dạng bar. Persistence và toxic flow **không phải primitive đóng điểm** — chúng xuất hiện ở vị trí khác với ý nghĩa khác.

```
┌────────────────────────────────────────────────┐
│ SETUP BUCKET                   +0.72  conf 85% │  ← setup_composite
│ ├ Tự doanh (prop)     ████████░░  +0.80  ↑   │
│ └ Khối ngoại          ██████░░░░  +0.60  →   │
│                                                │
│ Persistence 18/20 ngày cùng chiều → ×0.95      │  ← multiplier, không phải bar
│                                                │
│ TRIGGER BUCKET                 +0.45  conf 60% │  ← trigger_composite
│ ├ Divergence          ██░░░░░░░░  +0.20  ↑   │
│ ├ Concentration       █████░░░░░  +0.50       │
│ │  — intraday (Phase 4) —                      │
│ ├ Order Flow Imbalance██████░░░░  +0.60       │
│ ├ Block Trades        ████░░░░░░  +0.40  ●5   │
│ ├ VWAP Position       ███░░░░░░░  +0.30       │
│ ├ Auction Flow        ██░░░░░░░░  +0.20       │
│ └ Intraday Divergence ░░░░░░░░░░   0.00  (—) │
└────────────────────────────────────────────────┘
```

### Quy tắc render cứng

- **Mỗi bucket có 1 header row** hiển thị composite + confidence của bucket đó (`setup_composite`, `setup_confidence` và `trigger_composite`, `trigger_confidence`). User thấy đóng góp thực tế vào `setup_score` vs `trigger_score`, khớp với backend.
- **Chỉ primitives `bucket="setup"` nằm dưới SETUP BUCKET header**, **chỉ primitives `bucket="trigger"` nằm dưới TRIGGER BUCKET header**. Không bao giờ trộn.
- **Thứ tự primitive trong mỗi bucket** lấy từ key của `setup_weights` / `trigger_weights` trong config, không hard-code ở UI.
- Mỗi bar primitive click được → drill-down Lớp 3.
- Primitive có `confidence = 0` vẫn show nhưng xám hẳn + label "(—)" hoặc "no data", không ẩn hẳn.

### Persistence — hiển thị riêng, không phải bar

Persistence **không có `bucket` và không đóng điểm**. Backend dùng nó làm multiplier cho `setup_confidence`. UI phản ánh đúng:

- Hiển thị **dưới header SETUP BUCKET** như 1 dòng text annotation (không phải bar)
- Format gợi ý: `Persistence 18/20 ngày cùng chiều → ×0.95`
  - Phần trái: human-readable ("18/20 ngày cùng chiều", "11/20 dao động")
  - Mũi tên `→` trỏ sang multiplier đã áp dụng: `×0.95` (khi persistence cao → giữ gần 1.0) hoặc `×0.62` (khi dao động → kéo xuống gần 0.5)
- **Không** có bar, không có value signed — vì persistence không có "hướng" theo nghĩa bullish/bearish
- Click vào dòng annotation → drill-down Lớp 3 xem persistence.components
- Nếu `cfg.use_persistence = False` → ẩn dòng này hoàn toàn

**Lý do không dùng bar:** bar gợi ý "đang đóng 0.7 điểm vào composite" — sai với contract backend. User sẽ nhầm persistence là primitive như prop/foreign và cộng nhẩm sai.

### Toxic flow — hiển thị ở Block A (header), không phải Block B

Toxic cũng không phải primitive đóng điểm — là hard blocker. UI đã có xử lý riêng ở Block A (xem "Toxic case" bên dưới). **Không** xuất hiện như một row trong Block B breakdown.

### Trigger bucket trống (Phase 1)

Ở Phase 1 chưa có primitive trigger → `trigger_composite = 0`, `trigger_confidence = 0`. UI render header TRIGGER BUCKET với placeholder:

```
│ TRIGGER BUCKET                  0.00  (—)     │
│   No trigger primitives enabled yet            │
```

Không ẩn toàn bộ bucket — user phải biết bucket tồn tại nhưng chưa bật.

#### Block C — Flow chart mini (20 phiên gần nhất)

2 line đơn giản trên cùng chart:

```
Price  ────╱╲__╱╲___╱─╲__╱       (line xanh dương)
              ╱
Flow   ______╱─────╱──╱           (line cam, cumulative prop+foreign)
```

- Line 1: giá close
- Line 2: cumulative smart money flow
- Nếu **lệch pha** → hiển thị badge "⚠ DIVERGENCE" góc trên phải
- Nếu **toxic** → background đỏ nhạt + label "⚠ TOXIC FLOW"

**Nguyên tắc:** nhìn 1 giây là thấy cùng pha hay lệch pha. Không cần axis labels cầu kỳ.

#### Block D — Narrative (1-2 câu tự sinh)

```
"Tự doanh mua ròng 8/10 phiên gần nhất (tổng +45 tỷ).
 Khối ngoại cùng chiều nhẹ. Phiên hôm nay là load-up day
 (chiếm 35% tổng net 20 phiên)."
```

- Generated from primitive components (deterministic, không LLM runtime)
- Vị trí: dưới Block A hoặc trong Block A
- Đây là **giá trị cao nhất** cho user không rành — câu chuyện > con số

### Toxic case — layout thay đổi

Khi `is_toxic = True`, Block A đổi:

```
┌─────────────────────────────────────────┐
│  ⚠ TOXIC FLOW DETECTED                  │
│                                         │
│  Giá +5.2% trong 5 ngày nhưng           │
│  smart money bán ròng -38 tỷ            │
│                                         │
│  → Likely retail trap                   │
│  → Bullish signals will be blocked      │
└─────────────────────────────────────────┘
```

Background đỏ nhạt. Block B vẫn show bình thường. Block C background toxic highlight.

## Lớp 3 — Deep dive (drill-down)

**Không gian:** full panel/modal, riêng cho user nâng cao.
**Mục đích:** debug, verify, build trust.

### Khi nào show

- Click vào 1 bar primitive trong Block B
- Click vào dòng Persistence annotation (drill tới `PersistenceSignal.components`)
- Click "Deep dive" button ở card

### Nội dung

#### Tab "Raw data"
Bảng 20 phiên:
```
Date       Close  Chg%   Prop_Net  Foreign_Net  Combined  Volume
2026-04-07 45.2  +1.3%  +2.1B    +0.8B        +2.9B     1.2M
2026-04-06 44.6  -0.5%  +1.5B    -0.2B        +1.3B     0.8M
...
```

#### Tab "Z-score chart"
Chart theo thời gian của từng primitive (line chart), để user thấy evolution chứ không chỉ snapshot hôm nay.

#### Tab "Components"
Break xuống raw components của primitive được click:
```
Prop flow primitive:
  short_sum (10d):    +18.5B tỷ
  long_sum (20d):     +32.1B tỷ
  today:              +2.1B tỷ
  avg_traded_value:   45.0B tỷ/day
  short_ratio:        +0.041  (18.5 / (45 × 10))
  long_ratio:         +0.036
  today_ratio:        +0.047

  Normalized value:   +0.80
  Confidence:         0.95 (19/20 days have prop data)
```

#### Tab "Blockers & penalties"
Show bất kỳ hard/soft blocker nào đang active, giúp user hiểu vì sao score cuối = X. Toxic flow (nếu có) xuất hiện ở đây với đầy đủ thông tin (price delta 5d, smart money delta 5d, threshold, lý do trigger).

#### Tab "Scoring math"
Bảng phân rã đúng cách backend cộng điểm — giúp user verify không có double-counting:

```
Setup bucket
  setup_composite:       +0.72
  setup_confidence:      0.85  (sau persistence ×0.95)
  setup_smartmoney:      0.10  (weight từ ScoreWeightsV5)
  → contribution to setup_score: 0.72 × 0.85 × 0.10 = +0.0612

Trigger bucket
  trigger_composite:     +0.45
  trigger_confidence:    0.60
  trigger_smartmoney:    0.12
  → contribution to trigger_score: 0.45 × 0.60 × 0.12 = +0.0324

Persistence multiplier: ×0.95 (đã áp trên setup_confidence phía trên)
Toxic flag: False (không blocker)
```

Tab này **phải khớp với logic trong `_build_score_v5`** — là tool verify ngăn chặn drift giữa UI và backend.

## Filter & sort UI

Thêm vào sidebar filter:

```
☐ Only bullish SM (composite > +0.3)
☐ Only bearish SM (composite < -0.3)
☐ Hide toxic flow
☐ High confidence only (≥ 0.6)
☐ With divergence signal           (Phase 2)
☐ With intraday confirmation       (Phase 4)
```

Sort options:
- Sort by SM composite (desc/asc)
- Sort by SM confidence
- Sort by expected return (Phase 5)

## Tích hợp cụ thể với app hiện tại

### `src/app/stock_selector_app.py`

1. **Bảng selector chính** → thêm cột `SM` sau cột `Score`
   - Render theo Lớp 1 format
   - Sortable, filterable

2. **Hover payload / card chi tiết mã**
   - App hiện tại đã có breakdown các component score
   - Thêm 1 section "Smart Money" có 4 block (A/B/C/D)
   - Không đổi layout chính — chỉ thêm

3. **Filter panel** → thêm smart money filters

4. **Report output** (nếu có export HTML)
   - Mỗi mã trong report có smart money card (Lớp 2)

### Chart rendering

- Dùng thư viện chart đang có trong app
- Không introduce thư viện mới chỉ vì smart money
- Nếu app dùng plotly → dùng plotly; matplotlib → dùng matplotlib

## Do's & Don'ts

### Do
- ✅ Confidence luôn hiện cùng score
- ✅ Toxic flow phải nổi bật
- ✅ Màu theo hướng, đậm nhạt theo strength
- ✅ Narrative > số > chart (theo thứ tự ưu tiên đọc)
- ✅ Tất cả primitives đều show kể cả khi confidence thấp (xám)

### Don't
- ❌ Hiển thị số thập phân > 2 chữ số ở glance (`+0.72` được, `+0.7234` không)
- ❌ Ẩn primitive không có data (user không biết tại sao)
- ❌ Đổi màu theo strength (xanh nhạt → xanh đậm theo độ mạnh — gây confusion)
- ❌ Circular gauge cho composite (khó đọc so với bar horizontal)
- ❌ Spam icons/emojis trong glance layer (chỉ dùng ● ○ ↑ ↓ ✕ ─)
- ❌ Giấu toxic flow trong dropdown — phải luôn thấy ngay

## Trùng lặp có chủ đích

Cùng 1 thông tin xuất hiện 2-3 dạng (số, bar, câu). Đây **không phải** lỗi thiết kế — mà là cách user cross-check và tự build intuition. Beginner đọc câu trước, advanced scan số trước, ai cũng phục vụ được.

## Accessibility

- Không chỉ dựa vào màu. Ký hiệu ● ○ ↑ ↓ phải reliable kể cả khi colorblind.
- Tooltip text readable, không chỉ emoji.

## Phase rollout UI

- **Phase 1 done** → Lớp 1 + Block A + Block D (narrative). Block B đã có khung 2 bucket, nhưng TRIGGER BUCKET sẽ luôn ở trạng thái "no trigger primitives enabled yet" vì Phase 1 chưa có primitive trigger. SETUP BUCKET có 2 bar (prop, foreign).
- **Phase 2 done** → TRIGGER BUCKET bật lên với divergence + concentration. Thêm dòng annotation Persistence dưới SETUP BUCKET header (nếu `use_persistence=True`). Thêm toxic display ở Block A + toxic tab ở Lớp 3 Blockers & penalties. Bật tab "Scoring math" ở Lớp 3.
- **Phase 3** → Không đổi UI. Chỉ refactor backend — UI layer đọc `SmartMoneySignal` qua cùng contract `setup_composite/trigger_composite`, không cần biết data đến từ đâu.
- **Phase 4** → TRIGGER BUCKET thêm 5 row intraday (ofi, block_trade, vwap, auction, intraday_divergence). Không tạo bucket mới — tất cả vẫn nằm dưới TRIGGER BUCKET header cùng divergence/concentration. Block B có thể chèn divider `— intraday —` trong TRIGGER BUCKET cho dễ đọc, nhưng **header bucket không tách**.
- **Phase 5** → Block A thêm dòng "Expected return: +3.2% / 5d (from history)". Tab "Scoring math" thêm cột weight calibration source (hard-coded vs calibrated).

UI tăng dần cùng với backend. Không cần thiết kế hoàn chỉnh UI từ đầu rồi mới làm backend.

## Drift prevention

Do UI đã đồng bộ với backend contract ở nhiều tầng (bucket, persistence multiplier, toxic flag, scoring math tab), **UI không được render bất cứ thứ gì không có trong `SmartMoneySignal`**. Quy tắc:

- Không tính toán lại composite ở client (chỉ đọc từ `SmartMoneySignal.setup_composite`, `trigger_composite`, `composite`)
- Không gọi lại primitive tại client
- Không hard-code danh sách primitive ở UI code — iterate `SmartMoneySignal.primitives` và group theo `p.bucket`
- Nếu backend thêm primitive mới + khai báo bucket → UI tự động render đúng chỗ, không cần sửa UI code

Test integration: snapshot test — cùng fixture `SmartMoneySignal` → UI render cùng HTML. Đổi contract backend mà quên update UI sẽ làm test fail.
