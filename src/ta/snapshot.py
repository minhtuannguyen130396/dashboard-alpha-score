"""One symbol's full technical picture, as plain JSON-serialisable data.

Everything the report layer and the MCP tools need for a single stock is
computed here, in one pass over the price series.
"""
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from src.analysis.technical_indicators import (
    IndicatorGroup1, IndicatorGroup2, IndicatorGroup3, IndicatorGroup4,
)
from src.data.stock_data_loader import StockRecord
from src.ta import asof as asof_mod
from src.ta import candles, vsa
from src.ta.config import ScanConfig, get_profile
from src.ta.swings import RANGE, TREND_NAMES, build_market_structure
from src.ta.loader import is_averaged_series, load_recent
from src.ta.signals import (
    AdxState, RsiEvent, RsiZoneState, adx_state, detect_rsi_events, rsi_zone_state,
)


@dataclass
class Snapshot:
    symbol: str
    as_of: str
    bars: int
    price: Dict[str, Any]
    trend: Dict[str, Any]
    momentum: Dict[str, Any]
    volume: Dict[str, Any]
    levels: Dict[str, Any]
    rsi_zone: Dict[str, Any]
    adx: Dict[str, Any]
    last_bar: Dict[str, Any] = field(default_factory=dict)
    candles: List[Dict[str, Any]] = field(default_factory=list)
    vsa: List[Dict[str, Any]] = field(default_factory=list)
    recent_rsi_events: List[Dict[str, Any]] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    #: Mốc hồi tưởng người dùng yêu cầu (rỗng = chạy trên dữ liệu mới nhất).
    #: Khác ``as_of`` ở trên: đó là phiên cuối *có thật*, mốc yêu cầu có thể
    #: rơi vào ngày nghỉ nên hai giá trị thường lệch nhau vài ngày.
    as_of_requested: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def _last(series, default=None):
    if not series:
        return default
    for value in reversed(series):
        if value is not None:
            return value
    return default


def _round(value, digits=2):
    return round(float(value), digits) if value is not None else None


def _pct(new: Optional[float], old: Optional[float]) -> Optional[float]:
    if new is None or not old:
        return None
    return round((new / old - 1.0) * 100, 2)


def _position_vs(price: float, level: Optional[float]) -> Optional[float]:
    """How far price sits above (+) or below (-) a level, in percent."""
    return _pct(price, level)


