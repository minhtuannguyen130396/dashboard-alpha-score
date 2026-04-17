"""Unit tests for the smart_money module (Phase 1)."""
import unittest
from datetime import datetime, timedelta

from src.analysis.smart_money import (
    DEFAULT_SMART_MONEY_CONFIG,
    SmartMoneyConfig,
    compute_smart_money,
)
from src.analysis.smart_money.composite import _aggregate_bucket
from src.analysis.smart_money.normalize import (
    clamp,
    rolling_zscore,
    safe_ratio,
    winsorize,
)
from src.analysis.smart_money.primitives import (
    ForeignFlowPrimitive,
    PropFlowPrimitive,
)
from src.analysis.smart_money.types import FlowPrimitive
from src.data.stock_data_loader import StockRecord


def _mk_record(
    i: int,
    *,
    prop_net: float = 0.0,
    foreign_buy: float = 0.0,
    foreign_sell: float = 0.0,
    total_value: float = 100_000_000_000.0,  # 100B traded value
    putthrough_value: float = 0.0,
) -> StockRecord:
    base_dt = datetime(2026, 1, 1) + timedelta(days=i)
    return StockRecord(
        date=base_dt,
        symbol="TST",
        priceHigh=110.0,
        priceLow=90.0,
        priceOpen=100.0,
        priceAverage=100.0,
        priceClose=105.0,
        priceBasic=100.0,
        totalVolume=1_000_000.0,
        dealVolume=900_000.0,
        putthroughVolume=100_000.0,
        totalValue=total_value,
        putthroughValue=putthrough_value,
        buyForeignQuantity=0.0,
        buyForeignValue=foreign_buy,
        sellForeignQuantity=0.0,
        sellForeignValue=foreign_sell,
        buyCount=0.0,
        buyQuantity=0.0,
        sellCount=0.0,
        sellQuantity=0.0,
        adjRatio=1.0,
        currentForeignRoom=0.0,
        propTradingNetDealValue=None,
        propTradingNetPTValue=None,
        propTradingNetValue=prop_net,
        unit=1.0,
    )


class NormalizeTest(unittest.TestCase):
    def test_clamp_handles_nan(self) -> None:
        self.assertEqual(clamp(float("nan")), 0.0)
        self.assertEqual(clamp(2.0), 1.0)
        self.assertEqual(clamp(-5.0), -1.0)
        self.assertEqual(clamp(0.5), 0.5)

    def test_safe_ratio_zero_denom(self) -> None:
        self.assertEqual(safe_ratio(10, 0, fallback=-1), -1)
        self.assertEqual(safe_ratio(10, 5), 2)

    def test_winsorize_caps_extremes(self) -> None:
        s = [1, 2, 3, 4, 5, 6, 7, 8, 9, 1000]
        out = winsorize(s, p=0.1)
        self.assertLess(max(out), 1000)
        self.assertGreaterEqual(min(out), 1)

    def test_rolling_zscore_constant_returns_zero(self) -> None:
        self.assertEqual(rolling_zscore([5.0] * 30), 0.0)


class PropPrimitiveTest(unittest.TestCase):
    def test_strong_accumulation_positive_value(self) -> None:
        # Prop net buys 5B/day for 20 days on a 100B/day stock → +5%/bar
        recs = [_mk_record(i, prop_net=5_000_000_000) for i in range(20)]
        prim = PropFlowPrimitive().compute(recs, DEFAULT_SMART_MONEY_CONFIG)
        self.assertEqual(prim.bucket, "setup")
        self.assertGreater(prim.value, 0.5)
        self.assertEqual(prim.confidence, 1.0)

    def test_no_prop_data_zero_confidence(self) -> None:
        recs = [_mk_record(i, prop_net=0.0) for i in range(20)]
        prim = PropFlowPrimitive().compute(recs, DEFAULT_SMART_MONEY_CONFIG)
        self.assertEqual(prim.confidence, 0.0)
        self.assertEqual(prim.value, 0.0)

    def test_distribution_negative_value(self) -> None:
        recs = [_mk_record(i, prop_net=-5_000_000_000) for i in range(20)]
        prim = PropFlowPrimitive().compute(recs, DEFAULT_SMART_MONEY_CONFIG)
        self.assertLess(prim.value, -0.5)

    def test_single_huge_print_does_not_dominate(self) -> None:
        # 19 quiet bars + 1 huge buy → tanh-bounded, value stays sane
        recs = [_mk_record(i, prop_net=0.0) for i in range(19)]
        recs.append(_mk_record(19, prop_net=200_000_000_000))  # 2x daily traded
        prim = PropFlowPrimitive().compute(recs, DEFAULT_SMART_MONEY_CONFIG)
        self.assertLessEqual(prim.value, 1.0)


