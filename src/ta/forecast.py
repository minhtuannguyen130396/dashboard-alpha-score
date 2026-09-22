"""Written-down expectations, and the machinery to check whether they came true.

A forecast is a claim with a level attached: *if price closes above X (with
volume), it should reach Y; if it closes below Z first, the idea was wrong; and
if neither happens within N sessions, it has gone stale.* Storing that on disk
is what makes it checkable later instead of a feeling about a chart.

Nothing here notifies anything. Status changes are returned to the caller, and
the caller prints them — which is exactly when the user asks.
"""
import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import pandas as pd

from src.analysis.technical_indicators import IndicatorGroup1, IndicatorGroup2
from src.data.stock_data_loader import StockRecord
from src.ta.boxes import BREAKOUT_UP_CONFIRMED, BREAKOUT_UP_WEAK, INSIDE
from src.ta.formations import BEARISH as FORMATION_BEARISH
from src.ta.formations import FAILED as FORMATION_FAILED
from src.ta.formations import FORMING as FORMATION_FORMING
from src.ta import asof as asof_mod
from src.ta.loader import PROJECT_ROOT, load_recent
from src.ta.pivots import HIGH
from src.ta.signals import OVERSOLD_RECLAIM, detect_rsi_events
from src.ta.structure import Structure, build_structure
from src.ta.trendlines import RESISTANCE

FORECAST_DIR = PROJECT_ROOT / "forecasts"

# Status lifecycle
PENDING = "pending"            # waiting for the trigger
TRIGGERED = "triggered"        # trigger hit, running toward the target
HIT_TARGET = "hit_target"
INVALIDATED = "invalidated"
EXPIRED = "expired"
OPEN_STATUSES = (PENDING, TRIGGERED)

STATUS_VN = {
    PENDING: "chờ kích hoạt",
    TRIGGERED: "đã kích hoạt",
    HIT_TARGET: "🎯 đã đạt mục tiêu",
    INVALIDATED: "❌ đã bị phủ định",
    EXPIRED: "⏱ hết hạn",
}

BASIS_VN = {
    "box_breakout": "chờ phá hộp tích luỹ",
    "box_running": "đã phá hộp, đang chạy tới mục tiêu",
    "trendline_break": "chờ vượt đường nối đỉnh",
    "neckline_break": "chờ phá neckline mô hình đảo chiều",
    "neckline_running": "đã phá neckline, đang chạy tới mục tiêu",
    "rsi_reclaim": "RSI bật khỏi vùng quá bán",
    "manual": "tự đặt",
}

CLOSE_ABOVE = "close_above"
CLOSE_BELOW = "close_below"


@dataclass
class Forecast:
    id: str
    symbol: str
    created: str                     # bar date the forecast was built from
    basis: str
    direction: str                   # up | down
    trigger_type: str                # CLOSE_ABOVE | CLOSE_BELOW
    trigger_level: float
    target: float
    invalidation: float
    deadline_bars: int
    created_close: float
    status: str = PENDING
    confirm_volume_x: Optional[float] = None
    triggered_date: Optional[str] = None
    triggered_volume_x: Optional[float] = None
    resolved_date: Optional[str] = None
    resolved_close: Optional[float] = None
    bars_elapsed: int = 0
    current_close: Optional[float] = None
    current_volume_x: Optional[float] = None
    last_checked: Optional[str] = None
    note: str = ""
    evidence: Dict[str, Any] = field(default_factory=dict)
    history: List[Dict[str, str]] = field(default_factory=list)

    @property
    def is_open(self) -> bool:
        return self.status in OPEN_STATUSES

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Forecast":
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in data.items() if k in known})


# ---------------------------------------------------------------------------
# storage
# ---------------------------------------------------------------------------
def _slug(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]", "", text)


def make_id(symbol: str, created: str, basis: str) -> str:
    return f"{_slug(symbol)}-{created.replace('-', '')}-{_slug(basis)}"


def path_for(forecast_id: str) -> Path:
    return FORECAST_DIR / f"{_slug(forecast_id)}.json"


