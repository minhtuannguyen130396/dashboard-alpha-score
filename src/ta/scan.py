"""Batch scanner - run the signal rules across a basket of symbols.

Rules available:
  rsi_oversold_reclaim   RSI dug below oversold, turned, and came back to touch it
  rsi_overbought_loss    RSI pushed above overbought, turned, and came back to touch it
  rsi_turning_up         still inside the oversold zone but already turning back up
  rsi_turning_down       still inside the overbought zone but already turning back down
  adx_momentum           ADX above the momentum threshold (default 20)
"""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence

from src.analysis.technical_indicators import IndicatorGroup2
from src.ta.config import ScanConfig, get_profile
from src.ta import asof as asof_mod
from src.ta.loader import load_recent, missing_symbols, resolve_universe
from src.ta.signals import (
    OVERBOUGHT_LOSS, OVERSOLD_RECLAIM, adx_state, detect_rsi_events, rsi_zone_state,
)

RULES = (
    "rsi_oversold_reclaim",
    "rsi_overbought_loss",
    "rsi_turning_up",
    "rsi_turning_down",
    "adx_momentum",
)

#: Rules that only make sense when RSI has actually completed the round trip.
_EVENT_RULES = {
    "rsi_oversold_reclaim": OVERSOLD_RECLAIM,
    "rsi_overbought_loss": OVERBOUGHT_LOSS,
}

_QUALITY_POINTS = {"strong": 3, "normal": 2, "weak": 1}


@dataclass
class ScanHit:
    symbol: str
    as_of: str
    close: float
    change_pct: Optional[float]
    matched: List[str]
    score: int
    side: str                       # bullish | bearish | neutral
    rsi: Optional[float]
    rsi_state: str
    adx: Optional[float]
    adx_direction: str
    adx_regime: str
    event_date: Optional[str] = None
    event_kind: Optional[str] = None
    event_quality: Optional[str] = None
    bars_ago: Optional[int] = None
    divergence: bool = False
    note: str = ""
    detail: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ScanResult:
    as_of: str
    profile: str
    rules: List[str]
    universe_size: int
    scanned: int
    recent_bars: int
    hits: List[ScanHit] = field(default_factory=list)
    skipped: List[str] = field(default_factory=list)
    unknown_symbols: List[str] = field(default_factory=list)
    #: Mốc hồi tưởng đã yêu cầu (rỗng = dữ liệu mới nhất). Xem ``ta.asof``.
    as_of_requested: str = ""

    def to_dict(self) -> dict:
        return {**asdict(self), "hits": [h.to_dict() for h in self.hits]}


def _score(quality: Optional[str], adx, side: str, divergence: bool,
           price_confirms: bool) -> int:
    score = _QUALITY_POINTS.get(quality or "", 0)
    if adx.has_momentum:
        aligned = (side == "bullish" and adx.direction == "up") or (
            side == "bearish" and adx.direction == "down")
        score += 2 if aligned else 1
    if adx.rising:
        score += 1
    if divergence:
        score += 1
    if price_confirms:
        score += 1
    return score


