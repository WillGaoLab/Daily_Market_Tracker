"""Read, validate, and append the single Daily Market Tracker history file."""

from __future__ import annotations

import csv
import math
from datetime import date
from pathlib import Path

INSTRUMENT_KEYS = (
    "sp500",
    "nasdaq100",
    "dow",
    "vix",
    "bitcoin",
    "gold",
    "tnx",
    "dxy",
    "wti",
)
MISSING_VALUE = "NA"
FIELDNAMES = ["date", "source"]
for _key in INSTRUMENT_KEYS:
    if _key == "bitcoin":
        FIELDNAMES.extend(
            [
                "bitcoin_previous_close",
                "bitcoin_current",
                "bitcoin_change",
                "bitcoin_change_pct",
            ]
        )
    else:
        FIELDNAMES.extend(
            [
                f"{_key}_previous_close",
                f"{_key}_open",
                f"{_key}_gap",
                f"{_key}_gap_pct",
            ]
        )


class HistoryValidationError(ValueError):
    """history.csv does not match the expected schema or contains invalid data."""


def validate_record(
    row: dict[str, str], line_number: int | None = None, allow_missing: bool = False
) -> None:
    location = f" at row {line_number}" if line_number is not None else ""
    if list(row) != FIELDNAMES:
        raise HistoryValidationError(f"Unexpected history.csv fields{location}.")
    try:
        date.fromisoformat(row["date"])
    except (KeyError, TypeError, ValueError) as error:
        raise HistoryValidationError(f"Invalid ISO date{location}: {row.get('date')!r}") from error
    if not row["source"].strip():
        raise HistoryValidationError(f"Missing source{location}.")

    for field in FIELDNAMES[2:]:
        if row[field] == MISSING_VALUE:
            if allow_missing:
                continue
            raise HistoryValidationError(f"Missing {field}{location}.")
        try:
            value = float(row[field])
        except (KeyError, TypeError, ValueError) as error:
            raise HistoryValidationError(f"Invalid {field}{location}: {row.get(field)!r}") from error
        if not math.isfinite(value):
            raise HistoryValidationError(f"Non-finite {field}{location}.")


def read_history(path: Path) -> list[dict[str, str]]:
    """Return validated history rows, or an empty list before initialization."""
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != FIELDNAMES:
            raise HistoryValidationError("history.csv header does not match the required schema.")
        rows = list(reader)

    dates: set[str] = set()
    for line_number, row in enumerate(rows, start=2):
        validate_record(row, line_number, allow_missing=True)
        if row["date"] in dates:
            raise HistoryValidationError(f"Duplicate date in history.csv: {row['date']}")
        dates.add(row["date"])
    return rows


def append_record(path: Path, record: dict[str, str]) -> None:
    """Validate and append one unique record without rewriting prior history."""
    rows = read_history(path)
    validate_record(record)
    if any(row["date"] == record["date"] for row in rows):
        raise HistoryValidationError(f"Date already exists in history.csv: {record['date']}")

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDNAMES, lineterminator="\n")
        if not rows:
            writer.writeheader()
        writer.writerow(record)
