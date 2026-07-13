# Myanmar Agricultural Market Data

A small, auditable collector and weekly reporter for Myanmar agricultural market prices. [Wisarra](https://wisarra.com/en/market-price) is the first source; additional sources must use the same provenance-aware observation contract.

Every scheduled run records one immutable CSV snapshot. Reports and charts are rebuilt from those snapshots and committed alongside them, while the transparent snapshots remain the canonical source instead of a changing binary database.

## Repository structure

```text
data/
├── price-observation-schema.json
└── wisarra/
    ├── README.md
    └── snapshots/
        └── YYYY/
            └── YYYY-MM-DDTHH-MM-SSZ.csv

scripts/
├── dataset.py             # snapshot and comparable-series module
├── scrape_wisarra.py      # Wisarra extraction
├── analyze.py             # weekly report and chart selection
├── charts.py              # accessible SVG renderer
└── main.py                # pipeline entry point

artifacts/                 # generated and versioned in Git
├── reports/
└── charts/
```

## Data model

A comparable price series is identified by all of the following fields:

```text
source + product name + location + marketplace + market-chain level + currency + quantity + unit
```

This prevents different publishers, retail/wholesale tiers, markets, or trading units from being joined into false trends. Product, location, marketplace, quantity, unit, and decimal price values remain as published. `observed_at` records when the price applies; `collected_at` records when the repository captured it. Charts retain only the latest observation for each exact series in each ISO week, and reports compare the latest two available ISO weeks independently for each source.

See [`data/price-observation-schema.json`](data/price-observation-schema.json) for the shared snapshot row contract.

## Running locally

The project uses only the Python standard library.

```bash
# Scrape, append a snapshot, and generate artifacts
python -m scripts.main

# Rebuild reports and charts without network access
python -m scripts.main --skip-scrape

# Run the test suite
python -m unittest discover -s tests -v
```

Generated charts are flat, stable per-series SVG files. `artifacts/charts/index.csv` maps each filename to its source, market tier, product, location, marketplace, currency, quantity, and unit. A series needs at least two weekly observations and one minimum, maximum, or modal price to produce a chart.

## Automation

GitHub Actions runs every Monday at 09:00 UTC. It currently collects Wisarra, then commits any new snapshots under configured source directories together with the regenerated report and charts. It also uploads the generated outputs as a convenient workflow download. Analysis databases are never committed.

## Adding another source

Add a source-specific scraper and a source directory under `data/<source>/snapshots/`, then register that collector in the pipeline entry point. The scraper must return rows matching the shared schema, including a documented market-chain level and separate observation and collection times, then record the batch through `PriceDataset`. Do not add source-specific report or chart logic.

Keep this repository focused on a few reliable price feeds. Large historical or contextual datasets belong in the external data library; for example, WFP comparisons should read an optional external path or temporary download rather than committing another copy here. The repository has a soft data-size ceiling of 25–50 MB.

## Data notes

- Repeated prices are retained because an unchanged observation still proves that the product was present.
- Prices are usually MMK, but currency is part of the series identity and must not be assumed.
- Trading quantities and units vary and must never be aggregated without conversion.
- `unspecified` is used when a source does not publish a retail, wholesale, farmgate, or export tier; the pipeline does not infer one.

## License and source

Each snapshot retains its source identifier and URL. Review every publisher's terms before adding, redistributing, or commercially using its data.
