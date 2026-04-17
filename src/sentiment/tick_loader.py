"""Load tick data (JSONL) and daily OHLCV reference data."""

import json
import os
from pathlib import Path
from typing import List, Optional

BASE_DIR = Path(__file__).resolve().parent.parent.parent  # project root


def load_ticks(symbol: str, date_str: str, base_dir: Path = BASE_DIR) -> List[dict]:
    """Load tick JSONL from data/<SYMBOL>/updatetrades/<YEAR>/<date>.json"""
    year = date_str[:4]
    filepath = base_dir / "data" / symbol / "updatetrades" / year / f"{date_str}.json"
    ticks = []
    if not filepath.exists():
        return ticks
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                ticks.append(json.loads(line))
    return ticks


def load_daily_ref(symbol: str, year_month: str, base_dir: Path = BASE_DIR) -> List[dict]:
    """Load monthly OHLCV from data/<SYMBOL>/<YEAR>/<YYYY-MM-DD>.json.

    year_month: e.g. "2026-03" -> looks for data/<SYM>/2026/2026-03-01.json
    """
    year = year_month[:4]
    filename = f"{year_month}-01.json"
    filepath = base_dir / "data" / symbol / year / filename
    if not filepath.exists():
        return []
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)


def get_daily_record(symbol: str, date_str: str, base_dir: Path = BASE_DIR) -> Optional[dict]:
    """Get a single day's OHLCV record from the monthly file."""
    year_month = date_str[:7]  # "2026-04" from "2026-04-13"
    records = load_daily_ref(symbol, year_month, base_dir)
    for rec in records:
        d = rec.get("date", "")[:10]
        if d == date_str:
            return rec
    return None


def detect_session(ticks: List[dict]) -> str:
    """Detect if data covers morning/afternoon/full session."""
    if not ticks:
        return "empty"
    last_ts = ticks[-1].get("ts", "")
    if not last_ts or "T" not in last_ts:
        return "unknown"
    time_part = last_ts.split("T")[1]
    parts = time_part.split(":")
    h = int(parts[0])
    if h < 12:
        return "morning"
    elif h < 14:
        return "afternoon"
    else:
        return "full"


def list_available_dates(symbol: str, base_dir: Path = BASE_DIR) -> List[str]:
    """Return sorted list of dates that have tick data for a symbol."""
    tick_dir = base_dir / "data" / symbol / "updatetrades"
    dates = []
    if not tick_dir.exists():
        return dates
    for year_dir in sorted(tick_dir.iterdir()):
        if year_dir.is_dir():
            for f in sorted(year_dir.glob("*.json")):
                date_str = f.stem  # "2026-04-13"
                dates.append(date_str)
    return dates


def list_symbols_with_ticks(base_dir: Path = BASE_DIR) -> List[str]:
    """Return sorted list of symbols that have updatetrades data."""
    data_dir = base_dir / "data"
    symbols = []
    if not data_dir.exists():
        return symbols
    for sym_dir in sorted(data_dir.iterdir()):
        if sym_dir.is_dir() and (sym_dir / "updatetrades").exists():
            symbols.append(sym_dir.name)
    return symbols