class ForeignPrimitiveTest(unittest.TestCase):
    def test_buy_dominates(self) -> None:
        recs = [
            _mk_record(i, foreign_buy=8_000_000_000, foreign_sell=1_000_000_000)
            for i in range(20)
        ]
        prim = ForeignFlowPrimitive().compute(recs, DEFAULT_SMART_MONEY_CONFIG)
        self.assertEqual(prim.bucket, "setup")
        self.assertGreater(prim.value, 0.5)
        self.assertEqual(prim.confidence, 1.0)

    def test_no_foreign_activity_zero_confidence(self) -> None:
        recs = [_mk_record(i) for i in range(20)]
        prim = ForeignFlowPrimitive().compute(recs, DEFAULT_SMART_MONEY_CONFIG)
        self.assertEqual(prim.confidence, 0.0)


class CompositeTest(unittest.TestCase):
    def test_aggregate_empty_returns_zero(self) -> None:
        v, c = _aggregate_bucket({}, {"prop": 0.5})
        self.assertEqual((v, c), (0.0, 0.0))

    def test_aggregate_zero_confidence_rebalances(self) -> None:
        prims = {
            "prop": FlowPrimitive(
                name="prop", bucket="setup",
                value=0.8, confidence=1.0,
            ),
            "foreign": FlowPrimitive(
                name="foreign", bucket="setup",
                value=-0.9, confidence=0.0,
            ),
        }
        v, c = _aggregate_bucket(prims, {"prop": 0.5, "foreign": 0.5})
        # Foreign drops out → composite = prop value, confidence = 0.5
        self.assertAlmostEqual(v, 0.8)
        self.assertAlmostEqual(c, 0.5)

    def test_trigger_zero_when_phase2_disabled(self) -> None:
        # Regression: with all Phase 2 features off, trigger bucket = 0
        cfg = SmartMoneyConfig(
            use_divergence=False,
            use_concentration=False,
            use_persistence=False,
            use_toxic_flow=False,
        )
        recs = [
            _mk_record(i, prop_net=2_000_000_000,
                       foreign_buy=3_000_000_000)
            for i in range(40)
        ]
        sig = compute_smart_money(recs, cfg)
        self.assertEqual(sig.trigger_composite, 0.0)
        self.assertEqual(sig.trigger_confidence, 0.0)
        self.assertGreater(sig.setup_composite, 0.0)
        self.assertGreater(sig.setup_confidence, 0.0)

    def test_bucket_no_overlap_invariant(self) -> None:
        cfg = SmartMoneyConfig()
        overlap = set(cfg.setup_weights) & set(cfg.trigger_weights)
        self.assertFalse(overlap)

    def test_primitive_bucket_matches_class_attribute(self) -> None:
        recs = [_mk_record(i, prop_net=1e9, foreign_buy=1e9) for i in range(40)]
        sig = compute_smart_money(recs)
        for name, p in sig.primitives.items():
            self.assertIn(p.bucket, ("setup", "trigger"))
            if name == "prop":
                self.assertEqual(p.bucket, "setup")
            if name == "foreign":
                self.assertEqual(p.bucket, "setup")

    def test_opposite_signs_cancel(self) -> None:
        recs = []
        for i in range(40):
            recs.append(_mk_record(
                i,
                prop_net=5_000_000_000,
                foreign_buy=0,
                foreign_sell=5_000_000_000,
            ))
        sig = compute_smart_money(recs)
        self.assertLess(abs(sig.setup_composite), 0.3)

    def test_empty_records(self) -> None:
        sig = compute_smart_money([])
        self.assertEqual(sig.setup_composite, 0.0)
        self.assertEqual(sig.label, "neutral")

    def test_label_classification(self) -> None:
        recs = [
            _mk_record(i, prop_net=8_000_000_000,
                       foreign_buy=8_000_000_000)
            for i in range(40)
        ]
        sig = compute_smart_money(recs)
        self.assertIn(sig.label, ("bull", "strong_bull"))


