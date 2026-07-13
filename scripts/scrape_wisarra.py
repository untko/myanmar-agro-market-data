"""
Scraper for Wisarra market prices.
The AJAX endpoint returns JSON: {"total": N, "data": "<html><tr>...</tr></html>"}
We parse the HTML from the JSON "data" field.
"""

import json
import re
import sys
from datetime import date, datetime
from html.parser import HTMLParser
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError


BASE_URL = "https://wisarra.com/en/market-price"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Accept": "application/json, text/html,application/xhtml+xml",
    "X-Requested-With": "XMLHttpRequest",
}
LANDING_HEADERS = {
    "User-Agent": HEADERS["User-Agent"],
    "Accept": "text/html,application/xhtml+xml",
}


class _VisibleTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self._hidden_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style"}:
            self._hidden_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style"} and self._hidden_depth:
            self._hidden_depth -= 1

    def handle_data(self, data: str) -> None:
        if not self._hidden_depth and (text := data.strip()):
            self.parts.append(text)


def parse_published_date(html: str) -> date:
    """Extract the source's visible market-price publication date."""
    parser = _VisibleTextParser()
    parser.feed(html)
    visible_text = " ".join(parser.parts)
    month_names = (
        "January|February|March|April|May|June|July|August|September|October|November|December"
    )
    match = re.search(
        rf"Agricultural Market Prices\s+({month_names})\s+(\d{{1,2}}),\s+(\d{{4}})\.?",
        visible_text,
    )
    if not match:
        raise ValueError("Wisarra market page does not contain a recognizable publication date")
    return datetime.strptime(" ".join(match.groups()), "%B %d %Y").date()


def fetch_published_date() -> date:
    """Fetch the landing page and return its visible publication date."""
    request = Request(BASE_URL, headers=LANDING_HEADERS)
    try:
        with urlopen(request, timeout=30) as response:
            return parse_published_date(response.read().decode("utf-8"))
    except (URLError, HTTPError) as error:
        raise RuntimeError(f"Failed to fetch Wisarra publication date: {error}") from error


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
    """Scrape all pages, requiring an explicit end-of-results page."""
    all_rows = []
    for page in range(1, max_pages + 1):
        print(f"  Fetching page {page}...", file=sys.stderr)
        html = fetch_page(page)

        if is_last_page(html):
            print(f"  Reached end at page {page}", file=sys.stderr)
            return all_rows

        rows = parse_rows(html)
        if not rows:
            raise RuntimeError(
                f"Wisarra page {page} contained neither price rows nor an end-of-results marker"
            )

        all_rows.extend(rows)
        print(f"    Got {len(rows)} rows (total: {len(all_rows)})", file=sys.stderr)

    raise RuntimeError(f"Wisarra scrape reached the {max_pages}-page limit without a confirmed end")


if __name__ == "__main__":
    rows = scrape_all()
    print(json.dumps(rows, ensure_ascii=False))
