"""Canonical snapshot storage and market-series preparation."""

from __future__ import annotations

import csv
import hashlib
import io
import re
from dataclasses import dataclass, fields
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Iterable, Mapping
from urllib.parse import urlparse


MARKET_CHAIN_LEVELS = frozenset({"farmgate", "wholesale", "retail", "fob_export", "unspecified"})


def _parse_price(value: object) -> Decimal | None:
    if value is None or str(value).strip() in {"", "-"}:
        return None
    try:
        price = Decimal(str(value).replace(",", "").strip())
    except InvalidOperation as error:
        raise ValueError("Prices must be non-negative decimal numbers") from error
    if not price.is_finite() or price < 0:
        raise ValueError("Prices must be non-negative decimal numbers")
    return price


def _format_price(value: Decimal | None) -> str:
    return "" if value is None else format(value, "f")


def _format_timestamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _coerce_timestamp(value: object, field_name: str) -> datetime:
    if isinstance(value, datetime):
        timestamp = value
    else:
        try:
            timestamp = datetime.fromisoformat(str(value or "").strip().replace("Z", "+00:00"))
        except ValueError as error:
            raise ValueError(f"Snapshot {field_name} must be an ISO 8601 timestamp") from error
    if timestamp.tzinfo is None:
        raise ValueError(f"Snapshot {field_name} must include a timezone")
    return timestamp.astimezone(timezone.utc)


def _validate_source_url(value: object) -> str:
    source_url = str(value or "").strip()
    parsed_url = urlparse(source_url)
    if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
        raise ValueError("Snapshot source_url must be an absolute HTTP(S) URL")
    return source_url


@dataclass(frozen=True, order=True)
class SeriesKey:
    """Everything that must remain constant within one comparable price series."""

    source: str
    name: str
    location: str
    marketplace: str
    market_chain_level: str
    currency: str
    quantity: str
    unit: str

    @classmethod
    def from_mapping(cls, row: Mapping[str, object]) -> "SeriesKey":
        values = {field: str(row.get(field) or "").strip() for field in SERIES_FIELDS}
        empty = [field for field, value in values.items() if not value]
        if empty:
            raise ValueError(f"Series identity fields cannot be empty: {', '.join(empty)}")
        if values["market_chain_level"] not in MARKET_CHAIN_LEVELS:
            allowed = ", ".join(sorted(MARKET_CHAIN_LEVELS))
            raise ValueError(f"Snapshot market_chain_level must be one of: {allowed}")
        return cls(**values)

    @property
    def stable_id(self) -> str:
        identity = "\x1f".join(getattr(self, field) for field in SERIES_FIELDS)
        digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:10]
        readable = re.sub(
            r"[^a-z0-9]+",
            "-",
            f"{self.source}-{self.name}-{self.marketplace}-{self.market_chain_level}".lower(),
        ).strip("-")
        return f"{readable[:70]}-{digest}"

    @property
    def unit_label(self) -> str:
        return " ".join(part for part in (self.quantity, self.unit) if part).strip()


@dataclass(frozen=True)
class PriceObservation:
    series: SeriesKey
    min_price: Decimal | None
    max_price: Decimal | None
    modal_price: Decimal | None
    observed_at: datetime
    collected_at: datetime
    source_record_id: str
    source_url: str


SERIES_FIELDS = tuple(field.name for field in fields(SeriesKey))
SNAPSHOT_COLUMNS = (
    "source",
    "source_record_id",
    "name",
    "location",
    "marketplace",
    "market_chain_level",
    "min_price",
    "max_price",
    "modal_price",
    "currency",
    "quantity",
    "unit",
    "observed_at",
    "collected_at",
    "source_url",
)
REQUIRED_INPUT_FIELDS = (
    *SERIES_FIELDS,
    "source_record_id",
    "min_price",
    "max_price",
    "modal_price",
    "observed_at",
    "source_url",
)


class PriceDataset:
    """Own immutable snapshots and expose comparable weekly price series."""

    def __init__(self, snapshots_dir: Path):
        self.snapshots_dir = Path(snapshots_dir)

    def record(
        self,
        rows: Iterable[Mapping[str, object]],
        collected_at: datetime | None = None,
    ) -> Path:
        rows = list(rows)
        if not rows:
            raise ValueError("Cannot record an empty scrape snapshot")
        collected_at = _coerce_timestamp(collected_at or datetime.now(timezone.utc), "collected_at")
        collection_timestamp = _format_timestamp(collected_at)
        output_path = self.snapshots_dir / collected_at.strftime("%Y") / f"{collected_at.strftime('%Y-%m-%dT%H-%M-%SZ')}.csv"

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
            modal_price = _parse_price(source_row.get("modal_price"))
            observed_at = _coerce_timestamp(source_row.get("observed_at"), "observed_at")
            writer.writerow(
                {
                    "source": series.source,
                    "source_record_id": str(source_row.get("source_record_id") or "").strip(),
                    "name": series.name,
                    "location": series.location,
                    "marketplace": series.marketplace,
                    "market_chain_level": series.market_chain_level,
                    "min_price": _format_price(min_price),
                    "max_price": _format_price(max_price),
                    "modal_price": _format_price(modal_price),
                    "currency": series.currency,
                    "quantity": series.quantity,
                    "unit": series.unit,
                    "observed_at": _format_timestamp(observed_at),
                    "collected_at": collection_timestamp,
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
                            modal_price=_parse_price(row.get("modal_price")),
                            observed_at=_coerce_timestamp(row.get("observed_at"), "observed_at"),
                            collected_at=_coerce_timestamp(row.get("collected_at"), "collected_at"),
                            source_record_id=str(row.get("source_record_id") or "").strip(),
                            source_url=_validate_source_url(row["source_url"]),
                        )
                    )
        return sorted(observations, key=lambda item: (item.series, item.observed_at, item.collected_at))

    def weekly_series(self, limit: int = 52) -> dict[SeriesKey, list[PriceObservation]]:
        by_series_week: dict[SeriesKey, dict[tuple[int, int], PriceObservation]] = {}
        for observation in self.load():
            year, week, _ = observation.observed_at.isocalendar()
            weekly = by_series_week.setdefault(observation.series, {})
            current = weekly.get((year, week))
            if current is None or (observation.observed_at, observation.collected_at) > (
                current.observed_at,
                current.collected_at,
            ):
                weekly[(year, week)] = observation

        result: dict[SeriesKey, list[PriceObservation]] = {}
        for key in sorted(by_series_week):
            history = sorted(by_series_week[key].values(), key=lambda item: (item.observed_at, item.collected_at))
            result[key] = history[-limit:]
        return result

    def observation_series(self) -> dict[SeriesKey, list[PriceObservation]]:
        """Group every collected observation by its exact market-series identity."""
        result: dict[SeriesKey, list[PriceObservation]] = {}
        for observation in self.load():
            result.setdefault(observation.series, []).append(observation)
        return result

    def latest_observed_date(self, source: str) -> date | None:
        """Return the latest published calendar date stored for one source."""
        dates = [
            observation.observed_at.date()
            for observation in self.load()
            if observation.series.source == source
        ]
        return max(dates, default=None)
