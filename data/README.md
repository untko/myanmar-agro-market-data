# Price data

Each source owns append-only collection batches under `data/<source>/snapshots/YYYY/`. All sources use [`price-observation-schema.json`](price-observation-schema.json); reports and charts are derived under the repository-level `artifacts/` directory.

The comparable-series grain is source, raw product name, raw location, raw marketplace, market-chain level, currency, raw quantity, and raw unit. Changing any one of those fields creates a different series. This keeps retail and wholesale prices, unlike trading units, and separate publishers out of the same trend.

Source-specific parsing belongs in the scraper for that source. Shared storage, weekly selection, reports, and charts remain source-agnostic.
