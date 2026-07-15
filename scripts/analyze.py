"""Weekly reporting and chart generation from canonical price snapshots."""

from __future__ import annotations

import csv
import json
import shutil
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from pathlib import Path
from typing import Mapping, Sequence
from urllib.parse import urlparse

from .charts import write_price_chart
from .dataset import PriceDataset, PriceObservation, SeriesKey


PROJECT_ROOT = Path(__file__).resolve().parent.parent
SNAPSHOTS_DIR = PROJECT_ROOT / "data" / "wisarra" / "snapshots"
REPORTS_DIR = PROJECT_ROOT / "artifacts" / "reports"
CHARTS_DIR = PROJECT_ROOT / "artifacts" / "charts"


def _week(point: PriceObservation) -> tuple[int, int]:
    year, week, _ = point.observed_at.isocalendar()
    return year, week


def _price(value: Decimal | None) -> str:
    if value is None:
        return "-"
    formatted = format(value, ",f")
    return formatted.rstrip("0").rstrip(".") if "." in formatted else formatted


def _price_summary(point: PriceObservation) -> str:
    if point.min_price is not None and point.max_price is not None:
        summary = _price(point.min_price) if point.min_price == point.max_price else f"{_price(point.min_price)}–{_price(point.max_price)}"
    elif point.min_price is not None:
        summary = f"From {_price(point.min_price)}"
    elif point.max_price is not None:
        summary = f"Up to {_price(point.max_price)}"
    elif point.modal_price is not None:
        return f"{_price(point.modal_price)} (modal)"
    else:
        return "Price unavailable"
    if point.modal_price is not None:
        summary += f"; modal {_price(point.modal_price)}"
    return summary


def _percent_change(previous: Decimal | None, current: Decimal | None) -> float | None:
    if previous in (None, 0) or current is None:
        return None
    return float(((current - previous) / previous) * 100)


def _markdown(value: str) -> str:
    return value.replace("|", "\\|")


class Movement(StrEnum):
    UP = "up"
    DOWN = "down"
    MIXED = "mixed"
    SAME = "same"
    NOT_COMPARABLE = "not_comparable"


@dataclass(frozen=True)
class PriceComparison:
    key: SeriesKey
    previous: PriceObservation
    current: PriceObservation
    min_change: float | None
    max_change: float | None
    modal_change: float | None
    magnitude: float
    movement: Movement


def _compare_prices(
    key: SeriesKey,
    previous: PriceObservation,
    current: PriceObservation,
) -> PriceComparison:
    min_change = _percent_change(previous.min_price, current.min_price)
    max_change = _percent_change(previous.max_price, current.max_price)
    modal_change = _percent_change(previous.modal_price, current.modal_price)
    changes = [value for value in (min_change, max_change, modal_change) if value is not None]
    if not changes:
        movement = Movement.NOT_COMPARABLE
    elif any(value > 0 for value in changes) and any(value < 0 for value in changes):
        movement = Movement.MIXED
    elif any(value > 0 for value in changes):
        movement = Movement.UP
    elif any(value < 0 for value in changes):
        movement = Movement.DOWN
    else:
        movement = Movement.SAME
    return PriceComparison(
        key=key,
        previous=previous,
        current=current,
        min_change=min_change,
        max_change=max_change,
        modal_change=modal_change,
        magnitude=max((abs(value) for value in changes), default=0),
        movement=movement,
    )


