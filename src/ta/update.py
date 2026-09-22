"""Pull fresh bars from FireAnt into ``data/``, then drop the stale caches.

``fireant_history_fetcher.fetch_all_stock_history`` covers the bulk backfill,
but it always walks the whole symbol list, dies on the first HTTP error, and
overwrites a month file even when the API answers with an empty list. A daily
"get me the latest close" needs the opposite properties, so this module owns
that path:

* scope — any universe or explicit symbol list, not always all 80
* isolation — one symbol failing is reported, not fatal
* safety — an empty API response never clobbers a file that already has bars
* freshness — ``loader.clear_cache()`` runs at the end, otherwise the
  long-lived MCP process keeps serving pre-update data
"""
import json
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import requests
from dateutil.relativedelta import relativedelta

from src.data.fireant_history_fetcher import (
    BASE_URL_TEMPLATE, DATE_START_FETCH, TOKEN_ENV_VAR, load_bearer_token,
)
from src.ta.loader import (
    BENCHMARK_FILE, BENCHMARK_GROUP_KEYS, DATA_DIR, DERIVATIVE_FILE,
    DERIVATIVE_GROUP_KEYS, GROUP_FILES, STOCK_LIST_DIR, benchmark_symbols,
    clear_cache, derivative_symbols, resolve_universe,
)

#: How many months back each mode reaches. ``None`` means "since listing".
MODES: Dict[str, Optional[int]] = {
    "latest": 1,       # this month only — the daily update
    "recent": 2,       # this month + last, safe across a month boundary
    "quarter": 4,
    "full": None,      # everything since DATE_START_FETCH; slow
}

MODE_VN = {
    "latest": "tháng hiện tại",
    "recent": "tháng này + tháng trước",
    "quarter": "4 tháng gần nhất",
    "full": "toàn bộ lịch sử",
}

_RETRY_STATUS = (429, 500, 502, 503, 504)
_MAX_ATTEMPTS = 3


@dataclass
class SymbolUpdate:
    symbol: str
    before: Optional[str] = None       # newest bar date on disk before the fetch
    after: Optional[str] = None        # ... and after
    new_bars: int = 0
    files_written: int = 0
    fetch_from: Optional[str] = None   # first date this run asked the API for
    error: Optional[str] = None
    warnings: List[str] = field(default_factory=list)

    @property
    def gap_days(self) -> int:
        """Days between the last bar on disk and the start of this fetch.

        A positive number means ``mode`` was too narrow to close the hole —
        the symbol has missing sessions no amount of re-running ``latest``
        will fill.
        """
        if not self.before or not self.fetch_from:
            return 0
        before = datetime.strptime(self.before, "%Y-%m-%d").date()
        start = datetime.strptime(self.fetch_from, "%Y-%m-%d").date()
        return max(0, (start - before).days - 1)

    @property
    def changed(self) -> bool:
        return self.new_bars > 0 or (self.after != self.before)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class UpdateResult:
    mode: str
    started: str
    duration_s: float = 0.0
    requested: int = 0
    results: List[SymbolUpdate] = field(default_factory=list)
    fatal: Optional[str] = None        # nothing ran at all (e.g. missing token)

    @property
    def changed(self) -> List[SymbolUpdate]:
        return [r for r in self.results if r.error is None and r.changed]

    @property
    def unchanged(self) -> List[SymbolUpdate]:
        return [r for r in self.results if r.error is None and not r.changed]

    @property
    def failed(self) -> List[SymbolUpdate]:
        return [r for r in self.results if r.error is not None]

    @property
    def new_bars(self) -> int:
        return sum(r.new_bars for r in self.results)

    @property
    def gaps(self) -> List[SymbolUpdate]:
        """Symbols whose history still has a hole after this run."""
        return sorted(
            (r for r in self.results if r.error is None and r.gap_days > 3),
            key=lambda r: -r.gap_days,
        )

    @property
    def latest_date(self) -> Optional[str]:
        dates = [r.after for r in self.results if r.after]
        return max(dates) if dates else None

    def to_dict(self) -> dict:
        return {
            "mode": self.mode, "started": self.started, "duration_s": self.duration_s,
            "requested": self.requested, "fatal": self.fatal,
            "results": [r.to_dict() for r in self.results],
        }


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _ipo_dates() -> Dict[str, date]:
    """Listing dates from every stock_list file, so ``full`` starts sensibly."""
    out: Dict[str, date] = {}
    for filename in (*GROUP_FILES.values(), BENCHMARK_FILE, DERIVATIVE_FILE):
        path = STOCK_LIST_DIR / filename
        if not path.is_file():
            continue
        try:
            items = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        for item in items:
            code, ipo = item.get("share_code"), item.get("ipo_date")
            if not code or not ipo or code in out:
                continue
            try:
                out[code] = datetime.strptime(ipo, "%Y-%m-%d").date()
            except ValueError:
                continue
    return out


