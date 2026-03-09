from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from stocktradebot.cli import app

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


def test_placeholder_command_is_available() -> None:
    result = runner.invoke(app, ["backfill"])

    assert result.exit_code == 0
    assert "reserved for a later roadmap phase" in result.stdout
