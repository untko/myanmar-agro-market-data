# Myanmar Agricultural Market Data

An automated, auditable archive of agricultural market prices published by [Wisarra](https://wisarra.com/en/market-price).

Every scheduled run records one immutable CSV snapshot. Reports and charts are rebuilt from those snapshots, so the repository stores transparent source data instead of a changing binary database or hundreds of generated chart files.

## Repository structure

```text
data/wisarra/
├── README.md
├── schema.json
└── snapshots/
    └── YYYY/
        └── YYYY-MM-DDTHH-MM-SSZ.csv

scripts/
├── dataset.py             # snapshot and comparable-series module
├── scrape_wisarra.py      # Wisarra extraction
├── analyze.py             # weekly report and chart selection
├── charts.py              # accessible SVG renderer
└── main.py                # pipeline entry point

artifacts/                 # generated locally; ignored by Git
├── reports/
└── charts/
```

## Data model

A comparable price series is identified by all of the following fields:

```text
product name + location + marketplace + currency + quantity + unit
```

This prevents prices from different markets or trading units from being joined into false trends. All raw observations remain in the snapshots; charts retain only the latest observation for each exact series in each ISO week.

See [`data/wisarra/schema.json`](data/wisarra/schema.json) for the snapshot row contract.

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

Generated charts are flat, stable per-series SVG files. `artifacts/charts/index.csv` maps each filename to its product, location, marketplace, currency, quantity, and unit. A series needs at least two weekly observations and one numeric price to produce a meaningful chart.

## Automation

GitHub Actions runs every Monday at 09:00 UTC. It commits only the new immutable snapshot and uploads the generated report and charts as a workflow artifact. Generated files and analysis databases are never committed.

## Adding another source

Add a source-specific scraper that returns rows matching the snapshot schema, then record the batch through `PriceDataset`. Do not add source-specific report or chart logic: the dataset module supplies exact comparable series to the shared analysis modules.

## Data notes

- Repeated prices are retained because an unchanged observation still proves that the product was present.
- Prices are usually MMK, but currency is part of the series identity and must not be assumed.
- Trading quantities and units vary and must never be aggregated without conversion.

## License and source

The underlying data is published by Wisarra International Co., Ltd. Review the source's terms before redistribution or commercial use.
