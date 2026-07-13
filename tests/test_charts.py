import unittest
from datetime import datetime, timezone

from scripts.charts import render_price_chart
from scripts.dataset import PriceObservation, SeriesKey


class PriceChartTests(unittest.TestCase):
    def test_chart_is_accessible_readable_and_identifies_one_market_series(self):
        key = SeriesKey(
            name="Paddy (Paw San) (Rainy 2022)",
            location="Pathein",
            marketplace="Dedaye",
            currency="MMK",
            quantity="100",
            unit="basket",
        )
        history = [
            PriceObservation(key, 650, 745, datetime(2026, 6, 30, tzinfo=timezone.utc), "https://wisarra.com/en/market-price"),
            PriceObservation(key, 680, 770, datetime(2026, 7, 6, tzinfo=timezone.utc), "https://wisarra.com/en/market-price"),
        ]

        svg = render_price_chart(key, history)

        self.assertIn('role="img"', svg)
        self.assertIn("<title>Paddy (Paw San) (Rainy 2022) prices — Dedaye market</title>", svg)
        self.assertIn("Pathein · MMK per 100 basket", svg)
        self.assertIn("30 Jun", svg)
        self.assertIn("6 Jul", svg)
        self.assertIn("Minimum", svg)
        self.assertIn("Maximum", svg)
        self.assertIn("Source: wisarra.com", svg)
        self.assertNotIn('transform="rotate(-30', svg)
        self.assertNotIn("#FF5722", svg)

    def test_missing_bounds_leave_truthful_gaps_in_lines_and_range_band(self):
        key = SeriesKey("Rice", "Yangon", "Bayint Naung", "MMK", "1", "bag")
        source = "https://example.org/prices"
        history = [
            PriceObservation(key, 80, 100, datetime(2026, 6, 22, tzinfo=timezone.utc), source),
            PriceObservation(key, 90, None, datetime(2026, 6, 29, tzinfo=timezone.utc), source),
            PriceObservation(key, None, 120, datetime(2026, 7, 6, tzinfo=timezone.utc), source),
        ]

        svg = render_price_chart(key, history)

        self.assertNotIn('class="maximum"', svg)
        self.assertNotIn('class="range"', svg)
        self.assertIn("Source: example.org", svg)


if __name__ == "__main__":
    unittest.main()
