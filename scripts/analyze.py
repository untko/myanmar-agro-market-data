"""
Analysis + chart generation for Wisarra price data.
Generates:
  1. Weekly markdown report (data/wisarra/reports/YYYY-WNN.md)
  2. SVG trend charts per product (data/wisarra/charts/<category>/*.svg)
  3. Summary stats for the GitHub Actions summary output
"""

import json
import os
import sqlite3
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import quote

# Add scripts dir to path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from db import (
    get_connection, db_path, get_latest_prices, get_price_history,
    get_scrape_log, get_product_names
)


REPORTS_DIR = Path(__file__).resolve().parent.parent / "data" / "wisarra" / "reports"
CHARTS_DIR = Path(__file__).resolve().parent.parent / "data" / "wisarra" / "charts"

# Category classification based on product name keywords
CATEGORIES = {
    "rice-paddy": ["Rice", "Paddy", "Wheat", "Corn", "Maize"],
    "legumes": ["Bean", "Pea", "Gram", "Lentil", "Pigeon", "Chick", "Lablab", "Mung", "Cow Pea"],
    "vegetables": ["Onion", "Potato", "Chili", "Tomato", "Pumpkin", "Carrot", "Cauliflower",
                   "Eggplant", "Radish", "Chayote", "Capsicum", "Bell Pepper", "Garden Pea",
                   "Snake Gourd", "Yard Long", "Garlic", "Bocate", "Soya", "Water Melon"],
    "fruits": ["Banana", "Pomelo", "Avocado", "Stawberry", "Custard", "Peasant"],
    "grains-seeds": ["Sesame", "Blackgram", "Castor", "Groundnut Oil", "Jaggery", "Tamarini"],
}


def categorize(product_name: str) -> str:
    for cat, keywords in CATEGORIES.items():
        for kw in keywords:
            if kw.lower() in product_name.lower():
                return cat
    return "other"


def parse_price(val) -> float | None:
    if val is None or val == "" or val == "-":
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def format_price(val, currency: str = "MMK") -> str:
    if val is None:
        return "-"
    if currency == "MMK":
        return f"{val:,.0f}"
    return f"{val:,.2f}"


