from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path

from alembic.config import Config as AlembicConfig
from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
    select,
)
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from alembic import command
from stocktradebot.config import AppConfig


def utc_now() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class AppState(Base):
    __tablename__ = "app_state"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    category: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False, index=True
    )


class BackfillRun(Base):
    __tablename__ = "backfill_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    requested_symbols: Mapped[str] = mapped_column(Text, nullable=False)
    primary_provider: Mapped[str] = mapped_column(String(50), nullable=False)
    secondary_provider: Mapped[str | None] = mapped_column(String(50), nullable=True)
    domain: Mapped[str] = mapped_column(String(32), nullable=False, default="daily", index=True)
    frequency: Mapped[str | None] = mapped_column(String(16), nullable=True, index=True)
    as_of_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    lookback_days: Mapped[int] = mapped_column(Integer, nullable=False)
    summary_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False, index=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ProviderPayload(Base):
    __tablename__ = "provider_payloads"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    provider: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    domain: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    request_url: Mapped[str] = mapped_column(Text, nullable=False)
    payload_format: Mapped[str] = mapped_column(String(16), nullable=False)
    payload_path: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    byte_count: Mapped[int] = mapped_column(Integer, nullable=False)
    row_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, index=True
    )


class DailyBarObservation(Base):
    __tablename__ = "daily_bar_observations"

    provider: Mapped[str] = mapped_column(String(50), primary_key=True)
    symbol: Mapped[str] = mapped_column(String(32), primary_key=True, index=True)
    trade_date: Mapped[date] = mapped_column(Date, primary_key=True, index=True)
    open: Mapped[float] = mapped_column(Float, nullable=False)
    high: Mapped[float] = mapped_column(Float, nullable=False)
    low: Mapped[float] = mapped_column(Float, nullable=False)
    close: Mapped[float] = mapped_column(Float, nullable=False)
    volume: Mapped[int] = mapped_column(BigInteger, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")
    split_adjusted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    payload_id: Mapped[int | None] = mapped_column(
        ForeignKey("provider_payloads.id"),
        nullable=True,
    )
    observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class CorporateActionObservation(Base):
    __tablename__ = "corporate_action_observations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    provider: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    ex_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    action_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    value: Mapped[float] = mapped_column(Float, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")
    payload_id: Mapped[int | None] = mapped_column(
        ForeignKey("provider_payloads.id"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class CanonicalDailyBar(Base):
    __tablename__ = "canonical_daily_bars"

    symbol: Mapped[str] = mapped_column(String(32), primary_key=True)
    trade_date: Mapped[date] = mapped_column(Date, primary_key=True, index=True)
    open: Mapped[float] = mapped_column(Float, nullable=False)
    high: Mapped[float] = mapped_column(Float, nullable=False)
    low: Mapped[float] = mapped_column(Float, nullable=False)
    close: Mapped[float] = mapped_column(Float, nullable=False)
    volume: Mapped[int] = mapped_column(BigInteger, nullable=False)
    validation_tier: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    primary_provider: Mapped[str] = mapped_column(String(50), nullable=False)
    confirming_provider: Mapped[str | None] = mapped_column(String(50), nullable=True)
    field_provenance: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )


class IntradayBarObservation(Base):
    __tablename__ = "intraday_bar_observations"

    provider: Mapped[str] = mapped_column(String(50), primary_key=True)
    symbol: Mapped[str] = mapped_column(String(32), primary_key=True, index=True)
    frequency: Mapped[str] = mapped_column(String(16), primary_key=True, index=True)
    bar_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), primary_key=True, index=True
    )
    session_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    open: Mapped[float] = mapped_column(Float, nullable=False)
    high: Mapped[float] = mapped_column(Float, nullable=False)
    low: Mapped[float] = mapped_column(Float, nullable=False)
    close: Mapped[float] = mapped_column(Float, nullable=False)
    volume: Mapped[int] = mapped_column(BigInteger, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")
    split_adjusted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    payload_id: Mapped[int | None] = mapped_column(
        ForeignKey("provider_payloads.id"), nullable=True
    )
    observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class CanonicalIntradayBar(Base):
    __tablename__ = "canonical_intraday_bars"

    symbol: Mapped[str] = mapped_column(String(32), primary_key=True)
    frequency: Mapped[str] = mapped_column(String(16), primary_key=True, index=True)
    bar_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), primary_key=True, index=True
    )
    session_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    open: Mapped[float] = mapped_column(Float, nullable=False)
    high: Mapped[float] = mapped_column(Float, nullable=False)
    low: Mapped[float] = mapped_column(Float, nullable=False)
    close: Mapped[float] = mapped_column(Float, nullable=False)
    volume: Mapped[int] = mapped_column(BigInteger, nullable=False)
    validation_tier: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    primary_provider: Mapped[str] = mapped_column(String(50), nullable=False)
    confirming_provider: Mapped[str | None] = mapped_column(String(50), nullable=True)
    field_provenance: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )


