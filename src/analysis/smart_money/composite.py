"""Composite aggregator for smart money primitives.

Splits primitives into two independent buckets (setup, trigger), aggregates
each into a normalized value + confidence, then exposes a UI-only merged
composite for display. Scoring engines consume ``setup_*`` / ``trigger_*``
directly and never read the merged ``composite``.

Phase 2 adds:
- Persistence multiplier on ``setup_confidence`` (NOT a bucket primitive)
- Toxic flow detection that sets ``is_toxic`` without modifying composites

Phase 3 adds the multi-timeframe entry point ``compute_smart_money_v3`` that
accepts pre-adapted ``DailyFlowRecord`` / ``IntradayFlowRecord`` lists; the
classic ``compute_smart_money`` keeps its ``StockRecord`` signature for
backwards compatibility with existing scoring callers.
"""
from typing import Dict, List, Optional, Tuple

from src.analysis.smart_money.config import (
    DEFAULT_SMART_MONEY_CONFIG,
    SmartMoneyConfig,
)
from src.analysis.smart_money.narrative import generate_narrative
from src.analysis.smart_money.primitives import (
    ConcentrationPrimitive,
    DivergencePrimitive,
    ForeignFlowPrimitive,
    PersistenceDetector,
    PropFlowPrimitive,
    ToxicFlowDetector,
)
from src.analysis.smart_money.types import FlowPrimitive, SmartMoneySignal


def _aggregate_bucket(
    primitives: Dict[str, FlowPrimitive],
    weights: Dict[str, float],
) -> Tuple[float, float]:
    """Weighted average over primitives, weighted by configured weight × confidence.

    Confidence of the bucket = effective weight / max configured weight.
    A bucket whose primitives all have confidence=0 also has confidence=0.
    """
    if not primitives or not weights:
        return 0.0, 0.0

    total_weight = 0.0
    weighted_sum = 0.0
    for name, prim in primitives.items():
        base_w = weights.get(name, 0.0)
        if base_w <= 0:
            continue
        eff_w = base_w * max(0.0, min(1.0, prim.confidence))
        weighted_sum += prim.value * eff_w
        total_weight += eff_w

    max_weight = sum(w for n, w in weights.items() if n in primitives)
    if max_weight <= 0 or total_weight <= 0:
        return 0.0, 0.0
    composite = weighted_sum / total_weight
    confidence = total_weight / max_weight
    composite = max(-1.0, min(1.0, composite))
    confidence = max(0.0, min(1.0, confidence))
    return composite, confidence


def _ui_merge(
    setup_val: float, setup_conf: float,
    trigger_val: float, trigger_conf: float,
    w_setup: float, w_trigger: float,
) -> Tuple[float, float]:
    ws = w_setup * setup_conf
    wt = w_trigger * trigger_conf
    total = ws + wt
    if total <= 0:
        return 0.0, 0.0
    composite = (setup_val * ws + trigger_val * wt) / total
    max_total = w_setup + w_trigger
    confidence = total / max_total if max_total > 0 else 0.0
    return composite, confidence


def _classify_label(composite: float, confidence: float) -> str:
    if confidence < 0.2:
        return "neutral"
    mag = abs(composite)
    if mag >= 0.6 and confidence >= 0.5:
        return "strong_bull" if composite > 0 else "strong_bear"
    if mag >= 0.3:
        return "bull" if composite > 0 else "bear"
    return "neutral"


def _detect_trend(records: List, primitives: Dict[str, FlowPrimitive]) -> str:
    prop = primitives.get("prop")
    if not prop or prop.confidence < 0.3:
        return "stable"
    short_sum = prop.components.get("short_sum", 0.0)
    long_sum = prop.components.get("long_sum", 0.0)
    prior_sum = long_sum - short_sum
    if prior_sum == 0 and short_sum == 0:
        return "stable"
    if abs(short_sum) > abs(prior_sum) * 1.2:
        return "strengthening"
    if abs(short_sum) < abs(prior_sum) * 0.8:
        return "weakening"
    return "stable"


