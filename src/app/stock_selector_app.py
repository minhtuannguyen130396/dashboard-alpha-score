"""
Stock Selector App - v2
Modern tkinter UI for backtesting and data management.
Backward-compatible: `create_app` alias kept at module level.
"""

import json
import threading
import tkinter as tk
from tkinter import ttk

from tkcalendar import DateEntry

from src.backtesting.backtest_runner import run_backtest_chart, run_backtest_report
from src.data.fireant_history_fetcher import fetch_all_stock_history

LIST_ALL = "stock_list\\list_all_stock.json"

CLR = {
    "bg": "#0F172A",
    "bg2": "#1E293B",
    "surface": "#1E293B",
    "surface2": "#273548",
    "border": "#334155",
    "text": "#F1F5F9",
    "text_muted": "#94A3B8",
    "primary": "#3B82F6",
    "primary_dk": "#2563EB",
    "success": "#10B981",
    "success_dk": "#059669",
    "warning": "#F59E0B",
    "warning_dk": "#D97706",
    "danger": "#EF4444",
    "header_bg": "#0F172A",
    "header_fg": "#F1F5F9",
    "accent": "#6366F1",
    "listbox_alt": "#243044",
    "listbox_sel": "#3B82F6",
}

threads: list[threading.Thread] = []


def _load_records(path: str) -> list[dict]:
    with open(path, "r", encoding="utf-8") as fh:
        return json.loads(fh.read().strip())


def get_all_stock_records() -> list[dict]:
    """Return the full stock dataset, including group metadata for later filters."""
    return _load_records(LIST_ALL)


def get_all_symbols() -> list[str]:
    return [record["share_code"] for record in get_all_stock_records()]


def _run_in_thread(task, on_start=None, on_done=None):
    """Run *task* in a daemon thread; call optional callbacks on main thread."""

    def _wrapped():
        if on_start:
            on_start()
        try:
            task()
        finally:
            if on_done:
                on_done()
            global threads
            threads = [t for t in threads if t.is_alive()]

    t = threading.Thread(target=_wrapped, daemon=True)
    threads.append(t)
    t.start()
    return t


