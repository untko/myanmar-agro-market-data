# Snapshot-backed market data architecture

## Context

The original pipeline committed a mutable SQLite database and category-organized SVG files. Categories were inferred from product-name keywords rather than source data. More seriously, chart history was grouped by product name alone, so observations from different marketplaces could be connected into one false trend.

## Decision

- Treat one immutable CSV per scrape as the canonical dataset.
- Identify comparable series by product name, location, marketplace, currency, quantity, and unit.
- Retain every raw observation, while using the latest observation per exact series and ISO week for reports and charts.
- Generate reports and charts under `artifacts/`, commit them alongside each snapshot, and also upload them from GitHub Actions for convenient bundled download.
- Use a flat stable chart identifier derived from the complete series identity; publish an `index.csv` manifest for discovery.
- Keep the pipeline dependency-free and test behavior through the snapshot, series, reporting, migration, and rendering interfaces.

## Migration

The 472 rows in the legacy SQLite database were exported without loss into three snapshot files:

- `2026-06-30T07-14-10Z.csv`: 159 observations
- `2026-06-30T08-11-31Z.csv`: 159 observations
- `2026-07-06T12-45-54Z.csv`: 154 observations

The binary database and category folders were removed from version control. Reports and redesigned flat chart artifacts remain versioned and can be rebuilt from the snapshots.

## Consequences

Repository diffs now show newly observed data directly. Charts no longer mix markets or units, reruns within one week no longer create duplicate x-axis points, and all derived outputs can be reproduced offline with `python -m scripts.main --skip-scrape`.

The post-implementation review also tightened the interfaces: empty or schema-invalid snapshots are rejected, report sections distinguish mixed minimum/maximum movements, missing chart bounds remain visible as gaps, source attribution is derived from observation metadata, and every series with at least two weeks and one numeric price receives a chart.
