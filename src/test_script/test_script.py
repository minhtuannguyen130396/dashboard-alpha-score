from datetime import datetime
from typing import List
from src.base.load_stock_data import load_stock_data
from src.calculate_stock_suites.calculate_stock_suites import calculate_stock_score
from src.draw_chart.draw_chart import draw_chart
from src.draw_chart.write_csv import StockCsvWriter,write_csv
from src.detect_market_behavior.detect_market_behavior import detect_market_behavior
from src.calculate_stock_suites.buy_script import trade_controller
def back_test_write_csv(symbols: List[str], start_date: str, end_date: str = None):
    start = datetime.strptime(start_date, '%Y-%m-%d')
    end = datetime.strptime(end_date, '%Y-%m-%d') if end_date else datetime.now()
    stock_csvs_prepared = []
    for symbol in symbols:
        print(f"Processing symbol: {symbol}")
        stock_records = load_stock_data(symbol, start, end)
        if(len(stock_records) < 50):
            print(f"No data found for {symbol}. Skipping...")
            continue
        list_points = []
        for index, record in enumerate(stock_records):
            if(index <50):
                list_points.append(0)
                continue
            record_50 = stock_records[index-50:index]
            point = calculate_stock_score(records = record_50)
            list_points.append(point)
        marketBehavior = detect_market_behavior(stock_records,list_points)
        
        list_fynance, actual_sale_point, actual_buy_point = trade_controller(
            stock_records, 
            marketBehavior.sale_point, 
            marketBehavior.buy_point,
            script_num=1,
            max_buy_times = 1, 
            cut_loss_pct=10.0,
        )
    
            
        def log_fynance():
            print()
            print("-------------------------------------------------------------------")
            for record in list_fynance:
                date_fmt = '%d-%m-%Y'
                print(
                    f"{record.date_buy.strftime(date_fmt)} {record.date_sale.strftime(date_fmt)}  "
                    f"Hold: {record.hoding_day:>4d}  "
                    f"Profit: {record.profit:>7.2f}%  "
                    f"Cash: {record.cash:>10.2f}  "
                    f"B: {record.buy_value:>10.2f}/{record.buy_volume:<5d}  "
                    f"S: {record.sale_value:>10.2f}/{record.sale_volume:<5d}"
                )
            print("--------------------------------------------------------------------")
        log_fynance() 
        stock_csvs_prepared.append(StockCsvWriter(symbol, list_fynance)) 
    write_csv(stock_csvs_prepared, start_date, end_date)
    
    
def backtest_draw_chart(symbol: str, start_date: str, end_date: str = None):
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
    
    list_fynance, actual_sale_point, actual_buy_point = trade_controller(
        stock_records, 
        marketBehavior.sale_point, 
        marketBehavior.buy_point,
        script_num=1,
        max_buy_times = 1, 
        cut_loss_pct=10.0,
    )
    def log_fynance():
        print()
        print()
        print()
        print("-------------------------------------------------------------------")
        for record in list_fynance:
            date_fmt = '%d-%m-%Y'
            print(
                f"{record.date_buy.strftime(date_fmt)} {record.date_sale.strftime(date_fmt)}  "
                f"Hold: {record.hoding_day:>4d}  "
                f"Profit: {record.profit:>7.2f}%  "
                f"Cash: {record.cash:>10.2f}  "
                f"B: {record.buy_value:>10.2f}/{record.buy_volume:<5d}  "
                f"S: {record.sale_value:>10.2f}/{record.sale_volume:<5d}"
            )
        print("--------------------------------------------------------------------")
    log_fynance()  
    draw_chart(stock_records, marketBehavior,actual_sale_point, actual_buy_point,list_fynance)