def _month_windows(start: date, end: date) -> List[Tuple[date, date]]:
    """One (from, to) pair per calendar month, clamped to ``end``.

    Files are named by the first day of their month, matching the layout
    ``fireant_history_fetcher`` already writes.
    """
    windows: List[Tuple[date, date]] = []
    cursor = start.replace(day=1)
    while cursor <= end:
        month_end = cursor + relativedelta(months=1) - timedelta(days=1)
        windows.append((max(cursor, start), min(month_end, end)))
        cursor += relativedelta(months=1)
    return windows


def _resolve_start(mode: str, symbol: str, today: date, ipos: Dict[str, date],
                   months: Optional[int]) -> date:
    back = months if months is not None else MODES[mode]
    ipo = ipos.get(symbol, datetime.strptime(DATE_START_FETCH, "%Y-%m-%d").date())
    if back is None:
        return max(ipo, datetime.strptime(DATE_START_FETCH, "%Y-%m-%d").date())
    first_of_month = today.replace(day=1)
    return max(ipo, first_of_month - relativedelta(months=back - 1))


def _count_bars(path: Path) -> int:
    if not path.is_file():
        return 0
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return 0
    return len(data) if isinstance(data, list) else 0


def _get(url: str, headers: dict, params: dict, timeout: int) -> list:
    """GET with a short retry on the transient statuses FireAnt actually returns."""
    last_error = None
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        try:
            response = requests.get(url, headers=headers, params=params, timeout=timeout)
            if response.status_code in _RETRY_STATUS and attempt < _MAX_ATTEMPTS:
                time.sleep(1.5 * attempt)
                continue
            response.raise_for_status()
            payload = response.json()
            return payload if isinstance(payload, list) else []
        except (requests.Timeout, requests.ConnectionError) as exc:
            last_error = exc
            if attempt < _MAX_ATTEMPTS:
                time.sleep(1.5 * attempt)
                continue
            raise
    if last_error:
        raise last_error
    return []


def _update_one(symbol: str, mode: str, months: Optional[int], today: date,
                ipos: Dict[str, date], headers: dict, timeout: int) -> SymbolUpdate:
    from src.ta.loader import latest_date

    out = SymbolUpdate(symbol=symbol, before=latest_date(symbol))
    start = _resolve_start(mode, symbol, today, ipos, months)
    out.fetch_from = start.isoformat()
    if start > today:
        return out

    symbol_dir = DATA_DIR / symbol
    url = BASE_URL_TEMPLATE.format(share_code=symbol)

    try:
        for window_start, window_end in _month_windows(start, today):
            days = (window_end - window_start).days + 1
            payload = _get(url, headers, {
                "startDate": window_start.isoformat(),
                "endDate": window_end.isoformat(),
                "offset": 0,
                "limit": days,
            }, timeout)

            year_dir = symbol_dir / str(window_start.year)
            target = year_dir / f"{window_start.replace(day=1).isoformat()}.json"
            existing = _count_bars(target)

            if not payload:
                # Never trade real bars for an empty answer — a holiday month,
                # a rate-limited response and a delisting all look the same here.
                if existing:
                    out.warnings.append(
                        f"{window_start:%Y-%m}: API trả rỗng, giữ nguyên {existing} phiên đã có"
                    )
                continue

            year_dir.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                              encoding="utf-8")
            out.files_written += 1
            out.new_bars += max(0, len(payload) - existing)
    except Exception as exc:
        out.error = f"{type(exc).__name__}: {exc}"

    return out