class Phase2Test(unittest.TestCase):
    def test_concentration_load_up_day(self) -> None:
        from src.analysis.smart_money.primitives import ConcentrationPrimitive

        # 19 quiet days, day 20 = huge buy + green + high volume
        recs = [_mk_record(i, prop_net=100_000_000) for i in range(19)]
        big = _mk_record(
            19, prop_net=20_000_000_000,
            total_value=300_000_000_000,  # 3x normal volume → high RVOL
        )
        recs.append(big)
        prim = ConcentrationPrimitive().compute(recs, DEFAULT_SMART_MONEY_CONFIG)
        self.assertEqual(prim.bucket, "trigger")
        self.assertGreater(prim.value, 0.3)
        self.assertEqual(prim.components["is_load_up"], 1.0)

    def test_concentration_no_signal_low_rvol(self) -> None:
        from src.analysis.smart_money.primitives import ConcentrationPrimitive

        recs = [_mk_record(i, prop_net=1e9) for i in range(20)]
        prim = ConcentrationPrimitive().compute(recs, DEFAULT_SMART_MONEY_CONFIG)
        # Even flow → low concentration ratio
        self.assertLess(abs(prim.value), 0.5)

    def test_persistence_high_when_consistent(self) -> None:
        from src.analysis.smart_money.primitives import PersistenceDetector

        recs = [_mk_record(i, prop_net=1e9) for i in range(20)]
        sig = PersistenceDetector().compute(recs, DEFAULT_SMART_MONEY_CONFIG)
        self.assertAlmostEqual(sig.value, 1.0)
        self.assertAlmostEqual(sig.confidence, 1.0)

    def test_persistence_low_when_noisy(self) -> None:
        from src.analysis.smart_money.primitives import PersistenceDetector

        recs = []
        for i in range(20):
            recs.append(_mk_record(i, prop_net=1e9 if i % 2 == 0 else -1e9))
        sig = PersistenceDetector().compute(recs, DEFAULT_SMART_MONEY_CONFIG)
        self.assertEqual(sig.value, 0.0)

    def test_persistence_multiplier_lowers_setup_confidence(self) -> None:
        # Noisy alternating prop flow → persistence ≈ 0 → multiplier 0.5
        recs = []
        for i in range(40):
            recs.append(_mk_record(
                i, prop_net=2e9 if i % 2 == 0 else -2e9,
                foreign_buy=1e9, foreign_sell=0,
            ))
        cfg_off = SmartMoneyConfig(use_persistence=False, use_divergence=False,
                                   use_concentration=False, use_toxic_flow=False)
        cfg_on = SmartMoneyConfig(use_persistence=True, use_divergence=False,
                                  use_concentration=False, use_toxic_flow=False)
        sig_off = compute_smart_money(recs, cfg_off)
        sig_on = compute_smart_money(recs, cfg_on)
        self.assertLess(sig_on.setup_confidence, sig_off.setup_confidence)
        # Composite values should not change — only confidence
        self.assertAlmostEqual(sig_on.setup_composite, sig_off.setup_composite, places=4)

    def test_toxic_flow_detection(self) -> None:
        from src.analysis.smart_money.primitives import ToxicFlowDetector

        recs = []
        # 15 normal flat bars
        for i in range(15):
            r = _mk_record(i)
            r.priceClose = 100.0
            recs.append(r)
        # 5 bars: price rallies +5%, smart money distributes hard
        for i in range(15, 20):
            r = _mk_record(
                i,
                prop_net=-30_000_000_000,
                foreign_buy=0,
                foreign_sell=30_000_000_000,
            )
            r.priceClose = 100.0 + (i - 14) * 1.0  # +5%
            recs.append(r)
        toxic = ToxicFlowDetector().detect(recs, DEFAULT_SMART_MONEY_CONFIG)
        self.assertTrue(toxic)

    def test_toxic_flow_not_triggered_normal(self) -> None:
        from src.analysis.smart_money.primitives import ToxicFlowDetector

        recs = [_mk_record(i, prop_net=1e9, foreign_buy=1e9) for i in range(20)]
        self.assertFalse(ToxicFlowDetector().detect(recs, DEFAULT_SMART_MONEY_CONFIG))

    def test_toxic_label_overrides(self) -> None:
        recs = []
        for i in range(15):
            r = _mk_record(i)
            r.priceClose = 100.0
            recs.append(r)
        for i in range(15, 20):
            r = _mk_record(
                i, prop_net=-30_000_000_000,
                foreign_sell=30_000_000_000,
            )
            r.priceClose = 100.0 + (i - 14) * 1.0
            recs.append(r)
        sig = compute_smart_money(recs)
        self.assertTrue(sig.is_toxic)
        self.assertEqual(sig.label, "toxic")

    def test_phase2_disabled_matches_phase1_setup(self) -> None:
        # Regression: Phase 2 OFF should not affect setup_composite
        recs = [_mk_record(i, prop_net=2e9, foreign_buy=2e9) for i in range(40)]
        cfg_p1 = SmartMoneyConfig(
            use_divergence=False, use_concentration=False,
            use_persistence=False, use_toxic_flow=False,
        )
        sig = compute_smart_money(recs, cfg_p1)
        self.assertGreater(sig.setup_composite, 0.0)
        self.assertEqual(sig.trigger_composite, 0.0)
        self.assertFalse(sig.is_toxic)


class IntegrationV5Test(unittest.TestCase):
    def test_v5_runs_end_to_end(self) -> None:
        from src.analysis.signal_scoring_v5 import calculate_signal_score_v5

        recs = [
            _mk_record(i, prop_net=2_000_000_000,
                       foreign_buy=3_000_000_000)
            for i in range(80)
        ]
        score = calculate_signal_score_v5(recs)
        self.assertIn(score.label, ("bullish", "bearish"))
        self.assertGreaterEqual(score.final_score, 0.0)
        self.assertLessEqual(score.final_score, 1.0)
        # Smart money fields populated
        self.assertIn(score.smart_money_label,
                      ("strong_bull", "bull", "neutral", "bear", "strong_bear", "toxic"))

    def test_v5_warmup(self) -> None:
        from src.analysis.signal_scoring_v5 import calculate_signal_score_v5

        recs = [_mk_record(i) for i in range(10)]
        score = calculate_signal_score_v5(recs)
        self.assertIn("Warm-up<30", score.reasons)


if __name__ == "__main__":
    unittest.main()
