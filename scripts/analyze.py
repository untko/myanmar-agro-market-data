"""Weekly reporting and chart generation from canonical price snapshots."""

from __future__ import annotations

import csv
import json
import shutil
from pathlib import Path
from typing import Mapping, Sequence

from .charts import write_price_chart
from .dataset import PriceDataset, PriceObservation, SeriesKey


PROJECT_ROOT = Path(__file__).resolve().parent.parent
SNAPSHOTS_DIR = PROJECT_ROOT / "data" / "wisarra" / "snapshots"
REPORTS_DIR = PROJECT_ROOT / "artifacts" / "reports"
CHARTS_DIR = PROJECT_ROOT / "artifacts" / "charts"


def _week(point: PriceObservation) -> tuple[int, int]:
    year, week, _ = point.scraped_at.isocalendar()
    return year, week


def _price(value: int | None) -> str:
    return "-" if value is None else f"{value:,.0f}"


def _percent_change(previous: int | None, current: int | None) -> float | None:
    if previous in (None, 0) or current is None:
        return None
    return ((current - previous) / previous) * 100


def _markdown(value: str) -> str:
    return value.replace("|", "\\|")


def _comparison_row(
    key: SeriesKey,
    previous: PriceObservation,
    current: PriceObservation,
) -> dict[str, object]:
    min_change = _percent_change(previous.min_price, current.min_price)
    max_change = _percent_change(previous.max_price, current.max_price)
    changes = [value for value in (min_change, max_change) if value is not None]
    direction = "same"
    if any(value > 0 for value in changes):
        direction = "up"
    elif any(value < 0 for value in changes):
        direction = "down"
    return {
        "key": key,
        "previous": previous,
        "current": current,
        "max_change": max_change,
        "magnitude": max((abs(value) for value in changes), default=0),
        "direction": direction,
    }


def generate_report(
    series: Mapping[SeriesKey, Sequence[PriceObservation]],
    output_dir: Path = REPORTS_DIR,
) -> dict[str, object]:
    """Generate a report comparing exact market series across the latest two weeks."""
    points = [point for history in series.values() for point in history]
    if not points:
        raise ValueError("Cannot generate a report without observations")

    weeks = sorted({_week(point) for point in points})
    latest_week = weeks[-1]
    previous_week = weeks[-2] if len(weeks) > 1 else None
    latest = {key: point for key, history in series.items() for point in history if _week(point) == latest_week}
    previous = (
        {key: point for key, history in series.items() for point in history if _week(point) == previous_week}
        if previous_week
        else {}
    )

    comparisons = [
        _comparison_row(key, previous[key], latest[key])
        for key in sorted(latest.keys() & previous.keys())
    ]
    increases = sorted(
        (row for row in comparisons if row["direction"] == "up"),
        key=lambda row: row["magnitude"],
        reverse=True,
    )
    decreases = sorted(
        (row for row in comparisons if row["direction"] == "down"),
        key=lambda row: row["magnitude"],
        reverse=True,
    )
    unchanged = [row for row in comparisons if row["direction"] == "same"]
    new_keys = sorted(latest.keys() - previous.keys())
    removed_keys = sorted(previous.keys() - latest.keys())

    latest_date = max(point.scraped_at for point in latest.values())
    previous_date = max((point.scraped_at for point in previous.values()), default=None)
    report_path = Path(output_dir) / f"{latest_week[0]}-W{latest_week[1]:02d}.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)

    lines = [
        "# Myanmar Agricultural Market Prices",
        "",
        f"**Source:** [Wisarra](https://wisarra.com/en/market-price)  ",
        f"**Latest observation:** {latest_date:%Y-%m-%d}  ",
    ]
    if previous_date:
        lines.append(f"**Previous comparison:** {previous_date:%Y-%m-%d}  ")
    lines.extend(
        [
            f"**Market series tracked:** {len(latest)}",
            "",
            "## Summary",
            "",
            "| Metric | Count |",
            "|---|---:|",
            f"| Price increased | {len(increases)} |",
            f"| Price decreased | {len(decreases)} |",
            f"| Price unchanged | {len(unchanged)} |",
            f"| New market series | {len(new_keys)} |",
            f"| Removed market series | {len(removed_keys)} |",
            "",
        ]
    )

    def add_change_table(title: str, rows: Sequence[dict[str, object]]) -> None:
        if not rows:
            return
        lines.extend(
            [
                f"## {title}",
                "",
                "| Product | Location | Market | Previous Max | Current Max | Change |",
                "|---|---|---|---:|---:|---:|",
            ]
        )
        for row in rows[:10]:
            key = row["key"]
            previous_point = row["previous"]
            current_point = row["current"]
            change = row["max_change"]
            change_text = "N/A" if change is None else f"{change:+.1f}%"
            lines.append(
                f"| {_markdown(key.name)} | {_markdown(key.location)} | {_markdown(key.marketplace)} "
                f"| {_price(previous_point.max_price)} | {_price(current_point.max_price)} | {change_text} |"
            )
        lines.append("")

    add_change_table("Price increases", increases)
    add_change_table("Price decreases", decreases)

    if new_keys:
        lines.extend(["## New market series", ""])
        for key in new_keys:
            point = latest[key]
            lines.append(
                f"- **{_markdown(key.name)}** — {_markdown(key.marketplace)}, {_markdown(key.location)}: "
                f"{_price(point.min_price)}–{_price(point.max_price)} {key.currency} per {_markdown(key.unit_label)}"
            )
        lines.append("")

    if removed_keys:
        lines.extend(["## Removed market series", ""])
        for key in removed_keys:
            lines.append(f"- **{_markdown(key.name)}** — {_markdown(key.marketplace)}, {_markdown(key.location)}")
        lines.append("")

    if unchanged:
        lines.extend([f"## Unchanged ({len(unchanged)} series)", "", "<details><summary>Show series</summary>", ""])
        for row in unchanged:
            key = row["key"]
            point = row["current"]
            lines.append(
                f"- {_markdown(key.name)} — {_markdown(key.marketplace)}, {_markdown(key.location)}: "
                f"{_price(point.min_price)}–{_price(point.max_price)} {key.currency} per {_markdown(key.unit_label)}"
            )
        lines.extend(["", "</details>", ""])

    report_path.write_text("\n".join(lines), encoding="utf-8")
    return {
        "report_path": str(report_path),
        "price_up": len(increases),
        "price_down": len(decreases),
        "price_same": len(unchanged),
        "new_series": len(new_keys),
        "removed_series": len(removed_keys),
        "total_series": len(latest),
    }


