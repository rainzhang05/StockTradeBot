from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any


@dataclass(slots=True, frozen=True)
class DailyBarRecord:
    provider: str
    symbol: str
    trade_date: date
    open: float
    high: float
    low: float
    close: float
    volume: int
    currency: str = "USD"
    split_adjusted: bool = False

    def field_values(self) -> dict[str, float | int]:
        return {
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
        }


@dataclass(slots=True, frozen=True)
class CorporateActionRecord:
    provider: str
    symbol: str
    ex_date: date
    action_type: str
    value: float
    currency: str = "USD"


@dataclass(slots=True, frozen=True)
class FundamentalObservationRecord:
    provider: str
    symbol: str
    metric_name: str
    source_concept: str
    fiscal_period_end: date
    fiscal_period_type: str
    filed_at: datetime
    available_at: datetime
    unit: str
    value: float
    form_type: str | None = None
    accession: str | None = None


@dataclass(slots=True, frozen=True)
class ProviderHistoryPayload:
    provider: str
    symbol: str
    domain: str
    requested_at: datetime
    request_url: str
    payload_format: str
    raw_payload: str
    bars: tuple[DailyBarRecord, ...] = ()
    corporate_actions: tuple[CorporateActionRecord, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True, frozen=True)
class FundamentalPayload:
    provider: str
    symbol: str
    domain: str
    requested_at: datetime
    request_url: str
    payload_format: str
    raw_payload: str
    observations: tuple[FundamentalObservationRecord, ...]
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True, frozen=True)
class StoredPayloadRef:
    relative_path: str
    absolute_path: Path
    checksum_sha256: str
    byte_count: int


@dataclass(slots=True, frozen=True)
class CanonicalBarRecord:
    symbol: str
    trade_date: date
    open: float
    high: float
    low: float
    close: float
    volume: int
    validation_tier: str
    primary_provider: str
    confirming_provider: str | None
    field_provenance: dict[str, str]


@dataclass(slots=True, frozen=True)
class DataQualityIncidentRecord:
    symbol: str
    trade_date: date
    domain: str
    affected_fields: tuple[str, ...]
    involved_providers: tuple[str, ...]
    observed_values: dict[str, dict[str, float | int]]
    resolution_status: str = "open"
    operator_notes: str | None = None


@dataclass(slots=True, frozen=True)
class UniverseSelectionRecord:
    symbol: str
    asset_type: str
    rank: int | None
    liquidity_score: float | None
    inclusion_reason: str
    latest_validation_tier: str


@dataclass(slots=True, frozen=True)
class UniverseSnapshotRecord:
    effective_date: date
    selection_version: str
    summary: dict[str, Any]
    members: tuple[UniverseSelectionRecord, ...]

    @property
    def stock_count(self) -> int:
        return sum(1 for member in self.members if member.asset_type == "stock")

    @property
    def etf_count(self) -> int:
        return sum(1 for member in self.members if member.asset_type == "etf")


@dataclass(slots=True, frozen=True)
class BackfillSummary:
    run_id: int
    as_of_date: date
    requested_symbols: tuple[str, ...]
    primary_provider: str
    secondary_provider: str | None
    payload_count: int
    observation_count: int
    fundamentals_payload_count: int
    fundamentals_observation_count: int
    canonical_count: int
    incident_count: int
    universe_snapshot_id: int | None
    validation_counts: dict[str, int]
    providers_used: tuple[str, ...]


@dataclass(slots=True, frozen=True)
class FeatureRowRecord:
    feature_set_version: str
    symbol: str
    trade_date: date
    universe_snapshot_id: int | None
    values: dict[str, float | None]
    fundamentals_available_at: datetime | None


@dataclass(slots=True, frozen=True)
class LabelRowRecord:
    label_version: str
    symbol: str
    trade_date: date
    values: dict[str, float | None]


@dataclass(slots=True, frozen=True)
class DatasetSnapshotSummary:
    snapshot_id: int
    as_of_date: date
    universe_snapshot_id: int | None
    feature_set_version: str
    label_version: str
    row_count: int
    null_statistics: dict[str, int]
    artifact_path: str
    metadata: dict[str, Any]