def generate_svg_chart(history: list[dict], product_name: str, output_path: Path):
    """Generate a clean SVG trend chart for a single product."""
    if not history:
        return

    # Sort by date ascending
    history = sorted(history, key=lambda x: x["scraped_at"])

    # Extract data points
    dates = []
    min_prices = []
    max_prices = []

    for h in history:
        dates.append(h["scraped_at"][:10])  # YYYY-MM-DD
        min_prices.append(parse_price(h["min_price"]))
        max_prices.append(parse_price(h["max_price"]))

    # Chart dimensions
    width = 800
    height = 300
    margin_left = 70
    margin_right = 30
    margin_top = 40
    margin_bottom = 60
    chart_w = width - margin_left - margin_right
    chart_h = height - margin_top - margin_bottom

    # Determine Y-axis range
    all_vals = [v for v in min_prices + max_prices if v is not None]
    if not all_vals:
        return

    y_min = min(all_vals) * 0.95
    y_max = max(all_vals) * 1.05
    y_range = y_max - y_min if y_max != y_min else 1

    def x_pos(i):
        if len(dates) <= 1:
            return margin_left + chart_w / 2
        return margin_left + (i / (len(dates) - 1)) * chart_w

    def y_pos(val):
        if val is None:
            return None
        return margin_top + chart_h - ((val - y_min) / y_range) * chart_h

    # Build SVG
    svg_parts = []
    svg_parts.append(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="{width}" height="{height}">')
    svg_parts.append(f'<style>')
    svg_parts.append(f'  text {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }}')
    svg_parts.append(f'  .title {{ font-size: 14px; font-weight: 600; fill: #1a1a1a; }}')
    svg_parts.append(f'  .axis {{ font-size: 10px; fill: #666; }}')
    svg_parts.append(f'  .grid {{ stroke: #e0e0e0; stroke-width: 0.5; }}')
    svg_parts.append(f'  .line-min {{ stroke: #2196F3; stroke-width: 2; fill: none; }}')
    svg_parts.append(f'  .line-max {{ stroke: #FF5722; stroke-width: 2; fill: none; }}')
    svg_parts.append(f'  .area {{ fill: rgba(33,150,243,0.08); }}')
    svg_parts.append(f'  .dot {{ fill: white; stroke-width: 1.5; }}')
    svg_parts.append(f'</style>')

    # Background
    svg_parts.append(f'<rect width="{width}" height="{height}" fill="#fafafa" rx="8"/>')

    # Title
    svg_parts.append(f'<text x="{width//2}" y="22" text-anchor="middle" class="title">{product_name}</text>')

    # Grid lines
    num_grid = 5
    for i in range(num_grid + 1):
        y = margin_top + (i / num_grid) * chart_h
        val = y_max - (i / num_grid) * y_range
        svg_parts.append(f'<line x1="{margin_left}" y1="{y}" x2="{margin_left + chart_w}" y2="{y}" class="grid"/>')
        svg_parts.append(f'<text x="{margin_left - 8}" y="{y + 3}" text-anchor="end" class="axis">{format_price(val)}</text>')

    # Build path for area + line
    min_points = [(x_pos(i), y_pos(v)) for i, v in enumerate(min_prices) if v is not None]
    max_points = [(x_pos(i), y_pos(v)) for i, v in enumerate(max_prices) if v is not None]

    # Area between min and max
    if len(min_points) >= 2 and len(max_points) >= 2:
        area_path = f"M {min_points[0][0]},{min_points[0][1]}"
        for x, y in min_points[1:]:
            area_path += f" L {x},{y}"
        # Go back along max line (reversed)
        for x, y in reversed(max_points):
            area_path += f" L {x},{y}"
        area_path += " Z"
        svg_parts.append(f'<path d="{area_path}" class="area"/>')

    # Min line
    if len(min_points) >= 2:
        line_path = f"M {min_points[0][0]},{min_points[0][1]}"
        for x, y in min_points[1:]:
            line_path += f" L {x},{y}"
        svg_parts.append(f'<path d="{line_path}" class="line-min"/>')
        for x, y in min_points:
            svg_parts.append(f'<circle cx="{x}" cy="{y}" r="3" class="dot" stroke="#2196F3"/>')

    # Max line
    if len(max_points) >= 2:
        line_path = f"M {max_points[0][0]},{max_points[0][1]}"
        for x, y in max_points[1:]:
            line_path += f" L {x},{y}"
        svg_parts.append(f'<path d="{line_path}" class="line-max"/>')
        for x, y in max_points:
            svg_parts.append(f'<circle cx="{x}" cy="{y}" r="3" class="dot" stroke="#FF5722"/>')

    # X-axis labels (show every nth)
    if len(dates) > 1:
        step = max(1, len(dates) // 6)
        for i in range(0, len(dates), step):
            svg_parts.append(f'<text x="{x_pos(i)}" y="{height - 10}" text-anchor="middle" class="axis" transform="rotate(-30, {x_pos(i)}, {height - 10})">{dates[i]}</text>')

    # Legend
    svg_parts.append(f'<line x1="{margin_left}" y1="{height - 35}" x2="{margin_left + 20}" y2="{height - 35}" class="line-min"/>')
    svg_parts.append(f'<text x="{margin_left + 25}" y="{height - 31}" class="axis">Min</text>')
    svg_parts.append(f'<line x1="{margin_left + 70}" y1="{height - 35}" x2="{margin_left + 90}" y2="{height - 35}" class="line-max"/>')
    svg_parts.append(f'<text x="{margin_left + 95}" y="{height - 31}" class="axis">Max</text>')

    svg_parts.append('</svg>')

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text('\n'.join(svg_parts), encoding='utf-8')


def generate_report(conn, output_dir: Path = REPORTS_DIR) -> dict:
    """Generate the weekly markdown report."""
    output_dir.mkdir(parents=True, exist_ok=True)

    now = datetime.now(timezone.utc)
    # ISO week number
    iso_year, iso_week, _ = now.isocalendar()
    report_filename = f"{iso_year}-W{iso_week:02d}.md"
    report_path = output_dir / report_filename

    # Get latest and previous prices
    latest = get_latest_prices(conn)
    latest_date = conn.execute("SELECT MAX(scraped_at) as d FROM prices").fetchone()["d"]

    # Get previous scrape date
    prev_row = conn.execute(
        "SELECT DISTINCT scraped_at FROM prices WHERE scraped_at < ? ORDER BY scraped_at DESC LIMIT 1",
        (latest_date,)
    ).fetchone()
    prev_date = prev_row["scraped_at"] if prev_row else None

    # Compare
    price_up = []
    price_down = []
    price_same = []
    new_products = []
    removed_products = []

    if prev_date:
        prev_prices = {}
        for r in conn.execute("SELECT * FROM prices WHERE scraped_at = ?", (prev_date,)).fetchall():
            key = f"{r['name']}|{r['location']}|{r['marketplace']}"
            prev_prices[key] = dict(r)

        for item in latest:
            key = f"{item['name']}|{item['location']}|{item['marketplace']}"
            if key in prev_prices:
                prev = prev_prices[key]
                prev_min = parse_price(prev["min_price"])
                prev_max = parse_price(prev["max_price"])
                curr_min = parse_price(item["min_price"])
                curr_max = parse_price(item["max_price"])

                min_change = None
                max_change = None

                if prev_min and curr_min:
                    min_change = ((curr_min - prev_min) / prev_min) * 100
                if prev_max and curr_max:
                    max_change = ((curr_max - prev_max) / prev_max) * 100

                if min_change is not None and max_change is not None:
                    if min_change == 0 and max_change == 0:
                        price_same.append({
                            "name": item["name"], "location": item["location"],
                            "min": curr_min, "max": curr_max, "currency": item["currency"]
                        })
                    elif min_change > 0 or max_change > 0:
                        price_up.append({
                            "name": item["name"], "location": item["location"],
                            "min": curr_min, "max": curr_max,
                            "prev_min": prev_min, "prev_max": prev_max,
                            "min_change": min_change, "max_change": max_change,
                            "currency": item["currency"]
                        })
                    elif min_change < 0 or max_change < 0:
                        price_down.append({
                            "name": item["name"], "location": item["location"],
                            "min": curr_min, "max": curr_max,
                            "prev_min": prev_min, "prev_max": prev_max,
                            "min_change": min_change, "max_change": max_change,
                            "currency": item["currency"]
                        })
            else:
                new_products.append({
                    "name": item["name"], "location": item["location"],
                    "min": parse_price(item["min_price"]),
                    "max": parse_price(item["max_price"]),
                    "currency": item["currency"]
                })

        # Check for removed products
        latest_keys = {f"{i['name']}|{i['location']}|{i['marketplace']}" for i in latest}
        for key in prev_prices:
            if key not in latest_keys:
                removed_products.append({
                    "name": prev_prices[key]["name"],
                    "location": prev_prices[key]["location"]
                })
    else:
        # First scrape — everything is "new"
        for item in latest:
            new_products.append({
                "name": item["name"], "location": item["location"],
                "min": parse_price(item["min_price"]),
                "max": parse_price(item["max_price"]),
                "currency": item["currency"]
            })

    # Sort by magnitude of change
    price_up.sort(key=lambda x: abs(x.get("max_change", 0) or 0), reverse=True)
    price_down.sort(key=lambda x: abs(x.get("max_change", 0) or 0), reverse=True)

    # Build markdown
    lines = []
    lines.append(f"# Agricultural Market Prices Report")
    lines.append(f"")
    lines.append(f"**Source:** [Wisarra](https://wisarra.com/en/market-price)")
    lines.append(f"**Scrape Date:** {latest_date[:10] if latest_date else 'N/A'}")
    if prev_date:
        lines.append(f"**Previous Scrape:** {prev_date[:10]}")
    lines.append(f"**Products Tracked:** {len(latest)}")
    lines.append(f"")

    # Summary box
    lines.append(f"## Summary")
    lines.append(f"")
    lines.append(f"| Metric | Count |")
    lines.append(f"|--------|-------|")
    lines.append(f"| 📈 Price Increased | {len(price_up)} |")
    lines.append(f"| 📉 Price Decreased | {len(price_down)} |")
    lines.append(f"| ➡️  Price Unchanged | {len(price_same)} |")
    lines.append(f"| 🆕 New Products | {len(new_products)} |")
    lines.append(f"| ❌ Removed Products | {len(removed_products)} |")
    lines.append(f"")

    if price_up:
        lines.append(f"## 📈 Price Increases (Top 10)")
        lines.append(f"")
        lines.append(f"| Product | Location | Previous Max | Current Max | Change |")
        lines.append(f"|---------|----------|--------------|--------------|--------|")
        for item in price_up[:10]:
            max_chg = item.get("max_change")
            chg_str = f"+{max_chg:.1f}%" if max_chg and max_chg > 0 else f"{max_chg:.1f}%" if max_chg else "N/A"
            lines.append(f"| {item['name']} | {item['location']} | {format_price(item['prev_max'], item['currency'])} | {format_price(item['max'], item['currency'])} | {chg_str} |")
        lines.append(f"")

    if price_down:
        lines.append(f"## 📉 Price Decreases (Top 10)")
        lines.append(f"")
        lines.append(f"| Product | Location | Previous Max | Current Max | Change |")
        lines.append(f"|---------|----------|--------------|--------------|--------|")
        for item in price_down[:10]:
            max_chg = item.get("max_change")
            chg_str = f"{max_chg:.1f}%" if max_chg and max_chg < 0 else f"{max_chg:.1f}%" if max_chg else "N/A"
            lines.append(f"| {item['name']} | {item['location']} | {format_price(item['prev_max'], item['currency'])} | {format_price(item['max'], item['currency'])} | {chg_str} |")
        lines.append(f"")

    if new_products:
        lines.append(f"## 🆕 New Products")
        lines.append(f"")
        for p in new_products:
            lines.append(f"- **{p['name']}** ({p['location']}): {format_price(p['min'], p['currency'])} - {format_price(p['max'], p['currency'])}")
        lines.append(f"")

    if removed_products:
        lines.append(f"## ❌ Removed Products")
        lines.append(f"")
        for p in removed_products:
            lines.append(f"- **{p['name']}** ({p['location']})")
        lines.append(f"")

    if price_same:
        lines.append(f"## ➡️ Unchanged ({len(price_same)} products)")
        lines.append(f"")
        lines.append(f"<details><summary>Click to expand</summary>")
        lines.append(f"")
        for p in price_same:
            lines.append(f"- {p['name']} ({p['location']}): {format_price(p['min'], p['currency'])} - {format_price(p['max'], p['currency'])}")
        lines.append(f"")
        lines.append(f"</details>")
        lines.append(f"")

    # Write report
    report_path.write_text('\n'.join(lines), encoding='utf-8')

    return {
        "report_path": str(report_path),
        "price_up": len(price_up),
        "price_down": len(price_down),
        "price_same": len(price_same),
        "new_products": len(new_products),
        "removed_products": len(removed_products),
        "total_products": len(latest),
    }


def generate_charts(conn, charts_dir: Path = CHARTS_DIR, top_n: int = 20):
    """Generate SVG charts for top products (by price volatility)."""
    products = get_product_names(conn)

    # Get products with most price changes (to prioritize charting)
    changed_products = conn.execute(
        """SELECT name, COUNT(*) as changes
           FROM (
               SELECT name, scraped_at, min_price, max_price,
                      LAG(max_price) OVER (PARTITION BY name ORDER BY scraped_at) as prev_max
               FROM prices
           )
           WHERE prev_max IS NOT NULL AND max_price != prev_max
           GROUP BY name ORDER BY changes DESC LIMIT ?""",
        (top_n,)
    ).fetchall()

    # Also get products with most data points (even if unchanged)
    all_products = conn.execute(
        """SELECT name, COUNT(*) as cnt FROM prices GROUP BY name ORDER BY cnt DESC LIMIT ?""",
        (top_n,)
    ).fetchall()

    chart_names = {r["name"] for r in changed_products}
    chart_names.update({r["name"] for r in all_products})

    generated = 0
    for name in chart_names:
        history = get_price_history(conn, name, limit=52)
        if len(history) < 2:
            continue

        cat = categorize(name)
        safe_name = name.replace("/", "-").replace(" ", "-").replace("(", "").replace(")", "")
        output_path = charts_dir / cat / f"{safe_name}.svg"

        generate_svg_chart(history, name, output_path)
        generated += 1

    return generated


def main():
    db = db_path()
    conn = get_connection(db)

    # Generate report
    print("Generating report...", file=sys.stderr)
    stats = generate_report(conn)
    print(f"  Report: {stats['report_path']}", file=sys.stderr)
    print(f"  Products: {stats['total_products']}, Up: {stats['price_up']}, Down: {stats['price_down']}, Same: {stats['price_same']}", file=sys.stderr)

    # Generate charts
    print("Generating charts...", file=sys.stderr)
    n = generate_charts(conn)
    print(f"  Generated {n} charts", file=sys.stderr)

    conn.close()

    # Output stats as JSON for GitHub Actions
    print(json.dumps(stats, indent=2))


if __name__ == "__main__":
    main()
