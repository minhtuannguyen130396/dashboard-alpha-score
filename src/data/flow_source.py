"""FlowSource protocol — bar-size agnostic source of flow records.

Phase 3 stub. ``DailyFlowSource`` wraps the existing JSON-on-disk loader
and refuses to serve intraday. ``TickFlowSource`` lives in tick_storage.py
and is enabled in Phase 4 once tick data is on disk.
"""
from datetime import date as _date
from typing import List, Optional, Protocol

from src.data.flow_records import (
    DailyFlowRecord,
    IntradayFlowRecord,
    stock_records_to_daily_flows,
)


class FlowSource(Protocol):
    def get_daily_flow(
        self, symbol: str, start: _date, end: _date,
    ) -> List[DailyFlowRecord]: ...

    def get_intraday_flow(
        self, symbol: str, day: _date, bar_size: str = "1m",
    ) -> Optional[List[IntradayFlowRecord]]: ...

    def supports_intraday(self) -> bool: ...


class DailyFlowSource:
    """Wraps ``stock_data_loader.load_stock_history`` and adapts to FlowRecord."""

    def supports_intraday(self) -> bool:
        return False

    def get_daily_flow(
        self, symbol: str, start: _date, end: _date,
    ) -> List[DailyFlowRecord]:
        from src.data.stock_data_loader import load_stock_history
        from datetime import datetime

        dt_start = datetime.combine(start, datetime.min.time())
        dt_end = datetime.combine(end, datetime.min.time())
        records = load_stock_history(symbol, dt_start, dt_end)
        return stock_records_to_daily_flows(records)

    def get_intraday_flow(
        self, symbol: str, day: _date, bar_size: str = "1m",
    ) -> Optional[List[IntradayFlowRecord]]:
        return None
