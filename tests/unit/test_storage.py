from __future__ import annotations

from pathlib import Path

import pytest

from stocktradebot.config import initialize_config
from stocktradebot.execution import simulation_status
from stocktradebot.storage import (
    database_exists,
    database_is_reachable,
    initialize_database,
    migration_paths,
    read_app_state,
    record_audit_event,
    upsert_app_state,
)


def test_initialize_database_runs_migrations(isolated_app_home: Path) -> None:
    config = initialize_config(isolated_app_home)

    initialize_database(config)

    assert database_exists(config)
    assert database_is_reachable(config)
    assert read_app_state(config, "schema_version") == "phase9"
    assert simulation_status(config)["mode_state"]["current_mode"] == "simulation"


def test_app_state_and_audit_events_can_be_written(isolated_app_home: Path) -> None:
    config = initialize_config(isolated_app_home)
    initialize_database(config)

    upsert_app_state(config, "mode", "simulation")
    record_audit_event(config, "test", "event recorded")

    assert read_app_state(config, "mode") == "simulation"


def test_migration_paths_prefer_packaged_assets(tmp_path: Path, monkeypatch) -> None:
    packaged_ini = tmp_path / "site-packages" / "stocktradebot" / "alembic.ini"
    packaged_ini.parent.mkdir(parents=True)
    packaged_ini.write_text("[alembic]\n", encoding="utf-8")
    packaged_scripts = packaged_ini.parent / "alembic"
    packaged_scripts.mkdir()

    monkeypatch.setattr(
        "stocktradebot.storage._packaged_resource_path",
        lambda relative_path: packaged_ini if relative_path == "alembic.ini" else packaged_scripts,
    )

    repository_ini = tmp_path / "repo" / "alembic.ini"
    repository_ini.parent.mkdir(parents=True)
    repository_ini.write_text("[alembic]\n", encoding="utf-8")
    repository_scripts = repository_ini.parent / "alembic"
    repository_scripts.mkdir()
    monkeypatch.setattr("stocktradebot.storage.repository_root", lambda: repository_ini.parent)

    assert migration_paths() == (packaged_ini, packaged_scripts)


def test_migration_paths_fall_back_to_repository_assets(tmp_path: Path, monkeypatch) -> None:
    repository_ini = tmp_path / "repo" / "alembic.ini"
    repository_ini.parent.mkdir(parents=True)
    repository_ini.write_text("[alembic]\n", encoding="utf-8")
    repository_scripts = repository_ini.parent / "alembic"
    repository_scripts.mkdir()

    monkeypatch.setattr("stocktradebot.storage._packaged_resource_path", lambda _relative: None)
    monkeypatch.setattr("stocktradebot.storage.repository_root", lambda: repository_ini.parent)

    assert migration_paths() == (repository_ini, repository_scripts)


def test_migration_paths_raise_clear_error_when_assets_are_missing(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr("stocktradebot.storage._packaged_resource_path", lambda _relative: None)
    monkeypatch.setattr("stocktradebot.storage.repository_root", lambda: tmp_path)

    with pytest.raises(FileNotFoundError, match="Alembic migration assets are missing"):
        migration_paths()
