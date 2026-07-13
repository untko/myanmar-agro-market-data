"""Upgrade legacy price snapshots to the multi-source provenance schema."""

from __future__ import annotations

import argparse
import csv
import os
import tempfile
from datetime import datetime
from pathlib import Path

from .dataset import PriceDataset, SNAPSHOT_COLUMNS


LEGACY_COLUMNS = (
    "name",
    "location",
    "marketplace",
    "min_price",
    "max_price",
    "currency",
    "quantity",
    "unit",
    "scraped_at",
    "source_url",
)


def migrate_snapshot(snapshot_path: Path, *, source: str, market_chain_level: str) -> bool:
    """Upgrade one v1 snapshot in place; return False when it is already current."""
    snapshot_path = Path(snapshot_path)
    with snapshot_path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        columns = tuple(reader.fieldnames or ())
        rows = list(reader)

    if columns == SNAPSHOT_COLUMNS:
        return False
    if columns != LEGACY_COLUMNS:
        raise ValueError(f"Snapshot {snapshot_path} does not match the legacy or current CSV columns")
    if not rows:
        raise ValueError(f"Snapshot {snapshot_path} is empty")

    timestamps = {row["scraped_at"] for row in rows}
    if len(timestamps) != 1:
        raise ValueError(f"Legacy snapshot {snapshot_path} contains multiple scrape timestamps")
    timestamp = timestamps.pop()
    collected_at = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    migrated_rows = [
        {
            "source": source,
            "source_record_id": "",
            "name": row["name"],
            "location": row["location"],
            "marketplace": row["marketplace"],
            "market_chain_level": market_chain_level,
            "min_price": row["min_price"],
            "max_price": row["max_price"],
            "modal_price": "",
            "currency": row["currency"],
            "quantity": row["quantity"],
            "unit": row["unit"],
            "observed_at": timestamp,
            "source_url": row["source_url"],
        }
        for row in rows
    ]

    with tempfile.TemporaryDirectory() as temp_dir:
        validation_dataset = PriceDataset(Path(temp_dir))
        generated = validation_dataset.record(migrated_rows, collected_at)
        if len(validation_dataset.load()) != len(rows):
            raise RuntimeError(f"Migration verification failed for {snapshot_path}")
        contents = generated.read_text(encoding="utf-8")
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=snapshot_path.parent,
            prefix=f".{snapshot_path.name}.migration-",
            delete=False,
        ) as handle:
            handle.write(contents)
            handle.flush()
            os.fsync(handle.fileno())
            temporary_path = Path(handle.name)
        temporary_path.replace(snapshot_path)
    finally:
        if temporary_path and temporary_path.exists():
            temporary_path.unlink()
    return True


def migrate_directory(snapshots_dir: Path, *, source: str, market_chain_level: str) -> list[Path]:
    migrated = []
    for snapshot_path in sorted(Path(snapshots_dir).glob("*/*.csv")):
        if migrate_snapshot(snapshot_path, source=source, market_chain_level=market_chain_level):
            migrated.append(snapshot_path)
    return migrated


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshots", type=Path)
    parser.add_argument("--source", required=True)
    parser.add_argument("--market-chain-level", required=True)
    args = parser.parse_args()
    migrated = migrate_directory(
        args.snapshots,
        source=args.source,
        market_chain_level=args.market_chain_level,
    )
    print(f"Migrated {len(migrated)} snapshots")


if __name__ == "__main__":
    main()