def create_stock_selector_app():
    root = tk.Tk()
    root.title("Stock Backtester")
    root.configure(bg=CLR["bg"])
    root.resizable(True, True)
    root.minsize(620, 680)

    # Center window on screen
    root.update_idletasks()
    w, h = 780, 720
    sw = root.winfo_screenwidth()
    sh = root.winfo_screenheight()
    root.geometry(f"{w}x{h}+{(sw-w)//2}+{(sh-h)//2}")

    _apply_theme(root)

    stock_records = get_all_stock_records()
    all_symbols = [record["share_code"] for record in stock_records]

    _group_to_symbols: dict[str, list[str]] = {}
    for rec in stock_records:
        for g in rec.get("stock_groups", []):
            _group_to_symbols.setdefault(g, []).append(rec["share_code"])
    all_groups = sorted(_group_to_symbols.keys())

    # ── Header ────────────────────────────────────────────────────────────────
    hdr = tk.Frame(root, bg=CLR["header_bg"])
    hdr.pack(fill="x")

    hdr_inner = tk.Frame(hdr, bg=CLR["header_bg"], pady=10)
    hdr_inner.pack(fill="x", padx=16)

    title_frame = tk.Frame(hdr_inner, bg=CLR["header_bg"])
    title_frame.pack(side="left")

    tk.Label(
        title_frame,
        text="📈  Stock Backtester",
        font=("Segoe UI", 15, "bold"),
        bg=CLR["header_bg"],
        fg=CLR["header_fg"],
    ).pack(side="left")

    tk.Label(
        title_frame,
        text=" v2",
        font=("Segoe UI", 9),
        bg=CLR["header_bg"],
        fg=CLR["text_muted"],
    ).pack(side="left", padx=(4, 0), anchor="s", pady=(0, 2))

    # Accent line under header
    tk.Frame(root, bg=CLR["primary"], height=2).pack(fill="x")

    # ── Status bar (pack before body so side="bottom" works) ─────────────────
    statusbar = tk.Frame(root, bg=CLR["bg2"])
    statusbar.pack(fill="x", side="bottom")
    tk.Frame(statusbar, bg=CLR["border"], height=1).pack(fill="x")

    bar_inner = tk.Frame(statusbar, bg=CLR["bg2"])
    bar_inner.pack(fill="x", padx=14, pady=5)

    _status_var = tk.StringVar(value="● Ready")
    status_lbl = tk.Label(
        bar_inner,
        textvariable=_status_var,
        font=("Segoe UI", 9),
        bg=CLR["bg2"],
        fg=CLR["success"],
    )
    status_lbl.pack(side="left")

    tk.Label(
        bar_inner,
        text="Stock Backtester  |  VN Market",
        font=("Segoe UI", 8),
        bg=CLR["bg2"],
        fg=CLR["border"],
    ).pack(side="right")

    # ── Body ──────────────────────────────────────────────────────────────────
    body = tk.Frame(root, bg=CLR["bg"])
    body.pack(fill="both", expand=True, padx=14, pady=10)

    # Left panel — symbol list
    left = _card(body)
    left.pack(side="left", fill="both", expand=True, padx=(0, 10))

    _section_header(left, "🔍  Symbols")

    # Group filter
    group_var = tk.StringVar(value="All Groups")
    group_frame = tk.Frame(left, bg=CLR["surface"])
    group_frame.pack(fill="x", padx=12, pady=(2, 4))

    _field_label(group_frame, "Group").pack(side="left")
    group_combo = ttk.Combobox(
        group_frame,
        textvariable=group_var,
        values=["All Groups"] + all_groups,
        state="readonly",
        font=("Segoe UI", 9),
        width=22,
    )
    group_combo.pack(side="left", padx=(8, 0), fill="x", expand=True)

    # Search box
    search_var = tk.StringVar()
    search_frame = tk.Frame(left, bg=CLR["surface"])
    search_frame.pack(fill="x", padx=12, pady=(0, 8))

    _field_label(search_frame, "Search").pack(side="left")
    search_entry = tk.Entry(
        search_frame,
        textvariable=search_var,
        font=("Segoe UI", 10),
        relief="flat",
        bg=CLR["surface2"],
        fg=CLR["text"],
        insertbackground=CLR["text"],
        highlightthickness=1,
        highlightbackground=CLR["border"],
        highlightcolor=CLR["primary"],
    )
    search_entry.pack(side="left", fill="x", expand=True, ipady=5, padx=(8, 0))

    # Divider
    tk.Frame(left, bg=CLR["border"], height=1).pack(fill="x", padx=12)

    lb_frame = tk.Frame(left, bg=CLR["surface"])
    lb_frame.pack(fill="both", expand=True, padx=12, pady=6)

    scrollbar = ttk.Scrollbar(lb_frame, orient="vertical")
    listbox = tk.Listbox(
        lb_frame,
        yscrollcommand=scrollbar.set,
        font=("Consolas", 11),
        selectbackground=CLR["listbox_sel"],
        selectforeground="#FFFFFF",
        activestyle="none",
        relief="flat",
        bd=0,
        highlightthickness=0,
        bg=CLR["surface"],
        fg=CLR["text"],
    )
    scrollbar.config(command=listbox.yview)
    scrollbar.pack(side="right", fill="y")
    listbox.pack(side="left", fill="both", expand=True)

    summary_frame = tk.Frame(left, bg=CLR["surface"])
    summary_frame.pack(fill="x", padx=12, pady=(2, 10))
    summary_var = tk.StringVar(value=f"All Stocks ({len(all_symbols)})")
    tk.Label(
        summary_frame,
        textvariable=summary_var,
        bg=CLR["surface"],
        fg=CLR["text_muted"],
        font=("Segoe UI", 8),
    ).pack(side="left")

    tk.Label(
        summary_frame,
        text="↵ Enter or double-click to chart",
        bg=CLR["surface"],
        fg=CLR["border"],
        font=("Segoe UI", 7),
    ).pack(side="right")

    def _get_pool() -> list[str]:
        g = group_var.get()
        if g == "All Groups":
            return all_symbols
        return _group_to_symbols.get(g, [])

    def _populate(*_):
        listbox.delete(0, "end")
        query = search_var.get().strip().upper()
        pool = _get_pool()
        for i, code in enumerate(pool):
            if query and query not in code.upper():
                continue
            listbox.insert("end", f"  {code}")
            # Alternating row background
            if i % 2 == 0:
                listbox.itemconfig("end", bg=CLR["surface"])
            else:
                listbox.itemconfig("end", bg=CLR["listbox_alt"])
        total = listbox.size()
        g = group_var.get()
        label = g if g != "All Groups" else "All"
        summary_var.set(f"{label} ({total} stocks)")
        if total > 0:
            listbox.selection_set(0)

    _populate()

    search_var.trace_add("write", lambda *_: _populate())
    group_combo.bind("<<ComboboxSelected>>", _populate)

    def _selected_symbol() -> str | None:
        sel = listbox.curselection()
        return listbox.get(sel[0]).strip() if sel else None

    # Right panel
    right = tk.Frame(body, bg=CLR["bg"])
    right.pack(side="left", fill="y")

    # ── Date Range card ───────────────────────────────────────────────────────
    date_card = _card(right, accent=CLR["primary"])
    date_card.pack(fill="x", pady=(0, 8))

    _section_header(date_card, "📅  Date Range")

    date_grid = tk.Frame(date_card, bg=CLR["surface"])
    date_grid.pack(fill="x", padx=12, pady=(0, 12))
    date_grid.columnconfigure(1, weight=1)

    _field_label(date_grid, "From").grid(row=0, column=0, sticky="w", pady=4)
    start_cal = DateEntry(
        date_grid,
        date_pattern="yyyy-MM-dd",
        year=2024,
        month=1,
        day=1,
        font=("Segoe UI", 10),
        background=CLR["primary"],
        foreground="white",
        headersbackground=CLR["primary_dk"],
        bordercolor=CLR["border"],
    )
    start_cal.grid(row=0, column=1, padx=(10, 0), pady=4, sticky="ew")

    _field_label(date_grid, "To").grid(row=1, column=0, sticky="w", pady=4)
    end_cal = DateEntry(
        date_grid,
        date_pattern="yyyy-MM-dd",
        font=("Segoe UI", 10),
        background=CLR["primary"],
        foreground="white",
        headersbackground=CLR["primary_dk"],
        bordercolor=CLR["border"],
    )
    end_cal.grid(row=1, column=1, padx=(10, 0), pady=4, sticky="ew")

    def _dates():
        return (
            start_cal.get_date().strftime("%Y-%m-%d"),
            end_cal.get_date().strftime("%Y-%m-%d"),
        )

    # ── Strategy card ─────────────────────────────────────────────────────────
    strat_card = _card(right, accent=CLR["primary"])
    strat_card.pack(fill="x", pady=(0, 8))

    _section_header(strat_card, "⚙  Scoring Engine")

    version_var = tk.StringVar(value="v4")
    strat_row = tk.Frame(strat_card, bg=CLR["surface"])
    strat_row.pack(fill="x", padx=12, pady=(0, 12))
    for label, val in (("V4 (legacy)", "v4"), ("V5 (smart-money)", "v5")):
        tk.Radiobutton(
            strat_row,
            text=label,
            variable=version_var,
            value=val,
            bg=CLR["surface"],
            activebackground=CLR["surface"],
            font=("Segoe UI", 10),
            anchor="w",
        ).pack(side="left", padx=(0, 12))

    def _version() -> str:
        return version_var.get()

    # ── Actions card ──────────────────────────────────────────────────────────
    act_card = _card(right, accent=CLR["success"])
    act_card.pack(fill="x", pady=(0, 8))

    _section_header(act_card, "▶  Actions")

    def _set_status(msg: str, color: str = CLR["success"]):
        _status_var.set(msg)
        status_lbl.configure(fg=color)

    def _btn_run_chart():
        sym = _selected_symbol()
        if not sym:
            return
        start_date, end_date = _dates()
        ver = _version()
        _set_status(f"⏳ Charting {sym} ({ver.upper()}) ...", CLR["warning"])
        _run_in_thread(
            lambda: run_backtest_chart(sym, start_date, end_date, version=ver),
            on_done=lambda: _set_status("● Ready"),
        )

    def _btn_test_all():
        pool = _get_pool()
        start_date, end_date = _dates()
        ver = _version()
        _set_status(f"⏳ Testing {len(pool)} stocks ({ver.upper()}) ...", CLR["warning"])
        _run_in_thread(
            lambda: run_backtest_report(pool, start_date, end_date, version=ver),
            on_done=lambda: _set_status("● Ready"),
        )

    def _btn_fetch_from_start():
        _set_status("⏳ Fetching all data from start ...", CLR["warning"])
        _run_in_thread(
            lambda: fetch_all_stock_history(update_mode="from_start"),
            on_done=lambda: _set_status("● Ready"),
        )

    def _btn_fetch_prev_month():
        _set_status("⏳ Updating previous month ...", CLR["warning"])
        _run_in_thread(
            lambda: fetch_all_stock_history(update_mode="previous_month"),
            on_done=lambda: _set_status("● Ready"),
        )

    _action_btn(act_card, "📊  Chart Selected", CLR["primary"], CLR["primary_dk"], _btn_run_chart)
    _action_btn(act_card, "🧪  Test All Stocks", CLR["success"], CLR["success_dk"], _btn_test_all)

    # Divider with label
    sep_frame = tk.Frame(act_card, bg=CLR["surface"])
    sep_frame.pack(fill="x", padx=12, pady=(6, 4))
    tk.Frame(sep_frame, bg=CLR["border"], height=1).pack(fill="x", side="left", expand=True, pady=8)
    tk.Label(
        sep_frame,
        text="  DATA  ",
        font=("Segoe UI", 7, "bold"),
        bg=CLR["surface"],
        fg=CLR["text_muted"],
    ).pack(side="left")
    tk.Frame(sep_frame, bg=CLR["border"], height=1).pack(fill="x", side="left", expand=True, pady=8)

    _action_btn(act_card, "⬇  Fetch From Start", CLR["warning"], CLR["warning_dk"], _btn_fetch_from_start)
    _action_btn(act_card, "🔄  Update Prev Month", CLR["surface2"], CLR["border"], _btn_fetch_prev_month)

    tk.Frame(act_card, bg=CLR["surface"], height=8).pack()

    # ── Bindings ──────────────────────────────────────────────────────────────
    listbox.bind("<Double-Button-1>", lambda _e: _btn_run_chart())
    listbox.bind("<Return>", lambda _e: _btn_run_chart())
    search_entry.bind("<Escape>", lambda _e: search_var.set(""))
    search_entry.focus_set()

    root.mainloop()


