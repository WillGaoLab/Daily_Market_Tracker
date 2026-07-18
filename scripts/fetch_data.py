"""Fetch one trading day's opening gaps from Yahoo Finance."""

from __future__ import annotations

import argparse
import json
import math
import time
from datetime import UTC, date, datetime, timedelta, tzinfo
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

TIMEZONE = ZoneInfo("America/New_York")
YAHOO_HOSTS = ("https://query1.finance.yahoo.com", "https://query2.finance.yahoo.com")

# key, display label, Yahoo Finance symbol
INSTRUMENTS = (
    ("sp500", "S&P 500", "^GSPC"),
    ("nasdaq100", "Nasdaq-100 Futures", "NQ=F"),
    ("dow", "Dow Jones Industrial Average", "^DJI"),
    ("vix", "VIX", "^VIX"),
    ("bitcoin", "Bitcoin", "BTC-USD"),
    ("gold", "Gold Futures", "GC=F"),
    ("tnx", "U.S. 10-Year Treasury Yield", "^TNX"),
    ("dxy", "U.S. Dollar Index", "DX-Y.NYB"),
    ("wti", "WTI Crude Oil", "CL=F"),
)


class DataUnavailable(RuntimeError):
    """Yahoo Finance did not return usable data."""


class MarketClosed(RuntimeError):
    """The requested date is not a U.S. equity trading day."""


def business_today() -> date:
    return datetime.now(TIMEZONE).date()


def _observed(day: date) -> date:
    if day.weekday() == 5:
        return day - timedelta(days=1)
    if day.weekday() == 6:
        return day + timedelta(days=1)
    return day


def _nth_weekday(year: int, month: int, weekday: int, occurrence: int) -> date:
    day = date(year, month, 1)
    return day + timedelta(days=(weekday - day.weekday()) % 7 + 7 * (occurrence - 1))


def _last_weekday(year: int, month: int, weekday: int) -> date:
    if month == 12:
        day = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        day = date(year, month + 1, 1) - timedelta(days=1)
    return day - timedelta(days=(day.weekday() - weekday) % 7)


def _easter_sunday(year: int) -> date:
    """Return Gregorian Easter using the Meeus/Jones/Butcher calculation."""
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = (h + l - 7 * m + 114) % 31 + 1
    return date(year, month, day)


def is_us_market_holiday(target_date: date) -> bool:
    """Return whether target_date is a regular NYSE full-day holiday.

    Rare one-off exchange closures are intentionally not guessed: Yahoo data
    must be present on any date not listed here.
    """
    year = target_date.year
    holidays = {
        _observed(date(year, 1, 1)),
        _nth_weekday(year, 1, 0, 3),
        _nth_weekday(year, 2, 0, 3),
        _easter_sunday(year) - timedelta(days=2),
        _last_weekday(year, 5, 0),
        _observed(date(year, 7, 4)),
        _nth_weekday(year, 9, 0, 1),
        _nth_weekday(year, 11, 3, 4),
        _observed(date(year, 12, 25)),
        _observed(date(year + 1, 1, 1)),
    }
    if year >= 2022:
        holidays.add(_observed(date(year, 6, 19)))
    return target_date in holidays


