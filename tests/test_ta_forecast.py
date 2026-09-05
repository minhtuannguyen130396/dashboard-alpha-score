import json
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional
from unittest import mock

from src.data.stock_data_loader import StockRecord
from src.ta import forecast as fc
from src.ta.forecast import (
    CLOSE_ABOVE, CLOSE_BELOW, EXPIRED, HIT_TARGET, INVALIDATED, PENDING,
    Forecast, evaluate, propose,
)


def _bar(i: int, close: float, volume: float = 1_000_000.0,
         high: Optional[float] = None, low: Optional[float] = None) -> StockRecord:
    return StockRecord(
        date=datetime(2026, 1, 1) + timedelta(days=i),
        symbol="TST",
        priceHigh=high if high is not None else close + 0.5,
        priceLow=low if low is not None else close - 0.5,
        priceOpen=close, priceAverage=close, priceClose=close, priceBasic=close,
        totalVolume=volume, dealVolume=volume, putthroughVolume=0.0,
        totalValue=0.0, putthroughValue=0.0,
        buyForeignQuantity=0.0, buyForeignValue=0.0,
        sellForeignQuantity=0.0, sellForeignValue=0.0,
        buyCount=0.0, buyQuantity=0.0, sellCount=0.0, sellQuantity=0.0,
        adjRatio=1.0, currentForeignRoom=0.0,
        propTradingNetDealValue=None, propTradingNetPTValue=None,
        propTradingNetValue=None, unit=1.0,
    )


def _series(closes: List[float], volumes: Optional[List[float]] = None) -> List[StockRecord]:
    volumes = volumes or [1_000_000.0] * len(closes)
    return [_bar(i, c, v) for i, (c, v) in enumerate(zip(closes, volumes))]


def _forecast(**kw) -> Forecast:
    base = dict(
        id="TST-20260101-box_breakout", symbol="TST", created="2026-01-01",
        basis="box_breakout", direction="up",
        trigger_type=CLOSE_ABOVE, trigger_level=22.0,
        target=25.0, invalidation=19.0, deadline_bars=10, created_close=20.0,
    )
    base.update(kw)
    return Forecast(**base)


class LifecycleTest(unittest.TestCase):
    """pending -> triggered -> hit_target / invalidated / expired."""

    def test_stays_pending_while_nothing_happens(self):
        records = _series([20.0] * 6)
        result, changed = evaluate(_forecast(), records)
        self.assertEqual(result.status, PENDING)
        self.assertIsNone(changed)
        self.assertEqual(result.bars_elapsed, 5)

    def test_triggers_then_reaches_the_target(self):
        records = _series([20.0, 20.5, 22.5, 23.5, 25.2])
        result, changed = evaluate(_forecast(), records)
        self.assertEqual(result.status, HIT_TARGET)
        self.assertEqual(changed, PENDING)
        self.assertEqual(result.triggered_date, "2026-01-03")
        self.assertEqual(result.resolved_date, "2026-01-05")
        self.assertEqual(result.resolved_close, 25.2)

    def test_invalidated_before_it_ever_triggers(self):
        records = _series([20.0, 19.5, 18.5, 22.5])
        result, _ = evaluate(_forecast(), records)
        self.assertEqual(result.status, INVALIDATED)
        self.assertEqual(result.resolved_date, "2026-01-03")
        self.assertIsNone(result.triggered_date)

    def test_invalidated_after_triggering(self):
        records = _series([20.0, 22.5, 21.0, 18.0])
        result, _ = evaluate(_forecast(), records)
        self.assertEqual(result.status, INVALIDATED)
        self.assertEqual(result.triggered_date, "2026-01-02")

    def test_expires_when_the_trigger_never_comes(self):
        records = _series([20.0] + [20.5] * 12)
        result, _ = evaluate(_forecast(deadline_bars=5), records)
        self.assertEqual(result.status, EXPIRED)

    def test_expires_after_triggering_without_reaching_the_target(self):
        records = _series([20.0, 22.5] + [23.0] * 10)
        result, _ = evaluate(_forecast(deadline_bars=4), records)
        self.assertEqual(result.status, EXPIRED)
        self.assertEqual(result.triggered_date, "2026-01-02")


class VolumeConfirmationTest(unittest.TestCase):
    """The 20 leading bars only seed the volume EMA; the forecast starts after them."""

    CREATED = "2026-01-20"          # bar index 19

    def _run(self, closes, volumes, **kw):
        records = _series([20.0] * 20 + closes, [1_000_000.0] * 20 + volumes)
        return evaluate(_forecast(created=self.CREATED, **kw), records)[0]

    def test_thin_volume_does_not_trigger(self):
        result = self._run([22.5, 23.0, 23.5], [900_000.0] * 3, confirm_volume_x=1.5)
        self.assertEqual(result.status, PENDING)
        self.assertIsNone(result.triggered_date)

    def test_heavy_volume_triggers(self):
        result = self._run([22.5, 23.0, 25.5], [4_000_000.0] * 3, confirm_volume_x=1.5)
        self.assertEqual(result.status, HIT_TARGET)
        self.assertGreaterEqual(result.triggered_volume_x, 1.5)

    def test_no_volume_requirement_triggers_on_price_alone(self):
        result = self._run([22.5, 25.5], [1_000_000.0] * 2, confirm_volume_x=None)
        self.assertEqual(result.status, HIT_TARGET)


