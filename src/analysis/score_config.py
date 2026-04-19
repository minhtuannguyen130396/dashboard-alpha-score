"""Score V4 configuration.

V4 supersedes V1, V2 and V3. Key tuning vs V3:
- Looser entry thresholds + lower hard blockers → more tradable signals.
- Wider rolling rank window (60 → 120 bars) so trending names don't get
  stuck in mid-rank purgatory.
- Smaller per-soft-blocker penalty so a single soft flag doesn't kill an
  otherwise good setup.
- Dedicated `sell_*` thresholds (decoupled from buy) — exits are looser
  than entries because the trade simulator already manages risk via
  ATR stop / trailing stop.
"""
from dataclasses import dataclass, field


@dataclass
class ScoreWeightsV4:
    # Setup: where the market is + precondition alignment
    setup_candle:    float = 0.15
    setup_trend:     float = 0.22
    setup_momentum:  float = 0.13
    setup_volume:    float = 0.13  # setup-volume = OBV/MFI trend
    setup_structure: float = 0.17
    setup_regime:    float = 0.10  # market regime alignment
    setup_prop:      float = 0.10  # domestic proprietary trading flow

    # Trigger: what's happening today that should pull the trigger
    trigger_confirmation: float = 0.35
    trigger_volume:       float = 0.25  # trigger-volume = RVOL / range
    trigger_candle:       float = 0.20
    trigger_momentum:     float = 0.10
    trigger_divergence:   float = 0.10

    final_setup:   float = 0.55
    final_trigger: float = 0.45


@dataclass
class ScoreThresholdsV4:
    setup_watch: float = 0.55
    setup_good:  float = 0.62

    # Entry gates (buy)
    final_signal:  float = 0.48
    trigger:       float = 0.43
    strong_signal: float = 0.78

    # Exit gates (sell) — intentionally looser than entry; trade
    # simulator already protects with ATR stop/trail.
    sell_final:   float = 0.50
    sell_trigger: float = 0.42

    # Hard blockers → rejection (only the genuinely dead-tape stuff)
    hard_adx_min:  float = 10.0
    hard_rvol_min: float = 0.3

    # Soft blockers → score penalty only
    soft_adx_min:       float = 18.0
    soft_rvol_min:      float = 0.7
    rsi_overbought:     float = 80.0
    rsi_oversold:       float = 20.0
    soft_penalty:       float = 0.04  # per soft blocker


@dataclass
class IndicatorPeriodsV4:
    ema_fast: int = 20
    ema_mid: int = 50
    ema_slow: int = 100
    atr: int = 14
    rsi: int = 14
    macd_fast: int = 12
    macd_slow: int = 26
    macd_signal: int = 9
    adx: int = 14
    rvol: int = 20
    swing_short: int = 10
    swing_long: int = 20
    obv_slope: int = 5
    mfi: int = 14
    roc: int = 5
    zscore_window: int = 120
    divergence_lookback: int = 14
    prop_short: int = 10   # short-window prop trading flow
    prop_long: int = 20    # long-window prop trading flow


@dataclass
class FeatureTogglesV4:
    use_candle: bool = True
    use_trend: bool = True
    use_momentum: bool = True
    use_volume: bool = True
    use_structure: bool = True
    use_confirmation: bool = True
    use_divergence: bool = True
    use_regime_align: bool = True
    use_prop: bool = True


@dataclass
class ScoreConfigV4:
    weights: ScoreWeightsV4 = field(default_factory=ScoreWeightsV4)
    thresholds: ScoreThresholdsV4 = field(default_factory=ScoreThresholdsV4)
    periods: IndicatorPeriodsV4 = field(default_factory=IndicatorPeriodsV4)
    toggles: FeatureTogglesV4 = field(default_factory=FeatureTogglesV4)


DEFAULT_SCORE_CONFIG_V4 = ScoreConfigV4()


