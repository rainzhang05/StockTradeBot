from __future__ import annotations

from pathlib import Path

from stocktradebot.config import AppConfig, initialize_config, load_config, resolve_app_home


def test_resolve_app_home_prefers_explicit_path(tmp_path: Path) -> None:
    explicit_home = tmp_path / "custom-home"
    assert resolve_app_home(explicit_home) == explicit_home.resolve()


def test_initialize_config_creates_expected_paths(isolated_app_home: Path) -> None:
    config = initialize_config()

    assert config.app_home == isolated_app_home
    assert config.config_path.exists()
    assert config.database_path.parent.exists()
    assert config.artifacts_dir.exists()
    assert config.logs_dir.exists()


def test_load_config_round_trips_overrides(isolated_app_home: Path) -> None:
    config = AppConfig.default(isolated_app_home)
    config.api_port = 8123
    config.timezone = "UTC"
    config.save()

    loaded = load_config(isolated_app_home)

    assert loaded.api_port == 8123
    assert loaded.timezone == "UTC"
    assert loaded.database_path == config.database_path
