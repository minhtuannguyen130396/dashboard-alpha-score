"""
Stock Selector App  ─  v2
─────────────────────────
Modern tkinter UI for backtesting and data management.
Backward-compatible: `create_app` alias kept at module level.
"""

import json
import threading
import tkinter as tk
from tkinter import ttk
from tkcalendar import DateEntry

from src.data.fireant_history_fetcher import fetch_all_stock_history
from src.backtesting.backtest_runner import run_backtest_report, run_backtest_chart

# ─── Stock list paths ────────────────────────────────────────────────────────
LIST_VN_30    = "Stock_List\\stock_vn_30.txt"
LIST_MID_CAB  = "Stock_List\\stock_mid_cab.txt"
LIST_LARGE_CAB= "Stock_List\\stock_large_cab.txt"
LIST_OTHER    = "Stock_List\\stock_other.txt"
LIST_ALL      = "Stock_List\\list_all_stock.json"

# ─── Group metadata ──────────────────────────────────────────────────────────
GROUPS = [
    {"label": "VN30",      "color": "#FF6B6B", "bg": "#FFF0F0", "path": LIST_VN_30},
    {"label": "Large Cap", "color": "#2ECC71", "bg": "#F0FFF4", "path": LIST_LARGE_CAB},
    {"label": "Mid Cap",   "color": "#3B82F6", "bg": "#EFF6FF", "path": LIST_MID_CAB},
    {"label": "Other",     "color": "#94A3B8", "bg": "#F8FAFC", "path": LIST_OTHER},
]

# ─── Color palette ───────────────────────────────────────────────────────────
CLR = {
    "bg":          "#F1F5F9",
    "surface":     "#FFFFFF",
    "border":      "#E2E8F0",
    "text":        "#1E293B",
    "text_muted":  "#64748B",
    "primary":     "#2563EB",
    "primary_dk":  "#1D4ED8",
    "success":     "#059669",
    "warning":     "#D97706",
    "danger":      "#DC2626",
    "header_bg":   "#1E293B",
    "header_fg":   "#F8FAFC",
}

threads: list[threading.Thread] = []


# ─── Data helpers ─────────────────────────────────────────────────────────────
def _load_codes(path: str) -> list[str]:
    with open(path, "r", encoding="utf-8") as fh:
        data = json.loads(fh.read().strip())
    return [r["share_code"] for r in data]


def get_list_symbols():
    return (
        _load_codes(LIST_VN_30),
        _load_codes(LIST_LARGE_CAB),
        _load_codes(LIST_MID_CAB),
        _load_codes(LIST_OTHER),
    )


def get_all_symbols():
    return _load_codes(LIST_ALL)


# ─── Thread helper ────────────────────────────────────────────────────────────
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


