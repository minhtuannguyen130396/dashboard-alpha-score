"""Tests for smart_money Phase 3-5 (FlowRecord adapter, intraday, calibration)."""
import json
import shutil
import tempfile
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path

from src.analysis.smart_money import (
    SmartMoneyConfig,
    compute_smart_money,
    compute_smart_money_mtf,
)
from src.analysis.smart_money.calibration import (
    CalibratedWeights,
    DriftMonitor,
    WeightCalibrator,
    load_calibrated_weights,
)
from src.analysis.smart_money.calibration.weight_calibrator import (
    TrainingSignal,
    save_calibrated_weights,
)
from src.analysis.smart_money.primitives_intraday import (
    AuctionFlowPrimitive,
    BlockTradePrimitive,
    IntradayDivergencePrimitive,
    OrderFlowImbalancePrimitive,
    VWAPRelationshipPrimitive,
)
from src.analysis.smart_money.tick.trade_classifier import (
    TradeClassifier,
    bvc_classify,
    lee_ready_classify,
    tick_rule_classify,
)
from src.data.flow_records import (
    DailyFlowRecord,
    IntradayFlowRecord,
    RawTick,
    stock_record_to_daily_flow,
)
from src.data.intraday_feature_cache import (
    IntradayFeatureCache,
    IntradayFeatureRow,
)
from src.data.stock_data_loader import StockRecord
from src.data.tick_storage import (
    read_tick_day,
    resample_to_bars,
    write_tick_day,
)


# =============================================================================
# Phase 3: FlowRecord adapter
# =============================================================================

def _stock_record(i: int, **kwargs) -> StockRecord:
    base = datetime(2026, 1, 1) + timedelta(days=i)
    return StockRecord(
        date=base,
        symbol=kwargs.get("symbol", "TST"),
        priceHigh=110.0, priceLow=90.0, priceOpen=100.0,
        priceAverage=100.0, priceClose=105.0, priceBasic=100.0,
        totalVolume=1_000_000.0, dealVolume=900_000.0,
        putthroughVolume=100_000.0,
        totalValue=kwargs.get("total_value", 100_000_000_000.0),
        putthroughValue=0.0,
        buyForeignQuantity=0.0,
        buyForeignValue=kwargs.get("foreign_buy", 0.0),
        sellForeignQuantity=0.0,
        sellForeignValue=kwargs.get("foreign_sell", 0.0),
        buyCount=0.0, buyQuantity=0.0, sellCount=0.0, sellQuantity=0.0,
        adjRatio=1.0, currentForeignRoom=0.0,
        propTradingNetDealValue=None, propTradingNetPTValue=None,
        propTradingNetValue=kwargs.get("prop_net", 0.0),
        unit=1.0,
    )


class FlowRecordAdapterTest(unittest.TestCase):
    def test_round_trip_preserves_flow_fields(self) -> None:
        rec = _stock_record(0, prop_net=5e9, foreign_buy=3e9, foreign_sell=1e9)
        flow = stock_record_to_daily_flow(rec)
        self.assertEqual(flow.prop_net_value, 5e9)
        self.assertEqual(flow.foreign_buy_value, 3e9)
        self.assertEqual(flow.foreign_sell_value, 1e9)
        self.assertEqual(flow.close, 105.0)
        # Adapter exposes legacy attribute names so primitives still work
        self.assertEqual(flow.priceClose, 105.0)
        self.assertEqual(flow.propTradingNetValue, 5e9)

    def test_compute_smart_money_works_on_daily_flow_records(self) -> None:
        recs = [
            stock_record_to_daily_flow(
                _stock_record(i, prop_net=2e9, foreign_buy=2e9)
            )
            for i in range(40)
        ]
        sig = compute_smart_money(recs)
        self.assertGreater(sig.setup_composite, 0.0)


# =============================================================================
# Phase 3: tick storage round-trip
# =============================================================================

class TickStorageTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp()

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_write_read_round_trip(self) -> None:
        ticks = [
            RawTick(
                timestamp=datetime(2026, 4, 1, 9, 15, 0) + timedelta(seconds=10 * i),
                price=100.0 + (i % 5) * 0.1,
                volume=100.0 + i,
                side=1 if i % 2 == 0 else -1,
            )
            for i in range(20)
        ]
        write_tick_day(self.tmp, "TST", date(2026, 4, 1), ticks, fmt="json")
        loaded = read_tick_day(self.tmp, "TST", date(2026, 4, 1))
        self.assertIsNotNone(loaded)
        self.assertEqual(len(loaded), 20)
        self.assertEqual(loaded[0].volume, 100.0)
        self.assertEqual(loaded[0].side, 1)

    def test_resample_to_bars(self) -> None:
        ticks = [
            RawTick(
                timestamp=datetime(2026, 4, 1, 9, 15, 0) + timedelta(seconds=30 * i),
                price=100.0 + i * 0.5,
                volume=100.0,
                side=1,
            )
            for i in range(20)
        ]
        bars = resample_to_bars(ticks, "5m")
        # 20 ticks at 30s spacing = 10 minutes → 2 five-minute bars, 10 ticks each
        self.assertEqual(len(bars), 2)
        self.assertEqual(bars[0].volume, 1000.0)
        self.assertEqual(bars[1].volume, 1000.0)
        # Aggregated volume conserved
        self.assertEqual(sum(b.volume for b in bars), sum(t.volume for t in ticks))


