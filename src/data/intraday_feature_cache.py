"""Intraday feature cache (Phase 4 §4.10).

Stores ~10 scalar features per (symbol, day) so primitives can normalize
against history without ever loading more than one day of raw tick data
at runtime.

Storage: JSON-per-month for portability and zero-deps. Production can swap
to parquet by changing the two `_load_month` / `_save_month` helpers — the
public API does not need to change.

    data_tick_features/
      daily/
        2026-04.json     ← list of IntradayFeatureRow dicts
      derived/
        median_trade_size_20d.json   ← {symbol: {date: scalar}}
"""
import json
from dataclasses import asdict, dataclass, field, fields
from datetime import date as _date, datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional


@dataclass
class IntradayFeatureRow:
    symbol: str
    date: _date
    # OFI
    ofi_composite: float = 0.0
    ofi_30min: float = 0.0
    ofi_eod: float = 0.0
    # Block trades
    median_trade_size: float = 0.0
    block_count: int = 0
    block_buy_volume: float = 0.0
    block_sell_volume: float = 0.0
    # VWAP
    vwap: float = 0.0
    close_vs_vwap_pct: float = 0.0
    upvol_ratio: float = 0.0
    # Auction
    auction_ato_net: float = 0.0
    auction_atc_net: float = 0.0
    # Data quality
    bars_with_trades: int = 0
    total_bars: int = 0
    data_quality_score: float = 0.0
    classifier_method: str = "tick_rule"
    computed_at: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["date"] = self.date.isoformat()
        d["computed_at"] = self.computed_at.isoformat()
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "IntradayFeatureRow":
        d = dict(d)
        d["date"] = _date.fromisoformat(d["date"])
        d["computed_at"] = datetime.fromisoformat(d["computed_at"])
        return cls(**d)


def _month_key(d: _date) -> str:
    return f"{d.year:04d}-{d.month:02d}"


class IntradayFeatureCache:
    def __init__(self, base_path: str):
        self.base = Path(base_path)
        self.daily_dir = self.base / "daily"
        self.derived_dir = self.base / "derived"

    # ----- Storage helpers -----------------------------------------------

    def _month_path(self, d: _date) -> Path:
        self.daily_dir.mkdir(parents=True, exist_ok=True)
        return self.daily_dir / f"{_month_key(d)}.json"

    def _load_month(self, d: _date) -> List[IntradayFeatureRow]:
        path = self._month_path(d)
        if not path.exists():
            return []
        with path.open("r", encoding="utf-8") as f:
            payload = json.load(f)
        return [IntradayFeatureRow.from_dict(r) for r in payload]

    def _save_month(self, d: _date, rows: List[IntradayFeatureRow]) -> None:
        path = self._month_path(d)
        with path.open("w", encoding="utf-8") as f:
            json.dump([r.to_dict() for r in rows], f, indent=2)

    # ----- Public API ----------------------------------------------------

    def write_day(self, rows: List[IntradayFeatureRow]) -> None:
        """Append/upsert rows for a single date. Idempotent."""
        if not rows:
            return
        by_month: Dict[str, List[IntradayFeatureRow]] = {}
        for r in rows:
            by_month.setdefault(_month_key(r.date), []).append(r)

        for month_key, batch in by_month.items():
            sample_date = batch[0].date
            existing = self._load_month(sample_date)
            # Upsert by (symbol, date)
            keyed = {(r.symbol, r.date): r for r in existing}
            for r in batch:
                keyed[(r.symbol, r.date)] = r
            merged = sorted(keyed.values(), key=lambda r: (r.date, r.symbol))
            self._save_month(sample_date, merged)

    def load_row(self, symbol: str, day: _date) -> Optional[IntradayFeatureRow]:
        for r in self._load_month(day):
            if r.symbol == symbol and r.date == day:
                return r
        return None

    def load_feature(
        self, symbol: str, feature: str,
        end_date: _date, lookback: int = 20,
    ) -> List[float]:
        """Return up to ``lookback`` scalars for ``feature`` ending at ``end_date``.

        Walks back month-by-month so a 20-day lookback never reads more than
        2 month files even at month boundaries.
        """
        out: List[float] = []
        cursor = _date(end_date.year, end_date.month, 1)
        # Pull current month plus the previous one to cover lookback windows
        # that span a month boundary.
        for offset in range(0, 3):
            if offset == 0:
                month = cursor
            else:
                # Step back one month
                year, month_num = cursor.year, cursor.month
                month_num -= 1
                if month_num <= 0:
                    month_num = 12
                    year -= 1
                cursor = _date(year, month_num, 1)
                month = cursor
            rows = [
                r for r in self._load_month(month)
                if r.symbol == symbol and r.date <= end_date
            ]
            rows.sort(key=lambda r: r.date, reverse=True)
            for r in rows:
                if hasattr(r, feature):
                    out.append(float(getattr(r, feature)))
                if len(out) >= lookback:
                    return list(reversed(out))
        return list(reversed(out))

    def load_scalar(
        self, symbol: str, feature: str, as_of: _date,
    ) -> Optional[float]:
        """Load a derived rolling scalar (e.g. ``median_trade_size_20d``)."""
        path = self.derived_dir / f"{feature}.json"
        if not path.exists():
            return None
        with path.open("r", encoding="utf-8") as f:
            payload = json.load(f)
        sym_payload = payload.get(symbol, {})
        # Find the latest date ≤ as_of
        candidates = sorted(
            (_date.fromisoformat(d), v) for d, v in sym_payload.items()
            if _date.fromisoformat(d) <= as_of
        )
        return candidates[-1][1] if candidates else None

    def write_scalar(
        self, feature: str, symbol: str, as_of: _date, value: float,
    ) -> None:
        self.derived_dir.mkdir(parents=True, exist_ok=True)
        path = self.derived_dir / f"{feature}.json"
        if path.exists():
            with path.open("r", encoding="utf-8") as f:
                payload = json.load(f)
        else:
            payload = {}
        sym = payload.setdefault(symbol, {})
        sym[as_of.isoformat()] = float(value)
        with path.open("w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)

    def rebuild_scalars(self, symbol: str, as_of: _date) -> None:
        """Recompute the standard derived rollups for ``symbol`` at ``as_of``."""
        history = self.load_feature(
            symbol, "median_trade_size", end_date=as_of, lookback=20,
        )
        if history:
            from statistics import median
            self.write_scalar("median_trade_size_20d", symbol, as_of, median(history))

        ofi_history = self.load_feature(
            symbol, "ofi_composite", end_date=as_of, lookback=60,
        )
        if ofi_history:
            self.write_scalar(
                "ofi_baseline_60d", symbol, as_of,
                sum(ofi_history) / len(ofi_history),
            )
