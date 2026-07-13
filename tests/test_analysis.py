import csv
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from scripts.analyze import generate_charts, generate_report
from scripts.dataset import PriceObservation, SeriesKey


def series_key(marketplace: str) -> SeriesKey:
    return SeriesKey(
        name="Paddy (Paw San) (Rainy 2022)",
        location="Pathein",
        marketplace=marketplace,
        currency="MMK",
        quantity="100",
        unit="basket",
    )


class AnalysisTests(unittest.TestCase):
    def setUp(self):
        dedaye = series_key("Dedaye")
        pathein = series_key("Pathein")
        self.series = {
            dedaye: [
                PriceObservation(dedaye, 650, 745, datetime(2026, 6, 30, tzinfo=timezone.utc)),
                PriceObservation(dedaye, 680, 770, datetime(2026, 7, 6, tzinfo=timezone.utc)),
            ],
            pathein: [
                PriceObservation(pathein, 700, 1000, datetime(2026, 6, 30, tzinfo=timezone.utc)),
                PriceObservation(pathein, 1000, 1500, datetime(2026, 7, 6, tzinfo=timezone.utc)),
            ],
        }

    def test_report_compares_exact_market_series_week_over_week(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            stats = generate_report(self.series, Path(temp_dir))
            report = Path(stats["report_path"]).read_text(encoding="utf-8")

            self.assertEqual(Path(stats["report_path"]).name, "2026-W28.md")
            self.assertIn("| Product | Location | Market | Previous Max | Current Max | Change |", report)
            self.assertIn("| Paddy (Paw San) (Rainy 2022) | Pathein | Pathein | 1,000 | 1,500 | +50.0% |", report)
            self.assertIn("| Paddy (Paw San) (Rainy 2022) | Pathein | Dedaye | 745 | 770 | +3.4% |", report)

    def test_chart_generation_is_flat_stable_and_manifested(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            generated = generate_charts(self.series, output_dir, top_n=20)

            self.assertEqual(generated, 2)
            self.assertFalse(any(path.is_dir() for path in output_dir.iterdir()))
            svg_files = sorted(output_dir.glob("*.svg"))
            self.assertEqual(len(svg_files), 2)
            self.assertTrue(all(path.name.endswith(".svg") for path in svg_files))

            with (output_dir / "index.csv").open(newline="", encoding="utf-8") as handle:
                manifest = list(csv.DictReader(handle))
            self.assertEqual({row["marketplace"] for row in manifest}, {"Dedaye", "Pathein"})
            self.assertEqual({row["file"] for row in manifest}, {path.name for path in svg_files})


if __name__ == "__main__":
    unittest.main()
