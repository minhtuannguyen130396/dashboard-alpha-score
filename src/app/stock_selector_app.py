import json
import threading
import tkinter as tk
from tkinter import ttk

from tkcalendar import DateEntry

from src.data.fireant_history_fetcher import fetch_all_stock_history
from src.backtesting.backtest_runner import run_backtest_report, run_backtest_chart

LIST_VN_30 = "Stock_List\\stock_vn_30.txt"
LIST_MID_CAB = "Stock_List\\stock_mid_cab.txt"
LIST_LARGE_CAB = "Stock_List\\stock_large_cab.txt"
LIST_OTHER = "Stock_List\\stock_other.txt"
LIST_ALL = "Stock_List\\list_all_stock.json"
threads = []


def get_all_symbols():
    def load_stocks_from_txt(path: str):
        with open(path, "r", encoding="utf-8") as handle:
            content = handle.read().strip()
        return json.loads(content)

    return [record["share_code"] for record in load_stocks_from_txt(LIST_ALL)]


def get_list_symbols():
    def load_stocks_from_txt(path: str):
        with open(path, "r", encoding="utf-8") as handle:
            content = handle.read().strip()
        return json.loads(content)

    list_vn_30 = [record["share_code"] for record in load_stocks_from_txt(LIST_VN_30)]
    list_large_cap = [record["share_code"] for record in load_stocks_from_txt(LIST_LARGE_CAB)]
    list_medium_cap = [record["share_code"] for record in load_stocks_from_txt(LIST_MID_CAB)]
    list_other = [record["share_code"] for record in load_stocks_from_txt(LIST_OTHER)]
    return list_vn_30, list_large_cap, list_medium_cap, list_other


def create_stock_selector_app():
    root = tk.Tk()
    root.title("Symbol and Date Selector")

    frame = ttk.Frame(root)
    frame.pack(padx=10, pady=10, fill="both", expand=True)

    ttk.Label(frame, text="Select Symbol:").pack(anchor="w")
    listbox = tk.Listbox(frame, height=10)
    listbox.pack(fill="both", expand=True)

    def insert_group(items, color):
        for item in items:
            index = listbox.size()
            listbox.insert("end", item)
            listbox.itemconfig(index, bg=color)

    list_vn_30, list_large_cap, list_medium_cap, list_other = get_list_symbols()
    insert_group(list_vn_30, "#FFC1C1")
    insert_group(list_large_cap, "#C1FFC1")
    insert_group(list_medium_cap, "#C1C1FF")
    insert_group(list_other, "#F0F0F0")

    if listbox.size() > 0:
        listbox.selection_set(0)

    date_frame = ttk.Frame(root)
    date_frame.pack(padx=10, pady=(0, 10), fill="x")

    ttk.Label(date_frame, text="Start date:").grid(row=0, column=0, sticky="w")
    start_cal = DateEntry(
        date_frame,
        date_pattern="yyyy-MM-dd",
        year=2024,
        month=1,
        day=1,
    )
    start_cal.grid(row=0, column=1, padx=5)

    ttk.Label(date_frame, text="End date:").grid(row=1, column=0, sticky="w")
    end_cal = DateEntry(date_frame, date_pattern="yyyy-MM-dd")
    end_cal.grid(row=1, column=1, padx=5)

    def start_background_task(task):
        def wrapped_task():
            try:
                task()
            finally:
                global threads
                threads = [thread for thread in threads if thread.is_alive()]

        worker = threading.Thread(target=wrapped_task, daemon=True)
        threads.append(worker)
        worker.start()

    def on_submit(event=None):
        selected_indices = listbox.curselection()
        symbol = listbox.get(selected_indices[0]) if selected_indices else None
        start_date = start_cal.get_date().strftime("%Y-%m-%d")
        end_date = end_cal.get_date().strftime("%Y-%m-%d")
        start_background_task(lambda: run_backtest_chart(symbol, start_date, end_date))

    listbox.bind("<Double-Button-1>", on_submit)

    def report_all_stocks(event=None):
        start_date = start_cal.get_date().strftime("%Y-%m-%d")
        end_date = end_cal.get_date().strftime("%Y-%m-%d")
        start_background_task(
            lambda: run_backtest_report(
                list_vn_30 + list_large_cap + list_medium_cap + list_other,
                start_date,
                end_date,
            )
        )

    ttk.Button(root, text="Test All", command=report_all_stocks).pack(pady=(0, 10))
    ttk.Button(
        root,
        text="Update Data From Start",
        command=lambda: start_background_task(
            lambda: fetch_all_stock_history(update_mode="from_start")
        ),
    ).pack(pady=(0, 10))
    ttk.Button(
        root,
        text="Update Previous Month",
        command=lambda: start_background_task(
            lambda: fetch_all_stock_history(update_mode="previous_month")
        ),
    ).pack(pady=(0, 10))
    root.mainloop()


create_app = create_stock_selector_app
