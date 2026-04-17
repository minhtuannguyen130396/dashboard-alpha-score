## graphify

This project has a graphify knowledge graph at graphify-out/.

Rules:
- Before answering architecture or codebase questions, read graphify-out/GRAPH_REPORT.md for god nodes and community structure
- If graphify-out/wiki/index.md exists, navigate it instead of reading raw files
- After modifying code files in this session, run `python3 -c "from graphify.watch import _rebuild_code; from pathlib import Path; _rebuild_code(Path('.'))"` to keep the graph current

## Project Overview

Hệ thống chấm điểm tín hiệu giao dịch cổ phiếu Việt Nam. Entry point: `main.py` → `create_stock_selector_app()` (desktop UI tkinter).

**Luồng chính:**
1. User chọn mã cổ phiếu + ngày trong UI
2. Fetch lịch sử giá từ FireAnt API (`src/data/fireant_history_fetcher.py`)
3. Tính chỉ báo kỹ thuật (`src/analysis/technical_indicators.py`)
4. `SignalScoreV4` chấm điểm theo hai cổng: setup_score (xu hướng) + trigger_score (điều kiện vào lệnh), có hard/soft blockers và regime alignment
5. Smart Money layer (`src/analysis/smart_money/`) phân tích dòng tiền tổ chức: prop flow, foreign flow, OFI, block trades, divergence
6. `MarketBehaviorAnalyzer` ra quyết định BUY/SELL cuối cùng mỗi bar
7. HTML chart tương tác được render qua TradingView Lightweight Charts (`src/reporting/chart_renderer_v2.py`)
8. Backtest chạy qua `TradeSimulatorV4` (single-position long-only, luật VN T+3)

**Abstractions cốt lõi:**
- `FlowPrimitive` — atom của Smart Money (value [-1..+1], confidence [0..1], bucket)
- `SmartMoneyConfig` — toàn bộ tunables của hệ thống Smart Money
- `SignalScoreV4` — kết quả chấm điểm tín hiệu
- `MarketBehaviorSnapshot` — chuỗi dữ liệu theo ngày cho chart renderer
