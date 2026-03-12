from __future__ import annotations

from datetime import date
from pathlib import Path

from typer.testing import CliRunner

from stocktradebot.cli import app
from stocktradebot.data.models import BackfillSummary
from stocktradebot.execution import (
    ModeTransitionSummary,
    SimulationRunSummary,
    TradingOperationSummary,
)
from stocktradebot.models import BacktestRunSummary, TrainingRunSummary

runner = CliRunner()


def test_init_command_bootstraps_runtime(isolated_app_home: Path) -> None:
    result = runner.invoke(app, ["init"])

    assert result.exit_code == 0
    assert "Initialized StockTradeBot" in result.stdout
    assert (isolated_app_home / "config.json").exists()
    assert (isolated_app_home / "logs" / "events.jsonl").exists()


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
    called_kwargs: dict[str, object] = {}

    def fake_backfill_market_data(*args, **kwargs) -> BackfillSummary:
        called_kwargs.update(kwargs)
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

    result = runner.invoke(
        app,
        [
            "backfill",
            "--symbol",
            "AAPL",
            "--as-of",
            "2026-03-06",
            "--full-history",
            "--historical-snapshots",
        ],
    )

    assert result.exit_code == 0
    assert '"run_id": 7' in result.stdout
    assert '"canonical_count": 2' in result.stdout
    assert called_kwargs["full_history"] is True
    assert called_kwargs["historical_snapshots"] is True


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


def test_simulate_command_returns_simulation_summary(
    isolated_app_home: Path,
    monkeypatch,
) -> None:
    def fake_simulate_trading_day(*args, **kwargs) -> SimulationRunSummary:
        return SimulationRunSummary(
            run_id=13,
            mode="simulation",
            status="completed",
            as_of_date=date(2026, 4, 15),
            decision_date=date(2026, 4, 15),
            model_version="linear-correlation-v1-test",
            dataset_snapshot_id=9,
            regime="risk-on",
            start_nav=100_000.0,
            end_nav=99_975.0,
            cash_start=100_000.0,
            cash_end=79_980.0,
            gross_exposure_target=0.2,
            gross_exposure_actual=0.199,
            turnover_ratio=0.10,
            target_snapshot_id=21,
            post_trade_snapshot_id=22,
            order_count=2,
            fill_count=2,
            freeze_triggered=False,
            artifact_path="artifacts/reports/simulation.json",
            metadata={"risk_checks": {"pretrade": [], "posttrade": []}},
        )

    monkeypatch.setattr("stocktradebot.cli.simulate_trading_day", fake_simulate_trading_day)

    result = runner.invoke(app, ["simulate", "--as-of", "2026-04-15"])

    assert result.exit_code == 0
    assert '"run_id": 13' in result.stdout
    assert '"regime": "risk-on"' in result.stdout


def test_paper_command_reports_status_by_default(
    isolated_app_home: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "stocktradebot.cli.paper_status",
        lambda *_args, **_kwargs: {
            "mode_state": {"current_mode": "simulation", "live_profile": "manual"},
            "active_freeze": None,
            "paper_safe_days": 0,
        },
    )

    result = runner.invoke(app, ["paper"])

    assert result.exit_code == 0
    assert '"paper_safe_days": 0' in result.stdout


def test_paper_command_runs_paper_flow(
    isolated_app_home: Path,
    monkeypatch,
) -> None:
    def fake_paper_trade_day(*args, **kwargs) -> SimulationRunSummary:
        return SimulationRunSummary(
            run_id=14,
            mode="paper",
            status="completed",
            as_of_date=date(2026, 4, 15),
            decision_date=date(2026, 4, 15),
            model_version="linear-correlation-v1-test",
            dataset_snapshot_id=9,
            regime="neutral",
            start_nav=100_000.0,
            end_nav=100_200.0,
            cash_start=100_000.0,
            cash_end=79_500.0,
            gross_exposure_target=0.2,
            gross_exposure_actual=0.2,
            turnover_ratio=0.12,
            target_snapshot_id=31,
            post_trade_snapshot_id=32,
            order_count=2,
            fill_count=2,
            freeze_triggered=False,
            artifact_path="artifacts/reports/paper.json",
            metadata={"broker_sync_snapshot_ids": {"pre": 1, "post": 2}},
        )

    monkeypatch.setattr("stocktradebot.cli.paper_trade_day", fake_paper_trade_day)

    result = runner.invoke(app, ["paper", "--run", "--as-of", "2026-04-15"])

    assert result.exit_code == 0
    assert '"mode": "paper"' in result.stdout
    assert '"run_id": 14' in result.stdout


