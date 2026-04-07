import json
import os
import tempfile
import unittest
from pathlib import Path

from src.data.stock_data_loader import load_stock_history


class LoadStockHistoryAdjustmentTest(unittest.TestCase):
    def test_ohlc_prices_are_adjusted_by_adj_ratio(self) -> None:
        payload = [
            {
                "date": "2026-04-07T00:00:00",
                "symbol": "TST",
                "priceHigh": 120.0,
                "priceLow": 80.0,
                "priceOpen": 100.0,
                "priceAverage": 95.0,
                "priceClose": 90.0,
                "priceBasic": 110.0,
                "totalVolume": 1000.0,
                "dealVolume": 900.0,
                "putthroughVolume": 100.0,
                "totalValue": 95000.0,
                "putthroughValue": 10000.0,
                "buyForeignQuantity": 10.0,
                "buyForeignValue": 1000.0,
                "sellForeignQuantity": 5.0,
                "sellForeignValue": 500.0,
                "buyCount": 1.0,
                "buyQuantity": 10.0,
                "sellCount": 1.0,
                "sellQuantity": 5.0,
                "adjRatio": 2.0,
                "currentForeignRoom": 0.0,
                "propTradingNetDealValue": 0.0,
                "propTradingNetPTValue": 0.0,
                "propTradingNetValue": 0.0,
                "unit": 1000.0,
            }
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            data_file = Path(temp_dir) / "data" / "TST" / "2026" / "2026-04-01.json"
            data_file.parent.mkdir(parents=True, exist_ok=True)
            data_file.write_text(json.dumps(payload), encoding="utf-8")

            old_cwd = os.getcwd()
            try:
                os.chdir(temp_dir)
                records = load_stock_history("TST", "2026-04-01", "2026-04-30")
            finally:
                os.chdir(old_cwd)

        self.assertEqual(len(records), 1)
        record = records[0]
        self.assertEqual(record.priceHigh, 60.0)
        self.assertEqual(record.priceLow, 40.0)
        self.assertEqual(record.priceOpen, 50.0)
        self.assertEqual(record.priceAverage, 47.5)
        self.assertEqual(record.priceClose, 45.0)
        self.assertEqual(record.priceBasic, 55.0)


if __name__ == "__main__":
    unittest.main()
