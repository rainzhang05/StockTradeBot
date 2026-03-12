from __future__ import annotations

from datetime import date
from pathlib import Path

from stocktradebot.config import initialize_config
from stocktradebot.research.optimize import ExperimentResult, run_research_optimization


def test_run_research_optimization_writes_ranked_report(
    tmp_path: Path,
    monkeypatch,
) -> None:
    source_app_home = tmp_path / "source-home"
    initialize_config(source_app_home)

    monkeypatch.setattr("stocktradebot.research.optimize.initialize_database", lambda _config: None)
    monkeypatch.setattr(
        "stocktradebot.research.optimize.market_data_status",
        lambda _config: {"daily_readiness": {"promotion_state": "promotion-blocked"}},
    )
    monkeypatch.setattr(
        "stocktradebot.research.optimize._latest_daily_trade_date",
        lambda _config, _quality_scope: date(2026, 3, 11),
    )
    monkeypatch.setattr(
        "stocktradebot.research.optimize._ensure_sufficient_history",
        lambda *_args: None,
    )
    monkeypatch.setattr(
        "stocktradebot.research.optimize._prepare_research_config",
        lambda *_args: None,
    )

    def fake_run_experiment(
        _config,
        *,
        label,
        experiment,
        as_of_date,
        trained_models=None,
    ):
        assert as_of_date == date(2026, 3, 11)
        assert isinstance(trained_models, dict)
        if label == "baseline":
            total_return = 0.04
            max_drawdown = -0.12
            turnover_ratio = 0.25
        else:
            total_return = 0.03
            max_drawdown = -0.10
            turnover_ratio = 0.20
            if (
                experiment.model_family == "rank-ensemble-v1"
                and experiment.rebalance_interval_days == 5
                and experiment.risk_on_target_positions == 15
                and abs(experiment.turnover_penalty - 0.10) < 1e-9
                and abs(experiment.risk_off_gross_exposure - 0.20) < 1e-9
                and experiment.defensive_etf_symbol == "IEF"
            ):
                total_return = 0.11
                max_drawdown = -0.08
                turnover_ratio = 0.14
        return ExperimentResult(
            label=label,
            config=experiment,
            success=True,
            model_version=f"{label}-model",
            backtest_run_id=1,
            total_return=total_return,
            benchmark_symbol="SPY",
            benchmark_return=0.02,
            excess_return=total_return - 0.02,
            max_drawdown=max_drawdown,
            turnover_ratio=turnover_ratio,
            trade_count=12,
            average_positions=9.5,
            artifact_path="artifacts/reports/example.json",
            duration_seconds=0.01,
        )

    monkeypatch.setattr("stocktradebot.research.optimize._run_experiment", fake_run_experiment)

    output_path = tmp_path / "report.json"
    summary = run_research_optimization(
        source_app_home=source_app_home,
        output_path=output_path,
        isolated_root=tmp_path / "isolated",
    )

    assert summary.output_path == output_path
    assert summary.best_run is not None
    assert summary.best_run.config.model_family == "rank-ensemble-v1"
    assert summary.best_run.total_return == 0.11
    assert output_path.exists()
    isolated_config = initialize_config(summary.isolated_app_home)
    assert (
        isolated_config.database_path
        == summary.isolated_app_home / "runtime" / "stocktradebot.sqlite3"
    )
    payload = summary.report_payload
    assert payload["baseline"]["total_return"] == 0.04
    assert payload["best_run"]["total_return"] == 0.11
    assert len(payload["leaderboard"]) == 486
    assert payload["winning_configuration"]["rebalance_interval_days"] == 5
    assert payload["suspected_profit_drags"][0]["category"] == "data_gating"
