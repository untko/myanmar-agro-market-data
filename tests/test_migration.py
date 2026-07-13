import sqlite3
import tempfile
import unittest
from pathlib import Path

from scripts.dataset import PriceDataset
from scripts.migrate_legacy_db import migrate_database


class LegacyMigrationTests(unittest.TestCase):
    def test_each_scrape_becomes_one_snapshot_without_losing_rows(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            database_path = root / "prices.db"
            connection = sqlite3.connect(database_path)
            connection.execute(
                """CREATE TABLE prices (
                    name TEXT, location TEXT, marketplace TEXT,
                    min_price INTEGER, max_price INTEGER, currency TEXT,
                    quantity TEXT, unit TEXT, scraped_at TEXT
                )"""
            )
            connection.executemany(
                "INSERT INTO prices VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    ("Rice", "Yangon", "Bayint Naung", 100, 120, "MMK", "1", "bag", "2026-06-30T07:14:10Z"),
                    ("Paddy", "Pathein", "Dedaye", 650, 745, "MMK", "100", "basket", "2026-06-30T07:14:10Z"),
                    ("Rice", "Yangon", "Bayint Naung", 110, 130, "MMK", "1", "bag", "2026-07-06T12:45:54Z"),
                ],
            )
            connection.commit()
            connection.close()

            dataset = PriceDataset(root / "snapshots")
            snapshots = migrate_database(database_path, dataset)

            self.assertEqual([path.name for path in snapshots], [
                "2026-06-30T07-14-10Z.csv",
                "2026-07-06T12-45-54Z.csv",
            ])
            self.assertEqual(len(dataset.load()), 3)


if __name__ == "__main__":
    unittest.main()
