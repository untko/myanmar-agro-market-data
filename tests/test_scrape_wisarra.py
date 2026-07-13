import unittest
from datetime import date
from unittest.mock import patch

from scripts.scrape_wisarra import parse_published_date, scrape_all


class WisarraScraperTests(unittest.TestCase):
    def test_market_page_published_date_is_extracted_from_visible_content(self):
        html = """
        <main>
          <h2>Agricultural Market Prices</h2>
          <p><div><span style="font-size: 0.9rem;">July 8, 2026.</span></div></p>
          <p>Other page text dated January 1, 2020.</p>
        </main>
        """

        self.assertEqual(parse_published_date(html), date(2026, 7, 8))

    def test_missing_published_date_fails_instead_of_guessing_collection_time(self):
        with self.assertRaisesRegex(ValueError, "publication date"):
            parse_published_date("<h2>Agricultural Market Prices</h2><table></table>")

    def test_hidden_script_date_is_not_treated_as_visible_publication_date(self):
        html = """
        <script>Agricultural Market Prices July 9, 2026.</script>
        <h2>Agricultural Market Prices</h2><span>July 8, 2026.</span>
        """

        self.assertEqual(parse_published_date(html), date(2026, 7, 8))

    def test_unexpected_empty_page_rejects_partial_scrape(self):
        row = """
        <tr><td>Rice</td><td>Yangon</td><td>War Tan</td><td>100</td>
        <td>120</td><td>MMK</td><td>1</td><td>basket</td></tr>
        """
        with patch("scripts.scrape_wisarra.fetch_page", side_effect=[row, "<html>Temporary response</html>"]):
            with self.assertRaisesRegex(RuntimeError, "page 2"):
                scrape_all(max_pages=2)

    def test_page_limit_rejects_scrape_without_confirmed_end(self):
        row = """
        <tr><td>Rice</td><td>Yangon</td><td>War Tan</td><td>100</td>
        <td>120</td><td>MMK</td><td>1</td><td>basket</td></tr>
        """
        with patch("scripts.scrape_wisarra.fetch_page", return_value=row):
            with self.assertRaisesRegex(RuntimeError, "page limit"):
                scrape_all(max_pages=1)


if __name__ == "__main__":
    unittest.main()
