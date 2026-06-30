"""
Main entry point: scrape + store + analyze.
Usage: python main.py [--skip-scrape]
"""

import json
import sys
import os
from datetime import datetime, timezone
from pathlib import Path

# Add scripts dir to path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from scrape_wisarra import scrape_all
from db import (
    get_connection, db_path, init_db, upsert_prices, log_scrape
)
from analyze import generate_report, generate_charts


def main():
    skip_scrape = "--skip-scrape" in sys.argv

    # 1. Scrape
    if not skip_scrape:
        print("🔍 Scraping wisarra.com...", file=sys.stderr)
        try:
            rows = scrape_all()
            print(f"  Scraped {len(rows)} rows", file=sys.stderr)
        except Exception as e:
            print(f"  Scrape failed: {e}", file=sys.stderr)
            # Log the failure
            db = db_path()
            conn = get_connection(db)
            init_db(conn)
            log_scrape(conn, "wisarra", 0, {"inserted": 0, "updated": 0, "unchanged": 0},
                       "error", str(e))
            conn.close()
            sys.exit(1)
    else:
        print("  Skipping scrape (--skip-scrape)", file=sys.stderr)
        rows = []

    # 2. Store
    if rows:
        print("💾 Storing in SQLite...", file=sys.stderr)
        db = db_path()
        conn = get_connection(db)
        init_db(conn)
        counts = upsert_prices(conn, rows)
        log_scrape(conn, "wisarra", len(rows), counts, "success")
        print(f"  Inserted: {counts['inserted']}, Updated: {counts['updated']}, Unchanged: {counts['unchanged']}", file=sys.stderr)
        conn.close()

    # 3. Analyze
    print("📊 Generating analysis...", file=sys.stderr)
    db = db_path()
    conn = get_connection(db)
    stats = generate_report(conn)
    n_charts = generate_charts(conn)
    conn.close()

    print(f"  Report: {stats['report_path']}", file=sys.stderr)
    print(f"  Charts: {n_charts} SVGs", file=sys.stderr)

    # Output JSON for GitHub Actions to read
    output = {
        "scrape_success": True,
        "rows": len(rows) if rows else 0,
        "stats": stats,
        "charts_generated": n_charts,
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
