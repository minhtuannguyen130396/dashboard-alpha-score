import os
import json
import glob
from datetime import datetime
import pandas as pd
import pandas_ta as ta
import plotly.graph_objects as go
from src.base.load_stock_data import load_stock_data
from src.calculate_stock_suites.calculate_stock_suites import calculate_stock_score
from src.draw_chart.draw_chart import draw_candlestick_plotly
from src.detect_market_behavior.detect_market_behavior import detect_market_behavior
from src.calculate_stock_suites.buy_script import trade_controller
def backtest(symbol: str, start_date: str, end_date: str = None):
    start = datetime.strptime(start_date, '%Y-%m-%d')
    end = datetime.strptime(end_date, '%Y-%m-%d') if end_date else datetime.now()
    stock_records = load_stock_data(symbol, start, end)
    list_points = []
    for index, record in enumerate(stock_records):
        if(index <50):
            list_points.append(0)
            continue
        record_50 = stock_records[index-50:index]
        point = calculate_stock_score(records = record_50)
        list_points.append(point)
    marketBehavior = detect_market_behavior(stock_records,list_points)
    
    cash, actual_sale_point, actual_buy_point = trade_controller(
        stock_records, 
        marketBehavior.sale_point, 
        marketBehavior.buy_point,
        script_num=1,
        max_buy_times = 1, 
        cut_loss_pct=5.0,
    )
    print(f"Total cash after trading: {cash}")
    #print(f"Buy list: {buy_list}")
    #print(f"Sale list: {sale_list}")
    
    draw_candlestick_plotly(stock_records, marketBehavior,actual_sale_point, actual_buy_point,cash)
    #print(f"Score for {symbol} from {start_date} to {end_date}")
    #print(f"list record: {list_points}")
    
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Backtest a stock with basic indicators")
    parser.add_argument('symbol', help='Stock symbol (folder name under data)')
    parser.add_argument('start_date', help='Start date YYYY-MM-DD')
    parser.add_argument('--end_date', help='End date YYYY-MM-DD', default=None)
    args = parser.parse_args()
    backtest(args.symbol, args.start_date, args.end_date)
