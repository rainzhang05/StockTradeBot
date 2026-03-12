from __future__ import annotations

from datetime import date
from pathlib import Path

from stocktradebot.config import initialize_config
from stocktradebot.research.optimize import (
    ExperimentConfig,
    ExperimentResult,
    _select_stage_b_winner,
    run_research_optimization,
)


def _result(
    *,
    label: str,
    stage: str,
    config: ExperimentConfig,
    walk_forward_total_return: float,
    holdout_total_return: float,
    benchmark_return: float = 0.02,
    max_drawdown: float = -0.10,
    turnover_ratio: float = 0.20,
) -> ExperimentResult:
    return ExperimentResult(
        label=label,
        stage=stage,
        config=config,
        success=True,
        model_version=f"{label}-model",
        walk_forward_backtest_run_id=1,
        holdout_backtest_run_id=2,
        walk_forward_metrics={
            "run_id": 1,
            "mode": "walk-forward-validation",
            "start_date": "2025-01-01",
            "end_date": "2025-12-31",
            "benchmark_symbol": "SPY",
            "quality_scope": "research",
            "total_return": walk_forward_total_return,
            "benchmark_return": benchmark_return,
            "excess_return": walk_forward_total_return - benchmark_return,
            "annualized_return": walk_forward_total_return,
            "annualized_volatility": 0.12,
            "sharpe_ratio": 1.4,
            "max_drawdown": max_drawdown,
            "turnover_ratio": turnover_ratio,
            "trade_count": 12,
            "average_positions": 9.5,
            "artifact_path": "artifacts/reports/walk-forward.json",
            "metadata": {},
        },
        holdout_metrics={
            "run_id": 2,
            "mode": "static-model",
            "start_date": "2025-11-01",
            "end_date": "2025-12-31",
            "benchmark_symbol": "SPY",
            "quality_scope": "research",
            "total_return": holdout_total_return,
            "benchmark_return": benchmark_return,
            "excess_return": holdout_total_return - benchmark_return,
            "annualized_return": holdout_total_return,
            "annualized_volatility": 0.11,
            "sharpe_ratio": 1.5,
            "max_drawdown": max_drawdown,
            "turnover_ratio": turnover_ratio,
            "trade_count": 8,
            "average_positions": 8.0,
            "artifact_path": "artifacts/reports/holdout.json",
            "metadata": {},
        },
        duration_seconds=0.01,
    )


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
        stage,
        experiment,
        as_of_date,
        trained_models=None,
    ):
        assert as_of_date == date(2026, 3, 11)
        assert isinstance(trained_models, dict)
        if label == "baseline":
            return _result(
                label=label,
                stage=stage,
                config=experiment,
                walk_forward_total_return=0.04,
                holdout_total_return=0.03,
                max_drawdown=-0.12,
                turnover_ratio=0.25,
            )
        if (
            stage == "stage-c"
            and experiment.model_family == "rank-ensemble-v1"
            and experiment.rebalance_interval_days == 5
            and experiment.risk_on_target_positions == 15
            and abs(experiment.turnover_penalty - 0.10) < 1e-9
            and abs(experiment.risk_off_gross_exposure - 0.20) < 1e-9
            and experiment.defensive_etf_symbol == "IEF"
        ):
            return _result(
                label=label,
                stage=stage,
                config=experiment,
                walk_forward_total_return=0.11,
                holdout_total_return=0.09,
                max_drawdown=-0.08,
                turnover_ratio=0.14,
            )
        if stage == "stage-b" and experiment.model_family == "rank-ensemble-v1":
            return _result(
                label=label,
                stage=stage,
                config=experiment,
                walk_forward_total_return=0.09,
                holdout_total_return=0.08,
                max_drawdown=-0.09,
                turnover_ratio=0.18,
            )
        return _result(
            label=label,
            stage=stage,
            config=experiment,
            walk_forward_total_return=0.03,
            holdout_total_return=0.025,
            max_drawdown=-0.10,
            turnover_ratio=0.20,
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
    assert summary.best_run.walk_forward_total_return == 0.11
    assert output_path.exists()
    assert summary.applied_source_config is not None
    assert summary.applied_source_config["model_family"] == "rank-ensemble-v1"
    isolated_config = initialize_config(summary.isolated_app_home)
    assert (
        isolated_config.database_path
        == summary.isolated_app_home / "runtime" / "stocktradebot.sqlite3"
    )
    payload = summary.report_payload
    assert payload["baseline"]["walk_forward_metrics"]["total_return"] == 0.04
    assert payload["best_run"]["walk_forward_metrics"]["total_return"] == 0.11
    assert payload["activation"]["activated"] is True
    assert len(payload["leaderboard"]) == 222
    assert payload["winning_configuration"]["rebalance_interval_days"] == 5
    assert payload["suspected_profit_drags"][0]["category"] == "data_gating"


def test_stage_b_stability_rule_prefers_linear_when_nonlinear_gain_is_small() -> None:
    linear_config = ExperimentConfig(
        quality_scope="research",
        model_family="linear-correlation-v1",
        feature_set_version="daily-alpha-v2",
        label_version="forward-excess-v2",
        target_label_name="ranking_label_5d_excess",
        rebalance_interval_days=3,
        risk_on_target_positions=20,
        turnover_penalty=0.10,
        risk_off_gross_exposure=0.35,
        defensive_etf_symbol=None,
    )
    nonlinear_config = ExperimentConfig(
        quality_scope="research",
        model_family="gradient-boosting-v1",
        feature_set_version="daily-alpha-v2",
        label_version="forward-excess-v2",
        target_label_name="ranking_label_5d_excess",
        rebalance_interval_days=3,
        risk_on_target_positions=20,
        turnover_penalty=0.10,
        risk_off_gross_exposure=0.35,
        defensive_etf_symbol=None,
    )
    linear_result = _result(
        label="stage-b-001",
        stage="stage-b",
        config=linear_config,
        walk_forward_total_return=0.080,
        holdout_total_return=0.060,
    )
    nonlinear_result = _result(
        label="stage-b-002",
        stage="stage-b",
        config=nonlinear_config,
        walk_forward_total_return=0.095,
        holdout_total_return=0.068,
    )

    winner, stability_rule = _select_stage_b_winner([linear_result, nonlinear_result])

    assert winner == linear_result
    assert stability_rule["applied"] is True
    assert stability_rule["preferred_model_family"] == "linear-correlation-v1"