# ─── Main app ─────────────────────────────────────────────────────────────────
def create_stock_selector_app():
    root = tk.Tk()
    root.title("Stock Backtester")
    root.configure(bg=CLR["bg"])
    root.resizable(True, True)
    root.minsize(520, 620)

    _apply_theme(root)

    # ── Load data ──────────────────────────────────────────────────────────
    list_vn_30, list_large_cap, list_medium_cap, list_other = get_list_symbols()
    all_symbols: list[tuple[str, int]] = []          # (code, group_index)
    for gi, codes in enumerate([list_vn_30, list_large_cap, list_medium_cap, list_other]):
        for code in codes:
            all_symbols.append((code, gi))

    # ── Header bar ────────────────────────────────────────────────────────
    hdr = tk.Frame(root, bg=CLR["header_bg"], pady=12)
    hdr.pack(fill="x")
    tk.Label(
        hdr, text="📈  Stock Backtester",
        font=("Segoe UI", 16, "bold"),
        bg=CLR["header_bg"], fg=CLR["header_fg"],
    ).pack(side="left", padx=18)
    _status_var = tk.StringVar(value="Ready")
    tk.Label(
        hdr, textvariable=_status_var,
        font=("Segoe UI", 9), bg=CLR["header_bg"], fg="#94A3B8",
    ).pack(side="right", padx=18)

    # ── Body ──────────────────────────────────────────────────────────────
    body = tk.Frame(root, bg=CLR["bg"])
    body.pack(fill="both", expand=True, padx=14, pady=10)

    # ── LEFT: symbol panel ────────────────────────────────────────────────
    left = _card(body)
    left.pack(side="left", fill="both", expand=True, padx=(0, 7))

    tk.Label(
        left, text="Symbols",
        font=("Segoe UI", 11, "bold"),
        bg=CLR["surface"], fg=CLR["text"],
    ).pack(anchor="w", padx=12, pady=(12, 4))

    # Search box
    search_var = tk.StringVar()
    search_frame = tk.Frame(left, bg=CLR["surface"])
    search_frame.pack(fill="x", padx=12, pady=(0, 6))
    tk.Label(search_frame, text="🔍", bg=CLR["surface"], fg=CLR["text_muted"],
             font=("Segoe UI", 10)).pack(side="left")
    search_entry = tk.Entry(
        search_frame, textvariable=search_var,
        font=("Segoe UI", 10), relief="flat",
        bg=CLR["bg"], fg=CLR["text"], insertbackground=CLR["text"],
    )
    search_entry.pack(side="left", fill="x", expand=True, ipady=4, padx=(4, 0))

    # Separator
    tk.Frame(left, bg=CLR["border"], height=1).pack(fill="x", padx=12)

    # Listbox + scrollbar
    lb_frame = tk.Frame(left, bg=CLR["surface"])
    lb_frame.pack(fill="both", expand=True, padx=12, pady=6)

    scrollbar = ttk.Scrollbar(lb_frame, orient="vertical")
    listbox = tk.Listbox(
        lb_frame,
        yscrollcommand=scrollbar.set,
        font=("Consolas", 10),
        selectbackground=CLR["primary"],
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

    # Legend
    legend_frame = tk.Frame(left, bg=CLR["surface"])
    legend_frame.pack(fill="x", padx=12, pady=(2, 10))
    for gi, g in enumerate(GROUPS):
        count = sum(1 for _, idx in all_symbols if idx == gi)
        dot = tk.Label(legend_frame, text="●", fg=g["color"],
                       bg=CLR["surface"], font=("Segoe UI", 10))
        dot.pack(side="left")
        tk.Label(legend_frame, text=f"{g['label']} ({count})",
                 bg=CLR["surface"], fg=CLR["text_muted"],
                 font=("Segoe UI", 8)).pack(side="left", padx=(1, 8))

    # Populate & filter listbox
    def _populate(filter_text=""):
        listbox.delete(0, "end")
        q = filter_text.strip().upper()
        for code, gi in all_symbols:
            if q and q not in code:
                continue
            idx = listbox.size()
            listbox.insert("end", f"  {code}")
            listbox.itemconfig(idx, bg=GROUPS[gi]["bg"], fg=CLR["text"])

    _populate()
    if listbox.size() > 0:
        listbox.selection_set(0)

    def _on_search(*_):
        _populate(search_var.get())

    search_var.trace_add("write", _on_search)

    def _selected_symbol() -> str | None:
        sel = listbox.curselection()
        return listbox.get(sel[0]).strip() if sel else None

    # ── RIGHT: controls panel ─────────────────────────────────────────────
    right = tk.Frame(body, bg=CLR["bg"])
    right.pack(side="left", fill="y")

    # Date card
    date_card = _card(right)
    date_card.pack(fill="x", pady=(0, 8))

    tk.Label(
        date_card, text="Date Range",
        font=("Segoe UI", 11, "bold"),
        bg=CLR["surface"], fg=CLR["text"],
    ).grid(row=0, column=0, columnspan=2, sticky="w", padx=12, pady=(12, 8))

    _date_label(date_card, "From").grid(row=1, column=0, sticky="w", padx=12, pady=3)
    start_cal = DateEntry(
        date_card, date_pattern="yyyy-MM-dd",
        year=2024, month=1, day=1,
        font=("Segoe UI", 10),
        background=CLR["primary"], foreground="white",
        headersbackground=CLR["primary_dk"],
    )
    start_cal.grid(row=1, column=1, padx=(4, 12), pady=3, sticky="ew")

    _date_label(date_card, "To").grid(row=2, column=0, sticky="w", padx=12, pady=3)
    end_cal = DateEntry(
        date_card, date_pattern="yyyy-MM-dd",
        font=("Segoe UI", 10),
        background=CLR["primary"], foreground="white",
        headersbackground=CLR["primary_dk"],
    )
    end_cal.grid(row=2, column=1, padx=(4, 12), pady=3, sticky="ew")
    tk.Frame(date_card, bg=CLR["surface"]).grid(row=3, pady=4)   # spacer

    def _dates():
        return (
            start_cal.get_date().strftime("%Y-%m-%d"),
            end_cal.get_date().strftime("%Y-%m-%d"),
        )

    # Score version card
    score_card = _card(right)
    score_card.pack(fill="x", pady=(0, 8))
    tk.Label(
        score_card, text="Score Version",
        font=("Segoe UI", 11, "bold"),
        bg=CLR["surface"], fg=CLR["text"],
    ).pack(anchor="w", padx=12, pady=(12, 4))
    score_version_var = tk.StringVar(value="v3")
    sv_row = tk.Frame(score_card, bg=CLR["surface"])
    sv_row.pack(fill="x", padx=12, pady=(0, 10))
    for val, lbl in [("v1", "V1 (legacy)"), ("v2", "V2"), ("v3", "V3 (new)")]:
        tk.Radiobutton(
            sv_row, text=lbl, value=val, variable=score_version_var,
            bg=CLR["surface"], fg=CLR["text"], selectcolor=CLR["surface"],
            activebackground=CLR["surface"], font=("Segoe UI", 9),
        ).pack(side="left", padx=(0, 6))

    # Action card
    act_card = _card(right)
    act_card.pack(fill="x", pady=(0, 8))

    tk.Label(
        act_card, text="Actions",
        font=("Segoe UI", 11, "bold"),
        bg=CLR["surface"], fg=CLR["text"],
    ).pack(anchor="w", padx=12, pady=(12, 8))

    def _set_status(msg: str):
        _status_var.set(msg)

    def _btn_run_chart():
        sym = _selected_symbol()
        if not sym:
            return
        s, e = _dates()
        sv = score_version_var.get()
        _set_status(f"Running chart: {sym} ({sv}) …")
        _run_in_thread(
            lambda: run_backtest_chart(sym, s, e, score_version=sv),
            on_done=lambda: _set_status("Ready"),
        )

    def _btn_test_all():
        s, e = _dates()
        combined = list_vn_30 + list_large_cap + list_medium_cap + list_other
        sv = score_version_var.get()
        _set_status(f"Testing {len(combined)} stocks ({sv}) …")
        _run_in_thread(
            lambda: run_backtest_report(combined, s, e, score_version=sv),
            on_done=lambda: _set_status("Ready"),
        )

    def _btn_fetch_from_start():
        _set_status("Fetching all data from start …")
        _run_in_thread(
            lambda: fetch_all_stock_history(update_mode="from_start"),
            on_done=lambda: _set_status("Ready"),
        )

    def _btn_fetch_prev_month():
        _set_status("Updating previous month …")
        _run_in_thread(
            lambda: fetch_all_stock_history(update_mode="previous_month"),
            on_done=lambda: _set_status("Ready"),
        )

    _action_btn(act_card, "▶  Chart Selected",      CLR["primary"],  _btn_run_chart)
    _action_btn(act_card, "📊  Test All Stocks",    CLR["success"],  _btn_test_all)

    # Separator
    tk.Frame(act_card, bg=CLR["border"], height=1).pack(fill="x", padx=12, pady=8)

    tk.Label(
        act_card, text="Data",
        font=("Segoe UI", 9, "bold"),
        bg=CLR["surface"], fg=CLR["text_muted"],
    ).pack(anchor="w", padx=12, pady=(0, 4))

    _action_btn(act_card, "⬇  Fetch From Start",   CLR["warning"],  _btn_fetch_from_start)
    _action_btn(act_card, "🔄  Update Prev Month",  CLR["text_muted"], _btn_fetch_prev_month)

    tk.Frame(act_card, bg=CLR["surface"]).pack(pady=4)  # spacer

    # ── Hint label ────────────────────────────────────────────────────────
    tk.Label(
        root, text="Double-click a symbol to run chart",
        font=("Segoe UI", 8), bg=CLR["bg"], fg=CLR["text_muted"],
    ).pack(pady=(0, 6))

    # ── Bindings ──────────────────────────────────────────────────────────
    listbox.bind("<Double-Button-1>", lambda _e: _btn_run_chart())
    listbox.bind("<Return>", lambda _e: _btn_run_chart())
    search_entry.bind("<Escape>", lambda _e: search_var.set(""))

    root.mainloop()


# ─── Widget helpers ───────────────────────────────────────────────────────────
def _apply_theme(root: tk.Tk):
    style = ttk.Style(root)
    style.theme_use("clam")
    style.configure("TFrame",  background=CLR["bg"])
    style.configure("TLabel",  background=CLR["bg"], foreground=CLR["text"])
    style.configure("TButton", font=("Segoe UI", 10))
    style.configure(
        "TScrollbar",
        troughcolor=CLR["bg"],
        background=CLR["border"],
        arrowcolor=CLR["text_muted"],
    )


def _card(parent) -> tk.Frame:
    """White card with a subtle border."""
    return tk.Frame(
        parent,
        bg=CLR["surface"],
        highlightbackground=CLR["border"],
        highlightthickness=1,
    )


def _date_label(parent, text: str) -> tk.Label:
    return tk.Label(
        parent, text=text,
        font=("Segoe UI", 9),
        bg=CLR["surface"], fg=CLR["text_muted"],
    )


def _action_btn(parent, text: str, color: str, command):
    btn = tk.Button(
        parent,
        text=text,
        font=("Segoe UI", 10, "bold"),
        bg=color,
        fg="#FFFFFF",
        activebackground=color,
        activeforeground="#FFFFFF",
        relief="flat",
        cursor="hand2",
        padx=10,
        pady=8,
        bd=0,
        command=command,
    )
    btn.pack(fill="x", padx=12, pady=3)

    # Hover effect
    def _on_enter(_):
        btn.configure(bg=_darken(color))

    def _on_leave(_):
        btn.configure(bg=color)

    btn.bind("<Enter>", _on_enter)
    btn.bind("<Leave>", _on_leave)
    return btn


def _darken(hex_color: str, factor: float = 0.85) -> str:
    """Return a slightly darker shade of *hex_color*."""
    hex_color = hex_color.lstrip("#")
    r, g, b = (int(hex_color[i:i+2], 16) for i in (0, 2, 4))
    r, g, b = (max(0, int(c * factor)) for c in (r, g, b))
    return f"#{r:02x}{g:02x}{b:02x}"


# ─── Backward-compat alias ───────────────────────────────────────────────────
create_app = create_stock_selector_app
