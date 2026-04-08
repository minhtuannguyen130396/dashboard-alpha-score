"""Intraday flow primitives (Phase 4) — all bucket="trigger".

Each primitive consumes pre-classified intraday bars and/or raw ticks for
the *signal day only*. History needed for percentile normalization comes
from ``IntradayFeatureCache`` (scalar per day), never from re-loading tick
raw of past days.
"""
from datetime import date as _date
from statistics import median
from typing import Dict, List, Optional

from src.analysis.smart_money.config import SmartMoneyConfig
from src.analysis.smart_money.normalize import clamp, rank_to_signed, safe_ratio, tanh_scale
from src.analysis.smart_money.types import FlowPrimitive
from src.data.flow_records import IntradayFlowRecord, RawTick


def _percentile_rank(history: List[float], value: float) -> float:
    if not history:
        return 0.5
    below = sum(1 for x in history if x < value)
    return below / len(history)


# =============================================================================
# OFI primitive
# =============================================================================

def _compute_ofi_scalar(bars: List[IntradayFlowRecord]) -> float:
    """Composite OFI: 0.4 × rolling-30min OFI + 0.6 × end-of-day 15-min OFI."""
    if not bars:
        return 0.0

    def _ofi(b_subset):
        buy = sum((b.buy_volume or 0.0) for b in b_subset)
        sell = sum((b.sell_volume or 0.0) for b in b_subset)
        total = buy + sell
        return safe_ratio(buy - sell, total) if total > 0 else 0.0

    # Approximate "30 min" / "15 min" by bar count, since bar size is config-driven
    bar_minutes = _bar_minutes(bars[0].bar_size)
    n_30 = max(1, 30 // bar_minutes)
    n_eod = max(1, 15 // bar_minutes)
    ofi_30 = _ofi(bars[-n_30:])
    ofi_eod = _ofi(bars[-n_eod:])
    return 0.4 * ofi_30 + 0.6 * ofi_eod


def _bar_minutes(bar_size: str) -> int:
    s = bar_size.strip().lower()
    if s.endswith("m"):
        return int(s[:-1]) or 1
    if s.endswith("h"):
        return int(s[:-1]) * 60
    return 1


class OrderFlowImbalancePrimitive:
    name = "ofi"
    bucket = "trigger"

    def min_bars(self) -> int:
        return 5

    def compute(
        self,
        bars: List[IntradayFlowRecord],
        cfg: SmartMoneyConfig,
        symbol: Optional[str] = None,
        signal_date: Optional[_date] = None,
        cache=None,
    ) -> FlowPrimitive:
        if not bars or len(bars) < self.min_bars():
            return FlowPrimitive(
                name=self.name, bucket="trigger",
                value=0.0, confidence=0.0, components={}, reasons=["no bars"],
            )

        ofi_today = _compute_ofi_scalar(bars)

        history: List[float] = []
        if cache is not None and symbol and signal_date:
            history = cache.load_feature(
                symbol, "ofi_composite",
                end_date=_date.fromordinal(signal_date.toordinal() - 1),
                lookback=20,
            )

        if len(history) >= 10:
            rank = _percentile_rank(history, ofi_today)
            value = rank_to_signed(rank)
            confidence = 1.0 if len(history) >= 15 else 0.7
        else:
            # No baseline → fall back to raw tanh of OFI today
            value = tanh_scale(ofi_today, 2.0)
            confidence = 0.3

        return FlowPrimitive(
            name=self.name,
            bucket="trigger",
            value=value,
            confidence=confidence,
            components={
                "ofi_today": ofi_today,
                "history_len": float(len(history)),
            },
            reasons=[f"OFI today {ofi_today:+.2f}"],
        )


# =============================================================================
# Block trade primitive
# =============================================================================

class BlockTradePrimitive:
    name = "block_trade"
    bucket = "trigger"

    def compute(
        self,
        ticks: List[RawTick],
        cfg: SmartMoneyConfig,
        symbol: Optional[str] = None,
        signal_date: Optional[_date] = None,
        cache=None,
    ) -> FlowPrimitive:
        if not ticks:
            return FlowPrimitive(
                name=self.name, bucket="trigger",
                value=0.0, confidence=0.0, components={}, reasons=["no ticks"],
            )

        baseline = None
        if cache is not None and symbol and signal_date:
            baseline = cache.load_scalar(
                symbol, "median_trade_size_20d",
                as_of=_date.fromordinal(signal_date.toordinal() - 1),
            )
        cold_start = baseline is None
        if cold_start:
            baseline = median(t.volume for t in ticks)

        threshold = max(1.0, baseline * cfg.block_threshold_multiplier)
        blocks = [t for t in ticks if t.volume >= threshold]

        block_buy = sum(t.volume for t in blocks if t.side > 0)
        block_sell = sum(t.volume for t in blocks if t.side < 0)
        total = block_buy + block_sell

        if total == 0:
            return FlowPrimitive(
                name=self.name, bucket="trigger",
                value=0.0, confidence=0.0,
                components={"block_count": float(len(blocks))},
                reasons=["no classified blocks"],
            )

        value = clamp(2 * (block_buy - block_sell) / total, -1.0, 1.0)
        confidence = min(1.0, len(blocks) / 5.0)
        if cold_start:
            confidence *= 0.5

        return FlowPrimitive(
            name=self.name,
            bucket="trigger",
            value=value,
            confidence=confidence,
            components={
                "block_count": float(len(blocks)),
                "block_buy": block_buy,
                "block_sell": block_sell,
                "threshold": threshold,
                "cold_start": float(cold_start),
            },
            reasons=[f"{len(blocks)} blocks, net {value:+.2f}"],
        )


# =============================================================================
# VWAP relationship
# =============================================================================

class VWAPRelationshipPrimitive:
    name = "vwap_relationship"
    bucket = "trigger"

    def compute(
        self,
        bars: List[IntradayFlowRecord],
        cfg: SmartMoneyConfig,
        **_: object,
    ) -> FlowPrimitive:
        if not bars:
            return FlowPrimitive(
                name=self.name, bucket="trigger",
                value=0.0, confidence=0.0, components={}, reasons=["no bars"],
            )

        total_volume = sum(b.volume for b in bars)
        if total_volume <= 0:
            return FlowPrimitive(
                name=self.name, bucket="trigger",
                value=0.0, confidence=0.0, components={},
                reasons=["zero volume"],
            )

        total_vp = sum(b.close * b.volume for b in bars)
        vwap = total_vp / total_volume
        close = bars[-1].close
        if vwap <= 0:
            return FlowPrimitive(
                name=self.name, bucket="trigger",
                value=0.0, confidence=0.0, components={}, reasons=["bad vwap"],
            )

        above_vol = sum(b.volume for b in bars if b.close > vwap)
        upvol_ratio = above_vol / total_volume
        position = (close - vwap) / vwap

        value = clamp(
            0.5 * tanh_scale(position, 100.0)
            + 0.5 * (2 * upvol_ratio - 1),
            -1.0, 1.0,
        )
        confidence = min(1.0, len(bars) / 20.0)

        return FlowPrimitive(
            name=self.name,
            bucket="trigger",
            value=value,
            confidence=confidence,
            components={
                "vwap": vwap,
                "close": close,
                "upvol_ratio": upvol_ratio,
                "position": position,
            },
            reasons=[f"close {('>' if close>vwap else '<')} VWAP, upvol {upvol_ratio:.2f}"],
        )


# =============================================================================
# Auction flow
# =============================================================================

class AuctionFlowPrimitive:
    name = "auction_flow"
    bucket = "trigger"

    def compute(
        self,
        ticks: List[RawTick],
        cfg: SmartMoneyConfig,
        **_: object,
    ) -> FlowPrimitive:
        if not ticks:
            return FlowPrimitive(
                name=self.name, bucket="trigger",
                value=0.0, confidence=0.0, components={},
                reasons=["no ticks"],
            )

        ato = [t for t in ticks if t.trade_type == "ATO"]
        atc = [t for t in ticks if t.trade_type == "ATC"]
        if not ato and not atc:
            return FlowPrimitive(
                name=self.name, bucket="trigger",
                value=0.0, confidence=0.0,
                components={}, reasons=["no auction ticks"],
            )

        ato_net = sum(t.side * t.volume for t in ato)
        atc_net = sum(t.side * t.volume for t in atc)
        total_volume = sum(t.volume for t in ticks) or 1.0

        ato_ratio = ato_net / total_volume
        atc_ratio = atc_net / total_volume

        value = clamp(tanh_scale(0.4 * ato_ratio + 0.6 * atc_ratio, 30.0), -1.0, 1.0)
        confidence = min(1.0, (len(ato) + len(atc)) / 10.0)

        return FlowPrimitive(
            name=self.name,
            bucket="trigger",
            value=value,
            confidence=confidence,
            components={
                "ato_net": ato_net,
                "atc_net": atc_net,
                "ato_count": float(len(ato)),
                "atc_count": float(len(atc)),
            },
            reasons=[f"ATO {ato_ratio*100:+.2f}%, ATC {atc_ratio*100:+.2f}%"],
        )


# =============================================================================
# Intraday divergence
# =============================================================================

class IntradayDivergencePrimitive:
    name = "intraday_divergence"
    bucket = "trigger"

    def compute(
        self,
        bars: List[IntradayFlowRecord],
        cfg: SmartMoneyConfig,
        **_: object,
    ) -> FlowPrimitive:
        if not bars or len(bars) < 4:
            return FlowPrimitive(
                name=self.name, bucket="trigger",
                value=0.0, confidence=0.0, components={},
                reasons=["insufficient bars"],
            )

        prices = [b.close for b in bars]
        per_bar_ofi = [
            (b.buy_volume or 0.0) - (b.sell_volume or 0.0) for b in bars
        ]

        # Compare first and last quarter using OFI *change* within each window,
        # not running max — cumulative OFI is monotone during a sustained buy
        # leg, so a max-vs-max test misses the bearish divergence we want.
        q = max(1, len(bars) // 4)
        early_high = max(prices[:q])
        late_high = max(prices[-q:])
        early_low = min(prices[:q])
        late_low = min(prices[-q:])
        early_ofi = sum(per_bar_ofi[:q])
        late_ofi = sum(per_bar_ofi[-q:])

        value = 0.0
        reason = ""
        if late_high > early_high and late_ofi < early_ofi:
            # Bearish: new price high, flow weakening
            value = -0.6
            reason = "intraday bearish div"
        elif late_low < early_low and late_ofi > early_ofi:
            value = 0.6
            reason = "intraday bullish div"

        confidence = min(1.0, len(bars) / 20.0)
        return FlowPrimitive(
            name=self.name,
            bucket="trigger",
            value=value,
            confidence=confidence if value != 0 else confidence * 0.3,
            components={
                "late_high": late_high,
                "early_high": early_high,
                "early_ofi": early_ofi,
                "late_ofi": late_ofi,
            },
            reasons=[reason] if reason else [],
        )


# =============================================================================
# Runner used by composite
# =============================================================================

def run_intraday_primitives(
    bars: Optional[List[IntradayFlowRecord]],
    raw_ticks: Optional[List[RawTick]],
    cfg: SmartMoneyConfig,
    symbol: Optional[str] = None,
    signal_date: Optional[_date] = None,
) -> Dict[str, FlowPrimitive]:
    """Run all enabled intraday primitives, returning a name → FlowPrimitive map."""
    out: Dict[str, FlowPrimitive] = {}
    cache = None
    if cfg.intraday_feature_cache_path:
        try:
            from src.data.intraday_feature_cache import IntradayFeatureCache
            cache = IntradayFeatureCache(cfg.intraday_feature_cache_path)
        except Exception:
            cache = None

    if cfg.use_ofi and bars:
        out["ofi"] = OrderFlowImbalancePrimitive().compute(
            bars, cfg, symbol=symbol, signal_date=signal_date, cache=cache,
        )
    if cfg.use_block_trades and raw_ticks:
        out["block_trade"] = BlockTradePrimitive().compute(
            raw_ticks, cfg, symbol=symbol, signal_date=signal_date, cache=cache,
        )
    if cfg.use_vwap_relationship and bars:
        out["vwap_relationship"] = VWAPRelationshipPrimitive().compute(bars, cfg)
    if cfg.use_auction_flow and raw_ticks:
        out["auction_flow"] = AuctionFlowPrimitive().compute(raw_ticks, cfg)
    if cfg.use_intraday_divergence and bars:
        out["intraday_divergence"] = IntradayDivergencePrimitive().compute(bars, cfg)
    return out
