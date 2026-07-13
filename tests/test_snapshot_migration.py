import csv
import tempfile
import unittest
from pathlib import Path

from scripts.dataset import PriceDataset, SNAPSHOT_COLUMNS
from scripts.migrate_snapshot_schema import migrate_snapshot


class SnapshotSchemaMigrationTests(unittest.TestCase):
    def test_corrected_july_collection_keeps_publication_and_collection_dates_separate(self):
        project_root = Path(__file__).resolve().parent.parent
        snapshot = project_root / "data/wisarra/snapshots/2026/2026-07-13T09-43-41Z.csv"
        with snapshot.open(newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))

        self.assertEqual(len(rows), 160)
        self.assertEqual({row["observed_at"] for row in rows}, {"2026-07-08T00:00:00Z"})
        self.assertEqual({row["collected_at"] for row in rows}, {"2026-07-13T09:43:41Z"})

    def test_legacy_wisarra_snapshot_is_upgraded_once_without_changing_values(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            snapshot = Path(temp_dir) / "2026" / "2026-06-30T07-14-10Z.csv"
            snapshot.parent.mkdir(parents=True)
            snapshot.write_text(
                "name,location,marketplace,min_price,max_price,currency,quantity,unit,scraped_at,source_url\n"
                "Rice,Yangon,Bayint Naung,100,120,MMK,1,bag,2026-06-30T07:14:10Z,https://wisarra.com/en/market-price\n",
                encoding="utf-8",
            )

            self.assertTrue(migrate_snapshot(snapshot, source="wisarra", market_chain_level="unspecified"))
            self.assertFalse(migrate_snapshot(snapshot, source="wisarra", market_chain_level="unspecified"))

            with snapshot.open(newline="", encoding="utf-8") as handle:
                reader = csv.DictReader(handle)
                rows = list(reader)
                self.assertEqual(tuple(reader.fieldnames or ()), SNAPSHOT_COLUMNS)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["source"], "wisarra")
            self.assertEqual(rows[0]["market_chain_level"], "unspecified")
            self.assertEqual(rows[0]["min_price"], "100")
            self.assertEqual(rows[0]["observed_at"], "2026-06-30T07:14:10Z")
            self.assertEqual(rows[0]["collected_at"], "2026-06-30T07:14:10Z")
            self.assertEqual(len(PriceDataset(snapshot.parent.parent).load()), 1)


if __name__ == "__main__":
    unittest.main()
