from dataclasses import dataclass
from datetime import datetime

@dataclass
class FynanceRecord:
    date_buy: datetime
    date_sale: datetime
    hoding_day: int
    profit: float
    profit_pct: float 
    cash: float
    stock_value: float
    stock_volume: float
    stock_symbol: str
    stock_price: float
    
    def __init__(
            self,
            date_buy: datetime,
            date_sale: datetime,
            hoding_day: int,
            profit: float,
            profit_pct: float,
            cash: float,
            buy_value: float,
            buy_volume: float,
            sale_value: str,
            sale_volume: float,
        ):
            self.date_buy = date_buy
            self.date_sale = date_sale
            self.hoding_day = hoding_day
            self.profit = profit
            self.profit_pct = profit_pct
            self.cash = cash
            self.buy_value = buy_value
            self.buy_volume = buy_volume
            self.sale_value = sale_value
            self.sale_volume = sale_volume
