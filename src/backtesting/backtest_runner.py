from datetime import datetime
from typing import List

from src.data.stock_data_loader import load_stock_history
from src.backtesting.trade_simulator import run_trade_simulation
from src.analysis.signal_scoring import calculate_signal_score
from src.analysis.market_behavior_analyzer import analyze_market_behavior
from src.reporting.chart_renderer_v2 import render_backtest_chart
from src.reporting.performance_report_writer import BacktestReportRow, write_backtest_report


def _build_signal_scores(stock_records):
    signal_scores = []
    for index in range(len(stock_records)):
        window_start = max(0, index - 79)
        signal_scores.append(calculate_signal_score(stock_records[window_start:index + 1]))
    return signal_scores


def run_backtest_report(symbols: List[str], start_date: str, end_date: str = None):
    start = datetime.strptime(start_date, "%Y-%m-%d")
    end = datetime.strptime(end_date, "%Y-%m-%d") if end_date else datetime.now()
    stock_csvs_prepared = []
    for symbol in symbols:
        print(f"Processing symbol: {symbol}")
        stock_records = load_stock_history(symbol, start, end)
        if len(stock_records) < 50:
            print(f"No data found for {symbol}. Skipping...")
            continue

        signal_scores = _build_signal_scores(stock_records)
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
