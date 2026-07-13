# Snapshot-backed market data architecture

## Context

The original pipeline committed a mutable SQLite database and category-organized SVG files. Categories were inferred from product-name keywords rather than source data. More seriously, chart history was grouped by product name alone, so observations from different marketplaces could be connected into one false trend.

## Decision

- Treat one immutable CSV per scrape as the canonical dataset.
- Identify comparable series by source, product name, location, marketplace, market-chain level, currency, quantity, and unit.
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

## Multi-source provenance follow-up

The first schema treated the collection timestamp as the market observation time and did not place the publisher or market-chain tier in the series identity. That was safe for one feed but would allow invalid comparisons after adding a retail or wholesale source.

The shared row contract now records `source`, optional `source_record_id`, `market_chain_level`, minimum/maximum/modal prices, and separate `observed_at` and `collected_at` timestamps. Comparable series include source and tier. Existing Wisarra snapshots were migrated with `market_chain_level=unspecified`; no retail or wholesale classification was inferred. Reports and chart manifests display both fields, and modal-only feeds are supported without pretending a single price is a range.

The repository remains intentionally small: source snapshots live below `data/<source>/`, generated outputs live below `artifacts/`, and large contextual or historical datasets are referenced externally rather than copied here.

## Source-update detection

Wisarra's landing page displays a publication date but does not expose an exact update timestamp, `Last-Modified` header, or `ETag`. The collector now fetches that landing page first and performs the full paginated scrape only when the visible date is newer than the latest stored Wisarra observation. The date-only value is encoded as midnight UTC; the actual fetch remains in `collected_at`.

Scheduled checks run on Saturday, Sunday, and Monday mornings after the expected Friday publication. This gives delayed updates two retries while limiting unchanged runs to one lightweight page request and no Git commit.

The GitHub Actions collection at `data/wisarra/snapshots/2026/2026-07-13T09-43-41Z.csv` originally used its collection time as `observed_at`. After publication-date detection established that the page identified the batch as July 8, all 160 rows were corrected to `observed_at=2026-07-08T00:00:00Z`; their original `collected_at=2026-07-13T09:43:41Z` values were preserved. A repository test fixes that row count and timestamp pair as an auditable one-time correction.