def generate_report(
    series: Mapping[SeriesKey, Sequence[PriceObservation]],
    output_dir: Path = REPORTS_DIR,
) -> dict[str, object]:
    """Compare exact market series across each source's latest two publications."""
    collected_points = [point for history in series.values() for point in history]
    if not collected_points:
        raise ValueError("Cannot generate a report without observations")

    latest_collection: dict[tuple[str, date], datetime] = {}
    for point in collected_points:
        edition = (point.series.source, point.observed_at.date())
        latest_collection[edition] = max(
            latest_collection.get(edition, point.collected_at),
            point.collected_at,
        )
    points = [
        point
        for point in collected_points
        if point.collected_at == latest_collection[(point.series.source, point.observed_at.date())]
    ]
    edition_series: dict[SeriesKey, list[PriceObservation]] = {}
    for point in points:
        edition_series.setdefault(point.series, []).append(point)

    latest: dict[SeriesKey, PriceObservation] = {}
    previous: dict[SeriesKey, PriceObservation] = {}
    returned_key_set: set[SeriesKey] = set()
    source_windows: dict[str, tuple[PriceObservation | None, PriceObservation]] = {}
    latest_weeks: list[tuple[int, int]] = []
    for source in sorted({point.series.source for point in points}):
        source_series = {
            key: history for key, history in edition_series.items() if key.source == source
        }
        source_dates = sorted(
            {point.observed_at.date() for history in source_series.values() for point in history}
        )
        source_latest_date = source_dates[-1]
        source_previous_date = source_dates[-2] if len(source_dates) > 1 else None
        for key, history in source_series.items():
            latest_matches = [point for point in history if point.observed_at.date() == source_latest_date]
            if latest_matches:
                latest[key] = max(latest_matches, key=lambda point: (point.observed_at, point.collected_at))
            previous_matches: list[PriceObservation] = []
            if source_previous_date:
                previous_matches = [
                    point for point in history if point.observed_at.date() == source_previous_date
                ]
                if previous_matches:
                    previous[key] = max(previous_matches, key=lambda point: (point.observed_at, point.collected_at))
                elif latest_matches and any(
                    point.observed_at.date() < source_previous_date for point in history
                ):
                    returned_key_set.add(key)
        latest_point = max(
            (point for key, point in latest.items() if key.source == source),
            key=lambda point: point.observed_at,
        )
        latest_weeks.append(_week(latest_point))
        previous_point = max(
            (point for key, point in previous.items() if key.source == source),
            key=lambda point: point.observed_at,
            default=None,
        )
        source_windows[source] = (previous_point, latest_point)

    comparisons = [
        _compare_prices(key, previous[key], latest[key])
        for key in sorted(latest.keys() & previous.keys())
    ]
    increases = sorted(
        (row for row in comparisons if row.movement is Movement.UP),
        key=lambda row: row.magnitude,
        reverse=True,
    )
    decreases = sorted(
        (row for row in comparisons if row.movement is Movement.DOWN),
        key=lambda row: row.magnitude,
        reverse=True,
    )
    mixed = sorted(
        (row for row in comparisons if row.movement is Movement.MIXED),
        key=lambda row: row.magnitude,
        reverse=True,
    )
    unchanged = [row for row in comparisons if row.movement is Movement.SAME]
    not_comparable = [row for row in comparisons if row.movement is Movement.NOT_COMPARABLE]
    returned_keys = sorted(returned_key_set & (latest.keys() - previous.keys()))
    newly_reported_keys = sorted((latest.keys() - previous.keys()) - set(returned_keys))
    not_reported_keys = sorted(previous.keys() - latest.keys())
    not_reported_verb = "was" if len(not_reported_keys) == 1 else "were"

    latest_date = max(point.observed_at for point in latest.values())
    previous_date = max((point.observed_at for point in previous.values()), default=None)
    report_week = max(latest_weeks)
    report_path = Path(output_dir) / f"{report_week[0]}-W{report_week[1]:02d}.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    source_points = {
        key.source: max(
            (point for series_key, point in latest.items() if series_key.source == key.source),
            key=lambda point: point.collected_at,
        )
        for key in latest
    }
    source_links = []
    for source, point in sorted(source_points.items()):
        source_host = (urlparse(point.source_url).hostname or point.source_url).removeprefix("www.")
        source_links.append(f"[{source_host}]({point.source_url})")

    lines = [
        "# Myanmar Agricultural Market Prices",
        "",
        "## Executive Summary",
        "",
        f"- **Coverage.** {len(latest)} exact market series from {len(source_points)} "
        f"{'source' if len(source_points) == 1 else 'sources'}, with the latest observation on {latest_date:%Y-%m-%d}.",
        (
            f"- **Edition-to-edition movement.** {len(increases)} increased, {len(decreases)} decreased, "
            f"{len(mixed)} had mixed range movement, {len(unchanged)} were unchanged, and "
            f"{len(not_comparable)} lacked a shared numeric measure."
            if previous_date
            else "- **Edition-to-edition movement.** No prior publication is available for comparison."
        ),
        (
            f"- **Coverage changes.** {len(newly_reported_keys)} newly reported, "
            f"{len(returned_keys)} returned after absence, and {len(not_reported_keys)} "
            f"{not_reported_verb} not reported in the latest edition."
            if previous_date
            else "- **Coverage changes.** No prior publication is available for comparison."
        ),
        "- **Comparability.** Changes are calculated only between observations with the same source, market tier, product, location, market, currency, quantity, and unit.",
        "",
        "## Scope",
        "",
        f"- **Sources:** {', '.join(sorted(source_points))}",
        f"- **Source pages:** {', '.join(source_links)}",
        f"- **Latest observation:** {latest_date:%Y-%m-%d}",
    ]
    if previous_date:
        if len(source_windows) == 1:
            lines.append(f"- **Previous comparison:** {previous_date:%Y-%m-%d}")
        else:
            for source, (source_previous, source_latest) in sorted(source_windows.items()):
                if source_previous:
                    lines.append(
                        f"- **{_markdown(source)} comparison:** "
                        f"{source_previous.observed_at:%Y-%m-%d} → {source_latest.observed_at:%Y-%m-%d}"
                    )
                else:
                    lines.append(f"- **{_markdown(source)} comparison:** no prior ISO week")
    lines.append("")
    lines.extend(
        [
            f"**Market series reported in the latest edition:** {len(latest)}",
            "",
            "## Edition-to-edition counts",
            "",
            "| Metric | Count |",
            "|---|---:|",
            f"| Price increased | {len(increases)} |",
            f"| Price decreased | {len(decreases)} |",
            f"| Range moved in opposite directions | {len(mixed)} |",
            f"| Price unchanged | {len(unchanged)} |",
            f"| Not comparable | {len(not_comparable)} |",
            f"| Newly reported market series | {len(newly_reported_keys)} |",
            f"| Returned after absence | {len(returned_keys)} |",
            f"| Not reported in latest edition | {len(not_reported_keys)} |",
            "",
        ]
    )

    def format_change(value: float | None) -> str:
        return "N/A" if value is None else f"{value:+.1f}%"

    def add_change_table(title: str, rows: Sequence[PriceComparison]) -> None:
        if not rows:
            return
        include_range = any(
            value is not None
            for row in rows
            for value in (
                row.previous.min_price,
                row.current.min_price,
                row.previous.max_price,
                row.current.max_price,
            )
        )
        include_modal = any(
            value is not None
            for row in rows
            for value in (row.previous.modal_price, row.current.modal_price)
        )
        headers = ["Source", "Tier", "Product", "Location", "Market", "Unit"]
        alignments = ["---"] * len(headers)
        if include_range:
            headers.extend(["Previous Min", "Current Min", "Min change", "Previous Max", "Current Max", "Max change"])
            alignments.extend(["---:"] * 6)
        if include_modal:
            headers.extend(["Previous Modal", "Current Modal", "Modal change"])
            alignments.extend(["---:"] * 3)
        lines.extend(
            [
                f"## {title}",
                "",
                f"| {' | '.join(headers)} |",
                f"|{'|'.join(alignments)}|",
            ]
        )
        for row in rows[:10]:
            key = row.key
            unit_context = f"{key.currency} per {key.unit_label}"
            cells = [
                _markdown(key.source),
                _markdown(key.market_chain_level),
                _markdown(key.name),
                _markdown(key.location),
                _markdown(key.marketplace),
                _markdown(unit_context),
            ]
            if include_range:
                cells.extend(
                    [
                        _price(row.previous.min_price),
                        _price(row.current.min_price),
                        format_change(row.min_change),
                        _price(row.previous.max_price),
                        _price(row.current.max_price),
                        format_change(row.max_change),
                    ]
                )
            if include_modal:
                cells.extend(
                    [
                        _price(row.previous.modal_price),
                        _price(row.current.modal_price),
                        format_change(row.modal_change),
                    ]
                )
            lines.append(f"| {' | '.join(cells)} |")
        lines.append("")

    add_change_table("Price increases", increases)
    add_change_table("Price decreases", decreases)
    add_change_table("Mixed range movements", mixed)

    if newly_reported_keys:
        lines.extend(["## Newly reported market series", ""])
        for key in newly_reported_keys:
            point = latest[key]
            lines.append(
                f"- **{_markdown(key.name)}** [{_markdown(key.source)} · {_markdown(key.market_chain_level)}] "
                f"— {_markdown(key.marketplace)}, {_markdown(key.location)}: "
                f"{_price_summary(point)} {key.currency} per {_markdown(key.unit_label)}"
            )
        lines.append("")

    if returned_keys:
        lines.extend(["## Returned after absence", ""])
        for key in returned_keys:
            point = latest[key]
            lines.append(
                f"- **{_markdown(key.name)}** [{_markdown(key.source)} · {_markdown(key.market_chain_level)}] "
                f"— {_markdown(key.marketplace)}, {_markdown(key.location)}: "
                f"{_price_summary(point)} {key.currency} per {_markdown(key.unit_label)}"
            )
        lines.append("")

    if not_reported_keys:
        lines.extend(["## Not reported in the latest edition", ""])
        lines.append("Absence means the source did not list the series in this edition; it does not prove that the product or market was removed.")
        lines.append("")
        for key in not_reported_keys:
            lines.append(
                f"- **{_markdown(key.name)}** [{_markdown(key.source)} · {_markdown(key.market_chain_level)}] "
                f"— {_markdown(key.marketplace)}, {_markdown(key.location)}"
            )
        lines.append("")

    if unchanged:
        lines.extend([f"## Unchanged ({len(unchanged)} series)", "", "<details><summary>Show series</summary>", ""])
        for row in unchanged:
            key = row.key
            point = row.current
            lines.append(
                f"- {_markdown(key.name)} [{_markdown(key.source)} · {_markdown(key.market_chain_level)}] "
                f"— {_markdown(key.marketplace)}, {_markdown(key.location)}: "
                f"{_price_summary(point)} {key.currency} per {_markdown(key.unit_label)}"
            )
        lines.extend(["", "</details>", ""])

    if not_comparable:
        lines.extend([f"## Not comparable ({len(not_comparable)} series)", ""])
        lines.append(
            "These series appeared in both editions but did not have the same numeric price measure available in both observations."
        )
        lines.append("")
        for row in not_comparable:
            key = row.key
            lines.append(
                f"- {_markdown(key.name)} [{_markdown(key.source)} · {_markdown(key.market_chain_level)}] "
                f"— {_markdown(key.marketplace)}, {_markdown(key.location)}: previous {_price_summary(row.previous)}; "
                f"current {_price_summary(row.current)}"
            )
        lines.append("")

    report_path.write_text("\n".join(lines), encoding="utf-8")
    return {
        "report_path": str(report_path),
        "price_up": len(increases),
        "price_down": len(decreases),
        "price_mixed": len(mixed),
        "price_same": len(unchanged),
        "price_not_comparable": len(not_comparable),
        "newly_reported_series": len(newly_reported_keys),
        "returned_series": len(returned_keys),
        "not_reported_series": len(not_reported_keys),
        "total_series": len(latest),
        "sources": sorted(source_points),
    }


