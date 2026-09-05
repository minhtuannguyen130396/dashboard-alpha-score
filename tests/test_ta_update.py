import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

import requests

from src.ta import loader, update as up
from src.ta.update import MODES, SymbolUpdate, UpdateResult, update_prices


def _quote(day: str, close: float = 20.0) -> dict:
    """A FireAnt historical-quote item, trimmed to the fields the loader reads."""
    return {
        "date": f"{day}T00:00:00", "symbol": "TST",
        "priceHigh": close + 0.5, "priceLow": close - 0.5, "priceOpen": close,
        "priceAverage": close, "priceClose": close, "priceBasic": close,
        "totalVolume": 1000.0, "dealVolume": 1000.0, "putthroughVolume": 0.0,
        "totalValue": 0.0, "putthroughValue": 0.0,
        "buyForeignQuantity": 0.0, "buyForeignValue": 0.0,
        "sellForeignQuantity": 0.0, "sellForeignValue": 0.0,
        "buyCount": 0.0, "buyQuantity": 0.0, "sellCount": 0.0, "sellQuantity": 0.0,
        "adjRatio": 1.0, "currentForeignRoom": 0.0, "unit": 1.0,
    }


class _Response:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code}")

    def json(self):
        return self._payload


class WindowTest(unittest.TestCase):
    def test_one_window_per_calendar_month_clamped_to_the_end(self):
        windows = up._month_windows(date(2026, 6, 15), date(2026, 8, 24))
        self.assertEqual(windows, [
            (date(2026, 6, 15), date(2026, 6, 30)),
            (date(2026, 7, 1), date(2026, 7, 31)),
            (date(2026, 8, 1), date(2026, 8, 24)),
        ])

    def test_a_single_month_is_one_window(self):
        self.assertEqual(
            up._month_windows(date(2026, 8, 1), date(2026, 8, 24)),
            [(date(2026, 8, 1), date(2026, 8, 24))],
        )


class ModeTest(unittest.TestCase):
    TODAY = date(2026, 8, 24)
    IPOS = {"TST": date(2010, 1, 1)}

    def _start(self, mode, months=None):
        return up._resolve_start(mode, "TST", self.TODAY, self.IPOS, months)

    def test_latest_covers_only_the_current_month(self):
        self.assertEqual(self._start("latest"), date(2026, 8, 1))

    def test_recent_reaches_back_one_month(self):
        self.assertEqual(self._start("recent"), date(2026, 7, 1))

    def test_quarter_reaches_back_three_months(self):
        self.assertEqual(self._start("quarter"), date(2026, 5, 1))

    def test_full_starts_at_the_configured_epoch(self):
        self.assertEqual(self._start("full"), date(2010, 1, 1))

    def test_a_late_listing_clamps_the_start(self):
        start = up._resolve_start("full", "NEW", self.TODAY, {"NEW": date(2024, 6, 5)}, None)
        self.assertEqual(start, date(2024, 6, 5))

    def test_explicit_months_overrides_the_mode(self):
        self.assertEqual(self._start("latest", months=3), date(2026, 6, 1))

    def test_an_unknown_mode_is_rejected(self):
        with self.assertRaises(ValueError):
            update_prices(symbols=["TST"], mode="yesterday")


class FetchTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.data = Path(self._tmp.name)
        self._patches = [
            mock.patch.object(up, "DATA_DIR", self.data),
            mock.patch.object(loader, "DATA_DIR", self.data),
            mock.patch.object(up, "load_bearer_token", lambda: "fake-token"),
            mock.patch.object(up, "_ipo_dates", lambda: {"TST": date(2010, 1, 1)}),
        ]
        for p in self._patches:
            p.start()
        loader.clear_cache()

    def tearDown(self):
        for p in self._patches:
            p.stop()
        loader.clear_cache()
        self._tmp.cleanup()

    def _month_file(self, symbol="TST") -> Path:
        today = date.today()
        return self.data / symbol / str(today.year) / f"{today.replace(day=1)}.json"

    def _seed(self, items, symbol="TST"):
        path = self._month_file(symbol)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(items), encoding="utf-8")
        return path

    def test_new_bars_are_written_and_counted(self):
        today = date.today()
        payload = [_quote(f"{today.replace(day=1)}"), _quote(f"{today}")]
        with mock.patch.object(up.requests, "get", return_value=_Response(payload)):
            result = update_prices(symbols=["TST"], mode="latest")
        entry = result.results[0]
        self.assertIsNone(entry.error)
        self.assertEqual(entry.new_bars, 2)
        self.assertEqual(entry.files_written, 1)
        self.assertEqual(json.loads(self._month_file().read_text(encoding="utf-8")), payload)

    def test_an_empty_response_never_clobbers_existing_bars(self):
        today = date.today()
        seeded = [_quote(f"{today.replace(day=1)}")]
        path = self._seed(seeded)
        with mock.patch.object(up.requests, "get", return_value=_Response([])):
            result = update_prices(symbols=["TST"], mode="latest")
        entry = result.results[0]
        self.assertEqual(json.loads(path.read_text(encoding="utf-8")), seeded,
                         "existing bars must survive an empty API answer")
        self.assertEqual(entry.files_written, 0)
        self.assertTrue(entry.warnings)

    def test_new_bars_count_only_the_increment(self):
        today = date.today()
        self._seed([_quote(f"{today.replace(day=1)}")])
        payload = [_quote(f"{today.replace(day=1)}"), _quote(f"{today}")]
        with mock.patch.object(up.requests, "get", return_value=_Response(payload)):
            result = update_prices(symbols=["TST"], mode="latest")
        self.assertEqual(result.results[0].new_bars, 1)

    def test_one_failing_symbol_does_not_stop_the_others(self):
        today = date.today()
        good = [_quote(f"{today}")]

        def _fake_get(url, **kwargs):
            return _Response(good) if "GOOD" in url else _Response(None, status_code=403)

        with mock.patch.object(up.requests, "get", side_effect=_fake_get):
            result = update_prices(symbols=["GOOD", "BAD"], mode="latest")
        self.assertEqual(len(result.results), 2)
        self.assertEqual(len(result.failed), 1)
        self.assertEqual(result.failed[0].symbol, "BAD")
        self.assertIn("403", result.failed[0].error)

    def test_reads_see_the_new_data_without_a_restart(self):
        today = date.today()
        # Warm the cache on an empty directory first — this is the stale-read trap.
        self.assertEqual(loader.load_recent("TST", 60), [])
        payload = [_quote(f"{today}", close=33.0)]
        with mock.patch.object(up.requests, "get", return_value=_Response(payload)):
            update_prices(symbols=["TST"], mode="latest")
        records = loader.load_recent("TST", 60)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].priceClose, 33.0)

    def test_a_write_by_another_process_is_picked_up_without_clearing(self):
        """The tkinter app writes in its own process and cannot clear our cache.

        So the cache must revalidate itself against the files on disk — this is
        the case that used to serve yesterday's close all session long.
        """
        today = date.today()
        self._seed([_quote(f"{today.replace(day=1)}", close=10.0)])
        self.assertEqual([r.priceClose for r in loader.load_recent("TST", 60)], [10.0])

        # Simulate the other process: overwrite the month file in place.
        # No clear_cache() call anywhere.
        self._seed([_quote(f"{today.replace(day=1)}", close=10.0),
                    _quote(f"{today}", close=11.0)])
        self.assertEqual([r.priceClose for r in loader.load_recent("TST", 60)],
                         [10.0, 11.0])

    def test_rewriting_the_same_bars_still_reads_correctly(self):
        today = date.today()
        bars = [_quote(f"{today}", close=12.0)]
        self._seed(bars)
        first = loader.load_recent("TST", 60)
        self._seed(bars)                      # identical content, new mtime
        second = loader.load_recent("TST", 60)
        self.assertEqual([r.priceClose for r in first], [r.priceClose for r in second])

    def test_a_retryable_status_is_retried_then_succeeds(self):
        today = date.today()
        responses = [_Response(None, 429), _Response([_quote(f"{today}")])]
        with mock.patch.object(up.requests, "get", side_effect=responses), \
                mock.patch.object(up.time, "sleep", lambda _s: None):
            result = update_prices(symbols=["TST"], mode="latest")
        self.assertIsNone(result.results[0].error)
        self.assertEqual(result.results[0].new_bars, 1)


class TokenTest(unittest.TestCase):
    def test_a_missing_token_is_reported_not_raised(self):
        def _boom():
            raise RuntimeError("Missing FireAnt token.")

        with mock.patch.object(up, "load_bearer_token", _boom):
            result = update_prices(symbols=["TST"], mode="latest")
        self.assertIsNotNone(result.fatal)
        self.assertIn("FIREANT_BEARER_TOKEN", result.fatal)
        self.assertEqual(result.results, [])

    def test_an_empty_universe_is_reported_not_raised(self):
        result = update_prices(universe="NOSUCHTICKER", mode="latest")
        self.assertIsNotNone(result.fatal)
        self.assertEqual(result.results, [])


