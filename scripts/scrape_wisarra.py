"""
Scraper for Wisarra market prices.
The AJAX endpoint returns JSON: {"total": N, "data": "<html><tr>...</tr></html>"}
We parse the HTML from the JSON "data" field.
"""

import json
import re
import sys
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError


BASE_URL = "https://wisarra.com/en/market-price"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Accept": "application/json, text/html,application/xhtml+xml",
    "X-Requested-With": "XMLHttpRequest",
}


def fetch_page(page_num: int) -> str:
    """Fetch a single page of results via the AJAX endpoint."""
    url = f"{BASE_URL}?page={page_num}"
    req = Request(url, headers=HEADERS)
    try:
        with urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8")
            # Try to parse as JSON first
            try:
                data = json.loads(raw)
                html = data.get("data", "")
                return html
            except json.JSONDecodeError:
                # Fallback: it might be raw HTML
                return raw
    except (URLError, HTTPError) as e:
        raise RuntimeError(f"Failed to fetch page {page_num}: {e}")


def parse_rows(html: str) -> list[dict]:
    """Parse HTML table rows into structured dicts."""
    rows = []
    # Match each <tr>...</tr> block
    row_pattern = re.compile(r"<tr>(.*?)</tr>", re.DOTALL)
    cell_pattern = re.compile(r"<td[^>]*>(.*?)</td>", re.DOTALL)

    for row_match in row_pattern.finditer(html):
        cells = cell_pattern.findall(row_match.group(1))
        if len(cells) == 8:
            rows.append({
                "name": cells[0].strip(),
                "location": cells[1].strip(),
                "marketplace": cells[2].strip(),
                "min_price": cells[3].strip() or None,
                "max_price": cells[4].strip() or None,
                "currency": cells[5].strip(),
                "quantity": cells[6].strip(),
                "unit": cells[7].strip(),
            })
    return rows


def is_last_page(html: str) -> bool:
    """Check if this page indicates no more results."""
    return "There is no price list" in html or "no price list" in html.lower()


def scrape_all(max_pages: int = 50) -> list[dict]:
    """Scrape all pages, return all rows."""
    all_rows = []
    for page in range(1, max_pages + 1):
        print(f"  Fetching page {page}...", file=sys.stderr)
        html = fetch_page(page)

        if is_last_page(html):
            print(f"  Reached end at page {page}", file=sys.stderr)
            break

        rows = parse_rows(html)
        if not rows:
            print(f"  No rows on page {page}, stopping", file=sys.stderr)
            break

        all_rows.extend(rows)
        print(f"    Got {len(rows)} rows (total: {len(all_rows)})", file=sys.stderr)

    return all_rows


if __name__ == "__main__":
    rows = scrape_all()
    print(json.dumps(rows, ensure_ascii=False))
