import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import Mock

from scripts.dataset import PriceDataset
from scripts.main import collect_wisarra_update


def stored_wisarra_row(observed_at: str) -> dict[str, str]:
    return {
        "source": "wisarra",
        "source_record_id": "",
        "name": "Rice",
        "location": "Yangon",
        "marketplace": "War Tan",
        "market_chain_level": "unspecified",
        "min_price": "100",
        "max_price": "120",
        "modal_price": "",
        "currency": "MMK",
        "quantity": "1",
        "unit": "basket",
        "observed_at": observed_at,
        "source_url": "https://wisarra.com/en/market-price",
    }


class MainPipelineTests(unittest.TestCase):
    def test_unchanged_site_date_skips_the_full_scrape(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            dataset = PriceDataset(Path(temp_dir))
            dataset.record(
                [stored_wisarra_row("2026-07-08T00:00:00Z")],
                datetime(2026, 7, 9, tzinfo=timezone.utc),
            )
            scrape = Mock(side_effect=AssertionError("full scrape should not run"))

            rows = collect_wisarra_update(
                dataset,
                published_date=date(2026, 7, 8),
                scrape=scrape,
            )

            self.assertIsNone(rows)
            scrape.assert_not_called()

    def test_new_site_date_is_used_as_observation_date_not_collection_time(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            dataset = PriceDataset(Path(temp_dir))
            collected_at = datetime(2026, 7, 18, 3, tzinfo=timezone.utc)
            scrape = Mock(
                return_value=[
                    {
                        "name": "Rice",
                        "location": "Yangon",
                        "marketplace": "War Tan",
                        "min_price": "130",
                        "max_price": "140",
                        "currency": "MMK",
                        "quantity": "1",
                        "unit": "basket",
                    }
                ]
            )

            rows = collect_wisarra_update(
                dataset,
                published_date=date(2026, 7, 15),
                scrape=scrape,
            )
            dataset.record(rows or [], collected_at)
            observation = dataset.load()[0]

            scrape.assert_called_once_with()
            self.assertEqual(observation.observed_at, datetime(2026, 7, 15, tzinfo=timezone.utc))
            self.assertEqual(observation.collected_at, collected_at)


if __name__ == "__main__":
    unittest.main()
