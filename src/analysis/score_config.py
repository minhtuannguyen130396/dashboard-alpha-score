from dataclasses import dataclass, field


@dataclass
class ScoreWeightsV2:
    # Setup score component weights (must sum to 1.0)
    setup_candle: float = 0.20
    setup_trend: float = 0.25
    setup_momentum: float = 0.20
    setup_volume: float = 0.20
    setup_structure: float = 0.15

    # Trigger score component weights (must sum to 1.0)
    trigger_confirmation: float = 0.35
    trigger_volume: float = 0.25
    trigger_candle: float = 0.20
    trigger_momentum: float = 0.10
    trigger_structure: float = 0.10

    # Final score blend
    final_setup: float = 0.55
    final_trigger: float = 0.45


@dataclass
class ScoreThresholdsV2:
    setup_watch: float = 0.55      # worth monitoring
    setup_good: float = 0.65       # solid setup
    trigger: float = 0.70          # entry signal
    strong_signal: float = 0.80    # high-conviction entry

    # Blocker thresholds
    adx_min: float = 20.0          # below this = likely sideway
    rvol_min: float = 0.8          # below this = weak volume
    rsi_overbought: float = 75.0   # bullish blocker
    rsi_oversold: float = 25.0     # bearish blocker


@dataclass
class IndicatorPeriodsV2:
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


@dataclass
class FeatureTogglesV2:
    use_candle: bool = True
    use_trend: bool = True
    use_momentum: bool = True
    use_volume: bool = True
    use_structure: bool = True
    use_confirmation: bool = True


@dataclass
class ScoreConfigV2:
    weights: ScoreWeightsV2 = field(default_factory=ScoreWeightsV2)
    thresholds: ScoreThresholdsV2 = field(default_factory=ScoreThresholdsV2)
    periods: IndicatorPeriodsV2 = field(default_factory=IndicatorPeriodsV2)
    toggles: FeatureTogglesV2 = field(default_factory=FeatureTogglesV2)


DEFAULT_SCORE_CONFIG_V2 = ScoreConfigV2()
