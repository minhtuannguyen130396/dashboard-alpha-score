"""Symbol universe + fast, cached price loading.

``load_stock_history`` walks every year directory a symbol has (2010..2026),
which costs ~1.2s per symbol. A batch scan only ever needs the last year or
two, so this module reads just the year folders the range touches and caches
the parsed result per (symbol, year).
"""
import json
import os
from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from src.data.stock_data_loader import StockRecord, record_from_json

#: Repo root — this file is at <root>/src/ta/loader.py
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"
STOCK_LIST_DIR = PROJECT_ROOT / "stock_list"

#: Named baskets, mapped to the JSON files already in ``stock_list/``.
GROUP_FILES: Dict[str, str] = {
    "vn30": "stock_vn_30.json",
    "largecap": "stock_large_cab.json",
    "midcap": "stock_mid_cab.json",
    "all": "list_all_stock.json",
}

#: Market benchmarks — indices, **not** tradable symbols.
#:
#: VNINDEX sits in ``data/`` next to the 80 stocks and loads through the same
#: ``StockRecord`` path, because FireAnt returns it with an identical schema.
#: That similarity is the trap: left alone, ``resolve_universe(None)`` would
#: hand it to every scan and ranking, and the whole market would show up as a
#: row competing with individual stocks. It is not a candidate — nobody buys
#: the index — and its bars are an average, so its ADX, its RSI and its swing
#: structure all read *smoother* than any constituent. One extra row would
#: quietly shift every percentile in ``ranking.py``.
#:
#: So benchmarks are held in their own registry and dropped from every group.
#: The only way to get one is to name it: ``resolve_universe("VNINDEX")``, or
#: ask for the ``benchmarks`` group. What they are *for* is comparison — how
#: far a symbol ran relative to the market, which is the thing a raw return
#: cannot tell you.
BENCHMARK_FILE = "benchmarks.json"
BENCHMARK_GROUP_KEYS = ("benchmark", "benchmarks", "index", "chi_so")

#: Derivatives — VN30 futures contracts, **not** tradable stock symbols either.
#:
#: Same trap as the benchmarks, one notch worse. FireAnt serves VN30F1M through
#: the identical ``historical-quotes`` endpoint with an identical payload
#: (``adjRatio: 1.0``, full OHLC, ``dealVolume``), so nothing downstream can
#: tell a futures contract from a stock. Left in the basket, VN30F1M would rank
#: as a "symbol" whose price is ~1980 "đồng", whose volume is 200k *contracts*
#: rather than shares, and whose ATR would blow out every percentile in
#: ``ranking.py``.
#:
#: The other reason to keep them apart is that a futures series is not one
#: instrument. ``VN30F1M`` is a *stitched* series: after each expiry it jumps to
#: the next contract, so a percentage change across that boundary is an
#: artefact, not a move. ``futures.py`` knows where those seams are; a generic
#: scanner does not.
DERIVATIVE_FILE = "derivatives.json"
DERIVATIVE_GROUP_KEYS = ("futures", "derivative", "derivatives", "phai_sinh", "phaisinh")


def available_symbols() -> List[str]:
    """Symbols that actually have daily price files on disk."""
    if not DATA_DIR.is_dir():
        return []
    out = []
    for d in sorted(DATA_DIR.iterdir()):
        if d.is_dir() and any(d.glob("[12][0-9][0-9][0-9]/*.json")):
            out.append(d.name)
    return out


@lru_cache(maxsize=1)
def _symbols_on_disk() -> frozenset:
    return frozenset(available_symbols())


@lru_cache(maxsize=1)
def benchmark_symbols() -> Tuple[str, ...]:
    """Index codes from ``stock_list/benchmarks.json`` — never stock symbols."""
    path = STOCK_LIST_DIR / BENCHMARK_FILE
    if not path.is_file():
        return ()
    try:
        items = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return ()
    return tuple(
        it["share_code"].upper() for it in items if it.get("share_code")
    )


def is_benchmark(symbol: str) -> bool:
    """True for VNINDEX and friends — the market, not a stock."""
    return symbol.strip().upper() in benchmark_symbols()


@lru_cache(maxsize=1)
def derivative_symbols() -> Tuple[str, ...]:
    """Futures codes from ``stock_list/derivatives.json`` — never stock symbols."""
    path = STOCK_LIST_DIR / DERIVATIVE_FILE
    if not path.is_file():
        return ()
    try:
        items = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return ()
    return tuple(
        it["share_code"].upper() for it in items if it.get("share_code")
    )


