"""Tunable thresholds for the TA engine — one place to change behaviour.

Every number a trader might want to argue about lives here, not scattered
through the detectors.
"""
from dataclasses import dataclass, replace
from typing import Dict


@dataclass(frozen=True)
class RsiConfig:
    """Rules for the RSI reversal signal.

    The signal the user asked for has three parts, in order:
      1. RSI enters the extreme zone (below ``oversold`` / above ``overbought``)
      2. RSI turns around inside the zone (a trough / peak forms)
      3. RSI comes back and touches the threshold again -> report
    """
    period: int = 14
    oversold: float = 30.0
    overbought: float = 70.0
    # Quality filters — recorded on every event, and used to mark it weak.
    min_bars_in_zone: int = 2      # a single-bar wick into the zone is noise
    min_depth: float = 3.0         # RSI must dig at least this far past the line
    # "dấu hiệu quay đầu" while still inside the zone (early watchlist state)
    turn_min_move: float = 2.0     # RSI points recovered off the extreme
    turn_min_bars: int = 1         # ... sustained for at least this many bars
    divergence_lookback: int = 40  # window to look for the previous extreme


@dataclass(frozen=True)
class AdxConfig:
    """ADX regime bands. ``trend_threshold`` is the user's 'có động lực' line."""
    period: int = 14
    trend_threshold: float = 20.0
    strong_threshold: float = 25.0
    slope_bars: int = 3            # ADX rising or falling, measured over N bars


@dataclass(frozen=True)
class ScanConfig:
    rsi: RsiConfig = RsiConfig()
    adx: AdxConfig = AdxConfig()
    lookback_days: int = 400       # history pulled before the window of interest
    recent_bars: int = 5           # how far back an event still counts as "mới"


#: Ready-made profiles. ``standard`` follows the textbook 30/70 lines;
#: ``aggressive`` suits VN mid-caps that rarely reach the textbook extremes.
PROFILES: Dict[str, ScanConfig] = {
    "standard": ScanConfig(),
    "aggressive": ScanConfig(
        rsi=replace(RsiConfig(), oversold=35.0, overbought=65.0, min_depth=2.0),
        adx=replace(AdxConfig(), trend_threshold=18.0),
    ),
    "strict": ScanConfig(
        rsi=replace(RsiConfig(), oversold=25.0, overbought=75.0,
                    min_bars_in_zone=3, min_depth=5.0),
        adx=replace(AdxConfig(), trend_threshold=25.0),
    ),
}


def get_profile(name: str = "standard") -> ScanConfig:
    if name not in PROFILES:
        raise ValueError(
            f"Unknown profile {name!r}. Available: {', '.join(PROFILES)}"
        )
    return PROFILES[name]