def build_snapshot(
    symbol: str,
    as_of: Optional[datetime] = None,
    lookback_days: int = 400,
    profile: str = "standard",
    records: Optional[List[StockRecord]] = None,
) -> Snapshot:
    cfg: ScanConfig = get_profile(profile)
    recs = records if records is not None else load_recent(symbol, lookback_days, as_of)
    if not recs:
        return Snapshot(
            symbol=symbol, as_of="-", bars=0, price={}, trend={}, momentum={},
            volume={}, levels={}, rsi_zone={}, adx={},
            warnings=[f"Không có dữ liệu cho {symbol} trong {lookback_days} ngày gần nhất"],
            as_of_requested=asof_mod.label(as_of),
        )

    last = recs[-1]
    averaged = is_averaged_series(symbol)
    warnings: List[str] = []
    if averaged:
        warnings.append(
            "Chuỗi bình quân (chỉ số ngành / thị trường) — không đọc hình nến "
            "và không đọc VSA: mỗi cây nến ở đây là trung bình của nhiều mã, "
            "không phải một phiên giao dịch có người mua người bán.")
    if len(recs) < 2 * cfg.adx.period:
        warnings.append(
            f"Chỉ có {len(recs)} phiên — cần ≥ {2 * cfg.adx.period} phiên để ADX có giá trị"
        )

    ema20 = IndicatorGroup1.ema(recs, 20)
    ema50 = IndicatorGroup1.ema(recs, 50)
    ema100 = IndicatorGroup1.ema(recs, 100)
    rsi = IndicatorGroup2.rsi(recs, cfg.rsi.period)
    macd_line, macd_sig, macd_hist = IndicatorGroup2.macd(recs)
    atr = IndicatorGroup3.atr(recs, 14)
    bb_up, bb_mid, bb_low = IndicatorGroup3.bollinger_bands(recs, 20)
    dc_up, dc_low = IndicatorGroup3.donchian_channel(recs, 20)
    mfi = IndicatorGroup4.mfi(recs, 14)

    close = last.priceClose
    prev_close = recs[-2].priceClose if len(recs) > 1 else close
    e20, e50, e100 = _last(ema20), _last(ema50), _last(ema100)
    atr14 = _last(atr)

    vols = [r.priceImpactVolume for r in recs]
    avg20 = sum(vols[-21:-1]) / 20 if len(vols) >= 21 else (sum(vols) / len(vols))
    w10 = recs[-10:]
    w20 = recs[-20:]

    market = build_market_structure(recs, atr=atr)
    shapes = candles.shapes(recs, atr)
    last_shape = shapes[-1]

    # Nến của một chuỗi bình quân không đọc được như nến của một mã.
    #
    # `_ICB_60` là trung bình của 33 mã, VNINDEX của hơn 300. "Sao băng" ở đó
    # nghĩa là các mã thành phần lệch pha nhau trong phiên — **không** phải
    # "bị đánh xuống từ vùng cao", vì không ai giao dịch cây nến ấy. Đây đúng
    # lập luận `candles.py` đã dùng để loại phiên trần/sàn (đóng cửa giá trần
    # trông y hệt marubozu tăng nhưng nghĩa ngược lại): một hình dạng đọc ra từ
    # chuỗi không thể sinh ra cái nghĩa của hình dạng đó.
    #
    # Số đo hình dạng (`close_pos`, `body_pct`, râu nến) vẫn giữ — chúng là
    # phép đo biên độ, đúng ở mọi chuỗi. Chỉ phần *phân loại thành tên gọi* bị
    # tắt, vì chính cái tên mới mang theo câu chuyện sai.
    bar_signals = [] if averaged else candles.detect(recs, -1, measured=shapes)
    vsa_signals = [] if averaged else vsa.detect(recs, -1, measured=shapes)

    zone: RsiZoneState = rsi_zone_state(recs, cfg.rsi, rsi)
    adx: AdxState = adx_state(recs, cfg.adx)
    events: List[RsiEvent] = detect_rsi_events(recs, cfg.rsi, rsi)

    if e20 is not None and e50 is not None:
        if close > e20 > e50:
            trend_label = "Tăng — giá trên EMA20 trên EMA50"
        elif close < e20 < e50:
            trend_label = "Giảm — giá dưới EMA20 dưới EMA50"
        elif close > e50:
            trend_label = "Hồi phục — giá trên EMA50 nhưng chưa vượt EMA20"
        else:
            trend_label = "Yếu — giá dưới EMA50"
    else:
        trend_label = "Chưa đủ dữ liệu EMA"
    # The EMA reading is a smoothed opinion; the swing sequence is what the
    # price series itself says. Print both — when they disagree, that is the
    # information.
    if market.trend != RANGE:
        trend_label += f" · {TREND_NAMES[market.trend].lower()}"
    elif market.swings:
        trend_label += " · cấu trúc chưa rõ ràng"

    return Snapshot(
        symbol=symbol,
        as_of=last.date.strftime("%Y-%m-%d"),
        as_of_requested=asof_mod.label(as_of),
        bars=len(recs),
        price={
            "close": _round(close),
            "open": _round(last.priceOpen),
            "high": _round(last.priceHigh),
            "low": _round(last.priceLow),
            "change_pct": _pct(close, prev_close),
            "change_5d": _pct(close, recs[-6].priceClose) if len(recs) > 5 else None,
            "change_20d": _pct(close, recs[-21].priceClose) if len(recs) > 20 else None,
        },
        trend={
            "label": trend_label,
            "ema20": _round(e20), "ema50": _round(e50), "ema100": _round(e100),
            "vs_ema20_pct": _position_vs(close, e20),
            "vs_ema50_pct": _position_vs(close, e50),
            "ema20_above_ema50": (e20 > e50) if (e20 is not None and e50 is not None) else None,
            "structure": market.trend,
            "structure_label": market.label,
            "swings": [s.short for s in market.swings[-6:]],
            "last_event": market.last_event.label if market.last_event else None,
        },
        momentum={
            "rsi14": _round(_last(rsi)),
            "macd_line": _round(_last(macd_line), 3),
            "macd_signal": _round(_last(macd_sig), 3),
            "macd_hist": _round(_last(macd_hist), 3),
            "mfi14": _round(_last(mfi)),
            "atr14": _round(atr14),
            "atr_pct": _round(atr14 / close * 100) if atr14 and close else None,
        },
        volume={
            "volume": int(last.priceImpactVolume),
            "avg20": int(avg20) if avg20 else 0,
            "rvol": _round(last.priceImpactVolume / avg20) if avg20 else None,
            "foreign_net": _round(last.buyForeignQuantity - last.sellForeignQuantity, 0),
        },
        levels={
            "swing_high_10": _round(max(r.priceHigh for r in w10)),
            "swing_low_10": _round(min(r.priceLow for r in w10)),
            "swing_high_20": _round(max(r.priceHigh for r in w20)),
            "swing_low_20": _round(min(r.priceLow for r in w20)),
            "donchian_high_20": _round(_last(dc_up)),
            "donchian_low_20": _round(_last(dc_low)),
            "bb_upper": _round(_last(bb_up)),
            "bb_mid": _round(_last(bb_mid)),
            "bb_lower": _round(_last(bb_low)),
        },
        last_bar={
            "spread_atr": last_shape.spread_atr,
            "close_pos": _round(last_shape.close_pos),
            "body_pct": _round(last_shape.body_pct),
            "upper_wick_pct": _round(last_shape.upper_wick / last_shape.bar_range)
            if last_shape.bar_range else None,
            "lower_wick_pct": _round(last_shape.lower_wick / last_shape.bar_range)
            if last_shape.bar_range else None,
            "direction": last_shape.direction,
            "limit": last_shape.limit,
            "change_vs_basic": last_shape.change_pct,
        },
        candles=[s.to_dict() for s in bar_signals],
        vsa=[s.to_dict() for s in vsa_signals],
        rsi_zone=zone.to_dict(),
        adx=adx.to_dict(),
        recent_rsi_events=[e.to_dict() for e in events[-5:]],
        warnings=warnings,
    )
