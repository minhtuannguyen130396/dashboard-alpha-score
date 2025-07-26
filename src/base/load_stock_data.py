import os
import json
import glob
from pathlib import Path
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, List, Union
import pandas as pd

@dataclass
class StockRecord:
    date: datetime
    symbol: str
    priceHigh: float
    priceLow: float
    priceOpen: float
    priceAverage: float
    priceClose: float
    priceBasic: float
    totalVolume: float
    dealVolume: float
    putthroughVolume: float
    totalValue: float
    putthroughValue: float
    buyForeignQuantity: float
    buyForeignValue: float
    sellForeignQuantity: float
    sellForeignValue: float
    buyCount: float
    buyQuantity: float
    sellCount: float
    sellQuantity: float
    adjRatio: float
    currentForeignRoom: float
    propTradingNetDealValue: Optional[float]
    propTradingNetPTValue: Optional[float]
    propTradingNetValue: Optional[float]
    unit: float
    
def load_stock_data(
    symbol: str,
    date_begin: Union[str, datetime],
    date_end: Optional[Union[str, datetime]] = None
) -> List[StockRecord]:
    """
    Load StockRecord từ thư mục `data` (cùng cấp với `src`),
    chỉ lấy các ngày từ date_begin đến date_end.
    Nếu date_end=None thì lấy từ date_begin đến hết.
    """
    # 1) Lấy đường dẫn tuyệt đối đến thư mục chứa dữ liệu
    root = os.getcwd()
    data_dir = Path(root) / 'data' / symbol
    if not data_dir.is_dir():
        raise FileNotFoundError(f"Not found file data {data_dir}")
    
    # 3) Parse ngày
    def _to_dt(x):
        if isinstance(x, datetime):
            return x
        return datetime.fromisoformat(x)
    dt_begin = _to_dt(date_begin)
    dt_end = _to_dt(date_end) if date_end is not None else None

    records: List[StockRecord] = []
    print(f"Loading {symbol} from {data_dir} for period {dt_begin} to {dt_end if dt_end else 'end of data'}")
    for year_dir in data_dir.iterdir():
        if not year_dir.is_dir():
            continue
        for json_file in year_dir.glob('*.json'):
            with json_file.open('r', encoding='utf-8') as f:
                items = json.load(f)
            for item in items:
                rec_dt = datetime.fromisoformat(item['date'])
                if rec_dt < dt_begin:
                    continue
                if dt_end is not None and rec_dt > dt_end:
                    continue
                records.append(StockRecord(
                    date=rec_dt,
                    symbol=item['symbol'],
                    priceHigh=item['priceHigh'] /item['adjRatio'],
                    priceLow=item['priceLow'] /item['adjRatio'],
                    priceOpen=item['priceOpen'] /item['adjRatio'],
                    priceAverage=item['priceAverage'] /item['adjRatio'],
                    priceClose=item['priceClose'] /item['adjRatio'],
                    priceBasic=item['priceBasic'] / item['adjRatio'],
                    totalVolume=item['totalVolume'],
                    dealVolume=item['dealVolume'],
                    putthroughVolume=item['putthroughVolume'],
                    totalValue=item['totalValue'],
                    putthroughValue=item['putthroughValue'],
                    buyForeignQuantity=item['buyForeignQuantity'],
                    buyForeignValue=item['buyForeignValue'],
                    sellForeignQuantity=item['sellForeignQuantity'],
                    sellForeignValue=item['sellForeignValue'],
                    buyCount=item['buyCount'],
                    buyQuantity=item['buyQuantity'],
                    sellCount=item['sellCount'],
                    sellQuantity=item['sellQuantity'],
                    adjRatio=item['adjRatio'],
                    currentForeignRoom=item['currentForeignRoom'],
                    propTradingNetDealValue=item.get('propTradingNetDealValue'),
                    propTradingNetPTValue=item.get('propTradingNetPTValue'),
                    propTradingNetValue=item.get('propTradingNetValue'),
                    unit=item['unit']
                ))
    records.sort(key=lambda r: r.date)
    return records