def is_derivative(symbol: str) -> bool:
    """True for VN30F1M and friends — a contract, not a stock."""
    return symbol.strip().upper() in derivative_symbols()


def non_tradable_symbols() -> frozenset:
    """Everything that must stay out of a scan/ranking basket: indices + futures."""
    return frozenset(benchmark_symbols()) | frozenset(derivative_symbols())


def _group_symbols(group: str) -> List[str]:
    if group in BENCHMARK_GROUP_KEYS:
        return list(benchmark_symbols())
    if group in DERIVATIVE_GROUP_KEYS:
        return list(derivative_symbols())
    filename = GROUP_FILES[group]
    path = STOCK_LIST_DIR / filename
    if not path.is_file():
        raise FileNotFoundError(f"Missing group file {path}")
    with path.open("r", encoding="utf-8") as f:
        items = json.load(f)
    return [it["share_code"] for it in items if it.get("share_code")]


def resolve_universe(spec: Optional[str] = None) -> List[str]:
    """Turn ``'vn30'``, ``'ACB,HPG'`` or ``None`` into a list of symbols.

    Symbols without data on disk are dropped, so callers never have to guard
    against ``FileNotFoundError`` mid-scan.

    Benchmarks **and futures contracts** are dropped from every *group*
    answer — ``None``, ``disk``, ``all``, ``vn30``. A scan of "the whole
    basket" means the stocks; VNINDEX, VN30 and VN30F1M are not among them.
    Naming one explicitly still works (``"VNINDEX"``, ``"FPT,VN30F1M"``, or
    the ``benchmarks`` / ``futures`` groups), because asking for the index or
    the contract by name is a different question from asking for the basket
    that happens to sit next to it on disk.
    """
    on_disk = _symbols_on_disk()
    marks = set(benchmark_symbols()) | set(derivative_symbols())

    if not spec or spec.strip().lower() in ("disk", "available"):
        return sorted(on_disk - marks)

    key = spec.strip().lower()
    if key in GROUP_FILES or key in BENCHMARK_GROUP_KEYS or key in DERIVATIVE_GROUP_KEYS:
        wanted = _group_symbols(key)
        # A stock group never smuggles in an index or a contract; the
        # benchmark/futures groups are nothing but those.
        if key in GROUP_FILES:
            wanted = [s for s in wanted if s.upper() not in marks]
    else:
        wanted = [s.strip().upper() for s in spec.replace(";", ",").split(",") if s.strip()]

    seen, out = set(), []
    for sym in wanted:
        if sym in on_disk and sym not in seen:
            seen.add(sym)
            out.append(sym)
    return out


def missing_symbols(spec: str) -> List[str]:
    """Requested symbols that have no data directory — worth telling the user."""
    on_disk = _symbols_on_disk()
    key = spec.strip().lower()
    is_group = (key in GROUP_FILES or key in BENCHMARK_GROUP_KEYS
                or key in DERIVATIVE_GROUP_KEYS)
    wanted = _group_symbols(key) if is_group else [
        s.strip().upper() for s in spec.replace(";", ",").split(",") if s.strip()
    ]
    return [s for s in dict.fromkeys(wanted) if s not in on_disk]


def _year_signature(symbol: str, year: int) -> Tuple[int, int, int]:
    """``(file count, newest mtime, total bytes)`` for one symbol-year.

    This is the cache validity stamp. It has to look at *file* mtimes, not the
    directory's: overwriting ``2026-08-01.json`` in place — exactly what a
    monthly refetch does — leaves the directory mtime untouched.

    Size is in there because mtime alone is not enough. Rewriting the month
    file twice inside one filesystem timestamp tick — a refetch immediately
    after an update, which is exactly what the tests do — leaves count and
    mtime identical and served stale bars. Bytes come free from the same
    ``stat()`` and separate the two writes whenever the content grew.

    Costs ~0.1 ms per symbol-year, against ~25 ms to parse one.
    """
    year_dir = DATA_DIR / symbol / str(year)
    count = 0
    newest = 0
    total = 0
    try:
        with os.scandir(year_dir) as entries:
            for entry in entries:
                if not entry.name.endswith(".json"):
                    continue
                count += 1
                stat = entry.stat()
                total += stat.st_size
                if stat.st_mtime_ns > newest:
                    newest = stat.st_mtime_ns
    except (FileNotFoundError, NotADirectoryError, PermissionError):
        return (0, 0, 0)
    return (count, newest, total)


