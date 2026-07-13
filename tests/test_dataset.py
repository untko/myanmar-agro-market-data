import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from scripts.dataset import PriceDataset, SeriesKey


def price_row(
    *,
    marketplace: str,
    min_price: str,
    max_price: str,
    quantity: str = "100",
    unit: str = "basket",
) -> dict[str, str]:
    return {
        "name": "Paddy (Paw San) (Rainy 2022)",
        "location": "Pathein",
        "marketplace": marketplace,
        "min_price": min_price,
        "max_price": max_price,
        "currency": "MMK",
        "quantity": quantity,
        "unit": unit,
        "source_url": "https://wisarra.com/en/market-price",
    }


class PriceDatasetTests(unittest.TestCase):
    def test_empty_scrape_is_rejected_instead_of_becoming_a_snapshot(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            dataset = PriceDataset(Path(temp_dir))
            with self.assertRaisesRegex(ValueError, "empty"):
                dataset.record([], datetime(2026, 7, 6, tzinfo=timezone.utc))
            self.assertEqual(list(Path(temp_dir).rglob("*.csv")), [])

    def test_snapshot_round_trip_is_immutable_and_auditable(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            dataset = PriceDataset(Path(temp_dir))
            observed_at = datetime(2026, 7, 6, 12, 45, 54, tzinfo=timezone.utc)
            rows = [
                price_row(marketplace="Dedaye", min_price="650", max_price="745"),
                price_row(marketplace="Pathein", min_price="1000", max_price="1500"),
            ]

            snapshot = dataset.record(rows, observed_at)
            observations = dataset.load()

            self.assertEqual(
                snapshot.relative_to(Path(temp_dir)).as_posix(),
                "2026/2026-07-06T12-45-54Z.csv",
            )
            self.assertEqual(len(observations), 2)
            self.assertEqual({item.series.marketplace for item in observations}, {"Dedaye", "Pathein"})
            self.assertEqual({item.scraped_at for item in observations}, {observed_at})

            # Replaying the same batch is idempotent, but a timestamp can never be rewritten.
            self.assertEqual(dataset.record(rows, observed_at), snapshot)
            changed_rows = [price_row(marketplace="Dedaye", min_price="700", max_price="800")]
            with self.assertRaisesRegex(ValueError, "immutable"):
                dataset.record(changed_rows, observed_at)

    def test_snapshot_rows_must_satisfy_the_documented_identity_and_source_contract(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            dataset = PriceDataset(Path(temp_dir))
            observed_at = datetime(2026, 7, 6, tzinfo=timezone.utc)

            missing_price_field = price_row(marketplace="Dedaye", min_price="650", max_price="745")
            del missing_price_field["min_price"]
            with self.assertRaisesRegex(ValueError, "min_price"):
                dataset.record([missing_price_field], observed_at)

            empty_market = price_row(marketplace="", min_price="650", max_price="745")
            with self.assertRaisesRegex(ValueError, "marketplace"):
                dataset.record([empty_market], observed_at)

            invalid_source = price_row(marketplace="Dedaye", min_price="650", max_price="745")
            invalid_source["source_url"] = "not a URL"
            with self.assertRaisesRegex(ValueError, "source_url"):
                dataset.record([invalid_source], observed_at)

            negative_price = price_row(marketplace="Dedaye", min_price="-1", max_price="745")
            with self.assertRaisesRegex(ValueError, "non-negative"):
                dataset.record([negative_price], observed_at)

    def test_manually_added_snapshot_is_validated_when_loaded(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            snapshots = Path(temp_dir)
            snapshot = snapshots / "2026" / "2026-07-06T12-45-54Z.csv"
            snapshot.parent.mkdir(parents=True)
            snapshot.write_text(
                "name,location,marketplace,min_price,max_price,currency,quantity,unit,scraped_at,source_url\n"
                "Rice,Yangon,Bayint Naung,100,120,MMK,1,bag,2026-07-06T12:45:54Z,not-a-url\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "source_url"):
                PriceDataset(snapshots).load()

    def test_weekly_series_never_mix_market_or_unit_and_keep_latest_observation(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            dataset = PriceDataset(Path(temp_dir))
            dataset.record(
                [
                    price_row(marketplace="Dedaye", min_price="650", max_price="745"),
                    price_row(marketplace="Pathein", min_price="700", max_price="1000"),
                    price_row(
                        marketplace="Dedaye",
                        min_price="12000",
                        max_price="16000",
                        quantity="1",
                        unit="ton",
                    ),
                ],
                datetime(2026, 6, 30, 7, 14, 10, tzinfo=timezone.utc),
            )
            dataset.record(
                [price_row(marketplace="Dedaye", min_price="675", max_price="760")],
                datetime(2026, 6, 30, 8, 11, 31, tzinfo=timezone.utc),
            )
            dataset.record(
                [
                    price_row(marketplace="Dedaye", min_price="680", max_price="770"),
                    price_row(marketplace="Pathein", min_price="1000", max_price="1500"),
                ],
                datetime(2026, 7, 6, 12, 45, 54, tzinfo=timezone.utc),
            )

            series = dataset.weekly_series()
            dedaye_baskets = SeriesKey(
                name="Paddy (Paw San) (Rainy 2022)",
                location="Pathein",
                marketplace="Dedaye",
                currency="MMK",
                quantity="100",
                unit="basket",
            )
            pathein_baskets = SeriesKey(
                name="Paddy (Paw San) (Rainy 2022)",
                location="Pathein",
                marketplace="Pathein",
                currency="MMK",
                quantity="100",
                unit="basket",
            )

            self.assertEqual(len(series), 3)
            self.assertEqual([point.max_price for point in series[dedaye_baskets]], [760, 770])
            self.assertEqual([point.max_price for point in series[pathein_baskets]], [1000, 1500])
            self.assertEqual(len(series[dedaye_baskets]), 2)


if __name__ == "__main__":
    unittest.main()
