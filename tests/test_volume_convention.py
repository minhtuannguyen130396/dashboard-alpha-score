import unittest
from datetime import datetime

from src.analysis.market_behavior_analyzer import analyze_market_behavior
from src.analysis.technical_indicators import average_volume
from src.data.stock_data_loader import StockRecord


def _record(day: int, deal_volume: float, total_volume: float) -> StockRecord:
    return StockRecord(
        date=datetime(2026, 4, day),
        symbol="TST",
        priceHigh=11.0,
        priceLow=9.0,
        priceOpen=10.0,
        priceAverage=10.0,
        priceClose=10.0,
        priceBasic=10.0,
        totalVolume=total_volume,
        dealVolume=deal_volume,
        putthroughVolume=total_volume - deal_volume,
        totalValue=0.0,
        putthroughValue=0.0,
        buyForeignQuantity=0.0,
        buyForeignValue=0.0,
        sellForeignQuantity=0.0,
        sellForeignValue=0.0,
        buyCount=0.0,
        buyQuantity=0.0,
        sellCount=0.0,
        sellQuantity=0.0,
        adjRatio=1.0,
        currentForeignRoom=0.0,
        propTradingNetDealValue=0.0,
        propTradingNetPTValue=0.0,
        propTradingNetValue=0.0,
        unit=1000.0,
    )


class VolumeConventionTest(unittest.TestCase):
    def test_average_volume_uses_deal_volume(self) -> None:
        records = [
            _record(1, deal_volume=100.0, total_volume=1000.0),
            _record(2, deal_volume=300.0, total_volume=5000.0),
        ]
        self.assertEqual(average_volume(records, period=2), 200.0)

    def test_market_behavior_volume_series_uses_deal_volume(self) -> None:
        records = [
            _record(1, deal_volume=100.0, total_volume=1000.0),
            _record(2, deal_volume=300.0, total_volume=5000.0),
        ]

        neutral_scores = []
        for _ in records:
            neutral_scores.append(type("Score", (), {
                "label": "none",
                "final_score": 0.0,
                "reason_text": "",
                "reasons": [],
                "candle_score": 0.0,
                "volume_score": 0.0,
                "context_score": 0.0,
                "pivot_score": 0.0,
            })())

        snapshot = analyze_market_behavior(records, neutral_scores)

        self.assertEqual(snapshot.total_volume, [100.0, 300.0])
        self.assertEqual(snapshot.hover_payloads[-1]["price"]["volume"], 300)


if __name__ == "__main__":
    unittest.main()