# ---------------------------------------------------------------------------
# entry point
# ---------------------------------------------------------------------------
def update_prices(
    universe: Optional[str] = None,
    mode: str = "latest",
    months: Optional[int] = None,
    max_workers: int = 6,
    timeout: int = 30,
    symbols: Optional[Sequence[str]] = None,
    include_benchmarks: bool = True,
    include_derivatives: bool = True,
) -> UpdateResult:
    """Fetch the newest bars for ``universe`` and refresh the read caches.

    Benchmarks **and futures contracts** ride along with a *basket* request.
    ``resolve_universe`` keeps VNINDEX, VN30 and VN30F1M out of every group —
    right for scanning, wrong here, because they would then never be refreshed
    by the daily ``/update`` and would sit quietly going stale until something
    tried to measure a stock against them. Asking for named symbols
    (``symbols=["FPT"]``, ``universe="FPT,HPG"``) means those and only those.

    A registry group (``"benchmarks"``, ``"futures"``) is resolved from the
    JSON file rather than from disk, because on the very first fetch there is
    no directory yet — ``resolve_universe`` would answer "nothing to update"
    for exactly the symbols this call exists to create.
    """
    if mode not in MODES:
        raise ValueError(f"Unknown mode {mode!r}. Available: {', '.join(MODES)}")

    started = time.time()
    result = UpdateResult(mode=mode, started=datetime.now().strftime("%Y-%m-%d %H:%M"))

    key = (universe or "").strip().lower()
    if symbols:
        wanted = list(symbols)
    elif key in BENCHMARK_GROUP_KEYS:
        wanted = list(benchmark_symbols())
    elif key in DERIVATIVE_GROUP_KEYS:
        wanted = list(derivative_symbols())
    else:
        wanted = resolve_universe(universe)

    asked_for_basket = symbols is None and (
        not key or key in ("disk", "available") or key in GROUP_FILES
    )
    if asked_for_basket:
        ride_along = []
        if include_benchmarks:
            ride_along += list(benchmark_symbols())
        if include_derivatives:
            ride_along += list(derivative_symbols())
        wanted += [s for s in ride_along if s not in wanted]
    result.requested = len(wanted)
    if not wanted:
        result.fatal = (
            f"Không có mã nào để cập nhật ({universe!r}). "
            "Dùng list_symbols để xem các mã có dữ liệu."
        )
        return result

    try:
        headers = {"Authorization": f"Bearer {load_bearer_token()}",
                   "Accept": "application/json"}
    except RuntimeError as exc:
        result.fatal = (
            f"{exc} Đặt biến môi trường {TOKEN_ENV_VAR} hoặc ghi token vào access_token.txt."
        )
        return result

    today = date.today()
    ipos = _ipo_dates()

    def _work(symbol: str) -> SymbolUpdate:
        try:
            return _update_one(symbol, mode, months, today, ipos, headers, timeout)
        except Exception as exc:                       # belt and braces
            return SymbolUpdate(symbol=symbol, error=f"{type(exc).__name__}: {exc}")

    with ThreadPoolExecutor(max_workers=max(1, max_workers)) as pool:
        result.results = list(pool.map(_work, wanted))

    # Newly written files are invisible to readers until the caches are dropped.
    clear_cache()

    from src.ta.loader import latest_date
    for item in result.results:
        if item.error is None:
            item.after = latest_date(item.symbol)

    result.duration_s = round(time.time() - started, 1)
    return result