def _scan_one(symbol: str, cfg: ScanConfig, rules: Sequence[str],
              as_of: Optional[datetime], lookback_days: int) -> Optional[ScanHit]:
    recs = load_recent(symbol, lookback_days, as_of)
    if len(recs) < cfg.rsi.period + 2:
        return None

    rsi = IndicatorGroup2.rsi(recs, cfg.rsi.period)
    zone = rsi_zone_state(recs, cfg.rsi, rsi)
    adx = adx_state(recs, cfg.adx)
    last = recs[-1]
    n = len(recs)

    matched: List[str] = []
    event = None

    wanted_events = [_EVENT_RULES[r] for r in rules if r in _EVENT_RULES]
    if wanted_events:
        for e in reversed(detect_rsi_events(recs, cfg.rsi, rsi)):
            if n - 1 - e.index >= cfg.recent_bars:
                break
            if e.kind in wanted_events:
                event = e
                matched.append(
                    "rsi_oversold_reclaim" if e.kind == OVERSOLD_RECLAIM
                    else "rsi_overbought_loss"
                )
                break

    if "rsi_turning_up" in rules and zone.state == "turning_up":
        matched.append("rsi_turning_up")
    if "rsi_turning_down" in rules and zone.state == "turning_down":
        matched.append("rsi_turning_down")
    if "adx_momentum" in rules and adx.has_momentum:
        matched.append("adx_momentum")

    if not matched:
        return None

    if event is not None:
        side = event.side
    elif "rsi_turning_up" in matched:
        side = "bullish"
    elif "rsi_turning_down" in matched:
        side = "bearish"
    elif adx.has_momentum and adx.direction in ("up", "down"):
        side = "bullish" if adx.direction == "up" else "bearish"
    else:
        side = "neutral"

    score = _score(
        event.quality if event else None, adx, side,
        event.divergence if event else False,
        event.price_confirms if event else False,
    )

    if event is not None:
        bars_ago = n - 1 - event.index
        when = "hôm nay" if bars_ago == 0 else f"{bars_ago} phiên trước"
        bullish = event.kind == OVERSOLD_RECLAIM
        kind_vn = ("RSI bật lên chạm lại ngưỡng quá bán" if bullish
                   else "RSI quay đầu chạm lại ngưỡng quá mua")
        extreme_vn = "đáy RSI" if bullish else "đỉnh RSI"
        note = (f"{kind_vn} ({when}): {extreme_vn} {event.extreme:.1f} sau "
                f"{event.bars_in_zone} phiên trong vùng, {event.quality}")
        if event.divergence:
            note += ", có phân kỳ"
    elif "rsi_turning_up" in matched or "rsi_turning_down" in matched:
        note = zone.label
    else:
        # Only ADX matched — describe ADX, not an RSI zone no rule asked about.
        note = adx.label

    prev_close = recs[-2].priceClose if n > 1 else last.priceClose
    return ScanHit(
        symbol=symbol,
        as_of=last.date.strftime("%Y-%m-%d"),
        close=round(last.priceClose, 2),
        change_pct=round((last.priceClose / prev_close - 1) * 100, 2) if prev_close else None,
        matched=matched,
        score=score,
        side=side,
        rsi=zone.rsi,
        rsi_state=zone.state,
        adx=adx.adx,
        adx_direction=adx.direction,
        adx_regime=adx.regime,
        event_date=event.date if event else None,
        event_kind=event.kind if event else None,
        event_quality=event.quality if event else None,
        bars_ago=(n - 1 - event.index) if event else None,
        divergence=event.divergence if event else False,
        note=note,
        detail={"rsi_zone": zone.to_dict(), "adx": adx.to_dict(),
                "event": event.to_dict() if event else None},
    )


def scan(
    universe: Optional[str] = None,
    rules: Optional[Sequence[str]] = None,
    profile: str = "standard",
    recent_bars: Optional[int] = None,
    as_of: Optional[datetime] = None,
    lookback_days: Optional[int] = None,
    min_score: int = 0,
    max_workers: int = 8,
) -> ScanResult:
    """Run ``rules`` over ``universe`` and return the hits, best score first."""
    cfg = get_profile(profile)
    if recent_bars is not None:
        cfg = ScanConfig(rsi=cfg.rsi, adx=cfg.adx,
                         lookback_days=cfg.lookback_days, recent_bars=recent_bars)
    lookback = lookback_days or cfg.lookback_days

    selected = [r for r in (rules or RULES) if r in RULES]
    if not selected:
        raise ValueError(f"No valid rule requested. Available: {', '.join(RULES)}")

    symbols = resolve_universe(universe)
    unknown = missing_symbols(universe) if universe else []

    hits: List[ScanHit] = []
    skipped: List[str] = []

    def _work(sym: str):
        try:
            return sym, _scan_one(sym, cfg, selected, as_of, lookback)
        except Exception as exc:                      # one bad symbol must not kill the scan
            return sym, exc

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        for sym, outcome in pool.map(_work, symbols):
            if isinstance(outcome, Exception):
                skipped.append(f"{sym}: {type(outcome).__name__}")
            elif outcome is not None and outcome.score >= min_score:
                hits.append(outcome)

    hits.sort(key=lambda h: (-h.score, h.bars_ago if h.bars_ago is not None else 99, h.symbol))
    as_of_str = max((h.as_of for h in hits), default=(as_of or datetime.now()).strftime("%Y-%m-%d"))

    return ScanResult(
        as_of=as_of_str,
        as_of_requested=asof_mod.label(as_of),
        profile=profile,
        rules=selected,
        universe_size=len(symbols),
        scanned=len(symbols),
        recent_bars=cfg.recent_bars,
        hits=hits,
        skipped=skipped,
        unknown_symbols=unknown,
    )
