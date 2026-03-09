from __future__ import annotations

from pathlib import Path

import pytest

from stocktradebot.config import (
    AppConfig,
    apply_config_patch,
    initialize_config,
    load_config,
    resolve_app_home,
)


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
    config.broker.enabled = True
    config.broker.paper_account_id = "DU1234567"
    config.broker.live_account_id = "U1234567"
    config.broker.gateway.base_url = "https://127.0.0.1:5000/v1/api"
    config.broker.live_manual_min_paper_days = 45
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
    assert loaded.broker.enabled is True
    assert loaded.broker.paper_account_id == "DU1234567"
    assert loaded.broker.live_account_id == "U1234567"
    assert loaded.broker.gateway.base_url == "https://127.0.0.1:5000/v1/api"
    assert loaded.broker.live_manual_min_paper_days == 45


def test_apply_config_patch_updates_nested_settings(isolated_app_home: Path) -> None:
    config = initialize_config(isolated_app_home)

    updated = apply_config_patch(
        config,
        {
            "timezone": "UTC",
            "data_providers": {
                "secondary_provider": "alpha_vantage",
                "alpha_vantage": {"enabled": True},
            },
            "fundamentals_provider": {"enabled": True, "user_agent": "StockTradeBot/phase7"},
            "broker": {
                "enabled": True,
                "paper_account_id": "DU1234567",
                "live_account_id": "U1234567",
            },
        },
    )

    reloaded = load_config(isolated_app_home)

    assert updated.timezone == "UTC"
    assert updated.data_providers.secondary_provider == "alpha_vantage"
    assert updated.data_providers.alpha_vantage.enabled is True
    assert updated.fundamentals_provider.user_agent == "StockTradeBot/phase7"
    assert reloaded.broker.enabled is True
    assert reloaded.broker.paper_account_id == "DU1234567"
    assert reloaded.broker.live_account_id == "U1234567"


def test_apply_config_patch_rejects_unknown_fields(isolated_app_home: Path) -> None:
    config = initialize_config(isolated_app_home)

    with pytest.raises(KeyError, match="Unsupported config field: invalid_field"):
        apply_config_patch(config, {"invalid_field": True})