def _assert_bucket_invariants(
    cfg: SmartMoneyConfig,
    primitives: Dict[str, FlowPrimitive],
) -> None:
    overlap = set(cfg.setup_weights) & set(cfg.trigger_weights)
    assert not overlap, f"primitive(s) assigned to both buckets: {overlap}"
    for name, p in primitives.items():
        if name in cfg.setup_weights:
            assert p.bucket == "setup", f"{name}: expected bucket=setup"
        if name in cfg.trigger_weights:
            assert p.bucket == "trigger", f"{name}: expected bucket=trigger"


# =============================================================================
# Per-layer compute (used by both single-layer and multi-timeframe paths)
# =============================================================================

def _resolve_weights(
    cfg: SmartMoneyConfig,
    regime: Optional[str] = None,
    symbol_class: Optional[str] = None,
) -> Tuple[Dict[str, float], Dict[str, float]]:
    """Pick (setup_weights, trigger_weights), honoring Phase 5 calibration."""
    if cfg.use_calibrated_weights:
        try:
            from src.analysis.smart_money.calibration import load_calibrated_weights
            cal = load_calibrated_weights(cfg.calibration_weights_file)
            learned = cal.get_weights(
                regime=regime if cfg.use_regime_weights else None,
                symbol_class=symbol_class if cfg.use_symbol_class_weights else None,
            )
            if learned:
                setup_keys = set(cfg.setup_weights)
                trigger_keys = set(cfg.trigger_weights)
                setup_w = {k: v for k, v in learned.items() if k in setup_keys}
                trigger_w = {k: v for k, v in learned.items() if k in trigger_keys}
                # Renormalize each side
                if setup_w:
                    s = sum(setup_w.values())
                    if s > 0:
                        setup_w = {k: v / s for k, v in setup_w.items()}
                if trigger_w:
                    s = sum(trigger_w.values())
                    if s > 0:
                        trigger_w = {k: v / s for k, v in trigger_w.items()}
                return (
                    setup_w or cfg.setup_weights,
                    trigger_w or cfg.trigger_weights,
                )
        except Exception:
            pass
    return cfg.setup_weights, cfg.trigger_weights


def _compute_daily_layer(
    records: List, cfg: SmartMoneyConfig,
    regime: Optional[str] = None,
    symbol_class: Optional[str] = None,
) -> Tuple[Dict[str, FlowPrimitive], float, float, float, float, bool]:
    """Run all daily primitives over ``records`` and return bucket outputs.

    Returns ``(primitives, setup_composite, setup_conf, trigger_composite,
    trigger_conf, is_toxic)``. Persistence (multiplier) and toxic (flag) are
    applied here so callers don't need to know about them.
    """
    primitives: Dict[str, FlowPrimitive] = {}

    if cfg.use_prop:
        p = PropFlowPrimitive()
        if len(records) >= p.min_records():
            primitives["prop"] = p.compute(records, cfg)

    if cfg.use_foreign:
        f = ForeignFlowPrimitive()
        if len(records) >= f.min_records():
            primitives["foreign"] = f.compute(records, cfg)

    if cfg.use_divergence:
        d = DivergencePrimitive()
        if len(records) >= d.min_records():
            primitives["divergence"] = d.compute(records, cfg)

    if cfg.use_concentration:
        c = ConcentrationPrimitive()
        if len(records) >= c.min_records():
            primitives["concentration"] = c.compute(records, cfg)

    _assert_bucket_invariants(cfg, primitives)

    setup_prims = {k: p for k, p in primitives.items() if p.bucket == "setup"}
    trigger_prims = {k: p for k, p in primitives.items() if p.bucket == "trigger"}

    setup_w, trigger_w = _resolve_weights(cfg, regime=regime, symbol_class=symbol_class)
    setup_composite, setup_conf = _aggregate_bucket(setup_prims, setup_w)
    trigger_composite, trigger_conf = _aggregate_bucket(trigger_prims, trigger_w)

    # Persistence multiplier (only on setup_confidence)
    if cfg.use_persistence:
        persistence = PersistenceDetector().compute(records, cfg)
        if persistence.confidence > 0:
            persistence_factor = 0.5 + 0.5 * abs(persistence.value)
            setup_conf *= persistence_factor

    # Toxic flow flag
    is_toxic = False
    if cfg.use_toxic_flow:
        is_toxic = ToxicFlowDetector().detect(records, cfg)

    return primitives, setup_composite, setup_conf, trigger_composite, trigger_conf, is_toxic


