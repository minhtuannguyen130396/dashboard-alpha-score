import os
import csv
import xlsxwriter
from datetime import datetime
from typing import List
from src.models.trade_record import TradeRecord


class BacktestReportRow:
    def __init__(self, symbol: str, list_fynance: List[TradeRecord]):
        self.symbol = symbol
        self.list_fynance = list_fynance


def write_backtest_report(
    list_stock: List[BacktestReportRow],
    start_date: str,
    end_date: str,
) -> None:
    today = datetime.now().strftime("%Y-%m-%d")
    output_dir = os.path.join("csv_files", today)
    os.makedirs(output_dir, exist_ok=True)

    # Use an Excel output file.
    file_path = os.path.join(output_dir, f"{start_date} to {end_date}.xlsx")

    # Find the widest profit row.
    max_cols = max((len(s.list_fynance) for s in list_stock), default=0)

    # Create the workbook and worksheet.
    workbook = xlsxwriter.Workbook(file_path)
    worksheet = workbook.add_worksheet("Profits")

    # Define cell formats.
    fmt_header = workbook.add_format({"bold": True, "align": "center"})
    fmt_pos = workbook.add_format({"bg_color": "#C6EFCE", "font_color": "#006100"})
    fmt_neg = workbook.add_format({"bg_color": "#FFC7CE", "font_color": "#9C0006"})

    # Write the header row.
    worksheet.write(0, 0, "Symbol", fmt_header)
    for i in range(max_cols):
        worksheet.write(0, i + 1, f"Profit {i+1}", fmt_header)
    worksheet.write(0, max_cols + 1, "Total Profit", fmt_header)

    # Write the data rows.
    for row_idx, stock in enumerate(list_stock, start=1):
        worksheet.write(row_idx, 0, stock.symbol)
        profits = [rec.profit for rec in stock.list_fynance]

        # Write each profit cell with conditional formatting.
        for col_idx, profit in enumerate(profits, start=1):
            cell_fmt = fmt_pos if profit > 0 else fmt_neg
            worksheet.write(row_idx, col_idx, profit, cell_fmt)

        # Calculate and write total profit.
        total = sum(profits)
        total_fmt = fmt_pos if total > 0 else fmt_neg
        worksheet.write(row_idx, max_cols + 1, total, total_fmt)

    workbook.close()

    # Open the file automatically on Windows.
    os.startfile(file_path)
    print(f"Excel file written to {file_path}")


def write_csv1(
    list_stock: List[BacktestReportRow],
    start_date: str,
    end_date: str,
) -> None:
    today = datetime.now().strftime("%Y-%m-%d")
    output_dir = os.path.join("csv_files", today)
    os.makedirs(output_dir, exist_ok=True)
    file_path = os.path.join(output_dir, f"{start_date} to {end_date}.csv")
    max_cols = max((len(s.list_fynance) for s in list_stock), default=0)
    header = ["Symbol"] + [f"Profit {i+1}" for i in range(max_cols)]
    with open(file_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        # writer.writerow(header)

        for stock in list_stock:
            profits = [rec.profit for rec in stock.list_fynance]
            row = [stock.symbol] + profits + [""] * (max_cols - len(profits))
            writer.writerow(row)
    print(f"CSV file written to {file_path}")
    os.startfile(file_path)


StockCsvWriter = BacktestReportRow
write_csv = write_backtest_report
