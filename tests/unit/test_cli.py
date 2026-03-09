from __future__ import annotations

from datetime import date
from pathlib import Path

from typer.testing import CliRunner

from stocktradebot.cli import app
from stocktradebot.data.models import BackfillSummary

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
