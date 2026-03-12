from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from sqlalchemy.orm import Session

from stocktradebot.config import apply_config_patch, initialize_config
from stocktradebot.data.models import BackfillSummary
from stocktradebot.models.types import BacktestRunSummary, TrainingRunSummary
from stocktradebot.storage import (
    BacktestRun,
    CanonicalDailyBar,
    DatasetSnapshot,
    ModelRegistryEntry,
    UniverseSnapshot,
    ValidationRun,
    create_db_engine,
    initialize_database,
)
from stocktradebot.strategy_modes import repair_strategy_mode_resources, strategy_mode_workspace


def test_strategy_mode_workspace_classifies_growth_profile(isolated_app_home) -> None:
    config = initialize_config(isolated_app_home)
    config = apply_config_patch(
        config,
        {
            "model_training": {
                "quality_scope": "research",
                "model_family": "linear-correlation-v1",
                "feature_set_version": "daily-alpha-v2",
                "label_version": "forward-return-v1",
                "target_label_name": "ranking_label_5d",
                "rebalance_interval_days": 3,
            },
            "portfolio": {
                "risk_on_target_positions": 20,
                "turnover_penalty": 0.10,
                "risk_off_gross_exposure": 0.35,
                "defensive_etf_symbol": None,
            },
        },
    )
    initialize_database(config)

    snapshot = strategy_mode_workspace(config, as_of_date=date(2026, 3, 12))

    assert snapshot["active_mode_key"] == "growth"
    assert snapshot["defined_mode_count"] == 1
    assert snapshot["empty_mode_count"] == 3
    growth_mode = next(item for item in snapshot["modes"] if item["key"] == "growth")
    conservative_mode = next(item for item in snapshot["modes"] if item["key"] == "conservative")
    assert growth_mode["defined"] is True
    assert growth_mode["classification"] == "current-winner"
    assert growth_mode["overall_status"] == "repair-needed"
    assert conservative_mode["defined"] is False
    assert conservative_mode["overall_status"] == "empty"


def test_strategy_mode_workspace_reports_ready_growth_resources(isolated_app_home) -> None:
    config = initialize_config(isolated_app_home)
    config = apply_config_patch(
        config,
        {
            "model_training": {
                "quality_scope": "research",
                "model_family": "linear-correlation-v1",
                "feature_set_version": "daily-alpha-v2",
                "label_version": "forward-return-v1",
                "target_label_name": "ranking_label_5d",
                "rebalance_interval_days": 3,
            },
            "portfolio": {
                "risk_on_target_positions": 20,
                "turnover_penalty": 0.10,
                "risk_off_gross_exposure": 0.35,
                "defensive_etf_symbol": None,
            },
        },
    )
    initialize_database(config)
    engine = create_db_engine(config)
    latest_trade_date = date(2026, 3, 11)
    try:
        with Session(engine) as session:
            base_snapshot_date = latest_trade_date - timedelta(days=23 * 30)
            for offset in range(24):
                session.add(
                    UniverseSnapshot(
                        effective_date=base_snapshot_date + timedelta(days=offset * 30),
                        stock_count=300,
                        etf_count=26,
                        selection_version="top-liquid-stocks-v2",
                        summary_json="{}",
                    )
                )

            start_date = latest_trade_date - timedelta(days=799)
            for offset in range(800):
                trade_date = start_date + timedelta(days=offset)
                session.add(
                    CanonicalDailyBar(
                        symbol="AAPL",
                        trade_date=trade_date,
                        open=100.0,
                        high=101.0,
                        low=99.0,
                        close=100.5,
                        volume=1_000_000,
                        validation_tier="verified",
                        primary_provider="stooq",
                        confirming_provider="yahoo",
                        field_provenance="{}",
                    )
                )

            dataset = DatasetSnapshot(
                as_of_date=latest_trade_date,
                as_of_timestamp=datetime(2026, 3, 11, 21, 0, tzinfo=UTC),
                frequency="daily",
                universe_snapshot_id=24,
                feature_set_version="daily-alpha-v2",
                label_version="forward-return-v1",
                canonicalization_version="v1",
                quality_scope="research",
                generation_code_version="test",
                row_count=2000,
                null_statistics_json="{}",
                metadata_json="{}",
                artifact_path="artifacts/datasets/growth.jsonl",
            )
            session.add(dataset)
            session.flush()

            model = ModelRegistryEntry(
                version="linear-correlation-v1-growth-test",
                family="linear-correlation-v1",
                frequency="daily",
                dataset_snapshot_id=dataset.id,
                quality_scope="research",
                feature_set_version="daily-alpha-v2",
                label_version="forward-return-v1",
                training_start_date=date(2023, 1, 1),
                training_end_date=latest_trade_date,
                training_row_count=2000,
                artifact_path="artifacts/models/growth.json",
                metrics_json='{"total_return": 0.2}',
                benchmark_metrics_json='{"benchmark_return": 0.1}',
                promotion_status="research-only",
                promotion_reasons_json='["research_scope_only"]',
            )
            session.add(model)
            session.flush()

            session.add(
                ValidationRun(
                    status="completed",
                    frequency="daily",
                    dataset_snapshot_id=dataset.id,
                    quality_scope="research",
                    model_entry_id=model.id,
                    fold_count=5,
                    artifact_path="artifacts/reports/validation.json",
                    summary_json="{}",
                    error_message=None,
                )
            )
            session.add(
                BacktestRun(
                    status="completed",
                    mode="static-model",
                    frequency="daily",
                    dataset_snapshot_id=dataset.id,
                    quality_scope="research",
                    model_entry_id=model.id,
                    benchmark_symbol="SPY",
                    start_date=date(2020, 3, 10),
                    end_date=latest_trade_date,
                    artifact_path="artifacts/reports/backtest.json",
                    summary_json='{"total_return": 0.25}',
                    error_message=None,
                )
            )
            session.commit()
    finally:
        engine.dispose()

    snapshot = strategy_mode_workspace(config, as_of_date=date(2026, 3, 12))

    growth_mode = next(item for item in snapshot["modes"] if item["key"] == "growth")
    assert snapshot["shared_resources"]["data_status"] == "ready"
    assert growth_mode["overall_status"] == "ready"
    assert growth_mode["resources"]["dataset"]["status"] == "ready"
    assert growth_mode["resources"]["model"]["status"] == "ready"
    assert growth_mode["resources"]["backtest"]["status"] == "ready"


