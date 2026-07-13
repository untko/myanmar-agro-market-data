"""Canonical snapshot storage and market-series preparation."""

from __future__ import annotations

import csv
import hashlib
import io
import re
from dataclasses import dataclass, fields
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Mapping
from urllib.parse import urlparse


def _parse_price(value: object) -> int | None:
    if value is None or str(value).strip() in {"", "-"}:
        return None
    price = int(str(value).replace(",", "").strip())
    if price < 0:
        raise ValueError("Prices must be non-negative integers")
    return price


def _format_timestamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def _validate_source_url(value: object) -> str:
    source_url = str(value or "").strip()
    parsed_url = urlparse(source_url)
    if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
        raise ValueError("Snapshot source_url must be an absolute HTTP(S) URL")
    return source_url


@dataclass(frozen=True, order=True)
class SeriesKey:
    """Everything that must remain constant within one comparable price series."""

    name: str
    location: str
    marketplace: str
    currency: str
    quantity: str
    unit: str

    @classmethod
    def from_mapping(cls, row: Mapping[str, object]) -> "SeriesKey":
        values = {field: str(row.get(field) or "").strip() for field in SERIES_FIELDS}
        empty = [field for field, value in values.items() if not value]
        if empty:
            raise ValueError(f"Series identity fields cannot be empty: {', '.join(empty)}")
        return cls(**values)

    @property
    def stable_id(self) -> str:
        identity = "\x1f".join(getattr(self, field) for field in SERIES_FIELDS)
        digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:10]
        readable = re.sub(r"[^a-z0-9]+", "-", f"{self.name}-{self.marketplace}".lower()).strip("-")
        return f"{readable[:70]}-{digest}"

    @property
    def unit_label(self) -> str:
        return " ".join(part for part in (self.quantity, self.unit) if part).strip()


@dataclass(frozen=True)
class PriceObservation:
    series: SeriesKey
    min_price: int | None
    max_price: int | None
    scraped_at: datetime
    source_url: str


SERIES_FIELDS = tuple(field.name for field in fields(SeriesKey))
SNAPSHOT_COLUMNS = (
    *SERIES_FIELDS[:3],
    "min_price",
    "max_price",
    *SERIES_FIELDS[3:],
    "scraped_at",
    "source_url",
)
REQUIRED_INPUT_FIELDS = (*SERIES_FIELDS, "min_price", "max_price", "source_url")


class PriceDataset:
    """Own immutable snapshots and expose comparable weekly price series."""

    def __init__(self, snapshots_dir: Path):
        self.snapshots_dir = Path(snapshots_dir)

    def record(
        self,
        rows: Iterable[Mapping[str, object]],
        observed_at: datetime | None = None,
    ) -> Path:
        rows = list(rows)
        if not rows:
            raise ValueError("Cannot record an empty scrape snapshot")
        observed_at = (observed_at or datetime.now(timezone.utc)).astimezone(timezone.utc)
        timestamp = _format_timestamp(observed_at)
        output_path = self.snapshots_dir / observed_at.strftime("%Y") / f"{observed_at.strftime('%Y-%m-%dT%H-%M-%SZ')}.csv"

        buffer = io.StringIO(newline="")
        writer = csv.DictWriter(buffer, fieldnames=SNAPSHOT_COLUMNS, lineterminator="\n")
        writer.writeheader()
        for source_row in rows:
            missing = [field for field in REQUIRED_INPUT_FIELDS if field not in source_row]
            if missing:
                raise ValueError(f"Snapshot row is missing required fields: {', '.join(missing)}")
            series = SeriesKey.from_mapping(source_row)
            source_url = _validate_source_url(source_row["source_url"])
            min_price = _parse_price(source_row.get("min_price"))
            max_price = _parse_price(source_row.get("max_price"))
            writer.writerow(
                {
                    "name": series.name,
                    "location": series.location,
                    "marketplace": series.marketplace,
                    "min_price": "" if min_price is None else min_price,
                    "max_price": "" if max_price is None else max_price,
                    "currency": series.currency,
                    "quantity": series.quantity,
                    "unit": series.unit,
                    "scraped_at": timestamp,
                    "source_url": source_url,
                }
            )

        contents = buffer.getvalue()
        if output_path.exists():
            if output_path.read_text(encoding="utf-8") == contents:
                return output_path
            raise ValueError(f"Snapshot {output_path} is immutable and already contains different data")

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(contents, encoding="utf-8")
        return output_path

    def load(self) -> list[PriceObservation]:
        observations: list[PriceObservation] = []
        for snapshot_path in sorted(self.snapshots_dir.glob("*/*.csv")):
            with snapshot_path.open(newline="", encoding="utf-8") as handle:
                reader = csv.DictReader(handle)
                if tuple(reader.fieldnames or ()) != SNAPSHOT_COLUMNS:
                    raise ValueError(f"Snapshot {snapshot_path} does not match the required CSV columns")
                for row in reader:
                    observations.append(
                        PriceObservation(
                            series=SeriesKey.from_mapping(row),
                            min_price=_parse_price(row.get("min_price")),
                            max_price=_parse_price(row.get("max_price")),
                            scraped_at=_parse_timestamp(row["scraped_at"]),
                            source_url=_validate_source_url(row["source_url"]),
                        )
                    )
        return sorted(observations, key=lambda item: (item.series, item.scraped_at))

    def weekly_series(self, limit: int = 52) -> dict[SeriesKey, list[PriceObservation]]:
        by_series_week: dict[SeriesKey, dict[tuple[int, int], PriceObservation]] = {}
        for observation in self.load():
            year, week, _ = observation.scraped_at.isocalendar()
            weekly = by_series_week.setdefault(observation.series, {})
            current = weekly.get((year, week))
            if current is None or observation.scraped_at > current.scraped_at:
                weekly[(year, week)] = observation

        result: dict[SeriesKey, list[PriceObservation]] = {}
        for key in sorted(by_series_week):
            history = sorted(by_series_week[key].values(), key=lambda item: item.scraped_at)
            result[key] = history[-limit:]
        return result