# =============================================================================
# Phase 4: trade classifier
# =============================================================================

class TradeClassifierTest(unittest.TestCase):
    def _make_ticks(self, prices, with_quotes=False):
        out = []
        for i, p in enumerate(prices):
            t = RawTick(
                timestamp=datetime(2026, 4, 1, 9, 15) + timedelta(seconds=i),
                price=p, volume=100.0,
            )
            if with_quotes:
                t.bid = p - 0.05
                t.ask = p + 0.05
            out.append(t)
        return out

    def test_tick_rule_marks_uptick_buy(self) -> None:
        ticks = self._make_ticks([100, 101, 101, 100])
        out = tick_rule_classify(ticks)
        self.assertEqual(out[1].side, 1)
        self.assertEqual(out[2].side, 1)   # zero-uptick carries
        self.assertEqual(out[3].side, -1)

    def test_lee_ready_uses_quotes(self) -> None:
        ticks = self._make_ticks([100, 101], with_quotes=True)
        out = lee_ready_classify(ticks)
        self.assertEqual(out[1].side, 1)

    def test_bvc_classifies_bars(self) -> None:
        bars = []
        for i in range(10):
            bars.append(IntradayFlowRecord(
                timestamp=datetime(2026, 4, 1, 9, 15) + timedelta(minutes=5 * i),
                bar_size="5m",
                open=100.0, high=101.0, low=99.5,
                close=100.5 + i * 0.1,
                volume=1000.0, traded_value=100_000.0,
            ))
        out = bvc_classify(bars)
        # Bars with close > open should have buy_volume > sell_volume
        for b in out:
            if b.close > b.open:
                self.assertGreater(b.buy_volume, b.sell_volume)

    def test_classifier_auto_resolves(self) -> None:
        # Without quotes → tick_rule
        without = self._make_ticks([100, 101])
        TradeClassifier(method="auto").classify_ticks(without)
        self.assertEqual(without[1].side, 1)


# =============================================================================
# Phase 4: intraday primitives
# =============================================================================

def _make_bars(n=20, bar_size="5m", price_drift=0.1, buy_heavy=True):
    out = []
    for i in range(n):
        close = 100.0 + i * price_drift
        b = IntradayFlowRecord(
            timestamp=datetime(2026, 4, 1, 9, 15) + timedelta(minutes=5 * i),
            bar_size=bar_size,
            open=close - 0.05, high=close + 0.1, low=close - 0.1,
            close=close, volume=1000.0, traded_value=100_000.0,
        )
        if buy_heavy:
            b.buy_volume, b.sell_volume = 700.0, 300.0
        else:
            b.buy_volume, b.sell_volume = 300.0, 700.0
        out.append(b)
    return out


class IntradayPrimitiveTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp()
        self.cfg = SmartMoneyConfig(use_intraday=True)

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_ofi_buy_dominant(self) -> None:
        bars = _make_bars(buy_heavy=True)
        prim = OrderFlowImbalancePrimitive().compute(bars, self.cfg)
        self.assertEqual(prim.bucket, "trigger")
        self.assertGreater(prim.value, 0.0)

    def test_ofi_sell_dominant(self) -> None:
        bars = _make_bars(buy_heavy=False)
        prim = OrderFlowImbalancePrimitive().compute(bars, self.cfg)
        self.assertLess(prim.value, 0.0)

    def test_block_trade_with_cache(self) -> None:
        cache = IntradayFeatureCache(self.tmp + "/features")
        cache.write_scalar("median_trade_size_20d", "TST", date(2026, 3, 31), 100.0)

        ticks = []
        for i in range(20):
            ticks.append(RawTick(
                timestamp=datetime(2026, 4, 1, 9, 15) + timedelta(seconds=i),
                price=100.0, volume=100.0, side=1,
            ))
        # 5 blocks of 5000 volume — well above 100 × 30 threshold
        for i in range(5):
            ticks.append(RawTick(
                timestamp=datetime(2026, 4, 1, 10) + timedelta(seconds=i),
                price=100.0, volume=5000.0, side=1,
            ))
        prim = BlockTradePrimitive().compute(
            ticks, self.cfg,
            symbol="TST", signal_date=date(2026, 4, 1), cache=cache,
        )
        self.assertGreater(prim.value, 0.5)
        self.assertEqual(prim.components["cold_start"], 0.0)

    def test_block_trade_cold_start(self) -> None:
        ticks = [
            RawTick(
                timestamp=datetime(2026, 4, 1, 9, 15) + timedelta(seconds=i),
                price=100.0, volume=100.0, side=1,
            )
            for i in range(20)
        ]
        ticks.append(RawTick(
            timestamp=datetime(2026, 4, 1, 10),
            price=100.0, volume=5000.0, side=1,
        ))
        prim = BlockTradePrimitive().compute(
            ticks, self.cfg,
            symbol="TST", signal_date=date(2026, 4, 1), cache=None,
        )
        self.assertEqual(prim.components["cold_start"], 1.0)

    def test_vwap_relationship(self) -> None:
        bars = _make_bars(price_drift=0.5, buy_heavy=True)
        prim = VWAPRelationshipPrimitive().compute(bars, self.cfg)
        self.assertGreater(prim.value, 0.0)

    def test_auction_flow(self) -> None:
        ticks = [
            RawTick(
                timestamp=datetime(2026, 4, 1, 9, 0),
                price=100.0, volume=10_000.0, side=1, trade_type="ATO",
            ),
            RawTick(
                timestamp=datetime(2026, 4, 1, 14, 30),
                price=101.0, volume=20_000.0, side=1, trade_type="ATC",
            ),
            RawTick(
                timestamp=datetime(2026, 4, 1, 9, 30),
                price=100.5, volume=5_000.0, side=0, trade_type="continuous",
            ),
        ]
        prim = AuctionFlowPrimitive().compute(ticks, self.cfg)
        self.assertGreater(prim.value, 0.0)

    def test_intraday_divergence_bearish(self) -> None:
        # Price up, flow weakening
        bars = []
        for i in range(20):
            close = 100.0 + i * 0.5
            b = IntradayFlowRecord(
                timestamp=datetime(2026, 4, 1, 9, 15) + timedelta(minutes=5 * i),
                bar_size="5m", open=close, high=close + 0.1, low=close - 0.1,
                close=close, volume=1000.0, traded_value=100_000.0,
            )
            if i < 10:
                b.buy_volume, b.sell_volume = 800.0, 200.0
            else:
                b.buy_volume, b.sell_volume = 300.0, 700.0
            bars.append(b)
        prim = IntradayDivergencePrimitive().compute(bars, self.cfg)
        self.assertLess(prim.value, 0.0)


class IntradayFeatureCacheTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp()

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_write_load_round_trip(self) -> None:
        cache = IntradayFeatureCache(self.tmp)
        rows = [
            IntradayFeatureRow(
                symbol="TST", date=date(2026, 4, i + 1),
                ofi_composite=0.1 * i, median_trade_size=100.0,
            )
            for i in range(5)
        ]
        cache.write_day(rows)
        loaded = cache.load_row("TST", date(2026, 4, 3))
        self.assertIsNotNone(loaded)
        self.assertAlmostEqual(loaded.ofi_composite, 0.2)

    def test_load_feature_history(self) -> None:
        cache = IntradayFeatureCache(self.tmp)
        rows = [
            IntradayFeatureRow(
                symbol="TST", date=date(2026, 4, i + 1),
                ofi_composite=float(i),
            )
            for i in range(10)
        ]
        cache.write_day(rows)
        history = cache.load_feature(
            "TST", "ofi_composite",
            end_date=date(2026, 4, 10), lookback=5,
        )
        self.assertEqual(history, [5.0, 6.0, 7.0, 8.0, 9.0])

    def test_idempotent_write(self) -> None:
        cache = IntradayFeatureCache(self.tmp)
        row = IntradayFeatureRow(symbol="TST", date=date(2026, 4, 1),
                                 ofi_composite=0.5)
        cache.write_day([row])
        row2 = IntradayFeatureRow(symbol="TST", date=date(2026, 4, 1),
                                  ofi_composite=0.7)
        cache.write_day([row2])
        loaded = cache.load_row("TST", date(2026, 4, 1))
        self.assertAlmostEqual(loaded.ofi_composite, 0.7)