def _apply_theme(root: tk.Tk):
    style = ttk.Style(root)
    style.theme_use("clam")
    style.configure("TFrame", background=CLR["bg"])
    style.configure("TLabel", background=CLR["bg"], foreground=CLR["text"])
    style.configure("TButton", font=("Segoe UI", 10))
    style.configure(
        "TScrollbar",
        troughcolor=CLR["bg"],
        background=CLR["border"],
        arrowcolor=CLR["text_muted"],
        bordercolor=CLR["bg"],
    )
    style.configure(
        "TCombobox",
        fieldbackground=CLR["surface2"],
        background=CLR["surface2"],
        foreground=CLR["text"],
        selectbackground=CLR["primary"],
        selectforeground="#FFFFFF",
        bordercolor=CLR["border"],
        arrowcolor=CLR["text_muted"],
    )
    style.map("TCombobox", fieldbackground=[("readonly", CLR["surface2"])])


def _card(parent, accent: str | None = None) -> tk.Frame:
    frame = tk.Frame(
        parent,
        bg=CLR["surface"],
        highlightbackground=CLR["border"],
        highlightthickness=1,
    )
    if accent:
        # Colored top accent line inside the card
        tk.Frame(frame, bg=accent, height=3).pack(fill="x")
    return frame


def _section_header(parent, text: str):
    tk.Label(
        parent,
        text=text,
        font=("Segoe UI", 10, "bold"),
        bg=CLR["surface"],
        fg=CLR["text"],
    ).pack(anchor="w", padx=12, pady=(10, 6))


def _field_label(parent, text: str) -> tk.Label:
    return tk.Label(
        parent,
        text=text,
        font=("Segoe UI", 9),
        bg=CLR["surface"],
        fg=CLR["text_muted"],
        width=6,
        anchor="w",
    )


def _action_btn(parent, text: str, color: str, hover_color: str, command):
    btn = tk.Button(
        parent,
        text=text,
        font=("Segoe UI", 10, "bold"),
        bg=color,
        fg="#FFFFFF",
        activebackground=hover_color,
        activeforeground="#FFFFFF",
        relief="flat",
        cursor="hand2",
        padx=10,
        pady=9,
        bd=0,
        command=command,
        anchor="w",
    )
    btn.pack(fill="x", padx=12, pady=3)

    btn.bind("<Enter>", lambda _: btn.configure(bg=hover_color))
    btn.bind("<Leave>", lambda _: btn.configure(bg=color))
    return btn


create_app = create_stock_selector_app
