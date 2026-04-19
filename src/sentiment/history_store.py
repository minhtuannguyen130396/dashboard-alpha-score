"""Save and load sentiment analysis history as JSON files."""

import json
from datetime import datetime
from pathlib import Path
from typing import List, Optional

BASE_DIR = Path(__file__).resolve().parent.parent.parent  # project root
HISTORY_DIR = BASE_DIR / "sentiment_history"


def save_result(
    symbol: str,
    date_str: str,
    metrics: dict,
    ai_analysis: dict,
    history_dir: Path = HISTORY_DIR,
) -> Path:
    """Save analysis result to sentiment_history/<SYMBOL>/<date>.json"""
    out_dir = history_dir / symbol
    out_dir.mkdir(parents=True, exist_ok=True)
    filepath = out_dir / f"{date_str}.json"
    result = {
        "symbol": symbol,
        "date": date_str,
        "computed_at": datetime.now().isoformat(),
        "session": metrics.get("session", ""),
        "metrics": metrics,
        "ai_analysis": ai_analysis,
    }
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    return filepath


def load_single(
    symbol: str, date_str: str, history_dir: Path = HISTORY_DIR
) -> Optional[dict]:
    """Load a single day's result."""
    filepath = history_dir / symbol / f"{date_str}.json"
    if not filepath.exists():
        return None
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)


def load_history(
    symbol: str,
    end_date: str,
    lookback: int = 10,
    history_dir: Path = HISTORY_DIR,
) -> List[dict]:
    """Load up to N most recent results before end_date (exclusive)."""
    sym_dir = history_dir / symbol
    if not sym_dir.exists():
        return []
    files = sorted(sym_dir.glob("*.json"))
    results = []
    for f in files:
        date_str = f.stem
        if date_str < end_date:
            try:
                with open(f, "r", encoding="utf-8") as fh:
                    results.append(json.load(fh))
            except (json.JSONDecodeError, IOError):
                continue
    return results[-lookback:]


def list_history_dates(
    symbol: str, history_dir: Path = HISTORY_DIR
) -> List[str]:
    """List all dates with saved history for a symbol."""
    sym_dir = history_dir / symbol
    if not sym_dir.exists():
        return []
    return sorted(f.stem for f in sym_dir.glob("*.json"))
