from datetime import datetime
from typing import List

from src.data.stock_data_loader import load_stock_history
from src.backtesting.trade_simulator import run_trade_simulation
from src.backtesting.metrics import compute_stats, format_stats
from src.analysis.signal_scoring_v4 import calculate_signal_score_v4
from src.analysis.market_behavior_analyzer import analyze_market_behavior
from src.reporting.chart_renderer_v2 import render_backtest_chart
from src.reporting.performance_report_writer import BacktestReportRow, write_backtest_report


# V4 lookback budget:
#   - EMA100 needs ~100 bars to stabilise
#   - rolling rank window is 120 bars
# 219 = 99 (EMA warm-up) + 120 (rank window). The slice end is exclusive
# of `index`, hence the -1 to include the current bar.
_LOOKBACK = 219


def _fmt_trade_volume(value: float) -> str:
    """Render integer-like volumes without decimals, partials with up to 2 decimals."""
    if float(value).is_integer():
        return f"{int(value)}"
    return f"{value:.2f}".rstrip("0").rstrip(".")


def _build_signal_scores(stock_records):
    signal_scores = []
    for index in range(len(stock_records)):
        window_start = max(0, index - _LOOKBACK)
        window = stock_records[window_start:index + 1]
        signal_scores.append(calculate_signal_score_v4(window))
    return signal_scores


def _print_trade_log(symbol: str, list_fynance) -> None:
    print()
    print("-------------------------------------------------------------------")
    for record in list_fynance:
        date_fmt = "%d-%m-%Y"
        print(
            f"{record.date_buy.strftime(date_fmt)} {record.date_sale.strftime(date_fmt)}  "
            f"Hold: {record.hoding_day:>4d}  "
            f"Profit: {record.profit:>7.2f}%  "
            f"Cash: {record.cash:>10.2f}  "
            f"B: {record.buy_value:>10.2f}/{_fmt_trade_volume(record.buy_volume):<5}  "
            f"S: {record.sale_value:>10.2f}/{_fmt_trade_volume(record.sale_volume):<5}"
        )
    print("--------------------------------------------------------------------")
    print(f"[{symbol}] {format_stats(compute_stats(list_fynance))}")


def run_backtest_report(symbols: List[str], start_date: str, end_date: str = None):
    start = datetime.strptime(start_date, "%Y-%m-%d")
    end = datetime.strptime(end_date, "%Y-%m-%d") if end_date else datetime.now()
    stock_csvs_prepared = []
    for symbol in symbols:
        print(f"Processing symbol: {symbol} (V4)")
        stock_records = load_stock_history(symbol, start, end)
        if len(stock_records) < 50:
            print(f"No data found for {symbol}. Skipping...")
            continue

        signal_scores = _build_signal_scores(stock_records)
        market_behavior = analyze_market_behavior(stock_records, signal_scores)
        list_fynance, _, _ = run_trade_simulation(
            stock_records,
            market_behavior.sale_point,
            market_behavior.buy_point,
        )
        _print_trade_log(symbol, list_fynance)
        stock_csvs_prepared.append(BacktestReportRow(symbol, list_fynance))

    write_backtest_report(stock_csvs_prepared, start_date, end_date)


def run_backtest_chart(symbol: str, start_date: str, end_date: str = None):
    start = datetime.strptime(start_date, "%Y-%m-%d")
    end = datetime.strptime(end_date, "%Y-%m-%d") if end_date else datetime.now()
    stock_records = load_stock_history(symbol, start, end)
    signal_scores = _build_signal_scores(stock_records)
    market_behavior = analyze_market_behavior(stock_records, signal_scores)
    list_fynance, actual_sale_point, actual_buy_point = run_trade_simulation(
        stock_records,
        market_behavior.sale_point,
        market_behavior.buy_point,
    )

    _print_trade_log(symbol, list_fynance)
    render_backtest_chart(
        stock_records,
        market_behavior,
        actual_sale_point,
        actual_buy_point,
        list_fynance,
    )


back_test_write_csv = run_backtest_report
backtest_draw_chart = run_backtest_chart
