"""Run the idempotent Daily Market Tracker update."""

from __future__ import annotations

import csv
import logging
import argparse
from datetime import date
from pathlib import Path

from fetch_data import MarketClosed, business_today, fetch_record
from generate_fingerprint import generate
from interactive_fingerprint import export_svg
from history import HistoryValidationError, append_record, read_history

PROJECT_ROOT = Path(__file__).resolve().parents[1]
HISTORY_PATH = PROJECT_ROOT / "data" / "history.csv"


def main(target_date: date | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    target_date = target_date or business_today()
    date_text = target_date.isoformat()
    try:
        history = read_history(HISTORY_PATH)
    except HistoryValidationError as error:
        logging.error("Invalid data/history.csv: %s", error)
        return 1
    if any(row["date"] == date_text for row in history):
        logging.info("Skipping %s: record already exists in data/history.csv.", date_text)
        if not (PROJECT_ROOT / "figures" / f"{date_text}.svg").exists():
            try:
                export_svg(date_text)
            except ValueError as error:
                record = next(row for row in history if row["date"] == date_text)
                if "NA" not in record.values():
                    logging.error("Could not generate interactive fingerprint: %s", error)
                    return 1
                logging.warning("Interactive figure unavailable: %s", error)
        return 0

    try:
        record = fetch_record(target_date)
    except MarketClosed as error:
        logging.info("Skipping %s: %s", date_text, error)
        return 0
    except Exception as error:
        logging.exception("Could not fetch complete Yahoo Finance data: %s", error)
        return 1

    try:
        append_record(HISTORY_PATH, record)
        figure = generate(date_text)
        export_svg(date_text)
    except (HistoryValidationError, ValueError) as error:
        logging.error("Could not update history or generate fingerprint: %s", error)
        return 1
    logging.info("Added %s and wrote %s.", HISTORY_PATH, figure)
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fetch, store, and render one market day.")
    parser.add_argument("--date", type=date.fromisoformat, default=None, help="ISO date to backfill.")
    args = parser.parse_args()
    raise SystemExit(main(args.date))
