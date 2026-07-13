"""Scrape Wisarra, record an immutable snapshot, and build analysis artifacts."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Mapping

from .analyze import CHARTS_DIR, REPORTS_DIR, SNAPSHOTS_DIR, generate_charts, generate_report
from .dataset import PriceDataset
from .scrape_wisarra import scrape_all


def run_pipeline(
    dataset: PriceDataset,
    rows: Iterable[Mapping[str, object]] | None,
    *,
    observed_at: datetime | None = None,
    reports_dir: Path = REPORTS_DIR,
    charts_dir: Path = CHARTS_DIR,
) -> dict[str, object]:
    """Record an optional scrape batch and build all derived artifacts."""
    snapshot_path = None
    if rows is not None:
        snapshot_path = dataset.record(rows, observed_at)

    series = dataset.weekly_series()
    if not series:
        raise RuntimeError("No snapshots are available for analysis")
    stats = generate_report(series, reports_dir)
    chart_count = generate_charts(series, charts_dir)
    return {
        "snapshot": str(snapshot_path) if snapshot_path else None,
        "stats": stats,
        "charts_generated": chart_count,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-scrape", action="store_true", help="Rebuild artifacts from existing snapshots")
    args = parser.parse_args()

    rows = None
    observed_at = None
    if not args.skip_scrape:
        print("Scraping wisarra.com...", file=sys.stderr)
        rows = scrape_all()
        observed_at = datetime.now(timezone.utc)
        print(f"  Scraped {len(rows)} rows", file=sys.stderr)
    else:
        print("Skipping scrape; rebuilding from committed snapshots", file=sys.stderr)

    result = run_pipeline(
        PriceDataset(SNAPSHOTS_DIR),
        rows,
        observed_at=observed_at,
    )
    print(f"  Report: {result['stats']['report_path']}", file=sys.stderr)
    print(f"  Charts: {result['charts_generated']}", file=sys.stderr)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