@lru_cache(maxsize=512)
def _load_year_cached(
    symbol: str, year: int, signature: Tuple[int, int, int]
) -> Tuple[StockRecord, ...]:
    """Parse one symbol-year. ``signature`` is part of the key, never read."""
    year_dir = DATA_DIR / symbol / str(year)
    if not year_dir.is_dir():
        return ()
    records: List[StockRecord] = []
    for json_file in sorted(year_dir.glob("*.json")):
        try:
            with json_file.open("r", encoding="utf-8") as f:
                items = json.load(f)
        except (json.JSONDecodeError, OSError):
            continue
        for item in items:
            try:
                records.append(record_from_json(item))
            except (KeyError, TypeError, ZeroDivisionError):
                continue
    records.sort(key=lambda r: r.date)
    return tuple(records)


def _load_year(symbol: str, year: int) -> Tuple[StockRecord, ...]:
    """Cached records for one symbol-year, re-parsed when the files change.

    Folding the on-disk signature into the cache key means a write by *any*
    process — this one, the tkinter app, a script, an rsync from the server —
    is picked up on the next read. Correctness no longer depends on the writer
    remembering to call ``clear_cache()``.
    """
    return _load_year_cached(symbol, year, _year_signature(symbol, year))


def clear_cache() -> None:
    """Drop every cached price file.

    Not needed for correctness — ``_load_year`` revalidates against file
    mtimes. Writers still call it to release memory promptly and to force a
    re-read on filesystems with coarse mtime resolution.
    """
    _load_year_cached.cache_clear()
    _symbols_on_disk.cache_clear()
    benchmark_symbols.cache_clear()
    derivative_symbols.cache_clear()


def load_prices(
    symbol: str,
    start: datetime,
    end: Optional[datetime] = None,
) -> List[StockRecord]:
    """Daily records for ``symbol`` in ``[start, end]``, reading only the
    year folders that range touches."""
    end = end or datetime.now()
    if end < start:
        start, end = end, start
    out: List[StockRecord] = []
    for year in range(start.year, end.year + 1):
        for rec in _load_year(symbol, year):
            if start <= rec.date <= end:
                out.append(rec)
    return out


def load_recent(symbol: str, lookback_days: int = 400,
                as_of: Optional[datetime] = None) -> List[StockRecord]:
    """The last ``lookback_days`` calendar days of history ending at ``as_of``."""
    end = as_of or datetime.now()
    return load_prices(symbol, end - timedelta(days=lookback_days), end)


def coverage(symbol: str) -> Optional[Tuple[str, str, int]]:
    """(first_date, last_date, bar_count) across all years, or None.

    Year folders can be entirely empty — a symbol listed after 2010 still
    gets a ``[]`` file for every pre-listing month, since the fetcher writes
    one file per calendar month regardless of whether FireAnt returned rows.
    So the first/last *non-empty* year has to be found by scanning, not by
    assuming ``years[0]``/``years[-1]`` have bars.
    """
    sym_dir = DATA_DIR / symbol
    if not sym_dir.is_dir():
        return None
    years = sorted(
        int(d.name) for d in sym_dir.iterdir()
        if d.is_dir() and d.name.isdigit()
    )
    if not years:
        return None
    total = 0
    first_recs: Optional[Tuple[StockRecord, ...]] = None
    last_recs: Optional[Tuple[StockRecord, ...]] = None
    for y in years:
        recs = _load_year(symbol, y)
        if not recs:
            continue
        total += len(recs)
        if first_recs is None:
            first_recs = recs
        last_recs = recs
    if first_recs is None or last_recs is None:
        return None
    return (
        first_recs[0].date.strftime("%Y-%m-%d"),
        last_recs[-1].date.strftime("%Y-%m-%d"),
        total,
    )


def latest_date(symbol: str) -> Optional[str]:
    """Newest bar date for a symbol without parsing every year."""
    sym_dir = DATA_DIR / symbol
    if not sym_dir.is_dir():
        return None
    years = sorted(
        (int(d.name) for d in sym_dir.iterdir() if d.is_dir() and d.name.isdigit()),
        reverse=True,
    )
    for y in years:
        recs = _load_year(symbol, y)
        if recs:
            return recs[-1].date.strftime("%Y-%m-%d")
    return None
