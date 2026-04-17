# Tick Sentiment Analyzer

Web app phân tích tâm lý thị trường từ dữ liệu tick chứng khoán Việt Nam.

## Chạy app

```bash
cd E:\Trader\support_trade_stock_tool
python src/sentiment/app.py
# Mở http://localhost:5000
```

## Cấu trúc

```
src/sentiment/
├── app.py              # Flask web server (routes: /, /api/analyze, /api/dates, /api/history, /api/batch_analyze)
├── tick_loader.py      # Đọc tick JSONL + daily OHLCV
├── metrics_engine.py   # Tính toán chỉ số
├── ai_analyst.py       # Gọi Gemini AI (model: gemini-flash-latest)
├── history_store.py    # Lưu/đọc JSON history
├── sentiment_guide.md  # System prompt hướng dẫn AI
├── .env                # GOOGLE_API_KEY=...
└── templates/index.html
```

## Dữ liệu đầu vào

**Tick data (JSONL):** `data/<SYMBOL>/updatetrades/<YEAR>/<YYYY-MM-DD>.json`
```json
{"ts": "2026-04-10T09:15:41", "price": 31.8, "volume": 316600, "side": "B", "trading_date": "2026-04-10"}
```
- `side`: `"B"` = mua chủ động, `"S"` = bán chủ động, `null` = ATO/ATC

**Daily OHLCV:** `data/<SYMBOL>/<YEAR>/<YYYY-MM-DD>.json`
- Fields: `priceOpen`, `priceClose`, `priceHigh`, `priceLow`, `buyForeignQuantity`, `sellForeignQuantity`, `propTradingNetDealValue`

## Metrics được tính (`metrics_engine.py`)

| Metric | Ý nghĩa |
|--------|---------|
| `aggression.ratio_vol` | Buy vol / Sell vol. >1.2=bullish, <0.8=bearish |
| `whale.net` | Whale net (top 5% vol). >0=tích lũy, <0=phân phối |
| `whale.buy_vwap / sell_vwap` | VWAP mua/bán của cá mập |
| `bot.pct` | % lệnh bot (volume lặp ≥10 lần) |
| `hourly_flow` | Dòng tiền buy/sell/net theo giờ |
| `flow_5m` | Dòng tiền 5 phút |
| `order_distribution` | Phân bổ lệnh theo kích thước (<1K, 1-5K, ..., >100K) |
| `momentum.parts` | 3 phần đầu/giữa/cuối phiên |
| `price_sensitivity.asymmetry` | >1.3=fear, <0.7=greed |
| `fear_greed.score` | Tổng hợp -7 đến +7 (5 yếu tố) |
| `large_orders` | Top 15 lệnh lớn nhất |

**Fear & Greed labels:** `EXTREME_FEAR` / `FEAR` / `SLIGHT_FEAR` / `NEUTRAL` / `SLIGHT_GREED` / `GREED` / `EXTREME_GREED`

## Lưu lịch sử

**Path:** `sentiment_history/<SYMBOL>/<YYYY-MM-DD>.json`
```json
{
  "symbol": "TCB", "date": "2026-04-10", "session": "full",
  "metrics": { ... },
  "ai_analysis": {
    "sentiment_label": "EXTREME_GREED", "score": 4,
    "summary": "...", "key_signals": [...],
    "vs_history": "...", "whale_interpretation": "...",
    "risk_level": "LOW", "outlook": "...", "recommendation": "..."
  }
}
```

## AI Output (Gemini)

AI trả về JSON tiếng Việt gồm 8 trường:
`sentiment_label`, `score`, `summary`, `key_signals`, `vs_history`, `whale_interpretation`, `risk_level`, `outlook`, `recommendation`

Nếu không có API key → fallback sang `analyze_without_ai()` (rule-based, cùng format output).

## Kết quả đã verify (TCB tháng 4/2026)

| Ngày | Session | F&G Score | Label |
|------|---------|-----------|-------|
| 08/04 | full | +4 | EXTREME_GREED |
| 09/04 | full | +2 | GREED |
| 10/04 | full | +4 | EXTREME_GREED |
| 13/04 | morning | -3 | FEAR |