def save(forecast: Forecast) -> Path:
    FORECAST_DIR.mkdir(parents=True, exist_ok=True)
    p = path_for(forecast.id)
    p.write_text(json.dumps(forecast.to_dict(), ensure_ascii=False, indent=2),
                 encoding="utf-8")
    return p


def load(forecast_id: str) -> Optional[Forecast]:
    p = path_for(forecast_id)
    if not p.is_file():
        return None
    try:
        return Forecast.from_dict(json.loads(p.read_text(encoding="utf-8")))
    except (json.JSONDecodeError, TypeError, OSError):
        return None


def load_all(symbols: Optional[Sequence[str]] = None,
             open_only: bool = False,
             as_of: Optional[datetime] = None) -> List[Forecast]:
    """Forecast đã lưu, lọc theo mã và theo mốc hồi tưởng.

    ``as_of`` bỏ đi những forecast được tạo *sau* mốc: một báo cáo giả định hôm
    nay là 01/01/2025 mà liệt kê kỳ vọng đặt tháng 8/2026 thì không còn là hồi
    tưởng nữa. ``open_only`` lúc đó cũng vô nghĩa — trạng thái lưu trên đĩa được
    tính từ những phiên bản replay chưa được biết, nên nó bị bỏ qua và việc phân
    loại đóng/mở dành cho ``evaluate`` chạy lại trong tầm nhìn của mốc.
    """
    if not FORECAST_DIR.is_dir():
        return []
    wanted = {s.upper() for s in symbols} if symbols else None
    out: List[Forecast] = []
    for p in sorted(FORECAST_DIR.glob("*.json")):
        try:
            forecast = Forecast.from_dict(json.loads(p.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, TypeError, OSError):
            continue
        if wanted and forecast.symbol.upper() not in wanted:
            continue
        if as_of is not None:
            if not asof_mod.before(as_of, forecast.created):
                continue
        elif open_only and not forecast.is_open:
            continue
        out.append(forecast)
    out.sort(key=lambda f: (f.symbol, f.created))
    return out


def delete(forecast_id: str) -> bool:
    p = path_for(forecast_id)
    if p.is_file():
        p.unlink()
        return True
    return False


# ---------------------------------------------------------------------------
# proposing forecasts from a structure
# ---------------------------------------------------------------------------
def propose(
    symbol: str,
    lookback_days: int = 180,
    as_of: Optional[datetime] = None,
    structure: Optional[Structure] = None,
) -> List[Forecast]:
    """Candidate forecasts the current chart justifies. Nothing is saved here."""
    st = structure or build_structure(symbol, lookback_days=lookback_days, as_of=as_of)
    if not st.records:
        return []

    recs = st.records
    close = recs[-1].priceClose
    atr = st.atr14 or (close * 0.02)
    out: List[Forecast] = []

    box = st.box
    if box is not None and box.state == INSIDE:
        height = box.top - box.bottom
        out.append(Forecast(
            id=make_id(symbol, st.as_of, "box_breakout"),
            symbol=st.symbol, created=st.as_of, basis="box_breakout", direction="up",
            trigger_type=CLOSE_ABOVE, trigger_level=box.top,
            target=round(box.top + height, 2), invalidation=box.bottom,
            deadline_bars=max(10, box.bars), created_close=close,
            confirm_volume_x=1.5,
            note=(f"Hộp {box.bottom}–{box.top} đã {box.bars} phiên. Đóng cửa vượt {box.top} "
                  f"kèm volume ≥ 1.5× thì mục tiêu đo được là {round(box.top + height, 2)}."),
            evidence={"box": box.to_dict(),
                      "pattern": st.pattern.name if st.pattern else None},
        ))

    if box is not None and box.state in (BREAKOUT_UP_CONFIRMED, BREAKOUT_UP_WEAK) \
            and box.target is not None and not box.target_hit:
        out.append(Forecast(
            id=make_id(symbol, st.as_of, "box_running"),
            symbol=st.symbol, created=st.as_of, basis="box_running", direction="up",
            trigger_type=CLOSE_ABOVE, trigger_level=box.top,
            target=box.target, invalidation=box.bottom,
            deadline_bars=max(10, box.bars), created_close=close,
            status=TRIGGERED,
            triggered_date=box.breakout_date, triggered_volume_x=box.breakout_volume_x,
            note=(f"Đã vượt hộp ngày {box.breakout_date}, đang chạy tới {box.target}; "
                  f"hỏng nếu đóng cửa dưới {box.bottom}."),
            evidence={"box": box.to_dict()},
        ))

    # Reversal formations map onto a forecast one-for-one: the neckline is the
    # trigger, the measured move is the target, and the shape names its own
    # invalidation. Nothing here needs inventing.
    for ev in getattr(st, "evidence", []):
        f = ev.formation
        if f.state == FORMATION_FAILED:
            continue
        down = f.bias == FORMATION_BEARISH
        measured = round(f.neckline_now - f.height if down
                         else f.neckline_now + f.height, 2)
        deadline = max(10, f.bars)
        if f.state == FORMATION_FORMING:
            out.append(Forecast(
                id=make_id(symbol, st.as_of, f"neckline_{f.kind}"),
                symbol=st.symbol, created=st.as_of, basis="neckline_break",
                direction="down" if down else "up",
                trigger_type=CLOSE_BELOW if down else CLOSE_ABOVE,
                trigger_level=f.neckline_now,
                target=measured, invalidation=f.invalidation,
                deadline_bars=deadline, created_close=close,
                confirm_volume_x=1.5,
                note=(f"{f.name} {f.start_date} → {f.end_date}. {ev.volume_note.capitalize()}. "
                      f"Đóng cửa {'dưới' if down else 'trên'} {f.neckline_now} kèm volume "
                      f"≥ 1.5× thì mục tiêu đo được {measured}."),
                evidence={"formation": f.to_dict(), "tier": ev.tier,
                          "candles": ev.candle_note},
            ))
        elif f.target is not None and not f.target_hit:
            out.append(Forecast(
                id=make_id(symbol, st.as_of, f"neckline_run_{f.kind}"),
                symbol=st.symbol, created=st.as_of, basis="neckline_running",
                direction="down" if down else "up",
                trigger_type=CLOSE_BELOW if down else CLOSE_ABOVE,
                trigger_level=f.neckline_now,
                target=f.target, invalidation=f.invalidation,
                deadline_bars=deadline, created_close=close,
                status=TRIGGERED,
                triggered_date=f.break_date, triggered_volume_x=f.break_volume_x,
                note=(f"{f.name} đã phá neckline ngày {f.break_date} "
                      f"({ev.volume_note}). Đang chạy tới {f.target}; "
                      f"hỏng nếu đóng cửa {'trên' if down else 'dưới'} {f.invalidation}."),
                evidence={"formation": f.to_dict(), "tier": ev.tier,
                          "candles": ev.candle_note},
            ))

    resistance = next((l for l in st.trendlines
                       if l.kind == RESISTANCE and not l.broken), None)
    if resistance is not None and abs(resistance.distance_pct) <= 5.0:
        level = resistance.value_now
        # After a break, price runs to the nearest overhead swing high — not to
        # the highest one on the chart. Cap it so a 15-bar target stays sane.
        cap = level + 3 * atr
        overhead = [p.price for p in st.pivots
                    if p.kind == HIGH and level < p.price <= cap]
        target = round(min(overhead) if overhead else cap, 2)
        out.append(Forecast(
            id=make_id(symbol, st.as_of, "trendline_break"),
            symbol=st.symbol, created=st.as_of, basis="trendline_break", direction="up",
            trigger_type=CLOSE_ABOVE, trigger_level=level,
            target=target,
            invalidation=round(min(r.priceLow for r in recs[-10:]), 2),
            deadline_bars=15, created_close=close, confirm_volume_x=1.3,
            note=(f"Giá cách đường nối đỉnh {resistance.distance_pct:+.1f}%. "
                  f"Vượt {level} thì mục tiêu {target} (đỉnh swing gần nhất phía trên)."),
            evidence={"trendline": resistance.to_dict()},
        ))

    rsi = IndicatorGroup2.rsi(recs, 14)
    events = detect_rsi_events(recs, rsi_series=rsi)
    if events:
        last = events[-1]
        bars_ago = len(recs) - 1 - last.index
        if last.kind == OVERSOLD_RECLAIM and bars_ago <= 5 and last.quality != "weak":
            ema20 = IndicatorGroup1.ema(recs, 20)
            ema_now = next((v for v in reversed(ema20) if v is not None), close)
            target = round(max(ema_now, close + 2 * atr), 2)
            out.append(Forecast(
                id=make_id(symbol, st.as_of, "rsi_reclaim"),
                symbol=st.symbol, created=st.as_of, basis="rsi_reclaim", direction="up",
                trigger_type=CLOSE_ABOVE, trigger_level=round(recs[-1].priceHigh, 2),
                target=target,
                invalidation=round(min(r.priceLow for r in recs[last.index:]), 2),
                deadline_bars=12, created_close=close,
                note=(f"RSI bật khỏi quá bán ngày {last.date} (đáy {last.extreme}, "
                      f"{last.quality}). Vượt đỉnh phiên gần nhất thì mục tiêu {target}."),
                evidence={"rsi_event": last.to_dict()},
            ))

    return out


# ---------------------------------------------------------------------------
# evaluation
# ---------------------------------------------------------------------------
def _volume_multiple(records: List[StockRecord]) -> List[float]:
    volumes = [r.priceImpactVolume for r in records]
    ema = pd.Series(volumes).ewm(span=20, adjust=False).mean().tolist()
    return [v / e if e else 0.0 for v, e in zip(volumes, ema)]


def _crossed(trigger_type: str, close: float, level: float) -> bool:
    return close > level if trigger_type == CLOSE_ABOVE else close < level


def evaluate(forecast: Forecast, records: List[StockRecord]) -> Tuple[Forecast, Optional[str]]:
    """Replay the bars after ``created`` and update the status.

    Returns the forecast and the previous status if it changed, else ``None``.
    Replaying from scratch each time keeps the stored file a pure cache — a
    corrupted or hand-edited status heals on the next check.
    """
    before = forecast.status
    today = records[-1].date.strftime("%Y-%m-%d") if records else None
    forecast.current_close = round(records[-1].priceClose, 2) if records else None

    forward = [r for r in records if r.date.strftime("%Y-%m-%d") > forecast.created]
    forecast.bars_elapsed = len(forward)
    forecast.last_checked = today
    if not forward:
        return forecast, None

    all_vol_x = _volume_multiple(records)
    vol_x = all_vol_x[-len(forward):]
    forecast.current_volume_x = round(all_vol_x[-1], 2) if all_vol_x else None
    up = forecast.direction == "up"

    # Re-derive from the recorded starting point rather than trusting the file.
    status = TRIGGERED if forecast.basis == "box_running" else PENDING
    triggered_at = 0 if status == TRIGGERED else None
    resolved_date = resolved_close = None
    triggered_date = forecast.triggered_date if status == TRIGGERED else None
    triggered_vol = forecast.triggered_volume_x if status == TRIGGERED else None

    for i, rec in enumerate(forward):
        date = rec.date.strftime("%Y-%m-%d")
        close = rec.priceClose

        if status == PENDING:
            # The idea can die before it ever starts.
            broke = close < forecast.invalidation if up else close > forecast.invalidation
            if broke:
                status, resolved_date, resolved_close = INVALIDATED, date, close
                break
            if _crossed(forecast.trigger_type, close, forecast.trigger_level):
                need = forecast.confirm_volume_x
                if need is None or vol_x[i] >= need:
                    status, triggered_at = TRIGGERED, i
                    triggered_date, triggered_vol = date, round(vol_x[i], 2)
                    continue
            if i + 1 >= forecast.deadline_bars:
                status, resolved_date, resolved_close = EXPIRED, date, close
                break

        elif status == TRIGGERED:
            hit = close >= forecast.target if up else close <= forecast.target
            if hit:
                status, resolved_date, resolved_close = HIT_TARGET, date, close
                break
            dead = close < forecast.invalidation if up else close > forecast.invalidation
            if dead:
                status, resolved_date, resolved_close = INVALIDATED, date, close
                break
            if triggered_at is not None and i - triggered_at >= forecast.deadline_bars:
                status, resolved_date, resolved_close = EXPIRED, date, close
                break

    forecast.status = status
    forecast.triggered_date = triggered_date
    forecast.triggered_volume_x = triggered_vol
    forecast.resolved_date = resolved_date
    forecast.resolved_close = round(resolved_close, 2) if resolved_close else None

    if status != before:
        forecast.history.append({
            "from": before, "to": status,
            "date": resolved_date or triggered_date or today or "",
            "checked": today or "",
        })
        return forecast, before
    return forecast, None


@dataclass
class CheckResult:
    as_of: str
    checked: int
    #: Mốc hồi tưởng đã yêu cầu (rỗng = kiểm tra trên dữ liệu mới nhất).
    as_of_requested: str = ""
    changes: List[Dict[str, Any]] = field(default_factory=list)
    forecasts: List[Forecast] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)


