import json
import tempfile
import unittest
from decimal import Decimal
from datetime import date, datetime, timezone
from pathlib import Path

from scripts.dataset import PriceDataset, SNAPSHOT_COLUMNS, SeriesKey


def price_row(
    *,
    marketplace: str,
    min_price: str,
    max_price: str,
    quantity: str = "100",
    unit: str = "basket",
    observed_at: str = "2026-07-06T00:00:00Z",
) -> dict[str, str]:
    return {
        "source": "wisarra",
        "source_record_id": "",
        "name": "Paddy (Paw San) (Rainy 2022)",
        "location": "Pathein",
        "marketplace": marketplace,
        "market_chain_level": "unspecified",
        "min_price": min_price,
        "max_price": max_price,
        "modal_price": "",
        "currency": "MMK",
        "quantity": quantity,
        "unit": unit,
        "observed_at": observed_at,
        "source_url": "https://wisarra.com/en/market-price",
    }


class PriceDatasetTests(unittest.TestCase):
    def test_latest_observed_date_can_be_checked_per_source(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            dataset = PriceDataset(Path(temp_dir))
            wisarra = price_row(
                marketplace="Dedaye",
                min_price="650",
                max_price="745",
                observed_at="2026-07-08T00:00:00Z",
            )
            cso = {
                **wisarra,
                "source": "cso",
                "market_chain_level": "retail",
                "observed_at": "2026-07-10T00:00:00Z",
                "source_url": "https://www.csostat.gov.mm/Statistics/MarketPrice",
            }
            dataset.record([wisarra, cso], datetime(2026, 7, 11, tzinfo=timezone.utc))

            self.assertEqual(dataset.latest_observed_date("wisarra"), date(2026, 7, 8))
            self.assertEqual(dataset.latest_observed_date("cso"), date(2026, 7, 10))
            self.assertIsNone(dataset.latest_observed_date("missing"))

    def test_documented_schema_columns_match_the_runtime_contract(self):
        schema_path = Path(__file__).resolve().parent.parent / "data" / "price-observation-schema.json"
        schema = json.loads(schema_path.read_text(encoding="utf-8"))

        self.assertEqual(tuple(schema["required"]), SNAPSHOT_COLUMNS)
        self.assertEqual(set(schema["properties"]), set(SNAPSHOT_COLUMNS))

    def test_series_keep_source_tier_observation_and_collection_context_separate(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            dataset = PriceDataset(Path(temp_dir))
            collected_at = datetime(2026, 7, 7, 9, 30, tzinfo=timezone.utc)
            retail = price_row(marketplace="Yangon", min_price="100", max_price="120")
            retail.update(
                source="cso",
                source_record_id="rice-2026-07-06",
                market_chain_level="retail",
                modal_price="110.50",
                observed_at="2026-07-06T00:00:00Z",
                source_url="https://www.csostat.gov.mm/Statistics/MarketPrice",
            )
            wholesale = {**retail, "source": "example-wholesale", "market_chain_level": "wholesale"}

            dataset.record([retail, wholesale], collected_at)
            observations = dataset.load()
            series = dataset.weekly_series()

            self.assertEqual(len(series), 2)
            self.assertEqual({item.series.source for item in observations}, {"cso", "example-wholesale"})
            self.assertEqual({item.series.market_chain_level for item in observations}, {"retail", "wholesale"})
            self.assertEqual({item.modal_price for item in observations}, {Decimal("110.50")})
            self.assertEqual({item.observed_at for item in observations}, {datetime(2026, 7, 6, tzinfo=timezone.utc)})
            self.assertEqual({item.collected_at for item in observations}, {collected_at})
            self.assertEqual({item.source_record_id for item in observations}, {"rice-2026-07-06"})

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
            self.assertEqual({item.observed_at for item in observations}, {datetime(2026, 7, 6, tzinfo=timezone.utc)})
            self.assertEqual({item.collected_at for item in observations}, {observed_at})

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

            invalid_tier = price_row(marketplace="Dedaye", min_price="650", max_price="745")
            invalid_tier["market_chain_level"] = "consumer-ish"
            with self.assertRaisesRegex(ValueError, "market_chain_level"):
                dataset.record([invalid_tier], observed_at)

            with self.assertRaisesRegex(ValueError, "collected_at.*timezone"):
                dataset.record(
                    [price_row(marketplace="Dedaye", min_price="650", max_price="745")],
                    datetime(2026, 7, 6),
                )

            naive_observation = price_row(marketplace="Dedaye", min_price="650", max_price="745")
            naive_observation["observed_at"] = "2026-07-06T00:00:00"
            with self.assertRaisesRegex(ValueError, "observed_at.*timezone"):
                dataset.record([naive_observation], observed_at)

    def test_manually_added_snapshot_is_validated_when_loaded(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            snapshots = Path(temp_dir)
            snapshot = snapshots / "2026" / "2026-07-06T12-45-54Z.csv"
            snapshot.parent.mkdir(parents=True)
            snapshot.write_text(
                "source,source_record_id,name,location,marketplace,market_chain_level,min_price,max_price,modal_price,currency,quantity,unit,observed_at,collected_at,source_url\n"
                "wisarra,,Rice,Yangon,Bayint Naung,unspecified,100,120,,MMK,1,bag,2026-07-06T12:45:54Z,2026-07-06T12:45:54Z,not-a-url\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "source_url"):
                PriceDataset(snapshots).load()

    def test_weekly_series_never_mix_market_or_unit_and_keep_latest_observation(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            dataset = PriceDataset(Path(temp_dir))
            dataset.record(
                [
                    price_row(marketplace="Dedaye", min_price="650", max_price="745", observed_at="2026-06-30T07:14:10Z"),
                    price_row(marketplace="Pathein", min_price="700", max_price="1000", observed_at="2026-06-30T07:14:10Z"),
                    price_row(
                        marketplace="Dedaye",
                        min_price="12000",
                        max_price="16000",
                        quantity="1",
                        unit="ton",
                        observed_at="2026-06-30T07:14:10Z",
                    ),
                ],
                datetime(2026, 6, 30, 7, 14, 10, tzinfo=timezone.utc),
            )
            dataset.record(
                [price_row(marketplace="Dedaye", min_price="675", max_price="760", observed_at="2026-06-30T08:11:31Z")],
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
                source="wisarra",
                name="Paddy (Paw San) (Rainy 2022)",
                location="Pathein",
                marketplace="Dedaye",
                market_chain_level="unspecified",
                currency="MMK",
                quantity="100",
                unit="basket",
            )
            pathein_baskets = SeriesKey(
                source="wisarra",
                name="Paddy (Paw San) (Rainy 2022)",
                location="Pathein",
                marketplace="Pathein",
                market_chain_level="unspecified",
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
