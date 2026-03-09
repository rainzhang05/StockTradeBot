from __future__ import annotations

from datetime import date
from pathlib import Path

from stocktradebot.config import initialize_config
from stocktradebot.models import backtest_model, model_status, train_model
from tests.fixtures.phase_data import seed_phase3_research_data


def test_train_model_and_backtest_are_reproducible(
    isolated_app_home: Path,
) -> None:
    config = initialize_config(isolated_app_home)
    seed_phase3_research_data(config)

    training_summary = train_model(config, as_of_date=date(2026, 4, 15))

    assert training_summary.run_id > 0
    assert training_summary.dataset_snapshot_id > 0
    assert training_summary.model_entry_id > 0
    assert training_summary.model_version.startswith("linear-correlation-v1-")
    assert training_summary.backtest_run_id > 0
    assert training_summary.validation_run_id > 0
    assert training_summary.metrics["total_return"] != 0.0
    assert training_summary.benchmark_metrics["benchmark_return"] != 0.0
    assert training_summary.promotion_status == "research-only"
    assert "paper_trading_history_below_required_30_days" in training_summary.promotion_reasons
    assert (config.app_home / training_summary.artifact_path).exists()

    backtest_summary = backtest_model(config, model_version=training_summary.model_version)

    assert backtest_summary.run_id > 0
    assert backtest_summary.model_version == training_summary.model_version
    assert backtest_summary.mode == "static-model"
    assert backtest_summary.total_return != 0.0
    assert backtest_summary.trade_count > 0
    assert (config.app_home / backtest_summary.artifact_path).exists()

    status = model_status(config)

    assert status["latest_model"]["version"] == training_summary.model_version
    assert status["latest_validation_run"]["fold_count"] >= 2
    assert status["latest_backtest_run"]["mode"] == "static-model"
    assert status["latest_training_run"]["model_version"] == training_summary.model_version
