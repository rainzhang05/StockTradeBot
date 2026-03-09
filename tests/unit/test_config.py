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
    assert config.raw_payload_dir.exists()
    assert config.dataset_artifacts_dir.exists()
    assert config.model_artifacts_dir.exists()
    assert config.report_artifacts_dir.exists()


def test_load_config_round_trips_overrides(isolated_app_home: Path) -> None:
    config = AppConfig.default(isolated_app_home)
    config.api_port = 8123
    config.timezone = "UTC"
    config.data_providers.secondary_provider = "alpha_vantage"
    config.fundamentals_provider.enabled = True
    config.fundamentals_provider.symbol_to_cik = {"AAPL": "320193"}
    config.universe.max_stocks = 120
    config.model_training.feature_set_version = "daily-core-v2"
    config.model_training.training_window_days = 150
    config.model_training.commission_bps = 2.5
    config.portfolio.defensive_etf_symbol = "SHY"
    config.portfolio.symbol_sectors = {"AAPL": "Technology"}
    config.risk.allow_research_models_in_simulation = False
    config.execution.base_slippage_bps = 7.5
    config.save()

    loaded = load_config(isolated_app_home)

    assert loaded.api_port == 8123
    assert loaded.timezone == "UTC"
    assert loaded.database_path == config.database_path
    assert loaded.data_providers.secondary_provider == "alpha_vantage"
    assert loaded.fundamentals_provider.enabled is True
    assert loaded.fundamentals_provider.symbol_to_cik["AAPL"] == "0000320193"
    assert loaded.universe.max_stocks == 120
    assert loaded.model_training.feature_set_version == "daily-core-v2"
    assert loaded.model_training.training_window_days == 150
    assert loaded.model_training.commission_bps == 2.5
    assert loaded.portfolio.defensive_etf_symbol == "SHY"
    assert loaded.portfolio.symbol_sectors["AAPL"] == "Technology"
    assert loaded.risk.allow_research_models_in_simulation is False
    assert loaded.execution.base_slippage_bps == 7.5
