from __future__ import annotations

import sys
import unittest
from datetime import UTC, date
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import fetch_data


class BitcoinChangeFieldsTests(unittest.TestCase):
    def test_uses_latest_utc_daily_open_and_current_market_price(self) -> None:
        bars = [
            {
                "date": date(2026, 7, 16),
                "open": 63_789.28,
                "close": 63_888.20,
            },
            {
                "date": date(2026, 7, 18),
                "open": 63_888.20,
                "close": 1.0,
            }
        ]

        result = fetch_data.bitcoin_change_fields(
            bars, current=63_861.86, current_utc_date=date(2026, 7, 18)
        )

        self.assertEqual(result["open"], 63_888.20)
        self.assertEqual(result["current"], 63_861.86)
        self.assertAlmostEqual(result["change"], -26.34)
        self.assertAlmostEqual(result["change_pct"], -26.34 / 63_888.20 * 100)

    def test_rejects_a_stale_daily_open(self) -> None:
        stale_bars = [{"date": date(2026, 7, 17), "open": 63_000.0}]

        with self.assertRaisesRegex(
            fetch_data.DataUnavailable, "current UTC date 2026-07-18"
        ):
            fetch_data.bitcoin_change_fields(
                stale_bars,
                current=63_861.86,
                current_utc_date=date(2026, 7, 18),
            )


class DailyBarTimezoneTests(unittest.TestCase):
    @patch("fetch_data.get_json")
    def test_bitcoin_midnight_timestamp_keeps_utc_date(self, get_json) -> None:
        get_json.return_value = {
            "chart": {
                "result": [
                    {
                        "timestamp": [1_768_521_600],
                        "indicators": {
                            "quote": [{"open": [63_888.20], "close": [63_861.86]}]
                        },
                    }
                ],
                "error": None,
            }
        }

        utc_bars = fetch_data.fetch_daily_bars("BTC-USD", UTC)
        new_york_bars = fetch_data.fetch_daily_bars("BTC-USD")

        self.assertEqual(utc_bars[0]["date"], date(2026, 1, 16))
        self.assertEqual(new_york_bars[0]["date"], date(2026, 1, 15))

    @patch("fetch_data.get_json")
    def test_bitcoin_keeps_current_open_when_close_is_null(self, get_json) -> None:
        get_json.return_value = {
            "chart": {
                "result": [
                    {
                        "timestamp": [1_768_435_200, 1_768_521_600],
                        "indicators": {
                            "quote": [
                                {
                                    "open": [63_000.0, 63_888.20],
                                    "close": [63_700.0, None],
                                }
                            ]
                        },
                    }
                ],
                "error": None,
            }
        }

        bars = fetch_data.fetch_daily_bars("BTC-USD", UTC, require_close=False)
        result = fetch_data.bitcoin_change_fields(
            bars,
            current=63_861.86,
            current_utc_date=date(2026, 1, 16),
        )

        self.assertEqual(len(bars), 2)
        self.assertNotIn("close", bars[-1])
        self.assertEqual(result["open"], 63_888.20)
        self.assertAlmostEqual(result["change"], -26.34)

    @patch("fetch_data.get_json")
    def test_bitcoin_rejects_non_finite_open(self, get_json) -> None:
        get_json.return_value = {
            "chart": {
                "result": [
                    {
                        "timestamp": [1_768_521_600],
                        "indicators": {"quote": [{"open": [float("nan")]}]},
                    }
                ],
                "error": None,
            }
        }

        with self.assertRaisesRegex(fetch_data.DataUnavailable, "no usable daily bars"):
            fetch_data.fetch_daily_bars("BTC-USD", UTC, require_close=False)


if __name__ == "__main__":
    unittest.main()
