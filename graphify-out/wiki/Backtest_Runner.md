# Backtest Runner

> 13 nodes · cohesion 0.24

## Summary

Orchestrator chạy toàn bộ backtest pipeline từ đầu đến cuối. `run_backtest_chart()` và `run_backtest_report()` là hai entry points được Stock Selector App gọi từ UI thread.

**Pipeline:** load stock history → `_build_signal_scores()` (chọn V4 hoặc V5 qua `_resolve_scorer()`) → `run_trade_simulation()` → tính metrics → render chart hoặc xuất CSV. `_print_trade_log()` in trade log ra console. `BacktestReportRow` + `write_backtest_report()` xử lý output CSV cho multi-symbol comparison.

## Key Concepts

- **backtest_runner.py** (6 connections) — `src\backtesting\backtest_runner.py`
- **_print_trade_log()** (4 connections) — `src\backtesting\backtest_runner.py`
- **run_backtest_chart()** (4 connections) — `src\backtesting\backtest_runner.py`
- **run_backtest_report()** (4 connections) — `src\backtesting\backtest_runner.py`
- **BacktestReportRow** (4 connections) — `src\reporting\performance_report_writer.py`
- **_build_signal_scores()** (3 connections) — `src\backtesting\backtest_runner.py`
- **_fmt_trade_volume()** (3 connections) — `src\backtesting\backtest_runner.py`
- **_resolve_scorer()** (3 connections) — `src\backtesting\backtest_runner.py`
- **performance_report_writer.py** (3 connections) — `src\reporting\performance_report_writer.py`
- **Render integer-like volumes without decimals, partials with up to 2 decimals.** (2 connections) — `src\backtesting\backtest_runner.py`
- **.__init__()** (1 connections) — `src\reporting\performance_report_writer.py`
- **write_backtest_report()** (1 connections) — `src\reporting\performance_report_writer.py`
- **write_csv1()** (1 connections) — `src\reporting\performance_report_writer.py`

## Relationships

- No strong cross-community connections detected

## Source Files

- `src\backtesting\backtest_runner.py`
- `src\reporting\performance_report_writer.py`

## Audit Trail

- EXTRACTED: 36 (92%)
- INFERRED: 3 (8%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*