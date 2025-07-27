from typing import List
from src.base.load_stock_data import StockRecord
import numpy as np
from src.base.load_stock_data import StockRecord
from src.base.load_stock_data import StockRecord
from src.math.indicatiors import IndicatorGroup4

class MartketBehaviorDetector:
    """Class to detect market behavior based on stock records."""
    sale_point = List[bool]
    buy_point = List[bool]
    big_buyer = List[bool]
    fomo_retail = List[bool]
    total_volume = List[int]
    ema_volume = List[int]
    def __init__(self):
        self.sale_point: List[bool] = []
        self.buy_point: List[bool] = []
        self.big_buyer: List[bool] = []
        self.fomo_retail: List[bool] = []
        self.total_volume: List[int] = []
        self.ema_volume: List[int] = []
    
    
def detect_market_behavior(
    stock_records: List[StockRecord],
    líst_point: List[float],
    sale_threshold: float = -5,
    buy_threshold: float = 5,
    period: int = 14,  # Số phiên để tính toán các chỉ số
) -> MartketBehaviorDetector:
    """Phát hiện hành vi thị trường dựa trên dữ liệu cổ phiếu."""
    
    marketBehavior = MartketBehaviorDetector()
    
    marketBehavior.big_buyer = IndicatorGroup4.is_big_buyer(stock_records, period)
    marketBehavior.fomo_retail = IndicatorGroup4.is_fomo_by_retail(stock_records,period)
    # Tìm điểm mua / bán
    list_point = np.array(líst_point)
    # Tính ngưỡng mua/bán dựa trên các điểm đã tính toán
    higher_therious = np.max(list_point)
    lower_therious = np.min(list_point)
    print(f"Lower threshold: {lower_therious} \nHigher threshold: {higher_therious}")
    # Xác định điểm mua và bán dựa trên ngưỡng
    buy_mask = np.array(list_point) == higher_therious
    sell_mask = np.array(list_point) <= sale_threshold
    marketBehavior.buy_point = buy_mask.tolist()
    marketBehavior.sale_point = sell_mask.tolist()
    # Tính toán khối lượng và đường trung bình khối lượng
    volume_series = [record.totalValue for record in stock_records]
    ema_volume = list(np.round(np.convolve(volume_series, np.ones(period)/period, mode='valid')))
    marketBehavior.total_volume = volume_series
    marketBehavior.ema_volume = ema_volume
    
    return marketBehavior
    
    