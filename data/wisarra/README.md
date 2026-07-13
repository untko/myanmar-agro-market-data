# Wisarra snapshots

This directory contains the canonical, auditable Wisarra market-price dataset.

Each file under `snapshots/YYYY/` is one immutable scrape batch. Rows retain the product, location, marketplace, currency, quantity, and unit published by Wisarra, plus the UTC observation time and source URL. Those six descriptive fields together identify one comparable market series; records with different markets or units must never be connected or compared as one series.

The row contract is documented in [`schema.json`](schema.json). Empty price cells represent unavailable prices.

Reports, charts, and analytical databases are derived from these snapshots. They are intentionally excluded from the canonical data directory and can be rebuilt with:

```bash
python -m scripts.main --skip-scrape
```
