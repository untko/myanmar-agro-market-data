# Wisarra snapshots

This directory contains the canonical, auditable Wisarra market-price dataset.

Each file under `snapshots/YYYY/` is one immutable scrape batch. Rows retain the product, location, marketplace, currency, quantity, and unit published by Wisarra. They also record the source, source URL, observation time, and collection time. Wisarra publishes a calendar date but no exact time; new snapshots encode that visible date as midnight UTC in `observed_at`, while `collected_at` records the actual fetch time. Snapshots collected before publication-date detection used collection time as the observation fallback.

Wisarra does not publish an unambiguous retail/wholesale label on this feed, so rows use `market_chain_level=unspecified` rather than inferring a tier.

The shared CSV row contract is documented in [`../price-observation-schema.json`](../price-observation-schema.json). Because CSV values are textual, non-negative prices are encoded as decimal strings; empty price cells represent unavailable prices.

Reports and charts are derived from these snapshots and versioned under the repository-level `artifacts/` directory. Analytical databases remain untracked. All derived outputs can be rebuilt with:

```bash
python -m scripts.main --skip-scrape
```
