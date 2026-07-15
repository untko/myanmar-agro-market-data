import csv
import tempfile
import unittest
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from scripts.analyze import generate_charts, generate_report
from scripts.dataset import PriceObservation, SeriesKey


def series_key(marketplace: str) -> SeriesKey:
    return SeriesKey(
        source="wisarra",
        name="Paddy (Paw San) (Rainy 2022)",
        location="Pathein",
        marketplace=marketplace,
        market_chain_level="unspecified",
        currency="MMK",
        quantity="100",
        unit="basket",
    )


def observation(
    key: SeriesKey,
    min_price: int | None,
    max_price: int | None,
    observed_at: datetime,
    source_url: str = "https://wisarra.com/en/market-price",
    modal_price: int | None = None,
    collected_at: datetime | None = None,
) -> PriceObservation:
    return PriceObservation(
        series=key,
        min_price=min_price,
        max_price=max_price,
        modal_price=modal_price,
        observed_at=observed_at,
        collected_at=collected_at or observed_at,
        source_record_id="",
        source_url=source_url,
    )


class AnalysisTests(unittest.TestCase):
    def setUp(self):
        dedaye = series_key("Dedaye")
        pathein = series_key("Pathein")
        self.series = {
            dedaye: [
                observation(dedaye, 650, 745, datetime(2026, 6, 30, tzinfo=timezone.utc)),
                observation(dedaye, 680, 770, datetime(2026, 7, 6, tzinfo=timezone.utc)),
            ],
            pathein: [
                observation(pathein, 700, 1000, datetime(2026, 6, 30, tzinfo=timezone.utc)),
                observation(pathein, 1000, 1500, datetime(2026, 7, 6, tzinfo=timezone.utc)),
            ],
        }

    def test_report_compares_exact_market_series_week_over_week(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            stats = generate_report(self.series, Path(temp_dir))
            report = Path(stats["report_path"]).read_text(encoding="utf-8")

            self.assertEqual(Path(stats["report_path"]).name, "2026-W28.md")
            self.assertTrue(report.startswith("# Myanmar Agricultural Market Prices\n\n## Executive Summary"))
            self.assertIn("same source, market tier, product, location, market, currency, quantity, and unit", report)
            self.assertIn("- **Previous comparison:** 2026-06-30", report)
            self.assertIn("- **Sources:** wisarra", report)
            self.assertIn("| Source | Tier | Product | Location | Market | Unit | Previous Min | Current Min | Min change | Previous Max | Current Max | Max change |", report)
            self.assertIn("| wisarra | unspecified | Paddy (Paw San) (Rainy 2022) | Pathein | Pathein | MMK per 100 basket | 700 | 1,000 | +42.9% | 1,000 | 1,500 | +50.0% |", report)
            self.assertIn("| wisarra | unspecified | Paddy (Paw San) (Rainy 2022) | Pathein | Dedaye | MMK per 100 basket | 650 | 680 | +4.6% | 745 | 770 | +3.4% |", report)

    def test_opposing_minimum_and_maximum_moves_are_reported_as_mixed(self):
        key = series_key("Mixed Market")
        source = "https://wisarra.com/en/market-price"
        series = {
            key: [
                observation(key, 100, 200, datetime(2026, 6, 30, tzinfo=timezone.utc), source),
                observation(key, 120, 180, datetime(2026, 7, 6, tzinfo=timezone.utc), source),
            ]
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            stats = generate_report(series, Path(temp_dir))
            report = Path(stats["report_path"]).read_text(encoding="utf-8")

            self.assertEqual(stats["price_mixed"], 1)
            self.assertIn("## Mixed range movements", report)
            self.assertNotIn("## Price increases", report)
            self.assertNotIn("## Price decreases", report)

    def test_modal_only_source_is_compared_and_chartable(self):
        key = SeriesKey("cso", "Rice", "Yangon", "Yangon", "retail", "MMK", "1", "pyi")
        source = "https://www.csostat.gov.mm/Statistics/MarketPrice"
        series = {
            key: [
                observation(key, None, None, datetime(2026, 6, 30, tzinfo=timezone.utc), source, Decimal("4200.50")),
                observation(key, None, None, datetime(2026, 7, 6, tzinfo=timezone.utc), source, Decimal("4300.75")),
            ]
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir)
            stats = generate_report(series, output / "reports")
            report = Path(stats["report_path"]).read_text(encoding="utf-8")
            chart_count = generate_charts(series, output / "charts")

            self.assertEqual(stats["price_up"], 1)
            self.assertEqual(chart_count, 1)
            self.assertIn("Previous Modal | Current Modal | Modal change", report)
            self.assertIn("| 4,200.5 | 4,300.75 | +2.4% |", report)

    def test_each_source_uses_its_own_latest_two_publications(self):
        wisarra = series_key("Dedaye")
        cso = SeriesKey("cso", "Rice", "Yangon", "Yangon", "retail", "MMK", "1", "pyi")
        series = {
            wisarra: [
                observation(wisarra, 650, 745, datetime(2026, 6, 30, tzinfo=timezone.utc)),
                observation(wisarra, 680, 770, datetime(2026, 7, 6, tzinfo=timezone.utc)),
            ],
            cso: [
                observation(cso, None, None, datetime(2026, 7, 6, tzinfo=timezone.utc), "https://www.csostat.gov.mm/Statistics/MarketPrice", 4200),
                observation(cso, None, None, datetime(2026, 7, 13, tzinfo=timezone.utc), "https://www.csostat.gov.mm/Statistics/MarketPrice", 4300),
            ],
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            stats = generate_report(series, Path(temp_dir))
            report = Path(stats["report_path"]).read_text(encoding="utf-8")

            self.assertEqual(stats["total_series"], 2)
            self.assertEqual(stats["not_reported_series"], 0)
            self.assertIn("**cso comparison:** 2026-07-06 → 2026-07-13", report)
            self.assertIn("**wisarra comparison:** 2026-06-30 → 2026-07-06", report)

    def test_report_distinguishes_new_returned_and_not_reported_series(self):
        continuing = series_key("Continuing")
        newly_reported = series_key("Newly Reported")
        returned = series_key("Returned")
        not_reported = series_key("Not Reported")
        source = "https://wisarra.com/en/market-price"
        series = {
            continuing: [
                observation(continuing, 100, 120, datetime(2026, 7, 6, tzinfo=timezone.utc), source),
                observation(continuing, 110, 130, datetime(2026, 7, 8, tzinfo=timezone.utc), source),
            ],
            newly_reported: [
                observation(newly_reported, 90, 100, datetime(2026, 7, 8, tzinfo=timezone.utc), source),
            ],
            returned: [
                observation(returned, 80, 90, datetime(2026, 6, 30, tzinfo=timezone.utc), source),
                observation(returned, 85, 95, datetime(2026, 7, 8, tzinfo=timezone.utc), source),
            ],
            not_reported: [
                observation(not_reported, 70, 80, datetime(2026, 7, 6, tzinfo=timezone.utc), source),
            ],
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            stats = generate_report(series, Path(temp_dir))
            report = Path(stats["report_path"]).read_text(encoding="utf-8")

            self.assertEqual(stats["newly_reported_series"], 1)
            self.assertEqual(stats["returned_series"], 1)
            self.assertEqual(stats["not_reported_series"], 1)
            self.assertIn("## Newly reported market series", report)
            self.assertIn("## Returned after absence", report)
            self.assertIn("## Not reported in the latest edition", report)
            self.assertIn("1 was not reported in the latest edition", report)
            self.assertNotIn("New market series", report)
            self.assertNotIn("Removed market series", report)

    def test_report_uses_latest_complete_batch_when_one_date_was_collected_twice(self):
        continuing = series_key("Continuing")
        omitted_later = series_key("Omitted Later")
        added_later = series_key("Added Later")
        source = "https://wisarra.com/en/market-price"
        previous_date = datetime(2026, 6, 30, tzinfo=timezone.utc)
        edition_date = datetime(2026, 7, 6, tzinfo=timezone.utc)
        first_collection = datetime(2026, 7, 6, 1, tzinfo=timezone.utc)
        corrected_collection = datetime(2026, 7, 6, 2, tzinfo=timezone.utc)
        series = {
            continuing: [
                observation(continuing, 100, 120, previous_date, source),
                observation(continuing, 105, 125, edition_date, source, collected_at=first_collection),
                observation(continuing, 110, 130, edition_date, source, collected_at=corrected_collection),
            ],
            omitted_later: [
                observation(omitted_later, 80, 90, previous_date, source),
                observation(omitted_later, 85, 95, edition_date, source, collected_at=first_collection),
            ],
            added_later: [
                observation(added_later, 70, 75, edition_date, source, collected_at=corrected_collection),
            ],
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            stats = generate_report(series, Path(temp_dir))
            report = Path(stats["report_path"]).read_text(encoding="utf-8")

            self.assertEqual(stats["total_series"], 2)
            self.assertEqual(stats["newly_reported_series"], 1)
            self.assertEqual(stats["not_reported_series"], 1)
            self.assertIn("Added Later", report)
            self.assertIn("Omitted Later", report)

    def test_not_comparable_explanation_refers_to_editions(self):
        empty = series_key("No Comparable Price")
        source = "https://wisarra.com/en/market-price"
        series = {
            empty: [
                observation(empty, None, 100, datetime(2026, 7, 6, tzinfo=timezone.utc), source),
                observation(empty, 100, None, datetime(2026, 7, 8, tzinfo=timezone.utc), source),
            ]
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            stats = generate_report(series, Path(temp_dir))
            report = Path(stats["report_path"]).read_text(encoding="utf-8")

            self.assertEqual(stats["price_not_comparable"], 1)
            self.assertIn("appeared in both editions", report)
            self.assertNotIn("appeared in both weeks", report)

    def test_chart_generation_is_flat_stable_and_manifested(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            generated = generate_charts(self.series, output_dir)

            self.assertEqual(generated, 2)
            self.assertFalse(any(path.is_dir() for path in output_dir.iterdir()))
            svg_files = sorted(output_dir.glob("*.svg"))
            self.assertEqual(len(svg_files), 2)
            self.assertTrue(all(path.name.endswith(".svg") for path in svg_files))

            with (output_dir / "index.csv").open(newline="", encoding="utf-8") as handle:
                manifest = list(csv.DictReader(handle))
            self.assertEqual({row["marketplace"] for row in manifest}, {"Dedaye", "Pathein"})
            self.assertEqual({row["source"] for row in manifest}, {"wisarra"})
            self.assertEqual({row["market_chain_level"] for row in manifest}, {"unspecified"})
            self.assertEqual({row["file"] for row in manifest}, {path.name for path in svg_files})

    def test_chart_generation_includes_every_chartable_series_by_default(self):
        third = series_key("Third Market")
        source = "https://wisarra.com/en/market-price"
        series = dict(self.series)
        series[third] = [
            observation(third, 500, 600, datetime(2026, 6, 30, tzinfo=timezone.utc), source),
            observation(third, 510, 620, datetime(2026, 7, 6, tzinfo=timezone.utc), source),
        ]
        with tempfile.TemporaryDirectory() as temp_dir:
            self.assertEqual(generate_charts(series, Path(temp_dir)), 3)

    def test_chart_generation_retains_history_when_latest_week_is_missing(self):
        missing_latest = series_key("Missing Latest")
        current = series_key("Current")
        source = "https://wisarra.com/en/market-price"
        series = {
            missing_latest: [
                observation(missing_latest, 100, 120, datetime(2026, 6, 23, tzinfo=timezone.utc), source),
                observation(missing_latest, 110, 130, datetime(2026, 6, 30, tzinfo=timezone.utc), source),
            ],
            current: [
                observation(current, 200, 220, datetime(2026, 6, 30, tzinfo=timezone.utc), source),
                observation(current, 210, 230, datetime(2026, 7, 6, tzinfo=timezone.utc), source),
            ],
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            self.assertEqual(generate_charts(series, output_dir), 2)
            manifest = (output_dir / "index.csv").read_text(encoding="utf-8")
            self.assertIn("Missing Latest", manifest)

    def test_chart_generation_skips_series_without_any_numeric_price(self):
        empty = series_key("No Price Market")
        source = "https://wisarra.com/en/market-price"
        series = dict(self.series)
        series[empty] = [
            observation(empty, None, None, datetime(2026, 6, 30, tzinfo=timezone.utc), source),
            observation(empty, None, None, datetime(2026, 7, 6, tzinfo=timezone.utc), source),
        ]
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir)
            stats = generate_report({empty: series[empty]}, output / "reports")
            report = Path(stats["report_path"]).read_text(encoding="utf-8")

            self.assertEqual(stats["price_same"], 0)
            self.assertEqual(stats["price_not_comparable"], 1)
            self.assertIn("| Not comparable | 1 |", report)
            self.assertIn("Price unavailable", report)
            self.assertEqual(generate_charts(series, output / "charts"), 2)


if __name__ == "__main__":
    unittest.main()