def test_repair_strategy_mode_resources_repairs_defined_mode_only(
    isolated_app_home,
    monkeypatch,
) -> None:
    config = initialize_config(isolated_app_home)
    initialize_database(config)
    called: list[tuple[str, object]] = []

    def fake_backfill(*_args, **kwargs):
        called.append(("backfill", kwargs["full_history"]))
        return BackfillSummary(
            run_id=7,
            as_of_date=date(2026, 3, 12),
            requested_symbols=("AAPL", "MSFT"),
            primary_provider="stooq",
            secondary_provider=None,
            payload_count=2,
            observation_count=2,
            fundamentals_payload_count=0,
            fundamentals_observation_count=0,
            canonical_count=2,
            incident_count=0,
            universe_snapshot_id=1,
            validation_counts={"verified": 2},
            providers_used=("stooq", "yahoo"),
        )

    def fake_train(*_args, **_kwargs):
        called.append(("train", "growth"))
        return TrainingRunSummary(
            run_id=3,
            dataset_snapshot_id=4,
            model_entry_id=5,
            model_version="linear-correlation-v1-growth",
            validation_run_id=6,
            backtest_run_id=7,
            feature_set_version="daily-alpha-v2",
            label_version="forward-return-v1",
            artifact_path="artifacts/models/growth.json",
            promotion_status="research-only",
            promotion_reasons=("research_scope_only",),
            metrics={"total_return": 0.2},
            benchmark_metrics={"benchmark_return": 0.1},
            metadata={},
            quality_scope="research",
        )

    def fake_backtest(*_args, **_kwargs):
        called.append(("backtest", "growth"))
        return BacktestRunSummary(
            run_id=8,
            model_version="linear-correlation-v1-growth",
            dataset_snapshot_id=4,
            mode="static-model",
            start_date=date(2025, 12, 1),
            end_date=date(2026, 1, 28),
            benchmark_symbol="SPY",
            total_return=0.3,
            benchmark_return=0.1,
            excess_return=0.2,
            annualized_return=0.25,
            annualized_volatility=0.15,
            sharpe_ratio=1.2,
            max_drawdown=-0.1,
            turnover_ratio=0.05,
            trade_count=10,
            average_positions=6.0,
            artifact_path="artifacts/reports/backtest.json",
            metadata={},
            quality_scope="research",
        )

    monkeypatch.setattr("stocktradebot.strategy_modes.backfill_market_data", fake_backfill)
    monkeypatch.setattr("stocktradebot.strategy_modes.train_model", fake_train)
    monkeypatch.setattr("stocktradebot.strategy_modes.backtest_model", fake_backtest)

    summary = repair_strategy_mode_resources(config, as_of_date=date(2026, 3, 12))

    assert summary["status"] == "completed"
    assert summary["performed_full_history_backfill"] is True
    completed_modes = [item for item in summary["mode_results"] if item["status"] == "completed"]
    skipped_modes = [item for item in summary["mode_results"] if item["status"] == "skipped"]
    assert [item["key"] for item in completed_modes] == ["growth"]
    assert {item["key"] for item in skipped_modes} == {
        "conservative",
        "balanced",
        "aggressive",
    }
    assert ("backfill", True) in called
    assert ("train", "growth") in called
    assert ("backtest", "growth") in called
