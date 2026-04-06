from dataclasses import dataclass
from datetime import datetime


@dataclass
class TradeRecord:
    date_buy: datetime
    date_sale: datetime
    hoding_day: int
    profit: float
    profit_pct: float
    cash: float
    buy_value: float
    buy_volume: float
    sale_value: float
    sale_volume: float

    @property
    def stock_value(self) -> float:
        return self.buy_value

    @property
    def stock_volume(self) -> float:
        return self.buy_volume

    @property
    def stock_symbol(self) -> str:
        return ""

    @property
    def stock_price(self) -> float:
        return self.sale_value


FynanceRecord = TradeRecord