class DownsideForecastTest(unittest.TestCase):
    def test_a_short_idea_runs_the_other_way(self):
        forecast = _forecast(direction="down", trigger_type=CLOSE_BELOW,
                             trigger_level=19.0, target=16.0, invalidation=22.0)
        result, _ = evaluate(forecast, _series([20.0, 18.5, 17.0, 15.5]))
        self.assertEqual(result.status, HIT_TARGET)
        self.assertEqual(result.resolved_close, 15.5)

    def test_a_short_idea_is_invalidated_by_a_rally(self):
        forecast = _forecast(direction="down", trigger_type=CLOSE_BELOW,
                             trigger_level=19.0, target=16.0, invalidation=22.0)
        result, _ = evaluate(forecast, _series([20.0, 21.0, 23.0]))
        self.assertEqual(result.status, INVALIDATED)


class ReplayTest(unittest.TestCase):
    """Status is re-derived from the bars, so a stale file heals itself."""

    def test_a_wrong_stored_status_is_corrected(self):
        records = _series([20.0, 20.5, 22.5, 23.5, 25.2])
        forecast = _forecast(status=INVALIDATED, resolved_date="1999-01-01")
        result, previous = evaluate(forecast, records)
        self.assertEqual(result.status, HIT_TARGET)
        self.assertEqual(previous, INVALIDATED)

    def test_a_change_is_recorded_in_history(self):
        records = _series([20.0, 22.5, 25.5])
        result, _ = evaluate(_forecast(), records)
        self.assertEqual(len(result.history), 1)
        self.assertEqual(result.history[0]["from"], PENDING)
        self.assertEqual(result.history[0]["to"], HIT_TARGET)

    def test_bars_before_creation_are_ignored(self):
        records = _series([30.0] * 5)          # all dated on or before "created"
        result, changed = evaluate(_forecast(created="2026-01-10"), records)
        self.assertEqual(result.bars_elapsed, 0)
        self.assertEqual(result.status, PENDING)
        self.assertIsNone(changed)


class StorageTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._patch = mock.patch.object(fc, "FORECAST_DIR", Path(self._tmp.name))
        self._patch.start()

    def tearDown(self):
        self._patch.stop()
        self._tmp.cleanup()

    def test_round_trip_through_disk(self):
        original = _forecast(note="ghi chú có dấu tiếng Việt")
        fc.save(original)
        loaded = fc.load(original.id)
        self.assertEqual(loaded.to_dict(), original.to_dict())

    def test_unknown_fields_in_the_file_are_ignored(self):
        original = _forecast()
        path = fc.save(original)
        data = json.loads(path.read_text(encoding="utf-8"))
        data["a_field_from_a_future_version"] = 123
        path.write_text(json.dumps(data), encoding="utf-8")
        self.assertEqual(fc.load(original.id).id, original.id)

    def test_a_corrupt_file_is_skipped_not_fatal(self):
        fc.save(_forecast())
        (Path(self._tmp.name) / "broken.json").write_text("{not json", encoding="utf-8")
        self.assertEqual(len(fc.load_all()), 1)

    def test_filtering_by_symbol_and_open_state(self):
        fc.save(_forecast(id="AAA-1", symbol="AAA"))
        fc.save(_forecast(id="BBB-1", symbol="BBB", status=HIT_TARGET))
        self.assertEqual([f.symbol for f in fc.load_all(["AAA"])], ["AAA"])
        self.assertEqual([f.symbol for f in fc.load_all(open_only=True)], ["AAA"])

    def test_delete(self):
        forecast = _forecast()
        fc.save(forecast)
        self.assertTrue(fc.delete(forecast.id))
        self.assertFalse(fc.delete(forecast.id))
        self.assertIsNone(fc.load(forecast.id))


class ProposeTest(unittest.TestCase):
    def test_proposals_on_real_data_are_internally_consistent(self):
        made = propose("ACB", lookback_days=200)
        for f in made:
            self.assertGreater(f.target, f.invalidation)
            self.assertGreater(f.deadline_bars, 0)
            self.assertTrue(f.note)
            self.assertEqual(f.id, fc.make_id(f.symbol, f.created, f.basis))
            if f.direction == "up":
                self.assertGreater(f.target, f.trigger_level)

    def test_no_data_yields_no_proposals(self):
        self.assertEqual(propose("NOSUCHTICKER", lookback_days=100), [])

    def test_a_past_setup_can_be_replayed_to_its_outcome(self):
        # GAS broke its box on 2026-08-07 with 1.71x volume and ran to the target.
        from src.ta.loader import load_recent
        made = propose("GAS", 180, as_of=datetime(2026, 8, 6))
        box = next((f for f in made if f.basis == "box_breakout"), None)
        self.assertIsNotNone(box, "a consolidation box should have been detected")
        result, previous = evaluate(box, load_recent("GAS", 400))
        self.assertEqual(result.status, HIT_TARGET)
        self.assertEqual(previous, PENDING)
        self.assertGreaterEqual(result.triggered_volume_x, 1.5)


if __name__ == "__main__":
    unittest.main()