def _chart_score(history: Sequence[PriceObservation]) -> tuple[int, float, int]:
    maximums = [point.max_price for point in history if point.max_price is not None]
    changes = sum(previous != current for previous, current in zip(maximums, maximums[1:]))
    percentages = [
        abs((current - previous) / previous)
        for previous, current in zip(maximums, maximums[1:])
        if previous
    ]
    return changes, max(percentages, default=0), len(history)


def generate_charts(
    series: Mapping[SeriesKey, Sequence[PriceObservation]],
    charts_dir: Path = CHARTS_DIR,
    top_n: int = 20,
) -> int:
    """Generate flat, stable chart artifacts for the most informative market series."""
    output_dir = Path(charts_dir)
    if output_dir.exists():
        for child in output_dir.iterdir():
            if child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink()
    output_dir.mkdir(parents=True, exist_ok=True)

    candidates = [(key, list(history)) for key, history in series.items() if len(history) >= 2]
    candidates.sort(key=lambda item: (_chart_score(item[1]), item[0].stable_id), reverse=True)
    selected = candidates[:top_n]

    manifest_path = output_dir / "index.csv"
    with manifest_path.open("w", newline="", encoding="utf-8") as handle:
        fieldnames = [
            "file",
            "series_id",
            "name",
            "location",
            "marketplace",
            "currency",
            "quantity",
            "unit",
            "observations",
        ]
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        for key, history in selected:
            filename = f"{key.stable_id}.svg"
            write_price_chart(output_dir / filename, key, history)
            writer.writerow(
                {
                    "file": filename,
                    "series_id": key.stable_id,
                    "name": key.name,
                    "location": key.location,
                    "marketplace": key.marketplace,
                    "currency": key.currency,
                    "quantity": key.quantity,
                    "unit": key.unit,
                    "observations": len(history),
                }
            )
    return len(selected)


def main() -> None:
    dataset = PriceDataset(SNAPSHOTS_DIR)
    series = dataset.weekly_series()
    stats = generate_report(series)
    chart_count = generate_charts(series)
    print(json.dumps({**stats, "charts_generated": chart_count}, indent=2))


if __name__ == "__main__":
    main()