class DataQualityIncident(Base):
    __tablename__ = "data_quality_incidents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    trade_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    domain: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    affected_fields: Mapped[str] = mapped_column(Text, nullable=False)
    involved_providers: Mapped[str] = mapped_column(Text, nullable=False)
    observed_values: Mapped[str] = mapped_column(Text, nullable=False)
    resolution_status: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    operator_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, index=True
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class UniverseSnapshot(Base):
    __tablename__ = "universe_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    effective_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    stock_count: Mapped[int] = mapped_column(Integer, nullable=False)
    etf_count: Mapped[int] = mapped_column(Integer, nullable=False)
    selection_version: Mapped[str] = mapped_column(String(50), nullable=False)
    summary_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, index=True
    )


class UniverseSnapshotMember(Base):
    __tablename__ = "universe_snapshot_members"

    snapshot_id: Mapped[int] = mapped_column(
        ForeignKey("universe_snapshots.id"), primary_key=True, nullable=False
    )
    symbol: Mapped[str] = mapped_column(String(32), primary_key=True)
    asset_type: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    rank: Mapped[int | None] = mapped_column(Integer, nullable=True)
    liquidity_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    inclusion_reason: Mapped[str] = mapped_column(String(64), nullable=False)
    latest_validation_tier: Mapped[str] = mapped_column(String(20), nullable=False)


class FundamentalObservation(Base):
    __tablename__ = "fundamental_observations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    provider: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    metric_name: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    source_concept: Mapped[str] = mapped_column(String(128), nullable=False)
    fiscal_period_end: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    fiscal_period_type: Mapped[str] = mapped_column(String(16), nullable=False)
    filed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )
    unit: Mapped[str] = mapped_column(String(16), nullable=False)
    value: Mapped[float] = mapped_column(Float, nullable=False)
    form_type: Mapped[str | None] = mapped_column(String(16), nullable=True)
    accession: Mapped[str | None] = mapped_column(String(32), nullable=True)
    payload_id: Mapped[int | None] = mapped_column(
        ForeignKey("provider_payloads.id"),
        nullable=True,
    )
    observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class FeatureSetVersion(Base):
    __tablename__ = "feature_set_versions"

    version: Mapped[str] = mapped_column(String(64), primary_key=True)
    definition_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, index=True
    )


class FeatureSnapshotRow(Base):
    __tablename__ = "feature_snapshot_rows"

    feature_set_version: Mapped[str] = mapped_column(
        ForeignKey("feature_set_versions.version"),
        primary_key=True,
    )
    symbol: Mapped[str] = mapped_column(String(32), primary_key=True, index=True)
    trade_date: Mapped[date] = mapped_column(Date, primary_key=True, index=True)
    universe_snapshot_id: Mapped[int | None] = mapped_column(
        ForeignKey("universe_snapshots.id"),
        nullable=True,
    )
    values_json: Mapped[str] = mapped_column(Text, nullable=False)
    fundamentals_available_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class LabelVersion(Base):
    __tablename__ = "label_versions"

    version: Mapped[str] = mapped_column(String(64), primary_key=True)
    definition_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, index=True
    )


class LabelSnapshotRow(Base):
    __tablename__ = "label_snapshot_rows"

    label_version: Mapped[str] = mapped_column(
        ForeignKey("label_versions.version"),
        primary_key=True,
    )
    symbol: Mapped[str] = mapped_column(String(32), primary_key=True, index=True)
    trade_date: Mapped[date] = mapped_column(Date, primary_key=True, index=True)
    values_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class DatasetSnapshot(Base):
    __tablename__ = "dataset_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    as_of_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    as_of_timestamp: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    frequency: Mapped[str] = mapped_column(String(16), nullable=False, default="daily", index=True)
    universe_snapshot_id: Mapped[int | None] = mapped_column(
        ForeignKey("universe_snapshots.id"),
        nullable=True,
    )
    feature_set_version: Mapped[str] = mapped_column(
        ForeignKey("feature_set_versions.version"),
        nullable=False,
    )
    label_version: Mapped[str] = mapped_column(
        ForeignKey("label_versions.version"),
        nullable=False,
    )
    canonicalization_version: Mapped[str] = mapped_column(String(64), nullable=False)
    generation_code_version: Mapped[str] = mapped_column(String(64), nullable=False)
    row_count: Mapped[int] = mapped_column(Integer, nullable=False)
    null_statistics_json: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_json: Mapped[str] = mapped_column(Text, nullable=False)
    artifact_path: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, index=True
    )


