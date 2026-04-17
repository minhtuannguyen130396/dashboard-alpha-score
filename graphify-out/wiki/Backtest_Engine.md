# Backtest Engine

> 26 nodes · cohesion 0.10

## Key Concepts

- **TradeRecord** (9 connections) — `src\models\trade_record.py`
- **metrics.py** (5 connections) — `src\backtesting\metrics.py`
- **trade_record.py** (5 connections) — `src\models\trade_record.py`
- **trade_simulator.py** (5 connections) — `src\backtesting\trade_simulator.py`
- **run_trade_simulation()** (5 connections) — `src\backtesting\trade_simulator.py`
- **PerformanceStats** (4 connections) — `src\backtesting\metrics.py`
- **TradeConfigV4** (4 connections) — `src\backtesting\trade_simulator.py`
- **compute_stats()** (3 connections) — `src\backtesting\metrics.py`
- **performance_report_writer.py** (3 connections) — `src\reporting\performance_report_writer.py`
- **BacktestReportRow** (3 connections) — `src\reporting\performance_report_writer.py`
- **_build_trade_record()** (3 connections) — `src\backtesting\trade_simulator.py`
- **Trade simulator V4.  Single-position long-only simulator with realistic VN mar** (3 connections) — `src\backtesting\trade_simulator.py`
- **Emit a TradeRecord for ``fraction`` of a unit position.      ``profit`` is sca** (3 connections) — `src\backtesting\trade_simulator.py`
- **Single-position simulator. Returns trades, sale-marker list, buy-marker list.** (3 connections) — `src\backtesting\trade_simulator.py`
- **Performance metrics for backtest trade lists.  Computes the set called out in** (2 connections) — `src\backtesting\metrics.py`
- **_std()** (2 connections) — `src\backtesting\metrics.py`
- **_trail_k()** (2 connections) — `src\backtesting\trade_simulator.py`
- **format_stats()** (1 connections) — `src\backtesting\metrics.py`
- **.as_dict()** (1 connections) — `src\backtesting\metrics.py`
- **.__init__()** (1 connections) — `src\reporting\performance_report_writer.py`
- **write_backtest_report()** (1 connections) — `src\reporting\performance_report_writer.py`
- **write_csv1()** (1 connections) — `src\reporting\performance_report_writer.py`
- **stock_price()** (1 connections) — `src\models\trade_record.py`
- **stock_symbol()** (1 connections) — `src\models\trade_record.py`
- **stock_value()** (1 connections) — `src\models\trade_record.py`
- *... and 1 more nodes in this community*

## Relationships

- No strong cross-community connections detected

## Source Files

- `src\backtesting\metrics.py`
- `src\backtesting\trade_simulator.py`
- `src\models\trade_record.py`
- `src\reporting\performance_report_writer.py`

## Audit Trail

- EXTRACTED: 54 (74%)
- INFERRED: 19 (26%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*