from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from stocktradebot.config import initialize_config
from stocktradebot.data import backfill_market_data, market_data_status
from stocktradebot.models import backtest_model, model_status, train_model
from stocktradebot.storage import initialize_database
from tests.fixtures.phase_data import (
    FakeFundamentalsProvider,
    FakePriceProvider,
    fundamentals,
    price_series,
    seed_phase3_research_data,
)


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
    assert status["latest_model"]["quality_scope"] == "research"
    assert "research_scope_models_are_not_promotable" in training_summary.promotion_reasons


def test_provisional_only_data_can_train_in_research_scope_but_not_promotion_scope(
    isolated_app_home: Path,
) -> None:
    config = initialize_config(isolated_app_home)
    config.universe.stock_candidates = ["AAPL", "MSFT"]
    config.universe.curated_etfs = ["SPY"]
    config.universe.min_history_days = 20
    config.universe.liquidity_lookback_days = 20
    config.universe.max_stocks = 2
    config.model_training.min_feature_history_days = 40
    config.model_training.dataset_lookback_days = 140
    config.model_training.training_window_days = 20
    config.model_training.validation_window_days = 10
    config.model_training.walk_forward_step_days = 10
    config.model_training.min_training_rows = 20
    config.model_training.min_validation_folds = 2
    config.model_training.rebalance_interval_days = 5
    config.save()
    initialize_database(config)

    primary = FakePriceProvider(
        "stooq",
        bars_by_symbol={
            "AAPL": price_series(
                "stooq",
                "AAPL",
                start_date=date(2025, 11, 1),
                days=180,
                starting_close=100.0,
                daily_step=0.6,
            ),
            "MSFT": price_series(
                "stooq",
                "MSFT",
                start_date=date(2025, 11, 1),
                days=180,
                starting_close=200.0,
                daily_step=0.35,
            ),
            "SPY": price_series(
                "stooq",
                "SPY",
                start_date=date(2025, 11, 1),
                days=180,
                starting_close=500.0,
                daily_step=0.25,
            ),
        },
    )
    fundamentals_provider = FakeFundamentalsProvider(
        {"AAPL": fundamentals("AAPL"), "MSFT": fundamentals("MSFT")}
    )

    backfill_market_data(
        config,
        as_of_date=date(2026, 4, 15),
        lookback_days=140,
        symbols=["AAPL", "MSFT", "SPY"],
        providers=[primary],
        fundamentals_provider=fundamentals_provider,
        primary_provider="stooq",
        secondary_provider=None,
    )

    status = market_data_status(config)
    assert status["daily_readiness"]["research_state"] == "research-capable"
    assert status["daily_readiness"]["promotion_state"] == "promotion-blocked"

    training_summary = train_model(config, as_of_date=date(2026, 4, 15), quality_scope="research")

    assert training_summary.quality_scope == "research"
    assert training_summary.metrics["total_return"] != 0.0
    assert "research_scope_models_are_not_promotable" in training_summary.promotion_reasons

    backtest_summary = backtest_model(config, model_version=training_summary.model_version)
    assert backtest_summary.quality_scope == "research"
    assert backtest_summary.trade_count > 0

    with pytest.raises(RuntimeError, match="requested quality scope"):
        train_model(config, as_of_date=date(2026, 4, 15), quality_scope="promotion")
