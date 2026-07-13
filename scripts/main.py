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
from .scrape_wisarra import BASE_URL, scrape_all


def run_pipeline(
    dataset: PriceDataset,
    rows: Iterable[Mapping[str, object]] | None,
    *,
    collected_at: datetime | None = None,
    reports_dir: Path = REPORTS_DIR,
    charts_dir: Path = CHARTS_DIR,
) -> dict[str, object]:
    """Record an optional scrape batch and build all derived artifacts."""
    snapshot_path = None
    if rows is not None:
        snapshot_path = dataset.record(rows, collected_at)

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
    collected_at = None
    if not args.skip_scrape:
        print("Scraping wisarra.com...", file=sys.stderr)
        collected_at = datetime.now(timezone.utc)
        rows = [
            {
                **row,
                "source": "wisarra",
                "source_record_id": "",
                "market_chain_level": "unspecified",
                "modal_price": "",
                "observed_at": collected_at,
                "source_url": BASE_URL,
            }
            for row in scrape_all()
        ]
        print(f"  Scraped {len(rows)} rows", file=sys.stderr)
    else:
        print("Skipping scrape; rebuilding from committed snapshots", file=sys.stderr)

    result = run_pipeline(
        PriceDataset(SNAPSHOTS_DIR),
        rows,
        collected_at=collected_at,
    )
    print(f"  Report: {result['stats']['report_path']}", file=sys.stderr)
    print(f"  Charts: {result['charts_generated']}", file=sys.stderr)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
