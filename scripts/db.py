"""
Database layer for price storage.
Uses SQLite with upsert logic for idempotent scrapes.
"""

import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


DB_DIR = Path(__file__).resolve().parent.parent / "data" / "wisarra"


def db_path() -> Path:
    DB_DIR.mkdir(parents=True, exist_ok=True)
    return DB_DIR / "prices.db"


def get_connection(db_path_override: Path = None) -> sqlite3.Connection:
    path = db_path_override or db_path()
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db(conn: sqlite3.Connection):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS prices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            location TEXT NOT NULL,
            marketplace TEXT NOT NULL,
            min_price INTEGER,
            max_price INTEGER,
            currency TEXT NOT NULL,
            quantity TEXT,
            unit TEXT,
            scraped_at TEXT NOT NULL,
            UNIQUE(name, location, marketplace, scraped_at)
        );

        CREATE INDEX IF NOT EXISTS idx_name ON prices(name);
        CREATE INDEX IF NOT EXISTS idx_scraped_at ON prices(scraped_at);
        CREATE INDEX IF NOT EXISTS idx_location ON prices(location);

        CREATE TABLE IF NOT EXISTS scrape_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT NOT NULL,
            scraped_at TEXT NOT NULL,
            rows_scraped INTEGER NOT NULL,
            rows_inserted INTEGER NOT NULL,
            rows_updated INTEGER NOT NULL,
            rows_unchanged INTEGER NOT NULL,
            status TEXT NOT NULL,
            error_message TEXT
        );
    """)


def upsert_prices(conn: sqlite3.Connection, rows: list[dict]) -> dict:
    """
    Upsert price rows. Returns counts of inserted/updated/unchanged.
    Each row is keyed on (name, location, marketplace) — we compare
    min_price and max_price to detect changes.
    """
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    inserted = 0
    updated = 0
    unchanged = 0

    for row in rows:
        # Check if this product+location+marketplace already exists
        existing = conn.execute(
            """SELECT id, min_price, max_price FROM prices
               WHERE name = ? AND location = ? AND marketplace = ?
               ORDER BY scraped_at DESC LIMIT 1""",
            (row["name"], row["location"], row["marketplace"])
        ).fetchone()

        min_p = int(row["min_price"]) if row["min_price"] and row["min_price"] != "-" else None
        max_p = int(row["max_price"]) if row["max_price"] and row["max_price"] != "-" else None

        if existing:
            prev_min = existing["min_price"]
            prev_max = existing["max_price"]
            if prev_min == min_p and prev_max == max_p:
                unchanged += 1
                # Still record the scrape by inserting a new row with same data
                # (this is intentional — "no change" is data)
                conn.execute(
                    """INSERT INTO prices (name, location, marketplace, min_price, max_price, currency, quantity, unit, scraped_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (row["name"], row["location"], row["marketplace"], min_p, max_p,
                     row["currency"], row["quantity"], row["unit"], now)
                )
                inserted += 1  # it's a new timestamped record
            else:
                conn.execute(
                    """INSERT INTO prices (name, location, marketplace, min_price, max_price, currency, quantity, unit, scraped_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (row["name"], row["location"], row["marketplace"], min_p, max_p,
                     row["currency"], row["quantity"], row["unit"], now)
                )
                updated += 1
        else:
            conn.execute(
                """INSERT INTO prices (name, location, marketplace, min_price, max_price, currency, quantity, unit, scraped_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (row["name"], row["location"], row["marketplace"], min_p, max_p,
                 row["currency"], row["quantity"], row["unit"], now)
            )
            inserted += 1

    conn.commit()
    return {"inserted": inserted, "updated": updated, "unchanged": unchanged}


def log_scrape(conn: sqlite3.Connection, source: str, rows_scraped: int,
               counts: dict, status: str, error: str = None):
    conn.execute(
        """INSERT INTO scrape_log (source, scraped_at, rows_scraped, rows_inserted, rows_updated, rows_unchanged, status, error_message)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (source, datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
         rows_scraped, counts["inserted"], counts["updated"], counts["unchanged"],
         status, error)
    )
    conn.commit()


def get_latest_scrape_date(conn: sqlite3.Connection) -> str:
    row = conn.execute("SELECT MAX(scraped_at) as latest FROM prices").fetchone()
    return row["latest"] if row and row["latest"] else None


def get_product_names(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute("SELECT DISTINCT name FROM prices ORDER BY name").fetchall()
    return [r["name"] for r in rows]


def get_price_history(conn: sqlite3.Connection, product_name: str, limit: int = 52) -> list[dict]:
    rows = conn.execute(
        """SELECT scraped_at, min_price, max_price, location, marketplace
           FROM prices WHERE name = ?
           ORDER BY scraped_at DESC LIMIT ?""",
        (product_name, limit)
    ).fetchall()
    return [dict(r) for r in rows]


def get_latest_prices(conn: sqlite3.Connection) -> list[dict]:
    """Get the most recent price for each product."""
    rows = conn.execute(
        """SELECT p.* FROM prices p
           INNER JOIN (
               SELECT name, location, marketplace, MAX(scraped_at) as max_date
               FROM prices GROUP BY name, location, marketplace
           ) latest ON p.name = latest.name AND p.location = latest.location
               AND p.marketplace = latest.marketplace AND p.scraped_at = latest.max_date
           ORDER BY p.name"""
    ).fetchall()
    return [dict(r) for r in rows]


def get_previous_prices(conn: sqlite3.Connection) -> dict:
    """Get the second-most recent price for each product (for comparison)."""
    rows = conn.execute(
        """SELECT p.name, p.min_price, p.max_price, p.scraped_at
           FROM prices p
           INNER JOIN (
               SELECT name, location, marketplace, MAX(scraped_at) as max_date
               FROM prices GROUP BY name, location, marketplace
           ) latest ON p.name = latest.name AND p.location = latest.location
               AND p.marketplace = latest.marketplace AND p.scraped_at = latest.max_date
           WHERE p.scraped_at < latest.max_date
           ORDER BY p.name"""
    ).fetchall()
    result = {}
    for r in rows:
        key = f"{r['name']}|{r['min_price']}|{r['max_price']}"
        result[key] = dict(r)
    return result


def get_scrape_log(conn: sqlite3.Connection, limit: int = 10) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM scrape_log ORDER BY scraped_at DESC LIMIT ?",
        (limit,)
    ).fetchall()
    return [dict(r) for r in rows]