def compute_smart_money(
    records: List,
    cfg: SmartMoneyConfig = None,
    regime: Optional[str] = None,
    symbol_class: Optional[str] = None,
) -> SmartMoneySignal:
    """Compute the daily smart money signal for a single symbol.

    ``records`` is a list of ``StockRecord`` (or any object exposing the same
    fields). For multi-timeframe scoring with intraday data, see
    ``compute_smart_money_mtf`` (Phase 3+).
    """
    cfg = cfg or DEFAULT_SMART_MONEY_CONFIG

    if not records:
        return SmartMoneySignal(narrative="Chưa có dữ liệu.")

    primitives, setup_c, setup_conf, trigger_c, trigger_conf, is_toxic = (
        _compute_daily_layer(records, cfg, regime=regime, symbol_class=symbol_class)
    )

    ui_composite, ui_conf = _ui_merge(
        setup_c, setup_conf, trigger_c, trigger_conf,
        cfg.ui_weight_setup, cfg.ui_weight_trigger,
    )

    label = "toxic" if is_toxic else _classify_label(ui_composite, ui_conf)
    trend = _detect_trend(records, primitives)
    narrative = generate_narrative(primitives, ui_composite, label, is_toxic=is_toxic)

    return SmartMoneySignal(
        setup_composite=setup_c,
        setup_confidence=setup_conf,
        trigger_composite=trigger_c,
        trigger_confidence=trigger_conf,
        composite=ui_composite,
        confidence=ui_conf,
        label=label,
        is_toxic=is_toxic,
        trend=trend,
        primitives=primitives,
        narrative=narrative,
    )


# =============================================================================
# Multi-timeframe entry point (Phase 3+)
# =============================================================================

def compute_smart_money_mtf(
    daily_records: List,
    intraday_records: Optional[List] = None,
    raw_ticks: Optional[List] = None,
    cfg: SmartMoneyConfig = None,
    symbol: Optional[str] = None,
    signal_date=None,
    regime: Optional[str] = None,
    symbol_class: Optional[str] = None,
) -> SmartMoneySignal:
    """Multi-timeframe smart money compute (Phase 3+).

    Daily layer is always computed. Intraday layer plugs in only when
    ``cfg.use_intraday`` is on AND ``intraday_records`` is provided.
    """
    cfg = cfg or DEFAULT_SMART_MONEY_CONFIG

    if not daily_records:
        return SmartMoneySignal(narrative="Chưa có dữ liệu.")

    primitives, setup_c, setup_conf, trigger_c, trigger_conf, is_toxic = (
        _compute_daily_layer(daily_records, cfg, regime=regime, symbol_class=symbol_class)
    )

    # Intraday layer — adds only to trigger bucket
    if intraday_records and cfg.use_intraday:
        from src.analysis.smart_money.primitives_intraday import (
            run_intraday_primitives,
        )
        intraday_prims = run_intraday_primitives(
            intraday_records, raw_ticks, cfg,
            symbol=symbol, signal_date=signal_date,
        )
        for name, prim in intraday_prims.items():
            primitives[name] = prim

        trigger_prims = {k: p for k, p in primitives.items() if p.bucket == "trigger"}
        _, trigger_w = _resolve_weights(cfg, regime=regime, symbol_class=symbol_class)
        trigger_c, trigger_conf = _aggregate_bucket(trigger_prims, trigger_w)

    ui_composite, ui_conf = _ui_merge(
        setup_c, setup_conf, trigger_c, trigger_conf,
        cfg.ui_weight_setup, cfg.ui_weight_trigger,
    )

    label = "toxic" if is_toxic else _classify_label(ui_composite, ui_conf)
    trend = _detect_trend(daily_records, primitives)
    narrative = generate_narrative(primitives, ui_composite, label, is_toxic=is_toxic)

    return SmartMoneySignal(
        setup_composite=setup_c,
        setup_confidence=setup_conf,
        trigger_composite=trigger_c,
        trigger_confidence=trigger_conf,
        composite=ui_composite,
        confidence=ui_conf,
        label=label,
        is_toxic=is_toxic,
        trend=trend,
        primitives=primitives,
        narrative=narrative,
    )