class ModelTrainingRun(Base):
    __tablename__ = "model_training_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    as_of_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    frequency: Mapped[str] = mapped_column(String(16), nullable=False, default="daily", index=True)
    dataset_snapshot_id: Mapped[int | None] = mapped_column(
        ForeignKey("dataset_snapshots.id"),
        nullable=True,
    )
    model_family: Mapped[str] = mapped_column(String(64), nullable=False)
    model_version: Mapped[str | None] = mapped_column(String(128), nullable=True)
    summary_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, index=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ModelRegistryEntry(Base):
    __tablename__ = "model_registry_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    version: Mapped[str] = mapped_column(String(128), nullable=False, unique=True, index=True)
    family: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    frequency: Mapped[str] = mapped_column(String(16), nullable=False, default="daily", index=True)
    dataset_snapshot_id: Mapped[int] = mapped_column(
        ForeignKey("dataset_snapshots.id"),
        nullable=False,
    )
    feature_set_version: Mapped[str] = mapped_column(String(64), nullable=False)
    label_version: Mapped[str] = mapped_column(String(64), nullable=False)
    training_start_date: Mapped[date] = mapped_column(Date, nullable=False)
    training_end_date: Mapped[date] = mapped_column(Date, nullable=False)
    training_row_count: Mapped[int] = mapped_column(Integer, nullable=False)
    artifact_path: Mapped[str] = mapped_column(Text, nullable=False)
    metrics_json: Mapped[str] = mapped_column(Text, nullable=False)
    benchmark_metrics_json: Mapped[str] = mapped_column(Text, nullable=False)
    promotion_status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    promotion_reasons_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, index=True
    )


class ValidationRun(Base):
    __tablename__ = "validation_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    frequency: Mapped[str] = mapped_column(String(16), nullable=False, default="daily", index=True)
    dataset_snapshot_id: Mapped[int] = mapped_column(
        ForeignKey("dataset_snapshots.id"),
        nullable=False,
    )
    model_entry_id: Mapped[int | None] = mapped_column(
        ForeignKey("model_registry_entries.id"),
        nullable=True,
    )
    fold_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    artifact_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, index=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class BacktestRun(Base):
    __tablename__ = "backtest_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    mode: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    frequency: Mapped[str] = mapped_column(String(16), nullable=False, default="daily", index=True)
    dataset_snapshot_id: Mapped[int] = mapped_column(
        ForeignKey("dataset_snapshots.id"),
        nullable=False,
    )
    model_entry_id: Mapped[int | None] = mapped_column(
        ForeignKey("model_registry_entries.id"),
        nullable=True,
    )
    benchmark_symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    end_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    artifact_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, index=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class SystemModeState(Base):
    __tablename__ = "system_mode_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    current_mode: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    requested_mode: Mapped[str | None] = mapped_column(String(32), nullable=True)
    live_profile: Mapped[str] = mapped_column(String(32), nullable=False)
    is_frozen: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    active_freeze_event_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    freeze_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )


class ModeTransitionEvent(Base):
    __tablename__ = "mode_transition_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    previous_mode: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    new_mode: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    live_profile: Mapped[str] = mapped_column(String(32), nullable=False)
    source: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, index=True
    )


