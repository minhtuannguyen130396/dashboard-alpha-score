from dataclasses import dataclass
from datetime import datetime

@dataclass
class FynanceRecord:
    date: datetime
    profit: float
    cash: float
    stock_value: float
    stock_volume: float
    stock_symbol: str
    stock_price: float
    def __init__(
            self,
            date: datetime,
            profit: float,
            cash: float,
            stock_value: float,
            stock_volume: float,
            stock_symbol: str,
            stock_price: float,
        ):
            self.date = date
            self.profit = profit
            self.cash = cash
            self.stock_value = stock_value
            self.stock_volume = stock_volume
            self.stock_symbol = stock_symbol
            self.stock_price = stock_price
