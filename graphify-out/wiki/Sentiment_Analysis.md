# Sentiment Analysis

> Community · `src\sentiment\`

## Summary

Module phân tích tâm lý thị trường từ dữ liệu tick realtime — **độc lập hoàn toàn** với scoring pipeline chính (signal_scoring_v4/v5). Là Flask web app riêng, không được gọi từ `main.py`.

**Kiến trúc:**

**`app.py`** — Flask web server phục vụ tick sentiment analysis. Load cấu hình từ `src/sentiment/.env`. Expose REST API để trigger phân tích theo symbol + date.

**`tick_loader.py`** — Load tick data từ JSONL files: `data/<SYMBOL>/updatetrades/<YEAR>/<date>.json`. Cũng load OHLCV reference cho context. Đây là nguồn tick data **khác** với `tick_storage.py` của Smart Money (dùng parquet, riêng folder `data_tick/`).

**`metrics_engine.py`** — Tính toán sentiment metrics từ tick data: Fear & Greed index, whale activity (giao dịch lớn ≥ 2 tỷ VND), aggression index (tỷ lệ market order vs limit order), theo từng khung giờ trong phiên. Không dùng ML — thuần heuristic trên tick patterns.

**`ai_analyst.py`** — Gửi metrics đã tính lên **Google Gemini** (default: `gemini-flash-latest`) để sinh commentary tự nhiên bằng tiếng Việt. Dùng `sentiment_guide.md` làm system prompt. Build history summary từ các phiên trước để AI có context.

**`history_store.py`** — Lưu/load kết quả phân tích vào `sentiment_history/<SYMBOL>/<date>.json`. Mỗi entry gồm: date, session, metrics dict, ai_analysis dict.

## Source Files

- `src\sentiment\app.py`
- `src\sentiment\tick_loader.py`
- `src\sentiment\metrics_engine.py`
- `src\sentiment\ai_analyst.py`
- `src\sentiment\history_store.py`

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*
