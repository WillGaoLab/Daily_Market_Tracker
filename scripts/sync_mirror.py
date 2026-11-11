"""Copy one canonical observation and its exact figures without rewriting history."""

from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

from fetch_data import business_today, is_us_market_holiday
from history import append_record, read_history, validate_record


def sync(source: Path, destination: Path, target_date: date, verify_only: bool = False) -> dict:
    day = target_date.isoformat()
    rows = read_history(source / "data/history.csv")
    matches = [row for row in rows if row["date"] == day]
    if len(matches) != 1:
        raise ValueError(f"Canonical source must contain exactly one {day} row.")
    record = matches[0]
    validate_record(record)
    assets = {suffix: (source / "figures" / f"{day}.{suffix}").read_bytes() for suffix in ("png", "svg")}
    if not assets["png"].startswith(b"\x89PNG\r\n\x1a\n") or b"<svg" not in assets["svg"][:4096]:
        raise ValueError("Canonical figures are not valid PNG/SVG files.")
    if verify_only:
        return {"date": day, "status": "source_verified"}
    if source.resolve() == destination.resolve():
        raise ValueError("Source and mirror directories must differ.")
    existing = next((r for r in read_history(destination / "data/history.csv") if r["date"] == day), None)
    if existing and existing != record:
        raise ValueError(f"Mirror has a different {day} row; refusing to overwrite historical data.")
    # Validate everything before modifying files; only this date is ever staged.
    (destination / "figures").mkdir(parents=True, exist_ok=True)
    for suffix, content in assets.items():
        path = destination / "figures" / f"{day}.{suffix}"
        if not path.exists() or path.read_bytes() != content:
            path.write_bytes(content)
    if not existing:
        append_record(destination / "data/history.csv", record)
    return {"date": day, "status": "mirrored" if not existing else "verified_or_repaired"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--destination-root", type=Path, required=True)
    parser.add_argument("--date", type=date.fromisoformat, default=business_today())
    parser.add_argument("--verify-source-only", action="store_true")
    args = parser.parse_args()
    if args.date.weekday() >= 5 or is_us_market_holiday(args.date):
        print({"date": args.date.isoformat(), "status": "market_closed"})
    else:
        print(sync(args.source_root, args.destination_root, args.date, args.verify_source_only))
