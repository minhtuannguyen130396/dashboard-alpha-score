"""Bar-size agnostic flow record types (Phase 3).

Smart money primitives accept these instead of ``StockRecord`` so the same
class works for daily, intraday, or pre-aggregated bars regardless of where
the underlying data came from.
"""
from dataclasses import dataclass
from datetime import date as _date, datetime
from typing import List, Optional


@dataclass
class DailyFlowRecord:
    date: _date
    close: float
    open: float = 0.0
    high: float = 0.0
    low: float = 0.0
    volume: float = 0.0
    traded_value: float = 0.0          # priceImpactValue (deal value)
    prop_net_value: Optional[float] = None
    foreign_buy_value: Optional[float] = None
    foreign_sell_value: Optional[float] = None

    # Backwards-compat aliases for primitives written against StockRecord
    @property
    def priceClose(self) -> float:
        return self.close

    @property
    def priceOpen(self) -> float:
        return self.open

    @property
    def priceHigh(self) -> float:
        return self.high

    @property
    def priceLow(self) -> float:
        return self.low

    @property
    def propTradingNetValue(self) -> Optional[float]:
        return self.prop_net_value

    @property
    def buyForeignValue(self) -> Optional[float]:
        return self.foreign_buy_value

    @property
    def sellForeignValue(self) -> Optional[float]:
        return self.foreign_sell_value

    @property
    def totalValue(self) -> float:
        return self.traded_value

    @property
    def putthroughValue(self) -> float:
        return 0.0

    @property
    def priceAverage(self) -> float:
        return self.close

    @property
    def dealVolume(self) -> float:
        return self.volume


@dataclass
class IntradayFlowRecord:
    timestamp: datetime
    bar_size: str                       # "1m" | "5m" | "15m" | "1h"
    open: float
    high: float
    low: float
    close: float
    volume: float
    traded_value: float
    buy_volume: Optional[float] = None
    sell_volume: Optional[float] = None
    block_buy_count: Optional[int] = None
    block_sell_count: Optional[int] = None
    vwap: Optional[float] = None
    ofi: Optional[float] = None         # already-classified bar OFI


@dataclass
class RawTick:
    timestamp: datetime
    price: float
    volume: float
    side: int = 0                       # -1 sell, 0 unknown, +1 buy
    bid: Optional[float] = None
    ask: Optional[float] = None
    trade_type: str = "continuous"      # "continuous" | "ATO" | "ATC" | "lunch"


def stock_record_to_daily_flow(r) -> DailyFlowRecord:
    """Adapter from ``StockRecord`` to ``DailyFlowRecord``.

    Lives in this module so smart_money primitives can stay agnostic about
    the upstream loader. ``priceImpactValue`` is reconstructed as
    ``totalValue − putthroughValue`` (the analogue of ``priceImpactVolume``
    that the rest of the codebase already uses).
    """
    total = float(getattr(r, "totalValue", 0.0) or 0.0)
    pt = float(getattr(r, "putthroughValue", 0.0) or 0.0)
    deal_value = max(0.0, total - pt)
    if deal_value <= 0:
        deal_value = max(
            0.0,
            float(getattr(r, "priceAverage", 0.0) or 0.0)
            * float(getattr(r, "dealVolume", 0.0) or 0.0),
        )

    return DailyFlowRecord(
        date=r.date.date() if hasattr(r.date, "date") else r.date,
        open=float(getattr(r, "priceOpen", 0.0) or 0.0),
        high=float(getattr(r, "priceHigh", 0.0) or 0.0),
        low=float(getattr(r, "priceLow", 0.0) or 0.0),
        close=float(r.priceClose),
        volume=float(getattr(r, "dealVolume", 0.0) or 0.0),
        traded_value=deal_value,
        prop_net_value=getattr(r, "propTradingNetValue", None),
        foreign_buy_value=getattr(r, "buyForeignValue", None),
        foreign_sell_value=getattr(r, "sellForeignValue", None),
    )


def stock_records_to_daily_flows(records: List) -> List[DailyFlowRecord]:
    return [stock_record_to_daily_flow(r) for r in records]
