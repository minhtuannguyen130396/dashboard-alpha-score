from datetime import datetime
from typing import List, Literal

from src.data.stock_data_loader import load_stock_history
from src.backtesting.trade_simulator import run_trade_simulation
from src.analysis.signal_scoring import calculate_signal_score, calculate_signal_score_v2
from src.analysis.market_behavior_analyzer import analyze_market_behavior
from src.reporting.chart_renderer_v2 import render_backtest_chart
from src.reporting.performance_report_writer import BacktestReportRow, write_backtest_report

ScoreVersion = Literal["v1", "v2"]


# Minimum lookback per score version.
# v1 uses EMA50 at most  → 80 bars is sufficient.
# v2 uses EMA100         → needs ≥ 100 bars to initialise; 120 adds a 20-bar
#                          warmup buffer so the last EMA100 values are stable.
_LOOKBACK = {"v1": 79, "v2": 119}


def _build_signal_scores(stock_records, score_version: ScoreVersion = "v1"):
    lookback = _LOOKBACK.get(score_version, 79)
    signal_scores = []
    for index in range(len(stock_records)):
        window_start = max(0, index - lookback)
        window = stock_records[window_start:index + 1]
        if score_version == "v2":
            signal_scores.append(calculate_signal_score_v2(window))
        else:
            signal_scores.append(calculate_signal_score(window))
    return signal_scores


def run_backtest_report(symbols: List[str], start_date: str, end_date: str = None, score_version: ScoreVersion = "v1"):
    start = datetime.strptime(start_date, "%Y-%m-%d")
    end = datetime.strptime(end_date, "%Y-%m-%d") if end_date else datetime.now()
    stock_csvs_prepared = []
    for symbol in symbols:
        print(f"Processing symbol: {symbol} (score={score_version})")
        stock_records = load_stock_history(symbol, start, end)
        if len(stock_records) < 50:
            print(f"No data found for {symbol}. Skipping...")
            continue

        signal_scores = _build_signal_scores(stock_records, score_version)
        market_behavior = analyze_market_behavior(stock_records, signal_scores)
        list_fynance, actual_sale_point, actual_buy_point = run_trade_simulation(
            stock_records,
            market_behavior.sale_point,
            market_behavior.buy_point,
            script_num=1,
            max_buy_times=1,
            cut_loss_pct=10.0,
        )

        print()
        print("-------------------------------------------------------------------")
        for record in list_fynance:
            date_fmt = "%d-%m-%Y"
            print(
                f"{record.date_buy.strftime(date_fmt)} {record.date_sale.strftime(date_fmt)}  "
                f"Hold: {record.hoding_day:>4d}  "
                f"Profit: {record.profit:>7.2f}%  "
                f"Cash: {record.cash:>10.2f}  "
                f"B: {record.buy_value:>10.2f}/{record.buy_volume:<5d}  "
                f"S: {record.sale_value:>10.2f}/{record.sale_volume:<5d}"
            )
        print("--------------------------------------------------------------------")
        stock_csvs_prepared.append(BacktestReportRow(symbol, list_fynance))

    write_backtest_report(stock_csvs_prepared, start_date, end_date)


def run_backtest_chart(symbol: str, start_date: str, end_date: str = None, score_version: ScoreVersion = "v1"):
    start = datetime.strptime(start_date, "%Y-%m-%d")
    end = datetime.strptime(end_date, "%Y-%m-%d") if end_date else datetime.now()
    stock_records = load_stock_history(symbol, start, end)
    signal_scores = _build_signal_scores(stock_records, score_version)
    market_behavior = analyze_market_behavior(stock_records, signal_scores)
    list_fynance, actual_sale_point, actual_buy_point = run_trade_simulation(
        stock_records,
        market_behavior.sale_point,
        market_behavior.buy_point,
        script_num=1,
        max_buy_times=1,
        cut_loss_pct=10.0,
    )

    print()
    print()
    print()
    print("-------------------------------------------------------------------")
    for record in list_fynance:
        date_fmt = "%d-%m-%Y"
        print(
            f"{record.date_buy.strftime(date_fmt)} {record.date_sale.strftime(date_fmt)}  "
            f"Hold: {record.hoding_day:>4d}  "
            f"Profit: {record.profit:>7.2f}%  "
            f"Cash: {record.cash:>10.2f}  "
            f"B: {record.buy_value:>10.2f}/{record.buy_volume:<5d}  "
            f"S: {record.sale_value:>10.2f}/{record.sale_volume:<5d}"
        )
    print("--------------------------------------------------------------------")
    render_backtest_chart(
        stock_records,
        market_behavior,
        actual_sale_point,
        actual_buy_point,
        list_fynance,
    )


back_test_write_csv = run_backtest_report
backtest_draw_chart = run_backtest_chart