def generate_charts(
    series: Mapping[SeriesKey, Sequence[PriceObservation]],
    charts_dir: Path = CHARTS_DIR,
) -> int:
    """Generate one flat, stable chart artifact for every chartable market series."""
    output_dir = Path(charts_dir)
    if output_dir.exists():
        for child in output_dir.iterdir():
            if child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink()
    output_dir.mkdir(parents=True, exist_ok=True)

    candidates = [
        (key, list(history))
        for key, history in series.items()
        if len(history) >= 2
        and any(
            point.min_price is not None or point.max_price is not None or point.modal_price is not None
            for point in history
        )
    ]
    candidates.sort(key=lambda item: item[0].stable_id)

    manifest_path = output_dir / "index.csv"
    with manifest_path.open("w", newline="", encoding="utf-8") as handle:
        fieldnames = [
            "file",
            "series_id",
            "source",
            "market_chain_level",
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
        for key, history in candidates:
            filename = f"{key.stable_id}.svg"
            write_price_chart(output_dir / filename, key, history)
            writer.writerow(
                {
                    "file": filename,
                    "series_id": key.stable_id,
                    "source": key.source,
                    "market_chain_level": key.market_chain_level,
                    "name": key.name,
                    "location": key.location,
                    "marketplace": key.marketplace,
                    "currency": key.currency,
                    "quantity": key.quantity,
                    "unit": key.unit,
                    "observations": len(history),
                }
            )
    return len(candidates)


def main() -> None:
    dataset = PriceDataset(SNAPSHOTS_DIR)
    stats = generate_report(dataset.observation_series())
    chart_count = generate_charts(dataset.weekly_series())
    print(json.dumps({**stats, "charts_generated": chart_count}, indent=2))


if __name__ == "__main__":
    main()
