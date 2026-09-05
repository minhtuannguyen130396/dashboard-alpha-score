"""Render the interactive HTML chart for one symbol over a date range."""
from datetime import datetime
from typing import Optional

from src.data.stock_data_loader import load_stock_history
from src.analysis.market_behavior_analyzer import analyze_market_behavior
from src.reporting.chart_renderer_v2 import render_chart


def run_chart(symbol: str, start_date: str, end_date: Optional[str] = None) -> None:
    start = datetime.strptime(start_date, "%Y-%m-%d")
    end = datetime.strptime(end_date, "%Y-%m-%d") if end_date else datetime.now()

    stock_records = load_stock_history(symbol, start, end)
    if not stock_records:
        print(f"No data found for {symbol}.")
        return

    market_behavior = analyze_market_behavior(stock_records)

    # Draw the detected structure (trendlines, consolidation box, target) on top.
    from src.ta.overlays import build_overlays
    from src.ta.structure import build_structure
    structure = build_structure(symbol, records=stock_records)

    render_chart(stock_records, market_behavior, overlays=build_overlays(structure))