# =============================================================================
# V5 — V4 + smart money module (prop + foreign in Phase 1)
# =============================================================================
from src.analysis.smart_money.config import (
    DEFAULT_SMART_MONEY_CONFIG,
    SmartMoneyConfig,
)


@dataclass
class ScoreWeightsV5:
    # Setup bucket
    setup_candle:     float = 0.15
    setup_trend:      float = 0.22
    setup_momentum:   float = 0.13
    setup_volume:     float = 0.13
    setup_structure:  float = 0.17
    setup_regime:     float = 0.10
    setup_smartmoney: float = 0.10    # prop + foreign (Phase 1)

    # Trigger bucket — Phase 2 rebalance to make room for trigger_smartmoney
    trigger_confirmation: float = 0.30   # 0.35 → 0.30
    trigger_volume:       float = 0.22   # 0.25 → 0.22
    trigger_candle:       float = 0.18   # 0.20 → 0.18
    trigger_momentum:     float = 0.08   # 0.10 → 0.08
    trigger_divergence:   float = 0.10   # V4 price/indicator div, kept
    trigger_smartmoney:   float = 0.12   # Phase 2: divergence + concentration

    final_setup:   float = 0.55
    final_trigger: float = 0.45


@dataclass
class FeatureTogglesV5:
    use_candle: bool = True
    use_trend: bool = True
    use_momentum: bool = True
    use_volume: bool = True
    use_structure: bool = True
    use_confirmation: bool = True
    use_divergence: bool = True
    use_regime_align: bool = True
    use_smart_money: bool = True


@dataclass
class ScoreConfigV5:
    weights: ScoreWeightsV5 = field(default_factory=ScoreWeightsV5)
    thresholds: ScoreThresholdsV4 = field(default_factory=ScoreThresholdsV4)
    periods: IndicatorPeriodsV4 = field(default_factory=IndicatorPeriodsV4)
    toggles: FeatureTogglesV5 = field(default_factory=FeatureTogglesV5)
    smart_money: SmartMoneyConfig = field(default_factory=SmartMoneyConfig)

    def v4_compat(self) -> ScoreConfigV4:
        """Build a V4 config view that V4 helper functions can consume.

        V5 reuses V4's candle/trend/momentum/volume/structure/blocker helpers
        unchanged. Those helpers expect a ``ScoreConfigV4`` so we project the
        V5 thresholds + periods (the only fields they actually read) into one.
        """
        v4_weights = ScoreWeightsV4(
            setup_candle=self.weights.setup_candle,
            setup_trend=self.weights.setup_trend,
            setup_momentum=self.weights.setup_momentum,
            setup_volume=self.weights.setup_volume,
            setup_structure=self.weights.setup_structure,
            setup_regime=self.weights.setup_regime,
            setup_prop=0.0,
            trigger_confirmation=self.weights.trigger_confirmation,
            trigger_volume=self.weights.trigger_volume,
            trigger_candle=self.weights.trigger_candle,
            trigger_momentum=self.weights.trigger_momentum,
            trigger_divergence=self.weights.trigger_divergence,
            final_setup=self.weights.final_setup,
            final_trigger=self.weights.final_trigger,
        )
        v4_toggles = FeatureTogglesV4(
            use_candle=self.toggles.use_candle,
            use_trend=self.toggles.use_trend,
            use_momentum=self.toggles.use_momentum,
            use_volume=self.toggles.use_volume,
            use_structure=self.toggles.use_structure,
            use_confirmation=self.toggles.use_confirmation,
            use_divergence=self.toggles.use_divergence,
            use_regime_align=self.toggles.use_regime_align,
            use_prop=False,    # V5 handles flow via smart_money
        )
        return ScoreConfigV4(
            weights=v4_weights,
            thresholds=self.thresholds,
            periods=self.periods,
            toggles=v4_toggles,
        )


DEFAULT_SCORE_CONFIG_V5 = ScoreConfigV5()
