import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import Mock

from scripts.dataset import PriceDataset
from scripts.main import collect_wisarra_update, run_pipeline


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
    def test_pipeline_compares_publication_editions_even_within_one_iso_week(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            dataset = PriceDataset(root / "snapshots")
            reports = root / "reports"
            charts = root / "charts"
            source = "https://wisarra.com/en/market-price"

            def row(name: str, observed_at: str) -> dict[str, str]:
                return {
                    **stored_wisarra_row(observed_at),
                    "name": name,
                    "source_url": source,
                }

            dataset.record(
                [row("Returned", "2026-06-30T00:00:00Z")],
                datetime(2026, 6, 30, 1, tzinfo=timezone.utc),
            )
            dataset.record(
                [row("Continuing", "2026-07-06T00:00:00Z"), row("Not Reported", "2026-07-06T00:00:00Z")],
                datetime(2026, 7, 6, 1, tzinfo=timezone.utc),
            )
            dataset.record(
                [
                    row("Continuing", "2026-07-08T00:00:00Z"),
                    row("Returned", "2026-07-08T00:00:00Z"),
                    row("Newly Reported", "2026-07-08T00:00:00Z"),
                ],
                datetime(2026, 7, 8, 1, tzinfo=timezone.utc),
            )

            result = run_pipeline(dataset, None, reports_dir=reports, charts_dir=charts)

            self.assertEqual(result["stats"]["newly_reported_series"], 1)
            self.assertEqual(result["stats"]["returned_series"], 1)
            self.assertEqual(result["stats"]["not_reported_series"], 1)
            report = Path(result["stats"]["report_path"]).read_text(encoding="utf-8")
            self.assertIn("- **Previous comparison:** 2026-07-06", report)

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
