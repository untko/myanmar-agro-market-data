# myanmar-agro-market-data

Automated agricultural market price tracking for Myanmar. Data scraped weekly from [Wisarra.com](https://wisarra.com/en/market-price).

## What this does

1. **Scrapes** agricultural product prices every Monday at 09:00 UTC
2. **Stores** all historical data in SQLite (`data/wisarra/prices.db`)
3. **Generates** a weekly markdown report with price changes, trends, and new/removed products
4. **Creates** SVG trend charts for each tracked product
5. **Commits** everything to this repo automatically via GitHub Actions

## Data structure

```
data/wisarra/
├── prices.db          # SQLite database (all historical prices)
├── charts/            # SVG trend charts per product
│   ├── rice-paddy/
│   ├── legumes/
│   ├── vegetables/
│   ├── fruits/
│   └── grains-seeds/
└── reports/           # Weekly markdown summaries
    ├── 2026-W26.md
    └── ...
```

## Schema (SQLite)

```sql
CREATE TABLE prices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,           -- Product name
    location TEXT NOT NULL,       -- City/region
    marketplace TEXT NOT NULL,    -- Marketplace name
    min_price INTEGER,            -- Minimum price (in currency units)
    max_price INTEGER,            -- Maximum price
    currency TEXT NOT NULL,       -- MMK, USD, etc.
    quantity TEXT,                -- Quantity per unit
    unit TEXT,                    -- basket, viss, ton, pc, etc.
    scraped_at TEXT NOT NULL      -- ISO 8601 timestamp
);

CREATE TABLE scrape_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    scraped_at TEXT NOT NULL,
    rows_scraped INTEGER,
    rows_inserted INTEGER,
    rows_updated INTEGER,
    rows_unchanged INTEGER,
    status TEXT,                  -- success / error
    error_message TEXT
);
```

## Running locally

```bash
# Install dependencies
pip install -r requirements.txt

# Full scrape + analyze
python scripts/main.py

# Only analyze (skip scraping)
python scripts/main.py --skip-scrape
```

## Adding new sources

To add another scraping source:
1. Create `scripts/scrape_<source>.py` with a `scrape_all()` function
2. Create `data/<source>/` directory
3. Add source-specific analysis in `scripts/analyze_<source>.py`
4. Update `scripts/main.py` to call the new scraper
5. The GitHub Actions workflow will automatically pick it up

## Data notes

- **"No change" is recorded**: Even when prices don't change, a new row is inserted with the current timestamp. This proves the scrape happened and the product is still available.
- **Prices are in MMK** (Myanmar Kyat) unless otherwise noted. Some Shan region products are priced in USD.
- **Units vary**: basket (~50kg for rice, ~25kg for beans), viss (~1.6kg), ton, piece, etc.

## License

Data is sourced from Wisarra International Co., Ltd. and is their property.
