# Smart Money — Tổng quan & Lộ trình

## Mục tiêu

Xây dựng hệ thống phát hiện dòng tiền thông minh (institutional flow) cho từng mã cổ phiếu, bắt đầu từ dữ liệu daily đã có (tự doanh + khối ngoại), dần mở rộng ra tick data / intraday order flow, và tích hợp vào V5 scoring của app.

## Triết lý nền

Smart money **không phải** một con số duy nhất. Nó là composite của nhiều tín hiệu độc lập, mỗi tín hiệu đều có thể nhiễu. Kiến trúc chia lớp:

```
data layer (daily / tick)
    ↓
flow primitives  (prop, foreign, block, aggression, ...)
    ↓ mỗi primitive → normalized score [-1..+1] + confidence
composite smart money score
    ↓
tích hợp vào SignalScoreV5 như 1 component độc lập (setup_smartmoney)
```

Nguyên tắc cốt lõi: **mỗi primitive kèm confidence** (0..1). Ngày không có khối ngoại giao dịch → confidence của foreign primitive = 0, composite tự động rebalance weight sang primitive còn lại. V4 prop-score hiện tại chưa làm điều này.

## Cấu trúc thư mục tài liệu

| File | Nội dung |
|---|---|
| [README.md](README.md) | File này — overview và lộ trình tổng |
| [architecture.md](architecture.md) | Quyết định gộp vs tách, module layout, contracts |
| [phase_1_foundation.md](phase_1_foundation.md) | Foundation + 2 primitives đầu tiên (prop, foreign) |
| [phase_2_daily_enhancements.md](phase_2_daily_enhancements.md) | Divergence, concentration, persistence, toxic flow |
| [phase_3_tick_infrastructure.md](phase_3_tick_infrastructure.md) | Refactor abstraction để sẵn sàng cho tick data |
| [phase_4_tick_primitives.md](phase_4_tick_primitives.md) | Trade classification, OFI, block trades, VWAP... |
| [phase_5_adaptive.md](phase_5_adaptive.md) | Weight calibration, regime-dependent, symbol-class |
| [ui_display_guide.md](ui_display_guide.md) | Cách hiển thị 3 lớp (glance / card / deep dive) |

## Lộ trình cao cấp

| Phase | Mục tiêu | Data cần | Deliverable chính |
|---|---|---|---|
| **1** | Foundation + prop + foreign primitives | Daily (đã có) | `smart_money/` module, composite v1, tích hợp V5 |
| **2** | Nâng chất lượng primitives daily | Daily (đã có) | Divergence, concentration, toxic flow detection |
| **3** | Hạ tầng cho tick data | — (refactor) | Abstract `FlowSource`, bar-size agnostic primitives |
| **4** | Tick data primitives | Tick data (cần chuẩn bị nguồn) | OFI, block trades, VWAP, auction flow |
| **5** | Adaptive & learning | Backtest history | Weight calibration, regime-aware weights |

## Thứ tự ưu tiên thực dụng

| Sprint | Làm gì | Vì sao |
|---|---|---|
| 1 | Phase 1.1-1.5 (foundation + 2 primitives + composite) | Giá trị ngay, abstraction đúng cho về sau |
| 2 | Phase 1.6 + backtest so với V4 | Validate trước khi đi sâu |
| 3 | Phase 2.1 (divergence) + 2.4 (toxic flow) | ROI cao nhất trên daily data |
| 4 | Phase 2.2, 2.3 | Hoàn thiện daily primitives |
| 5 | Phase 3 toàn bộ (refactor interface) | **Không skip** — Phase 4 sẽ đau nếu skip |
| — | Quyết định nguồn tick data | **Blocker** cho Phase 4 |
| 6+ | Phase 4 | |

## Quyết định đã chốt

- **Gộp vào app hiện tại**, không tách repo. Chi tiết xem [architecture.md](architecture.md).
- **Tách module** `src/analysis/smart_money/` độc lập, signal_scoring chỉ import một chiều.
- **Smart money weight tổng ≤ 15% final score** cho đến khi có bằng chứng backtest cho phép tăng.

## Quyết định còn mở

- [ ] Nguồn tick data: SSI / VPS / Fiinquant / tự scrape? (blocker Phase 4)
- [ ] Storage format cho tick data: Parquet per symbol per day? (ảnh hưởng Phase 3.4)
- [ ] Có cần sector mapping không? (ảnh hưởng Phase 2.5 cross-section normalize)
- [ ] Có cần foreign ownership room data không? (ảnh hưởng confidence của foreign primitive)

## Rủi ro đã nhận diện

1. **Prop trading data quality không đều** — không phải mã nào cũng có data đủ mỗi phiên. Confidence phải phản ánh.
2. **Foreign full-room bias** — mã full room nhìn như distribution nhưng thực ra foreign không mua được.
3. **Outlier phá z-score** — 1 block trade lớn làm z-score 60 phiên vô nghĩa. Winsorize trước.
4. **Tick data VN quirks** — ATO/ATC là auction, lunch break, trade classification dễ fail.
5. **Overfit smart money** — giữ weight thấp cho đến khi có bằng chứng.

## Liên quan

- `src/analysis/signal_scoring_v4.py` — scoring hiện tại (có prop score thô)
- `src/analysis/score_config.py` — config V4 (sẽ có V5 kế thừa)
- `src/data/stock_data_loader.py` — `StockRecord` với `propTradingNetValue`, `buyForeignValue`, `sellForeignValue`
- `src/app/stock_selector_app.py` — app entry point, nơi tích hợp UI smart money