class FreezeEvent(Base):
    __tablename__ = "freeze_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    freeze_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    details_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    triggered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, index=True
    )
    cleared_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class SimulationRun(Base):
    __tablename__ = "simulation_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    mode: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    as_of_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    decision_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    model_entry_id: Mapped[int | None] = mapped_column(
        ForeignKey("model_registry_entries.id"),
        nullable=True,
    )
    dataset_snapshot_id: Mapped[int | None] = mapped_column(
        ForeignKey("dataset_snapshots.id"),
        nullable=True,
    )
    regime: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    gross_exposure_target: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    gross_exposure_actual: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    start_nav: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    end_nav: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    cash_start: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    cash_end: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    artifact_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, index=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PortfolioSnapshot(Base):
    __tablename__ = "portfolio_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    simulation_run_id: Mapped[int] = mapped_column(
        ForeignKey("simulation_runs.id"),
        nullable=False,
        index=True,
    )
    snapshot_type: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    trade_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    nav: Mapped[float] = mapped_column(Float, nullable=False)
    cash_balance: Mapped[float] = mapped_column(Float, nullable=False)
    gross_exposure: Mapped[float] = mapped_column(Float, nullable=False)
    net_exposure: Mapped[float] = mapped_column(Float, nullable=False)
    holding_count: Mapped[int] = mapped_column(Integer, nullable=False)
    turnover_ratio: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    metadata_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, index=True
    )


class PortfolioSnapshotPosition(Base):
    __tablename__ = "portfolio_snapshot_positions"

    snapshot_id: Mapped[int] = mapped_column(
        ForeignKey("portfolio_snapshots.id"),
        primary_key=True,
        nullable=False,
    )
    symbol: Mapped[str] = mapped_column(String(32), primary_key=True)
    target_weight: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    actual_weight: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    shares: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    price: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    market_value: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    sector: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    metadata_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")


class OrderIntent(Base):
    __tablename__ = "order_intents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    simulation_run_id: Mapped[int] = mapped_column(
        ForeignKey("simulation_runs.id"),
        nullable=False,
        index=True,
    )
    symbol: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    side: Mapped[str] = mapped_column(String(8), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    order_type: Mapped[str] = mapped_column(String(32), nullable=False)
    time_in_force: Mapped[str] = mapped_column(String(16), nullable=False)
    requested_shares: Mapped[float] = mapped_column(Float, nullable=False)
    requested_notional: Mapped[float] = mapped_column(Float, nullable=False)
    limit_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    reference_price: Mapped[float] = mapped_column(Float, nullable=False)
    expected_slippage_bps: Mapped[float] = mapped_column(Float, nullable=False)
    target_weight: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    metadata_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, index=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ExecutionFill(Base):
    __tablename__ = "execution_fills"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    simulation_run_id: Mapped[int] = mapped_column(
        ForeignKey("simulation_runs.id"),
        nullable=False,
        index=True,
    )
    order_intent_id: Mapped[int] = mapped_column(
        ForeignKey("order_intents.id"),
        nullable=False,
        index=True,
    )
    symbol: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    side: Mapped[str] = mapped_column(String(8), nullable=False)
    fill_status: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    filled_shares: Mapped[float] = mapped_column(Float, nullable=False)
    filled_notional: Mapped[float] = mapped_column(Float, nullable=False)
    fill_price: Mapped[float] = mapped_column(Float, nullable=False)
    commission: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    slippage_bps: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    expected_spread_bps: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    metadata_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    filled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, index=True
    )


class BrokerAccountSnapshot(Base):
    __tablename__ = "broker_account_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    simulation_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("simulation_runs.id"),
        nullable=True,
        index=True,
    )
    broker_name: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    mode: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    account_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    net_liquidation: Mapped[float] = mapped_column(Float, nullable=False)
    cash_balance: Mapped[float] = mapped_column(Float, nullable=False)
    buying_power: Mapped[float] = mapped_column(Float, nullable=False)
    available_funds: Mapped[float] = mapped_column(Float, nullable=False)
    cushion: Mapped[float | None] = mapped_column(Float, nullable=True)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, index=True
    )


class BrokerPositionSnapshot(Base):
    __tablename__ = "broker_position_snapshots"

    snapshot_id: Mapped[int] = mapped_column(
        ForeignKey("broker_account_snapshots.id"),
        primary_key=True,
        nullable=False,
    )
    symbol: Mapped[str] = mapped_column(String(32), primary_key=True)
    quantity: Mapped[float] = mapped_column(Float, nullable=False)
    market_price: Mapped[float] = mapped_column(Float, nullable=False)
    market_value: Mapped[float] = mapped_column(Float, nullable=False)
    average_cost: Mapped[float | None] = mapped_column(Float, nullable=True)
    unrealized_pnl: Mapped[float | None] = mapped_column(Float, nullable=True)
    realized_pnl: Mapped[float | None] = mapped_column(Float, nullable=True)
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="USD")
    payload_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")


