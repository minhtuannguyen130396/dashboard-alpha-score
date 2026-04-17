"""SmartMoneyConfig — tunables for the smart money module."""
from dataclasses import dataclass, field
from typing import Dict


@dataclass
class SmartMoneyConfig:
    # Primitives bật/tắt
    use_prop: bool = True
    use_foreign: bool = True
    use_divergence: bool = True        # Phase 2
    use_concentration: bool = True     # Phase 2
    use_persistence: bool = True       # Phase 2
    use_toxic_flow: bool = True        # Phase 2

    # Phase 3+ (intraday)
    use_intraday: bool = False
    use_ofi: bool = True
    use_block_trades: bool = True
    use_vwap_relationship: bool = True
    use_auction_flow: bool = True
    use_intraday_divergence: bool = True
    intraday_bar_size: str = "5m"
    weight_daily: float = 0.7
    weight_intraday: float = 0.3
    tick_storage_path: str = "data_tick"
    intraday_feature_cache_path: str = "data_tick_features"
    block_threshold_multiplier: float = 30.0
    trade_classification_method: str = "auto"  # tick_rule|lee_ready|bvc|auto

    # Phase 5 (calibration)
    use_calibrated_weights: bool = False
    calibration_weights_file: str = "calibrated_weights.json"
    use_regime_weights: bool = False
    use_symbol_class_weights: bool = False
    expected_return_bins_file: str = "expected_returns.json"

    # Setup bucket weights. Only primitives with bucket="setup" may appear.
    setup_weights: Dict[str, float] = field(default_factory=lambda: {
        "prop": 0.50,
        "foreign": 0.50,
    })

    # Trigger bucket weights. Phase 1 has no trigger primitives, but the
    # config already lists the Phase 2 names so bucket assignment is locked.
    # Phase 4: intraday primitive weights are present so composite can
    # aggregate them when bars/ticks arrive. When intraday is off, these
    # primitives are absent → _aggregate_bucket auto-rebalances.
    trigger_weights: Dict[str, float] = field(default_factory=lambda: {
        "divergence": 0.20,
        "concentration": 0.15,
        "ofi": 0.20,
        "block_trade": 0.15,
        "vwap_relationship": 0.10,
        "auction_flow": 0.10,
        "intraday_divergence": 0.10,
    })

    # UI-only weights for merging setup & trigger into signal.composite.
    # The scoring engine does NOT read these.
    ui_weight_setup: float = 0.6
    ui_weight_trigger: float = 0.4

    # Windows
    short_window: int = 10
    long_window: int = 20
    normalize_window: int = 60

    # Toxic detection (Phase 2)
    toxic_price_change_threshold: float = 0.03
    toxic_flow_opposite_threshold: float = -0.3


DEFAULT_SMART_MONEY_CONFIG = SmartMoneyConfig()
