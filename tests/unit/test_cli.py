from __future__ import annotations

from datetime import date
from pathlib import Path

from typer.testing import CliRunner

from stocktradebot.cli import app
from stocktradebot.data.models import BackfillSummary
from stocktradebot.models import BacktestRunSummary, TrainingRunSummary

runner = CliRunner()


def test_init_command_bootstraps_runtime(isolated_app_home: Path) -> None:
    result = runner.invoke(app, ["init"])

    assert result.exit_code == 0
    assert "Initialized StockTradeBot" in result.stdout
    assert (isolated_app_home / "config.json").exists()


def test_doctor_command_reports_all_checks(isolated_app_home: Path) -> None:
    runner.invoke(app, ["init"])

    result = runner.invoke(app, ["doctor"])

    assert result.exit_code == 0
    assert "app-home" in result.stdout
    assert "database-connectivity" in result.stdout


def test_status_command_returns_json(isolated_app_home: Path) -> None:
    runner.invoke(app, ["init"])

    result = runner.invoke(app, ["status"])

    assert result.exit_code == 0
    assert '"mode": "simulation"' in result.stdout


def test_root_command_supports_check_only(isolated_app_home: Path) -> None:
    result = runner.invoke(app, ["--check-only", "--no-browser"])

    assert result.exit_code == 0
    assert "UI: http://127.0.0.1:8000" in result.stdout


def test_backfill_command_runs_market_data_flow(
    isolated_app_home: Path,
    monkeypatch,
) -> None:
    def fake_backfill_market_data(*args, **kwargs) -> BackfillSummary:
        return BackfillSummary(
            run_id=7,
            as_of_date=date(2026, 3, 6),
            requested_symbols=("AAPL",),
            primary_provider="stooq",
            secondary_provider=None,
            payload_count=1,
            observation_count=2,
            fundamentals_payload_count=0,
            fundamentals_observation_count=0,
            canonical_count=2,
            incident_count=0,
            universe_snapshot_id=3,
            validation_counts={"provisional": 2},
            providers_used=("stooq",),
        )

    monkeypatch.setattr("stocktradebot.cli.backfill_market_data", fake_backfill_market_data)

    result = runner.invoke(app, ["backfill", "--symbol", "AAPL", "--as-of", "2026-03-06"])

    assert result.exit_code == 0
    assert '"run_id": 7' in result.stdout
    assert '"canonical_count": 2' in result.stdout


def test_train_command_runs_training_flow(
    isolated_app_home: Path,
    monkeypatch,
) -> None:
    def fake_train_model(*args, **kwargs) -> TrainingRunSummary:
        return TrainingRunSummary(
            run_id=11,
            dataset_snapshot_id=9,
            model_entry_id=4,
            model_version="linear-correlation-v1-test",
            validation_run_id=7,
            backtest_run_id=8,
            feature_set_version="daily-core-v1",
            label_version="forward-return-v1",
            artifact_path="artifacts/models/example.json",
            promotion_status="research-only",
            promotion_reasons=("paper_trading_history_below_required_30_days",),
            metrics={"total_return": 0.12},
            benchmark_metrics={"benchmark_return": 0.07},
            metadata={"fold_count": 2},
        )

    monkeypatch.setattr("stocktradebot.cli.train_model", fake_train_model)

    result = runner.invoke(app, ["train", "--as-of", "2026-03-06"])

    assert result.exit_code == 0
    assert '"run_id": 11' in result.stdout
    assert '"model_version": "linear-correlation-v1-test"' in result.stdout


def test_train_command_reports_missing_backfill_prerequisite(
    isolated_app_home: Path,
    monkeypatch,
) -> None:
    def fake_train_model(*args, **kwargs) -> TrainingRunSummary:
        raise RuntimeError("No universe snapshots are available. Run backfill first.")

    monkeypatch.setattr("stocktradebot.cli.train_model", fake_train_model)

    result = runner.invoke(app, ["train", "--as-of", "2026-03-06"])

    assert result.exit_code == 1
    assert "Run backfill first." in result.stderr


def test_backtest_command_returns_backtest_summary(
    isolated_app_home: Path,
    monkeypatch,
) -> None:
    def fake_backtest_model(*args, **kwargs) -> BacktestRunSummary:
        return BacktestRunSummary(
            run_id=12,
            model_version="linear-correlation-v1-test",
            dataset_snapshot_id=9,
            mode="static-model",
            start_date=date(2026, 2, 1),
            end_date=date(2026, 3, 6),
            benchmark_symbol="SPY",
            total_return=0.08,
            benchmark_return=0.03,
            excess_return=0.05,
            annualized_return=0.44,
            annualized_volatility=0.12,
            sharpe_ratio=1.8,
            max_drawdown=-0.04,
            turnover_ratio=0.16,
            trade_count=18,
            average_positions=2.0,
            artifact_path="artifacts/reports/example.json",
            metadata={"event_count": 20},
        )

    monkeypatch.setattr("stocktradebot.cli.backtest_model", fake_backtest_model)

    result = runner.invoke(app, ["backtest", "--model-version", "linear-correlation-v1-test"])

    assert result.exit_code == 0
    assert '"run_id": 12' in result.stdout
    assert '"mode": "static-model"' in result.stdout


def test_report_command_returns_model_status(
    isolated_app_home: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "stocktradebot.cli.model_status",
        lambda *_args, **_kwargs: {"latest_model": {"version": "linear-correlation-v1-test"}},
    )

    result = runner.invoke(app, ["report"])

    assert result.exit_code == 0
    assert '"linear-correlation-v1-test"' in result.stdout