def test_live_command_reports_status_by_default(
    isolated_app_home: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "stocktradebot.cli.live_status",
        lambda *_args, **_kwargs: {
            "mode_state": {"current_mode": "simulation", "live_profile": "manual"},
            "gates": {"manual": {"allowed": False}, "autonomous": {"allowed": False}},
            "latest_approvals": [],
        },
    )

    result = runner.invoke(app, ["live"])

    assert result.exit_code == 0
    assert '"current_mode": "simulation"' in result.stdout


def test_live_arm_command_returns_mode_transition(
    isolated_app_home: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "stocktradebot.cli.arm_live_mode",
        lambda *_args, **_kwargs: ModeTransitionSummary(
            previous_mode="paper",
            current_mode="live-manual",
            requested_mode="live-manual",
            live_profile="manual",
            status="armed",
            armed=True,
            reason="cli",
            metadata={"checks": []},
        ),
    )

    result = runner.invoke(app, ["live", "--arm"])

    assert result.exit_code == 0
    assert '"status": "armed"' in result.stdout
    assert '"current_mode": "live-manual"' in result.stdout


def test_live_run_and_approval_commands_return_operation_summaries(
    isolated_app_home: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "stocktradebot.cli.live_status",
        lambda *_args, **_kwargs: {
            "mode_state": {"current_mode": "live-manual", "live_profile": "manual"},
        },
    )
    monkeypatch.setattr(
        "stocktradebot.cli.prepare_live_trading_day",
        lambda *_args, **_kwargs: TradingOperationSummary(
            action="prepare-live-run",
            mode="live-manual",
            status="pending-approval",
            message="ready",
            run_id=22,
            approvals=(),
            metadata={},
        ),
    )
    monkeypatch.setattr(
        "stocktradebot.cli.approve_live_trading_run",
        lambda *_args, **_kwargs: TradingOperationSummary(
            action="approve-live-run",
            mode="live-manual",
            status="completed",
            message="approved",
            run_id=22,
            approvals=(),
            metadata={},
        ),
    )

    run_result = runner.invoke(app, ["live", "--run"])
    approve_result = runner.invoke(app, ["live", "--run", "--approve-all", "--run-id", "22"])

    assert run_result.exit_code == 0
    assert '"status": "pending-approval"' in run_result.stdout
    assert approve_result.exit_code == 0
    assert '"status": "completed"' in approve_result.stdout


def test_report_command_returns_model_status(
    isolated_app_home: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "stocktradebot.cli.model_status",
        lambda *_args, **_kwargs: {"latest_model": {"version": "linear-correlation-v1-test"}},
    )
    monkeypatch.setattr(
        "stocktradebot.cli.simulation_status",
        lambda *_args, **_kwargs: {"latest_run": {"id": 17}},
    )
    monkeypatch.setattr(
        "stocktradebot.cli.paper_status",
        lambda *_args, **_kwargs: {"latest_run": {"id": 18}},
    )
    monkeypatch.setattr(
        "stocktradebot.cli.live_status",
        lambda *_args, **_kwargs: {"latest_approvals": []},
    )

    result = runner.invoke(app, ["report"])

    assert result.exit_code == 0
    assert '"linear-correlation-v1-test"' in result.stdout
    assert '"latest_run": {' in result.stdout