def check_all(
    symbols: Optional[Sequence[str]] = None,
    open_only: bool = True,
    lookback_days: int = 400,
    as_of: Optional[datetime] = None,
    persist: Optional[bool] = None,
) -> CheckResult:
    """Re-evaluate stored forecasts against the newest bars and persist results.

    ``as_of`` chạy lại bài kiểm tra *như thể* hôm nay là ngày đó: chỉ những
    forecast tạo trước mốc được xét, và chỉ những phiên tới mốc được replay.

    Kết quả hồi tưởng **không được ghi xuống đĩa** (``persist`` mặc định tắt khi
    có ``as_of``): file forecast là cache của trạng thái *hiện tại*: ghi đè bằng
    trạng thái của một ngày trong quá khứ là tua ngược đúng cái mà ``/watch``
    dựa vào để báo thay đổi.
    """
    if persist is None:
        persist = as_of is None
    stored = load_all(symbols, open_only=open_only, as_of=as_of)
    result = CheckResult(
        as_of=asof_mod.label(as_of) or datetime.now().strftime("%Y-%m-%d"),
        checked=len(stored),
        as_of_requested=asof_mod.label(as_of),
    )
    by_symbol: Dict[str, List[StockRecord]] = {}

    for forecast in stored:
        try:
            recs = by_symbol.get(forecast.symbol)
            if recs is None:
                recs = load_recent(forecast.symbol, lookback_days, as_of)
                by_symbol[forecast.symbol] = recs
            if not recs:
                result.errors.append(f"{forecast.symbol}: không có dữ liệu")
                continue
            if as_of is not None:
                # Trạng thái trên đĩa là của *hôm nay*; đem so với bản replay tới
                # mốc thì mọi forecast đều "đổi trạng thái". Đặt lại về đúng điểm
                # xuất phát mà ``evaluate`` dùng, để phần được báo là thay đổi
                # thật sự đã xảy ra tính tới mốc.
                forecast.status = TRIGGERED if forecast.basis == "box_running" else PENDING
                forecast.history = []
            forecast, previous = evaluate(forecast, recs)
            if persist:
                save(forecast)
            if previous is not None:
                # Ghi thay đổi *trước* khi lọc: một kỳ vọng chạm mục tiêu rồi
                # đóng lại trước mốc chính là thứ đáng kể nhất của bản hồi tưởng,
                # mà `open_only` lại đúng là mặc định.
                result.changes.append({
                    "id": forecast.id, "symbol": forecast.symbol,
                    "from": previous, "to": forecast.status,
                    "date": forecast.resolved_date or forecast.triggered_date,
                    "close": round(recs[-1].priceClose, 2),
                    "target": forecast.target, "note": forecast.note,
                })
            if as_of is not None and open_only and not forecast.is_open:
                continue          # đã đóng *tính tới mốc*, không phải đóng hôm nay
            result.forecasts.append(forecast)
        except Exception as exc:                    # one bad file must not stop the check
            result.errors.append(f"{forecast.id}: {type(exc).__name__}: {exc}")

    if result.forecasts:
        result.as_of = max(
            (f.last_checked for f in result.forecasts if f.last_checked),
            default=result.as_of,
        )
    return result