def get_json(url: str, attempts: int = 3, timeout: int = 20) -> dict:
    last_error: Exception | None = None
    for attempt in range(attempts):
        request = Request(url, headers={"User-Agent": "daily-market-tracker/1.0"})
        try:
            with urlopen(request, timeout=timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as error:
            last_error = error
            if attempt < attempts - 1:
                time.sleep(1.5 * (attempt + 1))
    raise DataUnavailable(f"Yahoo request failed: {last_error}") from last_error


def fetch_daily_bars(
    symbol: str, bar_timezone: tzinfo = TIMEZONE, require_close: bool = True
) -> list[dict[str, float | date]]:
    """Return recent Yahoo daily bars with dates interpreted in bar_timezone."""
    params = urlencode({"range": "10d", "interval": "1d", "includePrePost": "false"})
    path = f"/v8/finance/chart/{symbol}?{params}"
    payload: dict | None = None
    last_error: Exception | None = None
    for host in YAHOO_HOSTS:
        try:
            payload = get_json(f"{host}{path}")
            break
        except DataUnavailable as error:
            last_error = error
    if payload is None:
        raise DataUnavailable(f"Yahoo unavailable for {symbol}: {last_error}")

    chart = payload.get("chart") or {}
    if chart.get("error"):
        raise DataUnavailable(f"Yahoo error for {symbol}: {chart['error']}")
    results = chart.get("result") or []
    if not results:
        raise DataUnavailable(f"Yahoo returned no chart data for {symbol}.")

    result = results[0]
    quote = (result.get("indicators") or {}).get("quote") or []
    if not quote:
        raise DataUnavailable(f"Yahoo returned no price fields for {symbol}.")

    timestamps = result.get("timestamp") or []
    opens = quote[0].get("open") or []
    closes = quote[0].get("close") or []
    bars: list[dict[str, float | date]] = []
    if require_close:
        for timestamp, open_, close in zip(timestamps, opens, closes, strict=True):
            if open_ is None or close is None:
                continue
            bars.append(
                {
                    "date": datetime.fromtimestamp(timestamp, bar_timezone).date(),
                    "open": float(open_),
                    "close": float(close),
                }
            )
    else:
        for timestamp, open_ in zip(timestamps, opens, strict=True):
            if open_ is None:
                continue
            try:
                daily_open = float(open_)
            except (TypeError, ValueError):
                continue
            if not math.isfinite(daily_open) or daily_open <= 0:
                continue
            bars.append(
                {
                    "date": datetime.fromtimestamp(timestamp, bar_timezone).date(),
                    "open": daily_open,
                }
            )
    if not bars:
        raise DataUnavailable(f"Yahoo returned no usable daily bars for {symbol}.")
    return sorted(bars, key=lambda bar: bar["date"])


def fetch_current_price(symbol: str) -> float:
    """Return Yahoo Finance's current regular-market price for one symbol."""
    params = urlencode({"range": "1d", "interval": "1m", "includePrePost": "false"})
    path = f"/v8/finance/chart/{symbol}?{params}"
    payload: dict | None = None
    last_error: Exception | None = None
    for host in YAHOO_HOSTS:
        try:
            payload = get_json(f"{host}{path}")
            break
        except DataUnavailable as error:
            last_error = error
    if payload is None:
        raise DataUnavailable(f"Yahoo unavailable for {symbol}: {last_error}")

    chart = payload.get("chart") or {}
    if chart.get("error"):
        raise DataUnavailable(f"Yahoo error for {symbol}: {chart['error']}")
    results = chart.get("result") or []
    if not results:
        raise DataUnavailable(f"Yahoo returned no chart data for {symbol}.")

    try:
        current = float((results[0].get("meta") or {})["regularMarketPrice"])
    except (KeyError, TypeError, ValueError) as error:
        raise DataUnavailable(f"Yahoo returned no current market price for {symbol}.") from error
    if not math.isfinite(current):
        raise DataUnavailable(f"Yahoo returned a non-finite current market price for {symbol}.")
    return current


def gap_fields(bars: list[dict[str, float | date]], target_date: date) -> dict[str, float]:
    """Calculate an opening gap against the prior available daily close."""
    target_index = next(
        (index for index, bar in enumerate(bars) if bar["date"] == target_date), None
    )
    if target_index is None or target_index == 0:
        raise DataUnavailable(f"No daily open and prior close available for {target_date.isoformat()}.")
    previous_close = float(bars[target_index - 1]["close"])
    open_ = float(bars[target_index]["open"])
    gap = open_ - previous_close
    return {
        "previous_close": previous_close,
        "open": open_,
        "gap": gap,
        "gap_pct": gap / previous_close * 100,
    }


def bitcoin_change_fields(
    bars: list[dict[str, float | date]], current: float, current_utc_date: date | None = None
) -> dict[str, float]:
    """Calculate Bitcoin's change from the current UTC daily open to its current price."""
    current_utc_date = current_utc_date or datetime.now(UTC).date()
    current_bars = [bar for bar in bars if bar["date"] == current_utc_date]
    if not current_bars:
        raise DataUnavailable(
            f"No valid BTC daily open available for current UTC date "
            f"{current_utc_date.isoformat()}."
        )
    daily_open = float(current_bars[-1]["open"])
    change = current - daily_open
    return {
        "open": daily_open,
        "current": current,
        "change": change,
        "change_pct": change / daily_open * 100,
    }


def fetch_record(target_date: date) -> dict[str, str]:
    """Fetch nine instruments and return one history.csv-compatible row."""
    if target_date.weekday() >= 5:
        raise MarketClosed(f"{target_date.isoformat()} is a weekend.")
    if is_us_market_holiday(target_date):
        raise MarketClosed(f"{target_date.isoformat()} is a scheduled U.S. market holiday.")

    record = {"date": target_date.isoformat(), "source": "Yahoo Finance"}
    for key, label, symbol in INSTRUMENTS:
        bars = fetch_daily_bars(
            symbol,
            UTC if key == "bitcoin" else TIMEZONE,
            require_close=key != "bitcoin",
        )
        try:
            if key == "bitcoin":
                values = bitcoin_change_fields(bars, fetch_current_price(symbol))
            else:
                values = gap_fields(bars, target_date)
        except DataUnavailable as error:
            raise DataUnavailable(f"{label}: {error}") from error
        for field, value in values.items():
            record[f"{key}_{field}"] = f"{value:.6f}"
    return record


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fetch daily opening gaps and Bitcoin's UTC-open-to-current change."
    )
    parser.add_argument("--date", type=date.fromisoformat, default=business_today())
    args = parser.parse_args()
    print(json.dumps(fetch_record(args.date), indent=2))


if __name__ == "__main__":
    main()
