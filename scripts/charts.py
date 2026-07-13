"""Accessible SVG price-range charts."""

from __future__ import annotations

from html import escape
from pathlib import Path
from typing import Sequence

from .dataset import PriceObservation, SeriesKey


def _number(value: float) -> str:
    return f"{value:,.0f}"


def _date_label(observation: PriceObservation) -> str:
    return observation.scraped_at.strftime("%d %b").lstrip("0")


def render_price_chart(key: SeriesKey, history: Sequence[PriceObservation]) -> str:
    """Render one exact market series as an accessible, publication-ready SVG."""
    if not history:
        raise ValueError("A chart requires at least one observation")

    history = sorted(history, key=lambda item: item.scraped_at)
    values = [
        value
        for point in history
        for value in (point.min_price, point.max_price)
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

    def x_position(index: int) -> float:
        if len(history) == 1:
            return left + chart_width / 2
        return left + index * chart_width / (len(history) - 1)

    def y_position(value: int | None) -> float | None:
        if value is None:
            return None
        return top + chart_height - ((value - y_min) / y_range) * chart_height

    min_points = [(x_position(i), y_position(point.min_price)) for i, point in enumerate(history) if point.min_price is not None]
    max_points = [(x_position(i), y_position(point.max_price)) for i, point in enumerate(history) if point.max_price is not None]

    title = f"{key.name} prices — {key.marketplace} market"
    unit_text = f"{key.currency} per {key.unit_label}" if key.unit_label else key.currency
    subtitle = f"{key.location} · {unit_text} · {_date_label(history[0])}–{_date_label(history[-1])} {history[-1].scraped_at.year}"
    description = (
        f"Minimum and maximum {key.name} prices in {key.marketplace}, {key.location}, "
        f"from {_date_label(history[0])} to {_date_label(history[-1])} {history[-1].scraped_at.year}."
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
        ".point-max { fill: #FFFFFF; stroke: #0F766E; stroke-width: 2.5; }",
        ".point-min { fill: #FFFFFF; stroke: #64748B; stroke-width: 2; }",
        ".direct-label { font-size: 13px; font-weight: 650; }",
        ".maximum-label { fill: #0F766E; }",
        ".minimum-label { fill: #52606D; }",
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

    if len(min_points) >= 2 and len(max_points) >= 2:
        polygon = " ".join(f"{x:.1f},{y:.1f}" for x, y in min_points + list(reversed(max_points)))
        parts.append(f'<polygon points="{polygon}" class="range"/>')

    for points, css_class in ((min_points, "minimum"), (max_points, "maximum")):
        if len(points) >= 2:
            path = " ".join(("M" if index == 0 else "L") + f" {x:.1f} {y:.1f}" for index, (x, y) in enumerate(points))
            parts.append(f'<path d="{path}" class="{css_class}"/>')

    for x, y in min_points:
        parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4" class="point-min"/>')
    for x, y in max_points:
        parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4.5" class="point-max"/>')

    if len(history) <= 8:
        label_indexes = list(range(len(history)))
    else:
        label_indexes = sorted({*range(0, len(history), max(1, len(history) // 6)), len(history) - 1})
    for index in label_indexes:
        parts.append(f'<text x="{x_position(index):.1f}" y="{top + chart_height + 34}" text-anchor="middle" class="axis">{escape(_date_label(history[index]))}</text>')

    if max_points:
        x, y = max_points[-1]
        latest_maximum = next(point.max_price for point in reversed(history) if point.max_price is not None)
        parts.append(f'<text x="{x + 15:.1f}" y="{y + 4:.1f}" class="direct-label maximum-label">Maximum · {_number(latest_maximum)}</text>')
    if min_points:
        x, y = min_points[-1]
        latest_minimum = next(point.min_price for point in reversed(history) if point.min_price is not None)
        parts.append(f'<text x="{x + 15:.1f}" y="{y + 4:.1f}" class="direct-label minimum-label">Minimum · {_number(latest_minimum)}</text>')

    parts.extend(
        [
            f'<text x="28" y="{top + chart_height / 2:.1f}" text-anchor="middle" class="axis" transform="rotate(-90 28 {top + chart_height / 2:.1f})">Price ({escape(key.currency)})</text>',
            f'<text x="{left}" y="{height - 28}" class="source">Source: Wisarra · Last observation {_date_label(history[-1])} {history[-1].scraped_at.year}</text>',
            "</svg>",
        ]
    )
    return "\n".join(parts)


def write_price_chart(output_path: Path, key: SeriesKey, history: Sequence[PriceObservation]) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(render_price_chart(key, history), encoding="utf-8")
    return output_path