class BrokerOrder(Base):
    __tablename__ = "broker_orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    simulation_run_id: Mapped[int] = mapped_column(
        ForeignKey("simulation_runs.id"),
        nullable=False,
        index=True,
    )
    order_intent_id: Mapped[int | None] = mapped_column(
        ForeignKey("order_intents.id"),
        nullable=True,
        index=True,
    )
    broker_name: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    mode: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    account_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    broker_order_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    broker_status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    approval_status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    side: Mapped[str] = mapped_column(String(8), nullable=False)
    order_type: Mapped[str] = mapped_column(String(32), nullable=False)
    time_in_force: Mapped[str] = mapped_column(String(16), nullable=False)
    requested_shares: Mapped[float] = mapped_column(Float, nullable=False)
    filled_shares: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    limit_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    average_fill_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    preview_commission: Mapped[float | None] = mapped_column(Float, nullable=True)
    warnings_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    payload_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )


class OrderApproval(Base):
    __tablename__ = "order_approvals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    simulation_run_id: Mapped[int] = mapped_column(
        ForeignKey("simulation_runs.id"),
        nullable=False,
        index=True,
    )
    order_intent_id: Mapped[int] = mapped_column(
        ForeignKey("order_intents.id"),
        nullable=False,
        index=True,
    )
    broker_order_id: Mapped[int | None] = mapped_column(
        ForeignKey("broker_orders.id"),
        nullable=True,
        index=True,
    )
    symbol: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    mode: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    requested_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    decided_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, index=True
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


def repository_root() -> Path:
    return Path(__file__).resolve().parents[2]


def package_root() -> Path:
    return Path(__file__).resolve().parent


def migration_paths() -> tuple[Path, Path]:
    packaged_ini = package_root() / "alembic.ini"
    packaged_scripts = package_root() / "alembic"
    if packaged_ini.exists() and packaged_scripts.exists():
        return packaged_ini, packaged_scripts

    root = repository_root()
    return root / "alembic.ini", root / "alembic"


def alembic_config(database_url: str) -> AlembicConfig:
    config_path, script_location = migration_paths()
    config = AlembicConfig(str(config_path))
    config.set_main_option("script_location", str(script_location))
    config.attributes["database_url"] = database_url
    return config


def create_db_engine(config: AppConfig) -> Engine:
    return create_engine(config.database_url(), future=True)


def initialize_database(config: AppConfig) -> None:
    config.ensure_runtime_dirs()
    command.upgrade(alembic_config(config.database_url()), "head")
    upsert_app_state(config, "schema_version", "phase6")
    ensure_system_mode_state(config)


def database_exists(config: AppConfig) -> bool:
    return config.database_path.exists()


def database_is_reachable(config: AppConfig) -> bool:
    if not database_exists(config):
        return False

    engine = create_db_engine(config)
    try:
        with Session(engine) as session:
            session.execute(select(1))
        return True
    finally:
        engine.dispose()


def upsert_app_state(config: AppConfig, key: str, value: str) -> None:
    engine = create_db_engine(config)
    try:
        with Session(engine) as session:
            existing = session.get(AppState, key)
            if existing is None:
                session.add(AppState(key=key, value=value))
            else:
                existing.value = value
            session.commit()
    finally:
        engine.dispose()


def read_app_state(config: AppConfig, key: str) -> str | None:
    if not database_exists(config):
        return None

    engine = create_db_engine(config)
    try:
        with Session(engine) as session:
            value = session.get(AppState, key)
            return value.value if value is not None else None
    finally:
        engine.dispose()


def record_audit_event(config: AppConfig, category: str, message: str) -> None:
    engine = create_db_engine(config)
    try:
        with Session(engine) as session:
            session.add(AuditEvent(category=category, message=message))
            session.commit()
    finally:
        engine.dispose()


def ensure_system_mode_state(config: AppConfig) -> None:
    engine = create_db_engine(config)
    try:
        with Session(engine) as session:
            existing = session.get(SystemModeState, 1)
            if existing is None:
                session.add(
                    SystemModeState(
                        id=1,
                        current_mode=config.execution.default_mode,
                        requested_mode=None,
                        live_profile=config.execution.live_profile,
                        is_frozen=False,
                        active_freeze_event_id=None,
                        freeze_reason=None,
                        metadata_json="{}",
                    )
                )
                session.commit()
    finally:
        engine.dispose()