class CompositeMTFTest(unittest.TestCase):
    def test_intraday_disabled_matches_daily_only(self) -> None:
        recs = [_stock_record(i, prop_net=2e9, foreign_buy=2e9) for i in range(40)]
        cfg = SmartMoneyConfig(use_intraday=False)
        sig_d = compute_smart_money(recs, cfg)
        sig_mtf = compute_smart_money_mtf(recs, intraday_records=None, cfg=cfg)
        self.assertAlmostEqual(sig_d.setup_composite, sig_mtf.setup_composite, places=4)
        self.assertAlmostEqual(sig_d.trigger_composite, sig_mtf.trigger_composite, places=4)

    def test_intraday_layer_adds_trigger_signal(self) -> None:
        recs = [_stock_record(i, prop_net=2e9, foreign_buy=2e9) for i in range(40)]
        bars = _make_bars(buy_heavy=True)
        cfg = SmartMoneyConfig(use_intraday=True)
        sig = compute_smart_money_mtf(
            recs, intraday_records=bars, cfg=cfg,
            symbol="TST", signal_date=date(2026, 4, 1),
        )
        self.assertGreater(sig.trigger_confidence, 0.0)


# =============================================================================
# Phase 5: calibration
# =============================================================================

class CalibrationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp()

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _synth_signals(self, n=200, useful_feature="prop"):
        """Synthetic data: useful_feature predicts hit, others are noise."""
        import random
        random.seed(42)
        sigs = []
        for _ in range(n):
            f_useful = random.uniform(-1, 1)
            f_noise = random.uniform(-1, 1)
            target = 1 if f_useful > 0.2 else 0
            sigs.append(TrainingSignal(
                features={useful_feature: f_useful, "noise": f_noise},
                forward_return_5d=0.05 if target else -0.02,
            ))
        return sigs

    def test_calibrator_picks_useful_feature(self) -> None:
        sigs = self._synth_signals()
        weights = WeightCalibrator(l2=0.1, hit_threshold=0.0).fit(sigs)
        # The useful feature should dominate
        self.assertGreater(weights["prop"], weights["noise"])

    def test_save_and_load_round_trip(self) -> None:
        sigs = self._synth_signals()
        cw = CalibratedWeights(default_weights=WeightCalibrator(hit_threshold=0.0).fit(sigs))
        path = self.tmp + "/weights.json"
        save_calibrated_weights(cw, path)
        loaded = load_calibrated_weights(path)
        self.assertEqual(loaded.default_weights.keys(), cw.default_weights.keys())

    def test_calibrated_weights_fallback_ladder(self) -> None:
        cw = CalibratedWeights(
            default_weights={"prop": 1.0},
            weights_by_regime={"bull_trend": {"prop": 0.5, "foreign": 0.5}},
            weights_by_symbol={"large_cap": {"prop": 0.7, "foreign": 0.3}},
            weights_matrix={"bull_trend::large_cap": {"prop": 0.4, "foreign": 0.6}},
        )
        # Most specific
        w = cw.get_weights(regime="bull_trend", symbol_class="large_cap")
        self.assertEqual(w["foreign"], 0.6)
        # Fall back to symbol class
        w = cw.get_weights(regime="unknown", symbol_class="large_cap")
        self.assertEqual(w["foreign"], 0.3)
        # Fall back to regime
        w = cw.get_weights(regime="bull_trend", symbol_class=None)
        self.assertEqual(w["prop"], 0.5)
        # Fall back to default
        w = cw.get_weights()
        self.assertEqual(w["prop"], 1.0)

    def test_drift_monitor_flags_pf_drop(self) -> None:
        # 90 baseline trades with PF ~ 2.0, then 90 recent trades with PF ~ 0.7
        baseline = ([0.05] * 60) + ([-0.025] * 30)   # gains 3.0 / losses 0.75 = 4.0
        recent = ([0.02] * 30) + ([-0.04] * 60)      # gains 0.6 / losses 2.4 = 0.25
        report = DriftMonitor(recent_window=90, baseline_window=90).check(
            baseline + recent
        )
        self.assertTrue(report.needs_recalibration)

    def test_drift_monitor_stable(self) -> None:
        returns = [0.01, -0.005] * 200
        report = DriftMonitor(recent_window=90, baseline_window=90).check(returns)
        self.assertFalse(report.needs_recalibration)

    def test_composite_with_calibrated_weights(self) -> None:
        # Save calibrated weights that boost prop and zero foreign
        cw = CalibratedWeights(default_weights={
            "prop": 1.0, "foreign": 0.0,
            "divergence": 0.5, "concentration": 0.5,
        })
        path = self.tmp + "/weights.json"
        save_calibrated_weights(cw, path)

        cfg = SmartMoneyConfig(
            use_calibrated_weights=True,
            calibration_weights_file=path,
        )
        recs = [
            _stock_record(i, prop_net=5e9, foreign_buy=0, foreign_sell=5e9)
            for i in range(40)
        ]
        sig = compute_smart_money(recs, cfg)
        # With calibrated weights, foreign weight = 0 → setup is positive
        # because prop dominates
        self.assertGreater(sig.setup_composite, 0.3)


if __name__ == "__main__":
    unittest.main()
