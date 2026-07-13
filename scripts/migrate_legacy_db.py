"""One-time migration from the tracked SQLite database to CSV snapshots."""

from __future__ import annotations

import argparse
import sqlite3
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from .dataset import PriceDataset


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATABASE = PROJECT_ROOT / "data" / "wisarra" / "prices.db"
DEFAULT_SNAPSHOTS = PROJECT_ROOT / "data" / "wisarra" / "snapshots"


def migrate_database(database_path: Path, dataset: PriceDataset) -> list[Path]:
    """Export every legacy scrape timestamp to one immutable snapshot."""
    database_path = Path(database_path).resolve()
    connection = sqlite3.connect(f"file:{database_path}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        rows = connection.execute(
            """SELECT name, location, marketplace, min_price, max_price,
                      currency, quantity, unit, scraped_at
               FROM prices
               ORDER BY scraped_at, name, location, marketplace, quantity, unit"""
        ).fetchall()
    finally:
        connection.close()

    batches: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        batches[row["scraped_at"]].append(dict(row))

    snapshots = []
    for timestamp in sorted(batches):
        observed_at = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        snapshots.append(dataset.record(batches[timestamp], observed_at))

    migrated_rows = len(dataset.load())
    if migrated_rows != len(rows):
        raise RuntimeError(f"Migration verification failed: expected {len(rows)} rows, found {migrated_rows}")
    return snapshots


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("database", nargs="?", type=Path, default=DEFAULT_DATABASE)
    parser.add_argument("--snapshots", type=Path, default=DEFAULT_SNAPSHOTS)
    args = parser.parse_args()

    snapshots = migrate_database(args.database, PriceDataset(args.snapshots))
    print(f"Migrated {len(snapshots)} scrape batches to {args.snapshots}")


if __name__ == "__main__":
    main()
