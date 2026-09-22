import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from src.ta import loader


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


class CoverageTest(unittest.TestCase):
    """coverage() must skip empty year folders, not bail out on them.

    The fetcher writes one file per calendar month regardless of whether
    FireAnt returned rows, so a symbol listed after 2010 has an oldest year
    folder made entirely of ``[]`` files (pre-listing months).
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.data = Path(self._tmp.name)
        self._patch = mock.patch.object(loader, "DATA_DIR", self.data)
        self._patch.start()
        loader.clear_cache()

    def tearDown(self):
        self._patch.stop()
        loader.clear_cache()
        self._tmp.cleanup()

    def _write(self, symbol: str, year: int, month: int, items: list) -> None:
        path = self.data / symbol / str(year) / f"{year:04d}-{month:02d}-01.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(items), encoding="utf-8")

    def test_skips_empty_oldest_year_to_find_the_real_first_bar(self):
        # 2010: every month pre-dates listing, so every file is `[]`.
        for month in range(1, 13):
            self._write("TST", 2010, month, [])
        # 2011: the symbol actually lists partway through the year.
        self._write("TST", 2011, 6, [])
        self._write("TST", 2011, 7, [_quote("2011-07-04"), _quote("2011-07-05")])
        self._write("TST", 2012, 1, [_quote("2012-01-03")])

        result = loader.coverage("TST")

        self.assertIsNotNone(result)
        first, last, bars = result
        self.assertEqual(first, "2011-07-04")
        self.assertEqual(last, "2012-01-03")
        self.assertEqual(bars, 3)

    def test_all_years_empty_returns_none(self):
        for month in range(1, 13):
            self._write("TST", 2010, month, [])

        self.assertIsNone(loader.coverage("TST"))

    def test_no_year_folders_returns_none(self):
        (self.data / "TST").mkdir(parents=True)

        self.assertIsNone(loader.coverage("TST"))


if __name__ == "__main__":
    unittest.main()


class SignatureTest(unittest.TestCase):
    """The cache stamp has to separate two writes inside one mtime tick.

    On this filesystem ``st_mtime_ns`` moves in ~0.5 ms steps, so two writes to
    the same file back to back carry the *same* mtime roughly 70% of the time.
    With only ``(file count, newest mtime)`` in the stamp, a monthly refetch
    that lands in the same tick as the previous write is invisible and the
    cache keeps serving the older parse. File size is read from the same
    ``stat()`` call and separates the two whenever the content changed length —
    which is what appending a session does.
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.data = Path(self._tmp.name)
        self._patch = mock.patch.object(loader, "DATA_DIR", self.data)
        self._patch.start()
        loader.clear_cache()

    def tearDown(self):
        self._patch.stop()
        loader.clear_cache()
        self._tmp.cleanup()

    def _write(self, items: list) -> None:
        path = self.data / "TST" / "2026" / "2026-08-01.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(items), encoding="utf-8")

    def test_appending_a_session_changes_the_stamp_even_within_one_tick(self):
        self._write([_quote("2026-08-03")])
        before = loader._year_signature("TST", 2026)
        self._write([_quote("2026-08-03"), _quote("2026-08-04")])
        after = loader._year_signature("TST", 2026)

        self.assertNotEqual(before, after)
        # Named explicitly: the point is that this holds even when mtime did
        # not move, which is the case the count-and-mtime stamp missed.
        if before[1] == after[1]:
            self.assertNotEqual(before[2], after[2])

    def test_an_untouched_folder_keeps_the_same_stamp(self):
        self._write([_quote("2026-08-03")])
        self.assertEqual(loader._year_signature("TST", 2026),
                         loader._year_signature("TST", 2026))

    def test_a_missing_folder_has_an_empty_stamp(self):
        self.assertEqual(loader._year_signature("NOPE", 2026), (0, 0, 0))


class BenchmarkExclusionTest(unittest.TestCase):
    """VNINDEX lives in data/ but must never be handed out as a stock.

    FireAnt returns the index with the *same* schema as a symbol, so nothing
    downstream would notice the difference — a scan would happily rank the
    whole market against its own constituents. The separation has to happen
    here, at the one place that decides what a universe contains.
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        root = Path(self._tmp.name)
        self.data = root / "data"
        self.lists = root / "stock_list"
        self.lists.mkdir(parents=True)

        self._patches = [
            mock.patch.object(loader, "DATA_DIR", self.data),
            mock.patch.object(loader, "STOCK_LIST_DIR", self.lists),
        ]
        for p in self._patches:
            p.start()
        loader.clear_cache()

        for symbol in ("AAA", "BBB", "VNINDEX"):
            self._write_bars(symbol)
        (self.lists / "list_all_stock.json").write_text(
            json.dumps([{"share_code": s} for s in ("AAA", "BBB", "VNINDEX")]),
            encoding="utf-8",
        )
        (self.lists / "benchmarks.json").write_text(
            json.dumps([{"share_code": "VNINDEX", "kind": "index"}]),
            encoding="utf-8",
        )

    def tearDown(self):
        for p in self._patches:
            p.stop()
        loader.clear_cache()
        self._tmp.cleanup()

    def _write_bars(self, symbol: str) -> None:
        path = self.data / symbol / "2026" / "2026-01-01.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps([_quote("2026-01-05")]), encoding="utf-8")

    def test_default_universe_drops_the_benchmark(self):
        self.assertEqual(loader.resolve_universe(), ["AAA", "BBB"])
        self.assertEqual(loader.resolve_universe("disk"), ["AAA", "BBB"])

    def test_named_group_drops_it_even_when_the_file_lists_it(self):
        # list_all_stock.json deliberately contains VNINDEX here: a stale entry
        # in a basket file must not be enough to put the index into a scan.
        self.assertEqual(loader.resolve_universe("all"), ["AAA", "BBB"])

    def test_asking_for_it_by_name_still_works(self):
        self.assertEqual(loader.resolve_universe("VNINDEX"), ["VNINDEX"])
        self.assertEqual(loader.resolve_universe("AAA,VNINDEX"), ["AAA", "VNINDEX"])

    def test_benchmark_group_returns_only_benchmarks(self):
        for key in ("benchmarks", "benchmark", "index"):
            self.assertEqual(loader.resolve_universe(key), ["VNINDEX"], key)

    def test_is_benchmark_is_case_insensitive(self):
        self.assertTrue(loader.is_benchmark("vnindex"))
        self.assertTrue(loader.is_benchmark(" VNINDEX "))
        self.assertFalse(loader.is_benchmark("AAA"))

    def test_missing_registry_leaves_every_symbol_available(self):
        (self.lists / "benchmarks.json").unlink()
        loader.clear_cache()
        self.assertEqual(loader.benchmark_symbols(), ())
        self.assertEqual(loader.resolve_universe(), ["AAA", "BBB", "VNINDEX"])
