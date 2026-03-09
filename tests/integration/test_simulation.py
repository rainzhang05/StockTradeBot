from __future__ import annotations

from datetime import date
from pathlib import Path

from stocktradebot.config import initialize_config
from stocktradebot.execution import simulate_trading_day, simulation_status
from stocktradebot.models import train_model
from tests.fixtures.phase_data import seed_phase3_research_data


def test_simulation_run_persists_orders_fills_and_snapshots(
    isolated_app_home: Path,
) -> None:
    config = initialize_config(isolated_app_home)
    seed_phase3_research_data(config)
    train_model(config, as_of_date=date(2026, 4, 15))

    summary = simulate_trading_day(config, as_of_date=date(2026, 4, 15))

    assert summary.run_id > 0
    assert summary.status == "completed"
    assert summary.regime in {"risk-on", "neutral", "risk-off"}
    assert summary.order_count > 0
    assert summary.fill_count > 0
    assert summary.target_snapshot_id is not None
    assert summary.post_trade_snapshot_id is not None
    assert (config.app_home / summary.artifact_path).exists()

    snapshot = simulation_status(config)

    assert snapshot["latest_run"]["id"] == summary.run_id
    assert snapshot["latest_target_snapshot"]["simulation_run_id"] == summary.run_id
    assert snapshot["latest_orders"]
    assert snapshot["latest_fills"]


def test_simulation_run_triggers_and_persists_freeze_on_abnormal_slippage(
    isolated_app_home: Path,
) -> None:
    config = initialize_config(isolated_app_home)
    seed_phase3_research_data(config)
    config.execution.base_slippage_bps = 80.0
    config.save()
    train_model(config, as_of_date=date(2026, 4, 15))

    summary = simulate_trading_day(config, as_of_date=date(2026, 4, 15))

    assert summary.freeze_triggered is True

    snapshot = simulation_status(config)

    assert snapshot["mode_state"]["is_frozen"] is True
    assert snapshot["active_freeze"]["freeze_type"] == "execution-slippage"
