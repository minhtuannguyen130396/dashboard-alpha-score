import threading
import tkinter as tk
from tkinter import ttk
from tkcalendar import DateEntry
import json
from src.test_script.test_script import backtest_draw_chart ,back_test_write_csv
from src.fetch_all.fetch_all_data import fetch_all_data
LIST_VN_30 =        'Stock_List\stock_vn_30.txt'
LIST_MID_CAB =      'Stock_List\stock_mid_cab.txt'
LIST_LARGE_CAB =    'Stock_List\stock_large_cab.txt'
LIST_OTHER =        'Stock_List\stock_other.txt'
# Sample lists
list_vn_30 = []
list_large_cap = []
list_medium_cap = []
list_other = []
def get_list_symbols():
    def load_stocks_from_txt(path: str):
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read().strip()
        return json.loads(content)
    # Convert to just share codes
    list_vn_30          = [r['share_code'] for r in load_stocks_from_txt(LIST_VN_30)]
    list_large_cap      = [r['share_code'] for r in load_stocks_from_txt(LIST_LARGE_CAB)]
    list_medium_cap     = [r['share_code'] for r in load_stocks_from_txt(LIST_MID_CAB)]
    list_other          = [r['share_code'] for r in load_stocks_from_txt(LIST_OTHER)]
    return list_vn_30, list_large_cap, list_medium_cap, list_other
# Thread pool to track running tasks
threads = []

# Main application
def create_app():
    root = tk.Tk()
    root.title("Symbol and Date Selector")
    
    # Symbol Listbox with colored groups
    frame = ttk.Frame(root)
    frame.pack(padx=10, pady=10, fill='both', expand=True)

    label = ttk.Label(frame, text="Select Symbol:")
    label.pack(anchor='w')

    listbox = tk.Listbox(frame, height=10)
    listbox.pack(fill='both', expand=True)

    # Function to insert and color items
    def insert_group(items, color):
        for item in items:
            idx = listbox.size()
            listbox.insert('end', item)
            listbox.itemconfig(idx, bg=color)
    list_vn_30, list_large_cap, list_medium_cap, list_other = get_list_symbols()
    # Insert groups
    insert_group(list_vn_30, '#FFC1C1')       # light red
    insert_group(list_large_cap, '#C1FFC1')    # light green
    insert_group(list_medium_cap, '#C1C1FF')   # light blue
    insert_group(list_other, '#F0F0F0')        # light gray

    # Set default selection to first symbol
    if listbox.size() > 0:
        listbox.selection_set(0)

    # Date selectors
    date_frame = ttk.Frame(root)
    date_frame.pack(padx=10, pady=(0, 10), fill='x')

    ttk.Label(date_frame, text="Start date:").grid(row=0, column=0, sticky='w')
    start_cal = DateEntry(
        date_frame, 
        date_pattern='yyyy-MM-dd',
        year = 2024,
        month = 1,
        day = 1
    )
    start_cal.grid(row=0, column=1, padx=5)

    ttk.Label(date_frame, text="End date:").grid(row=1, column=0, sticky='w')
    end_cal = DateEntry(
        date_frame, 
        date_pattern='yyyy-MM-dd'
    )
    end_cal.grid(row=1, column=1, padx=5)

    # Submit button
    def on_submit(event=None):
        selected_indices = listbox.curselection()
        symbol = listbox.get(selected_indices[0]) if selected_indices else None
        start_date = start_cal.get_date().strftime('%Y-%m-%d')
        end_date = end_cal.get_date().strftime('%Y-%m-%d')

        # Define thread target
        def task():
            backtest_draw_chart(symbol, start_date, end_date)
            # Cleanup finished threads
            global threads
            threads = [t for t in threads if t.is_alive()]

        t = threading.Thread(target=task, daemon=True)
        threads.append(t)
        t.start()
    # Bind double-click to submit
    listbox.bind('<Double-Button-1>', on_submit)    
    def report_all_stocks(event=None):
        start_date = start_cal.get_date().strftime('%Y-%m-%d')
        end_date = end_cal.get_date().strftime('%Y-%m-%d')
        back_test_write_csv(
            list_vn_30 + list_large_cap + list_medium_cap + list_other,
            start_date,
            end_date
        )
            
    submit_btn = ttk.Button(
        root,
        text="Test All",
        command=report_all_stocks
    )
    submit_btn.pack(pady=(0, 10))
    
    fetch_btn = ttk.Button(
        root,
        text="Fetch All Data",
        command=fetch_all_data
    )
    fetch_btn.pack(pady=(0, 10))
    root.mainloop()
