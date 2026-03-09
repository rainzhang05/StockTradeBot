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


def repository_root() -> Path:
    return Path(__file__).resolve().parents[2]


def alembic_config(database_url: str) -> AlembicConfig:
    root = repository_root()
    config = AlembicConfig(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "alembic"))
    config.attributes["database_url"] = database_url
    return config


def create_db_engine(config: AppConfig) -> Engine:
    return create_engine(config.database_url(), future=True)


def initialize_database(config: AppConfig) -> None:
    config.ensure_runtime_dirs()
    command.upgrade(alembic_config(config.database_url()), "head")
    upsert_app_state(config, "schema_version", "phase2")


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
