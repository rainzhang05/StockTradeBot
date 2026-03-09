from __future__ import annotations

from pathlib import Path

from stocktradebot.config import initialize_config
from stocktradebot.storage import (
    database_exists,
    database_is_reachable,
    initialize_database,
    read_app_state,
    record_audit_event,
    upsert_app_state,
)


def test_initialize_database_runs_migrations(isolated_app_home: Path) -> None:
    config = initialize_config(isolated_app_home)

    initialize_database(config)

    assert database_exists(config)
    assert database_is_reachable(config)
    assert read_app_state(config, "schema_version") == "phase1"


def test_app_state_and_audit_events_can_be_written(isolated_app_home: Path) -> None:
    config = initialize_config(isolated_app_home)
    initialize_database(config)

    upsert_app_state(config, "mode", "simulation")
    record_audit_event(config, "test", "event recorded")

    assert read_app_state(config, "mode") == "simulation"
