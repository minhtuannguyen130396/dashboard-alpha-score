import os
import csv
import xlsxwriter
from datetime import datetime
from typing import List
from src.detect_market_behavior.detect_market_behavior import MartketBehaviorDetector
from src.base.fynance import FynanceRecord

class StockCsvWriter:
    def __init__(self, symbol: str, list_fynance: List[FynanceRecord]):
        self.symbol = symbol
        self.list_fynance = list_fynance
def write_csv(
    list_stock: List[StockCsvWriter],
    start_date: str,
    end_date: str
) -> None:
    today = datetime.now().strftime('%Y-%m-%d')
    output_dir = os.path.join('csv_files', today)
    os.makedirs(output_dir, exist_ok=True)

    # Đổi đuôi file
    file_path = os.path.join(output_dir, f"{start_date} to {end_date}.xlsx")

    # Tìm số cột profit lớn nhất
    max_cols = max((len(s.list_fynance) for s in list_stock), default=0)

    # Tạo workbook và worksheet
    workbook  = xlsxwriter.Workbook(file_path)
    worksheet = workbook.add_worksheet("Profits")

    # Định nghĩa format
    fmt_header = workbook.add_format({'bold': True, 'align': 'center'})
    fmt_pos    = workbook.add_format({'bg_color': '#C6EFCE', 'font_color': '#006100'})
    fmt_neg    = workbook.add_format({'bg_color': '#FFC7CE', 'font_color': '#9C0006'})

    # Ghi header
    worksheet.write(0, 0, "Symbol", fmt_header)
    for i in range(max_cols):
        worksheet.write(0, i+1, f"Profit {i+1}", fmt_header)
    worksheet.write(0, max_cols+1, "Total Profit", fmt_header)

    # Ghi dữ liệu
    for row_idx, stock in enumerate(list_stock, start=1):
        worksheet.write(row_idx, 0, stock.symbol)
        profits = [rec.profit for rec in stock.list_fynance]
        # Ghi từng profit với màu
        for col_idx, profit in enumerate(profits, start=1):
            cell_fmt = fmt_pos if profit > 0 else fmt_neg
            worksheet.write(row_idx, col_idx, profit, cell_fmt)
        # Tính và ghi tổng profit
        total = sum(profits)
        total_fmt = fmt_pos if total > 0 else fmt_neg
        worksheet.write(row_idx, max_cols+1, total, total_fmt)

    workbook.close()

    # Mở file tự động (Windows)
    os.startfile(file_path)
    print(f"Excel file written to {file_path}")
    
def write_csv1(
    list_stock: List[StockCsvWriter],
    start_date: str,
    end_date: str
    ) -> None:
        today = datetime.now().strftime('%Y-%m-%d')
        output_dir = os.path.join('csv_files', today)
        os.makedirs(output_dir, exist_ok=True)
        file_path = os.path.join(output_dir, f"{start_date} to {end_date}.csv")
        max_cols = max((len(s.list_fynance) for s in list_stock), default=0)
        header = ['Symbol'] + [f'Profit {i+1}' for i in range(max_cols)]
        with open(file_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            #writer.writerow(header)

            for stock in list_stock:
                profits = [rec.profit for rec in stock.list_fynance]
                row = [stock.symbol] + profits + [''] * (max_cols - len(profits))
                writer.writerow(row)
        print(f"CSV file written to {file_path}")
        os.startfile(file_path)

    
    
    