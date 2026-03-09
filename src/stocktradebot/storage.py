from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from alembic.config import Config as AlembicConfig
from sqlalchemy import DateTime, Integer, String, Text, create_engine, select
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
    upsert_app_state(config, "schema_version", "phase1")


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
