"""Scrape Wisarra, record an immutable snapshot, and build analysis artifacts."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, time, timezone
from pathlib import Path
from typing import Callable, Iterable, Mapping

from .analyze import CHARTS_DIR, REPORTS_DIR, SNAPSHOTS_DIR, generate_charts, generate_report
from .dataset import PriceDataset
from .scrape_wisarra import BASE_URL, fetch_published_date, scrape_all


def collect_wisarra_update(
    dataset: PriceDataset,
    *,
    published_date: date,
    scrape: Callable[[], list[dict]] = scrape_all,
) -> list[dict[str, object]] | None:
    """Return adapted rows only when Wisarra's published date has advanced."""
    latest_date = dataset.latest_observed_date("wisarra")
    if latest_date is not None and published_date <= latest_date:
        return None
    observed_at = datetime.combine(published_date, time.min, tzinfo=timezone.utc)
    return [
        {
            **row,
            "source": "wisarra",
            "source_record_id": "",
            "market_chain_level": "unspecified",
            "modal_price": "",
            "observed_at": observed_at,
            "source_url": BASE_URL,
        }
        for row in scrape()
    ]


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

    dataset = PriceDataset(SNAPSHOTS_DIR)
    rows = None
    collected_at = None
    if not args.skip_scrape:
        collected_at = datetime.now(timezone.utc)
        published_date = fetch_published_date()
        print(f"Wisarra publication date: {published_date:%Y-%m-%d}", file=sys.stderr)
        rows = collect_wisarra_update(dataset, published_date=published_date)
        if rows is None:
            print("  Already collected; skipping full scrape", file=sys.stderr)
        else:
            print(f"  Scraped {len(rows)} rows", file=sys.stderr)
    else:
        print("Skipping scrape; rebuilding from committed snapshots", file=sys.stderr)

    result = run_pipeline(
        dataset,
        rows,
        collected_at=collected_at,
    )
    print(f"  Report: {result['stats']['report_path']}", file=sys.stderr)
    print(f"  Charts: {result['charts_generated']}", file=sys.stderr)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
