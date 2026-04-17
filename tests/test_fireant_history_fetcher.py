import json
import os
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from src.data.fireant_history_fetcher import _fetch_single_stock_history


class _DummyResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self):
        return self._payload


class FireantHistoryFetcherTest(unittest.TestCase):
    def test_fetch_single_stock_history_for_dxg_from_start_uses_2010_floor_and_writes_file(self) -> None:
        stock = {"share_code": "DXG", "ipo_date": "2009-12-14"}
        today = date(2010, 1, 15)
        payload = [{"symbol": "DXG", "date": "2010-01-15T00:00:00", "priceClose": 42.0}]
        request_calls: list[dict] = []

        def _fake_get(url, headers, params, timeout):
            request_calls.append(
                {
                    "url": url,
                    "headers": headers,
                    "params": params,
                    "timeout": timeout,
                }
            )
            return _DummyResponse(payload)

        with tempfile.TemporaryDirectory() as temp_dir:
            old_cwd = os.getcwd()
            try:
                os.chdir(temp_dir)
                with patch("src.data.fireant_history_fetcher.requests.get", side_effect=_fake_get):
                    symbol = _fetch_single_stock_history(
                        stock=stock,
                        update_mode="from_start",
                        today=today,
                        headers={"Authorization": "Bearer fake-token"},
                    )
            finally:
                os.chdir(old_cwd)

            output_file = Path(temp_dir) / "data" / "DXG" / "2010" / "2010-01-01.json"
            self.assertTrue(output_file.exists())
            self.assertEqual(json.loads(output_file.read_text(encoding="utf-8")), payload)

        self.assertEqual(symbol, "DXG")
        self.assertEqual(len(request_calls), 1)
        self.assertEqual(
            request_calls[0]["url"],
            "https://restv2.fireant.vn/symbols/DXG/historical-quotes",
        )
        self.assertEqual(request_calls[0]["params"]["startDate"], "2010-01-01")
        self.assertEqual(request_calls[0]["params"]["endDate"], "2010-01-15")
        self.assertEqual(request_calls[0]["params"]["limit"], 15)
        self.assertEqual(request_calls[0]["headers"]["Authorization"], "Bearer fake-token")
        self.assertEqual(request_calls[0]["timeout"], 30)


if __name__ == "__main__":
    unittest.main()
