"""Accessible SVG price-range charts."""

from __future__ import annotations

from decimal import Decimal
from html import escape
from pathlib import Path
from typing import Sequence
from urllib.parse import urlparse

from .dataset import PriceObservation, SeriesKey


def _number(value: Decimal | float | int) -> str:
    if isinstance(value, Decimal):
        formatted = format(value, ",f")
        return formatted.rstrip("0").rstrip(".") if "." in formatted else formatted
    return f"{value:,.0f}"


def _date_label(observation: PriceObservation) -> str:
    return observation.observed_at.strftime("%d %b").lstrip("0")


def _segments(points: Sequence[tuple[int, float, float, int]]) -> list[list[tuple[int, float, float, int]]]:
    """Split plotted points whenever an observation is missing."""
    result: list[list[tuple[int, float, float, int]]] = []
    current: list[tuple[int, float, float, int]] = []
    for point in points:
        if current and point[0] != current[-1][0] + 1:
            result.append(current)
            current = []
        current.append(point)
    if current:
        result.append(current)
    return result


def render_price_chart(key: SeriesKey, history: Sequence[PriceObservation]) -> str:
    """Render one exact market series as an accessible, publication-ready SVG."""
    if not history:
        raise ValueError("A chart requires at least one observation")

    history = sorted(history, key=lambda item: item.observed_at)
    values = [
        float(value)
        for point in history
        for value in (point.min_price, point.max_price, point.modal_price)
        if value is not None
    ]
    if not values:
        raise ValueError("A chart requires at least one numeric price")

    width, height = 960, 540
    left, right, top, bottom = 100, 150, 130, 90
    chart_width = width - left - right
    chart_height = height - top - bottom
    low, high = min(values), max(values)
    padding = max((high - low) * 0.12, high * 0.025, 1)
    y_min, y_max = max(0, low - padding), high + padding
    y_range = y_max - y_min or 1
    first_timestamp = history[0].observed_at
    elapsed_seconds = (history[-1].observed_at - first_timestamp).total_seconds()

    def x_position(index: int) -> float:
        if elapsed_seconds <= 0:
            return left + chart_width / 2
        point_seconds = (history[index].observed_at - first_timestamp).total_seconds()
        return left + (point_seconds / elapsed_seconds) * chart_width

    def week_serial(point: PriceObservation) -> int:
        return (point.observed_at.date().toordinal() - 1) // 7

    def y_position(value: Decimal | int | None) -> float | None:
        if value is None:
            return None
        return top + chart_height - ((float(value) - y_min) / y_range) * chart_height

    min_points = [
        (week_serial(point), x_position(index), y_position(point.min_price), point.min_price)
        for index, point in enumerate(history)
        if point.min_price is not None
    ]
    max_points = [
        (week_serial(point), x_position(index), y_position(point.max_price), point.max_price)
        for index, point in enumerate(history)
        if point.max_price is not None
    ]
    modal_points = [
        (week_serial(point), x_position(index), y_position(point.modal_price), point.modal_price)
        for index, point in enumerate(history)
        if point.modal_price is not None
    ]
    range_points = [
        (week_serial(point), x_position(index), y_position(point.min_price), y_position(point.max_price))
        for index, point in enumerate(history)
        if point.min_price is not None and point.max_price is not None
    ]

    title = f"{key.name} prices — {key.marketplace} market"
    unit_text = f"{key.currency} per {key.unit_label}" if key.unit_label else key.currency
    subtitle = (
        f"{key.location} · {key.source} · tier {key.market_chain_level} · {unit_text} · "
        f"{len(history)} weekly observations · "
        f"{_date_label(history[0])}–{_date_label(history[-1])} {history[-1].observed_at.year}"
    )
    description = (
        f"Available minimum, maximum, and modal {key.name} prices in {key.marketplace}, {key.location}, "
        f"from {_date_label(history[0])} to {_date_label(history[-1])} {history[-1].observed_at.year}. "
        f"Source {key.source}; market-chain level {key.market_chain_level}."
    )

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="{width}" height="{height}" role="img" aria-labelledby="chart-title chart-desc">',
        f"<title>{escape(title)}</title>",
        f'<desc id="chart-desc">{escape(description)}</desc>',
        "<style>",
        'text { font-family: Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; fill: #17212B; }',
        ".chart-title { font-size: 24px; font-weight: 650; }",
        ".subtitle { font-size: 14px; fill: #52606D; }",
        ".axis { font-size: 12px; fill: #697586; }",
        ".grid { stroke: #E5EAF0; stroke-width: 1; }",
        ".range { fill: #D9F3F0; fill-opacity: 0.72; }",
        ".maximum { stroke: #0F766E; stroke-width: 3; fill: none; }",
        ".minimum { stroke: #64748B; stroke-width: 2.25; stroke-dasharray: 7 5; fill: none; }",
        ".modal { stroke: #2563EB; stroke-width: 3; fill: none; }",
        ".point-max { fill: #FFFFFF; stroke: #0F766E; stroke-width: 2.5; }",
        ".point-min { fill: #FFFFFF; stroke: #64748B; stroke-width: 2; }",
        ".point-modal { fill: #FFFFFF; stroke: #2563EB; stroke-width: 2.5; }",
        ".direct-label { font-size: 13px; font-weight: 650; }",
        ".maximum-label { fill: #0F766E; }",
        ".minimum-label { fill: #52606D; }",
        ".combined-label { fill: #334155; }",
        ".modal-label { fill: #1D4ED8; }",
        ".source { font-size: 11px; fill: #7C8798; }",
        "</style>",
        f'<rect width="{width}" height="{height}" fill="#FFFFFF"/>',
        f'<text id="chart-title" x="{left}" y="48" class="chart-title">{escape(title)}</text>',
        f'<text x="{left}" y="76" class="subtitle">{escape(subtitle)}</text>',
    ]

    for index in range(5):
        fraction = index / 4
        y = top + fraction * chart_height
        value = y_max - fraction * y_range
        parts.append(f'<line x1="{left}" y1="{y:.1f}" x2="{left + chart_width}" y2="{y:.1f}" class="grid"/>')
        parts.append(f'<text x="{left - 15}" y="{y + 4:.1f}" text-anchor="end" class="axis">{escape(_number(value))}</text>')

    for segment in _segments(range_points):
        if len(segment) < 2:
            continue
        lower = [(x, min_y) for _, x, min_y, _ in segment]
        upper = [(x, max_y) for _, x, _, max_y in reversed(segment)]
        polygon = " ".join(f"{x:.1f},{y:.1f}" for x, y in lower + upper)
        parts.append(f'<polygon points="{polygon}" class="range"/>')

    for points, css_class in ((min_points, "minimum"), (max_points, "maximum"), (modal_points, "modal")):
        for segment in _segments(points):
            if len(segment) < 2:
                continue
            path = " ".join(
                ("M" if point_index == 0 else "L") + f" {x:.1f} {y:.1f}"
                for point_index, (_, x, y, _) in enumerate(segment)
            )
            parts.append(f'<path d="{path}" class="{css_class}"/>')

    for _, x, y, _ in min_points:
        parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4" class="point-min"/>')
    for _, x, y, _ in max_points:
        parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4.5" class="point-max"/>')
    for _, x, y, _ in modal_points:
        parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4.5" class="point-modal"/>')

    if len(history) <= 8:
        label_indexes = list(range(len(history)))
    else:
        label_indexes = sorted({*range(0, len(history), max(1, len(history) // 6)), len(history) - 1})
    for index in label_indexes:
        parts.append(f'<text x="{x_position(index):.1f}" y="{top + chart_height + 34}" text-anchor="middle" class="axis">{escape(_date_label(history[index]))}</text>')

    latest_max = max_points[-1] if max_points else None
    latest_min = min_points[-1] if min_points else None
    latest_modal = modal_points[-1] if modal_points else None
    if latest_max and latest_min and latest_max[0] == latest_min[0] and latest_max[3] == latest_min[3]:
        _, x, y, value = latest_max
        parts.append(f'<text x="{x + 15:.1f}" y="{y + 4:.1f}" class="direct-label combined-label">Minimum / maximum · {_number(value)}</text>')
    else:
        max_offset = 4
        min_offset = 4
        if latest_max and latest_min and latest_max[0] == latest_min[0] and abs(latest_max[2] - latest_min[2]) < 24:
            max_offset = -8
            min_offset = 16
        if latest_max:
            _, x, y, value = latest_max
            parts.append(f'<text x="{x + 15:.1f}" y="{y + max_offset:.1f}" class="direct-label maximum-label">Maximum · {_number(value)}</text>')
        if latest_min:
            _, x, y, value = latest_min
            parts.append(f'<text x="{x + 15:.1f}" y="{y + min_offset:.1f}" class="direct-label minimum-label">Minimum · {_number(value)}</text>')
    if latest_modal:
        _, x, y, value = latest_modal
        modal_offset = 4
        occupied = [point[2] for point in (latest_min, latest_max) if point and point[0] == latest_modal[0]]
        if any(abs(y - other_y) < 24 for other_y in occupied):
            modal_offset = 28
        parts.append(
            f'<text x="{x + 15:.1f}" y="{y + modal_offset:.1f}" '
            f'class="direct-label modal-label">Modal · {_number(value)}</text>'
        )

    source_host = (urlparse(history[-1].source_url).hostname or history[-1].source_url).removeprefix("www.")

    parts.extend(
        [
            f'<text x="28" y="{top + chart_height / 2:.1f}" text-anchor="middle" class="axis" transform="rotate(-90 28 {top + chart_height / 2:.1f})">Price ({escape(key.currency)})</text>',
            f'<text x="{left}" y="{height - 28}" class="source">Source: {escape(source_host)} · Last observation {_date_label(history[-1])} {history[-1].observed_at.year}</text>',
            "</svg>",
        ]
    )
    return "\n".join(parts)


def write_price_chart(output_path: Path, key: SeriesKey, history: Sequence[PriceObservation]) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(render_price_chart(key, history), encoding="utf-8")
    return output_path