class ResultShapeTest(unittest.TestCase):
    def test_buckets_partition_the_results(self):
        result = UpdateResult(mode="latest", started="now", results=[
            SymbolUpdate("A", before="2026-08-21", after="2026-08-24", new_bars=1),
            SymbolUpdate("B", before="2026-08-24", after="2026-08-24"),
            SymbolUpdate("C", error="HTTPError: 500"),
        ])
        self.assertEqual([r.symbol for r in result.changed], ["A"])
        self.assertEqual([r.symbol for r in result.unchanged], ["B"])
        self.assertEqual([r.symbol for r in result.failed], ["C"])
        self.assertEqual(result.new_bars, 1)
        self.assertEqual(result.latest_date, "2026-08-24")

    def test_a_hole_left_by_a_narrow_mode_is_flagged(self):
        result = UpdateResult(mode="latest", started="now", results=[
            # Last bar in April, but `latest` only asked for August.
            SymbolUpdate("STALE", before="2026-04-07", fetch_from="2026-08-01",
                         after="2026-08-24", new_bars=16),
            SymbolUpdate("FRESH", before="2026-08-21", fetch_from="2026-08-01",
                         after="2026-08-24", new_bars=1),
        ])
        self.assertEqual([r.symbol for r in result.gaps], ["STALE"])
        self.assertGreater(result.gaps[0].gap_days, 100)

    def test_no_gap_when_the_fetch_window_covers_the_last_bar(self):
        entry = SymbolUpdate("A", before="2026-08-21", fetch_from="2026-08-01")
        self.assertEqual(entry.gap_days, 0)

    def test_a_first_ever_download_is_not_a_gap(self):
        entry = SymbolUpdate("NEW", before=None, fetch_from="2026-08-01")
        self.assertEqual(entry.gap_days, 0)

    def test_every_mode_has_a_vietnamese_label(self):
        for mode in MODES:
            self.assertIn(mode, up.MODE_VN)


if __name__ == "__main__":
    unittest.main()


class BenchmarkRideAlongTest(unittest.TestCase):
    """A basket update refreshes VNINDEX; a named request does not.

    ``resolve_universe`` keeps the index out of every group, which is right for
    scanning and wrong for fetching: left to that rule alone the daily update
    would never touch VNINDEX, and it would go stale without anyone noticing
    until something tried to measure a stock against it.
    """

    def setUp(self):
        self._patches = [
            mock.patch.object(up, "load_bearer_token", lambda: "fake-token"),
            mock.patch.object(up, "benchmark_symbols", lambda: ("VNINDEX",)),
            mock.patch.object(up, "_ipo_dates", lambda: {}),
        ]
        for p in self._patches:
            p.start()

    def tearDown(self):
        for p in self._patches:
            p.stop()

    def _fetched(self, **kwargs) -> list:
        """Symbols an update actually asked the API for."""
        seen = []
        with mock.patch.object(up, "resolve_universe", lambda _s=None: ["AAA", "BBB"]), \
                mock.patch.object(up, "_update_one",
                                  lambda sym, *a, **k: seen.append(sym) or SymbolUpdate(symbol=sym)), \
                mock.patch.object(up, "latest_date", lambda _s: None, create=True):
            update_prices(**kwargs)
        return seen

    def test_a_basket_update_includes_the_benchmark(self):
        for universe in (None, "disk", "all", "vn30"):
            self.assertIn("VNINDEX", self._fetched(universe=universe), universe)

    def test_named_symbols_stay_exactly_what_was_asked(self):
        self.assertEqual(self._fetched(symbols=["FPT"]), ["FPT"])
        self.assertEqual(self._fetched(universe="AAA,BBB"), ["AAA", "BBB"])

    def test_it_can_be_turned_off(self):
        self.assertNotIn("VNINDEX", self._fetched(include_benchmarks=False))

    def test_the_benchmark_is_never_fetched_twice(self):
        with mock.patch.object(up, "resolve_universe", lambda _s=None: ["AAA", "VNINDEX"]):
            seen = []
            with mock.patch.object(up, "_update_one",
                                   lambda sym, *a, **k: seen.append(sym) or SymbolUpdate(symbol=sym)), \
                    mock.patch.object(up, "latest_date", lambda _s: None, create=True):
                update_prices(universe="all")
            self.assertEqual(seen.count("VNINDEX"), 1)
