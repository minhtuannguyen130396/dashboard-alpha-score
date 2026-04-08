"""Tick data storage helpers (Phase 3 stub, used by Phase 4 cache pipeline).

Storage layout:

    data_tick/
      <SYMBOL>/
        2026-04-01.parquet
        2026-04-02.parquet

Schema (per-row):
    time:       timestamp (ms)
    price:      float
    volume:     float
    side:       int8 (-1 sell, 0 unknown, +1 buy)
    bid:        float (nullable)
    ask:        float (nullable)
    trade_type: str ("continuous"|"ATO"|"ATC"|"lunch")

Phase 3 only defines the API + a JSON fallback so unit tests can round-trip
without requiring pyarrow. Phase 4 nightly batch jobs swap to parquet via
``write_tick_day(... format='parquet')``.
"""
import json
import os
from dataclasses import asdict
from datetime import date as _date, datetime
from pathlib import Path
from typing import List, Optional

from src.data.flow_records import IntradayFlowRecord, RawTick


def _symbol_dir(base: str, symbol: str) -> Path:
    p = Path(base) / symbol
    p.mkdir(parents=True, exist_ok=True)
    return p


def _day_path(base: str, symbol: str, day: _date, ext: str = "json") -> Path:
    return _symbol_dir(base, symbol) / f"{day.isoformat()}.{ext}"


def write_tick_day(
    base_path: str,
    symbol: str,
    day: _date,
    ticks: List[RawTick],
    fmt: str = "json",
) -> Path:
    """Persist a day's worth of ticks for a symbol. Idempotent: overwrites."""
    if fmt == "parquet":
        try:
            import pyarrow as pa
            import pyarrow.parquet as pq
        except ImportError as exc:
            raise RuntimeError("pyarrow not installed") from exc
        path = _day_path(base_path, symbol, day, "parquet")
        table = pa.table({
            "time":       [t.timestamp.isoformat() for t in ticks],
            "price":      [t.price for t in ticks],
            "volume":     [t.volume for t in ticks],
            "side":       [int(t.side) for t in ticks],
            "bid":        [t.bid for t in ticks],
            "ask":        [t.ask for t in ticks],
            "trade_type": [t.trade_type for t in ticks],
        })
        pq.write_table(table, path)
        return path

    path = _day_path(base_path, symbol, day, "json")
    payload = [
        {
            "time": t.timestamp.isoformat(),
            "price": t.price,
            "volume": t.volume,
            "side": int(t.side),
            "bid": t.bid,
            "ask": t.ask,
            "trade_type": t.trade_type,
        }
        for t in ticks
    ]
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f)
    return path


def read_tick_day(
    base_path: str, symbol: str, day: _date,
) -> Optional[List[RawTick]]:
    """Read a day's worth of ticks. Returns None if the file is missing.

    Tries parquet first, falls back to json.
    """
    pq_path = _day_path(base_path, symbol, day, "parquet")
    json_path = _day_path(base_path, symbol, day, "json")

    if pq_path.exists():
        try:
            import pyarrow.parquet as pq
            table = pq.read_table(pq_path)
            d = table.to_pydict()
            n = len(d["price"])
            return [
                RawTick(
                    timestamp=datetime.fromisoformat(d["time"][i]),
                    price=float(d["price"][i]),
                    volume=float(d["volume"][i]),
                    side=int(d["side"][i]),
                    bid=d["bid"][i],
                    ask=d["ask"][i],
                    trade_type=str(d["trade_type"][i]),
                )
                for i in range(n)
            ]
        except ImportError:
            pass

    if json_path.exists():
        with json_path.open("r", encoding="utf-8") as f:
            rows = json.load(f)
        return [
            RawTick(
                timestamp=datetime.fromisoformat(r["time"]),
                price=r["price"],
                volume=r["volume"],
                side=r["side"],
                bid=r.get("bid"),
                ask=r.get("ask"),
                trade_type=r.get("trade_type", "continuous"),
            )
            for r in rows
        ]

    return None


def resample_to_bars(
    ticks: List[RawTick], bar_size: str = "5m",
) -> List[IntradayFlowRecord]:
    """Aggregate raw ticks into OHLCV bars of size ``bar_size``."""
    if not ticks:
        return []

    minutes = _parse_minutes(bar_size)
    bucket_seconds = minutes * 60

    def _bucket_key(ts: datetime) -> datetime:
        epoch = int(ts.timestamp())
        bucket_start = (epoch // bucket_seconds) * bucket_seconds
        return datetime.fromtimestamp(bucket_start)

    bars: List[IntradayFlowRecord] = []
    current_key: Optional[datetime] = None
    current: List[RawTick] = []

    for t in ticks:
        key = _bucket_key(t.timestamp)
        if current_key is None:
            current_key = key
        if key != current_key and current:
            bars.append(_aggregate_bar(current_key, current, bar_size))
            current = []
            current_key = key
        current.append(t)
    if current and current_key is not None:
        bars.append(_aggregate_bar(current_key, current, bar_size))

    return bars


def _parse_minutes(bar_size: str) -> int:
    s = bar_size.strip().lower()
    if s.endswith("m"):
        return int(s[:-1])
    if s.endswith("h"):
        return int(s[:-1]) * 60
    if s.endswith("d"):
        return int(s[:-1]) * 60 * 24
    raise ValueError(f"Unknown bar size: {bar_size}")


def _aggregate_bar(
    ts: datetime, ticks: List[RawTick], bar_size: str,
) -> IntradayFlowRecord:
    prices = [t.price for t in ticks]
    volume = sum(t.volume for t in ticks)
    traded = sum(t.price * t.volume for t in ticks)
    buy_vol = sum(t.volume for t in ticks if t.side > 0)
    sell_vol = sum(t.volume for t in ticks if t.side < 0)
    vwap = traded / volume if volume > 0 else prices[-1]

    return IntradayFlowRecord(
        timestamp=ts,
        bar_size=bar_size,
        open=prices[0],
        high=max(prices),
        low=min(prices),
        close=prices[-1],
        volume=volume,
        traded_value=traded,
        buy_volume=buy_vol if buy_vol > 0 else None,
        sell_volume=sell_vol if sell_vol > 0 else None,
        vwap=vwap,
    )
