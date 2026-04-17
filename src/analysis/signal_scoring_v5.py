"""Signal Score V5 — V4 + smart money module.

V5 differs from V4 only in two places:

1. The prop-trading component (``setup_prop``) is replaced by a dedicated
   smart money module that aggregates multiple flow primitives (prop +
   foreign in Phase 1) with confidence-weighted compositing.
2. The setup and trigger buckets both expose a smart money slot, so
   intraday/trigger-side flow primitives (added in Phase 2+) can plug in
   without further refactoring.

All other scoring helpers (candle, trend, momentum, volume, structure,
confirmation, divergence, regime, blockers) are imported from V4 to keep
them in lock-step and make behavioral diffs easy to trace.
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from src.data.stock_data_loader import StockRecord
from src.analysis.smart_money import (
    SmartMoneySignal,
    compute_smart_money,
)
from src.analysis.score_config import (
    ScoreConfigV5,
    DEFAULT_SCORE_CONFIG_V5,
)
from src.analysis.signal_scoring_v4 import (
    Blocker,
    _score_candle_v4,
    _score_trend_v4,
    _score_momentum_v4,
    _score_volume_setup_v4,
    _score_volume_trigger_v4,
    _score_structure_v4,
    _score_confirmation_v4,
    _score_divergence_v4,
    _score_regime_align_v4,
    _detect_blockers_v4,
    _safe_last,
)
from src.analysis.technical_indicators import (
    IndicatorGroup2, IndicatorGroup3,
)


@dataclass
class SignalScoreV5:
    label: str = "none"
    regime: str = "unknown"
    setup_score: float = 0.0
    trigger_score: float = 0.0
    final_score: float = 0.0
    candle_score: float = 0.0
    trend_score: float = 0.0
    momentum_score: float = 0.0
    volume_setup_score: float = 0.0
    volume_trigger_score: float = 0.0
    structure_score: float = 0.0
    confirmation_score: float = 0.0
    divergence_score: float = 0.0
    regime_align_score: float = 0.0

    # Smart money — exposed split so UI / debug can see each side
    smart_money_setup_score: float = 0.0       # post-confidence, pre-weight
    smart_money_trigger_score: float = 0.0
    smart_money_setup_composite: float = 0.0   # raw [-1..+1]
    smart_money_trigger_composite: float = 0.0
    smart_money_confidence: float = 0.0        # UI-only merged
    smart_money_label: str = "neutral"
    smart_money_narrative: str = ""

    blockers: List[Blocker] = field(default_factory=list)
    reasons: List[str] = field(default_factory=list)

    @property
    def reason_text(self) -> str:
        return " | ".join(self.reasons)

    @property
    def volume_score(self) -> float:
        return round((self.volume_setup_score + self.volume_trigger_score) / 2, 4)

    @property
    def blockers_text(self) -> List[str]:
        return [f"[{b.severity}] {b.msg}" for b in self.blockers]


def _smart_money_directional_score(
    composite: float, confidence: float, bullish: bool,
) -> float:
    """Convert a signed composite to a bullish / bearish [0..1] score.

    ``max(0, ±composite) × confidence`` — when the flow opposes the trade
    direction, the slot contributes zero rather than a negative drag.
    """
    directional = composite if bullish else -composite
    if directional < 0:
        return 0.0
    return max(0.0, directional) * max(0.0, min(1.0, confidence))


def _build_score_v5(
    records: List[StockRecord],
    bullish: bool,
    cfg: ScoreConfigV5,
) -> SignalScoreV5:
    w = cfg.weights
    p = cfg.periods
    t = cfg.toggles

    candle_score, candle_r = _score_candle_v4(records, bullish, cfg.v4_compat()) if t.use_candle else (0.5, "")
    trend_score, trend_r = _score_trend_v4(records, bullish, cfg.v4_compat()) if t.use_trend else (0.5, "")
    momentum_score, momentum_r = _score_momentum_v4(records, bullish, cfg.v4_compat()) if t.use_momentum else (0.5, "")
    vol_setup, vs_r = _score_volume_setup_v4(records, bullish, cfg.v4_compat()) if t.use_volume else (0.5, "")
    vol_trig, vt_r = _score_volume_trigger_v4(records, bullish, cfg.v4_compat()) if t.use_volume else (0.5, "")
    structure_score, structure_r = _score_structure_v4(records, bullish, cfg.v4_compat()) if t.use_structure else (0.5, "")
    confirmation_score, conf_r = _score_confirmation_v4(records, bullish, cfg.v4_compat()) if t.use_confirmation else (0.5, "")
    divergence_score, div_r = _score_divergence_v4(records, bullish, cfg.v4_compat()) if t.use_divergence else (0.0, "")
    regime_align, reg_r, regime = _score_regime_align_v4(records, bullish, cfg.v4_compat()) if t.use_regime_align else (0.5, "", "unknown")

    # Smart money — single call, split into two buckets
    if t.use_smart_money:
        sm: SmartMoneySignal = compute_smart_money(records, cfg.smart_money)
    else:
        sm = SmartMoneySignal()

    sm_setup_score = _smart_money_directional_score(
        sm.setup_composite, sm.setup_confidence, bullish,
    )
    sm_trigger_score = _smart_money_directional_score(
        sm.trigger_composite, sm.trigger_confidence, bullish,
    )

    setup_score = (
        w.setup_candle       * candle_score
        + w.setup_trend      * trend_score
        + w.setup_momentum   * momentum_score
        + w.setup_volume     * vol_setup
        + w.setup_structure  * structure_score
        + w.setup_regime     * regime_align
        + w.setup_smartmoney * sm_setup_score
    )
    trigger_score = (
        w.trigger_confirmation * confirmation_score
        + w.trigger_volume       * vol_trig
        + w.trigger_candle       * candle_score
        + w.trigger_momentum     * momentum_score
        + w.trigger_divergence   * divergence_score
        + w.trigger_smartmoney   * sm_trigger_score
    )
    final_score = w.final_setup * setup_score + w.final_trigger * trigger_score

    # Blockers — reuse V4
    close = records[-1].priceClose
    adx = _safe_last(IndicatorGroup3.adx(records, p.adx))
    vols = [r.priceImpactVolume for r in records]
    avg_vol = sum(vols[-p.rvol:]) / min(p.rvol, len(vols)) if vols else 1.0
    rvol = records[-1].priceImpactVolume / avg_vol if avg_vol else 0.0
    rsi = _safe_last(IndicatorGroup2.rsi(records, p.rsi), 50.0)
    _, _, hist_s = IndicatorGroup2.macd(records, p.macd_fast, p.macd_slow, p.macd_signal)
    macd_hist = _safe_last(hist_s)
    macd_hist_prev = _safe_last(hist_s[:-1]) if len(hist_s) > 1 else 0.0
    atr = _safe_last(IndicatorGroup3.atr(records, p.atr))
    n = min(p.swing_short, len(records))
    swing_high = max(r.priceHigh for r in records[-n:])
    swing_low = min(r.priceLow for r in records[-n:])

    blockers = _detect_blockers_v4(
        records, bullish, adx, rvol, rsi,
        macd_hist, macd_hist_prev, close,
        swing_high, swing_low, atr, cfg.v4_compat(),
    )

    # Toxic flow hard blocker (Phase 2+ will populate is_toxic)
    if sm.is_toxic and bullish:
        blockers.append(Blocker(
            "toxic_flow", "hard",
            "retail FOMO, smart money exiting",
        ))

    soft_count = sum(1 for b in blockers if b.severity == "soft")
    final_score = max(0.0, final_score - soft_count * cfg.thresholds.soft_penalty)

    sm_reason = sm.narrative if sm.narrative else ""
    reasons = [r for r in [
        candle_r, trend_r, momentum_r, vs_r, vt_r,
        structure_r, conf_r, div_r, reg_r, sm_reason,
    ] if r]

    return SignalScoreV5(
        label="bullish" if bullish else "bearish",
        regime=regime,
        setup_score=round(setup_score, 4),
        trigger_score=round(trigger_score, 4),
        final_score=round(final_score, 4),
        candle_score=round(candle_score, 4),
        trend_score=round(trend_score, 4),
        momentum_score=round(momentum_score, 4),
        volume_setup_score=round(vol_setup, 4),
        volume_trigger_score=round(vol_trig, 4),
        structure_score=round(structure_score, 4),
        confirmation_score=round(confirmation_score, 4),
        divergence_score=round(divergence_score, 4),
        regime_align_score=round(regime_align, 4),
        smart_money_setup_score=round(sm_setup_score, 4),
        smart_money_trigger_score=round(sm_trigger_score, 4),
        smart_money_setup_composite=round(sm.setup_composite, 4),
        smart_money_trigger_composite=round(sm.trigger_composite, 4),
        smart_money_confidence=round(sm.confidence, 4),
        smart_money_label=sm.label,
        smart_money_narrative=sm.narrative,
        blockers=blockers,
        reasons=reasons,
    )


def calculate_signal_score_v5(
    records: List[StockRecord],
    cfg: Optional[ScoreConfigV5] = None,
) -> SignalScoreV5:
    if cfg is None:
        cfg = DEFAULT_SCORE_CONFIG_V5

    if len(records) < 30:
        return SignalScoreV5(reasons=["Warm-up<30"])

    bull = _build_score_v5(records, True, cfg)
    bear = _build_score_v5(records, False, cfg)

    winner = bull if bull.final_score >= bear.final_score else bear
    if len(records) < 60:
        winner.final_score = round(winner.final_score * 0.6, 4)
        winner.reasons.append("half-warmup")
    return winner
