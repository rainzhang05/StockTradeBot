from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from datetime import UTC, date, datetime
from itertools import product
from pathlib import Path
from time import monotonic
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from stocktradebot.config import AppConfig, initialize_config
from stocktradebot.data import backfill_market_data, market_data_status
from stocktradebot.models import backtest_model, train_model
from stocktradebot.storage import (
    BacktestRun,
    CanonicalDailyBar,
    UniverseSnapshot,
    create_db_engine,
    initialize_database,
    repository_root,
)

MODEL_FAMILIES: tuple[str, ...] = (
    "linear-correlation-v1",
    "gradient-boosting-v1",
    "rank-ensemble-v1",
)
REBALANCE_INTERVALS: tuple[int, ...] = (1, 3, 5)
RISK_ON_TARGET_POSITIONS: tuple[int, ...] = (10, 15, 20)
TURNOVER_PENALTIES: tuple[float, ...] = (0.10, 0.20, 0.35)
RISK_OFF_GROSS_EXPOSURES: tuple[float, ...] = (0.00, 0.20, 0.35)
DEFENSIVE_ETF_SYMBOLS: tuple[str | None, ...] = (None, "IEF")


def _timestamp_token() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")


@dataclass(slots=True, frozen=True)
class ExperimentConfig:
    model_family: str
    rebalance_interval_days: int
    risk_on_target_positions: int
    turnover_penalty: float
    risk_off_gross_exposure: float
    defensive_etf_symbol: str | None
    quality_scope: str = "research"

    def to_dict(self) -> dict[str, Any]:
        return {
            "quality_scope": self.quality_scope,
            "model_family": self.model_family,
            "rebalance_interval_days": self.rebalance_interval_days,
            "risk_on_target_positions": self.risk_on_target_positions,
            "turnover_penalty": self.turnover_penalty,
            "risk_off_gross_exposure": self.risk_off_gross_exposure,
            "defensive_etf_symbol": self.defensive_etf_symbol or "none",
        }


@dataclass(slots=True, frozen=True)
class ExperimentResult:
    label: str
    config: ExperimentConfig
    success: bool
    model_version: str | None
    backtest_run_id: int | None
    total_return: float | None
    benchmark_symbol: str | None
    benchmark_return: float | None
    excess_return: float | None
    max_drawdown: float | None
    turnover_ratio: float | None
    trade_count: int | None
    average_positions: float | None
    artifact_path: str | None
    duration_seconds: float
    error_message: str | None = None

    def ranking_key(self) -> tuple[float, float, float, str]:
        total_return = -self.total_return if self.total_return is not None else float("inf")
        drawdown = abs(self.max_drawdown) if self.max_drawdown is not None else float("inf")
        turnover = self.turnover_ratio if self.turnover_ratio is not None else float("inf")
        return (total_return, drawdown, turnover, self.label)

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "config": self.config.to_dict(),
            "success": self.success,
            "model_version": self.model_version,
            "backtest_run_id": self.backtest_run_id,
            "total_return": self.total_return,
            "benchmark_symbol": self.benchmark_symbol,
            "benchmark_return": self.benchmark_return,
            "excess_return": self.excess_return,
            "max_drawdown": self.max_drawdown,
            "turnover_ratio": self.turnover_ratio,
            "trade_count": self.trade_count,
            "average_positions": self.average_positions,
            "artifact_path": self.artifact_path,
            "duration_seconds": self.duration_seconds,
            "error_message": self.error_message,
        }


@dataclass(slots=True, frozen=True)
class OptimizationRunSummary:
    output_path: Path
    source_app_home: Path
    isolated_app_home: Path
    as_of_date: date
    baseline: ExperimentResult
    best_run: ExperimentResult | None
    leaderboard: tuple[ExperimentResult, ...]
    report_payload: dict[str, Any]


def _default_source_app_home() -> Path:
    return Path.home() / ".stocktradebot"


def _default_output_path() -> Path:
    root = repository_root() / "artifacts" / "reports"
    root.mkdir(parents=True, exist_ok=True)
    return root / f"research-optimization-{_timestamp_token()}.json"


def _copy_source_app_home(
    source_app_home: Path,
    *,
    isolated_root: Path | None = None,
) -> Path:
    if not source_app_home.exists():
        raise RuntimeError(f"Source app home does not exist: {source_app_home}")

    base_dir = isolated_root or (repository_root() / "artifacts" / "research-optimize")
    run_root = base_dir / _timestamp_token()
    isolated_app_home = run_root / "app-home"
    isolated_app_home.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source_app_home, isolated_app_home)
    return isolated_app_home


def _initialize_isolated_config(isolated_app_home: Path) -> AppConfig:
    config = initialize_config(isolated_app_home)
    defaults = AppConfig.default(isolated_app_home)
    config.database_path = defaults.database_path
    config.artifacts_dir = defaults.artifacts_dir
    config.logs_dir = defaults.logs_dir
    config.save()
    return config


def _latest_daily_trade_date(config: AppConfig, quality_scope: str) -> date:
    allowed_tiers = ("verified",) if quality_scope == "promotion" else ("verified", "provisional")
    engine = create_db_engine(config)
    try:
        with Session(engine) as session:
            latest = session.scalar(
                select(func.max(CanonicalDailyBar.trade_date)).where(
                    CanonicalDailyBar.validation_tier.in_(allowed_tiers)
                )
            )
    finally:
        engine.dispose()
    if latest is None:
        raise RuntimeError("No canonical daily bars are available in the source app home.")
    return latest


def _available_daily_trade_dates(config: AppConfig, quality_scope: str) -> int:
    allowed_tiers = ("verified",) if quality_scope == "promotion" else ("verified", "provisional")
    engine = create_db_engine(config)
    try:
        with Session(engine) as session:
            count = session.scalar(
                select(func.count(func.distinct(CanonicalDailyBar.trade_date))).where(
                    CanonicalDailyBar.validation_tier.in_(allowed_tiers)
                )
            )
    finally:
        engine.dispose()
    return int(count or 0)


def _required_daily_trade_dates(config: AppConfig) -> int:
    return (
        config.model_training.min_feature_history_days
        + config.model_training.training_window_days
        + config.model_training.validation_window_days * config.model_training.min_validation_folds
        + config.model_training.walk_forward_step_days
    )


def _minimum_research_trade_dates(config: AppConfig) -> int:
    # Keep at least roughly three years of daily history available for long-range research runs.
    return max(_required_daily_trade_dates(config), 252 * 3)


def _prepare_research_config(config: AppConfig) -> None:
    minimum_dataset_lookback_days = max(
        config.model_training.dataset_lookback_days,
        _minimum_research_trade_dates(config) * 2,
    )
    if config.model_training.dataset_lookback_days < minimum_dataset_lookback_days:
        config.model_training.dataset_lookback_days = minimum_dataset_lookback_days
        config.save()


def _available_universe_snapshot_dates(config: AppConfig, as_of_date: date) -> int:
    engine = create_db_engine(config)
    try:
        with Session(engine) as session:
            count = session.scalar(
                select(func.count(func.distinct(UniverseSnapshot.effective_date))).where(
                    UniverseSnapshot.effective_date <= as_of_date
                )
            )
    finally:
        engine.dispose()
    return int(count or 0)


def _ensure_sufficient_history(config: AppConfig, as_of_date: date) -> None:
    required_trade_dates = _minimum_research_trade_dates(config)
    available_trade_dates = _available_daily_trade_dates(config, "research")
    available_snapshot_dates = _available_universe_snapshot_dates(config, as_of_date)
    minimum_snapshot_dates = 12
    if (
        available_trade_dates >= required_trade_dates
        and available_snapshot_dates >= minimum_snapshot_dates
    ):
        return
    backfill_market_data(
        config,
        as_of_date=as_of_date,
        lookback_days=required_trade_dates,
        full_history=True,
        historical_snapshots=True,
    )


def _load_backtest_report(
    config: AppConfig, backtest_run_id: int
) -> tuple[str | None, dict[str, Any]]:
    engine = create_db_engine(config)
    try:
        with Session(engine) as session:
            run = session.get(BacktestRun, backtest_run_id)
            if run is None:
                raise RuntimeError(f"Backtest run {backtest_run_id} was not found.")
            if run.status != "completed":
                raise RuntimeError(
                    f"Backtest run {backtest_run_id} did not complete successfully: {run.status}"
                )
            return run.artifact_path, json.loads(run.summary_json or "{}")
    finally:
        engine.dispose()


def _baseline_config(config: AppConfig) -> ExperimentConfig:
    return ExperimentConfig(
        quality_scope="research",
        model_family="linear-correlation-v1",
        rebalance_interval_days=1,
        risk_on_target_positions=config.portfolio.risk_on_target_positions,
        turnover_penalty=config.portfolio.turnover_penalty,
        risk_off_gross_exposure=config.portfolio.risk_off_gross_exposure,
        defensive_etf_symbol=config.portfolio.defensive_etf_symbol,
    )


def _sweep_configs() -> list[ExperimentConfig]:
    return [
        ExperimentConfig(
            quality_scope="research",
            model_family=model_family,
            rebalance_interval_days=rebalance_interval_days,
            risk_on_target_positions=risk_on_target_positions,
            turnover_penalty=turnover_penalty,
            risk_off_gross_exposure=risk_off_gross_exposure,
            defensive_etf_symbol=defensive_etf_symbol,
        )
        for (
            model_family,
            rebalance_interval_days,
            risk_on_target_positions,
            turnover_penalty,
            risk_off_gross_exposure,
            defensive_etf_symbol,
        ) in product(
            MODEL_FAMILIES,
            REBALANCE_INTERVALS,
            RISK_ON_TARGET_POSITIONS,
            TURNOVER_PENALTIES,
            RISK_OFF_GROSS_EXPOSURES,
            DEFENSIVE_ETF_SYMBOLS,
        )
    ]


def _apply_experiment_config(config: AppConfig, experiment: ExperimentConfig) -> None:
    config.model_training.quality_scope = experiment.quality_scope
    config.model_training.model_family = experiment.model_family
    config.model_training.rebalance_interval_days = experiment.rebalance_interval_days
    config.model_training.target_portfolio_size = experiment.risk_on_target_positions
    config.portfolio.risk_on_target_positions = experiment.risk_on_target_positions
    config.portfolio.turnover_penalty = experiment.turnover_penalty
    config.portfolio.risk_off_gross_exposure = experiment.risk_off_gross_exposure
    config.portfolio.defensive_etf_symbol = experiment.defensive_etf_symbol
    config.save()


def _run_experiment(
    config: AppConfig,
    *,
    label: str,
    experiment: ExperimentConfig,
    as_of_date: date,
    trained_models: dict[str, str] | None = None,
) -> ExperimentResult:
    _apply_experiment_config(config, experiment)
    started = monotonic()
    model_cache = {} if trained_models is None else trained_models
    try:
        model_version = model_cache.get(experiment.model_family)
        if model_version is None:
            training_summary = train_model(
                config,
                as_of_date=as_of_date,
                quality_scope=experiment.quality_scope,
            )
            model_version = training_summary.model_version
            model_cache[experiment.model_family] = model_version

        backtest_summary = backtest_model(config, model_version=model_version)
        result = ExperimentResult(
            label=label,
            config=experiment,
            success=True,
            model_version=model_version,
            backtest_run_id=backtest_summary.run_id,
            total_return=backtest_summary.total_return,
            benchmark_symbol=backtest_summary.benchmark_symbol,
            benchmark_return=backtest_summary.benchmark_return,
            excess_return=backtest_summary.excess_return,
            max_drawdown=backtest_summary.max_drawdown,
            turnover_ratio=backtest_summary.turnover_ratio,
            trade_count=backtest_summary.trade_count,
            average_positions=backtest_summary.average_positions,
            artifact_path=backtest_summary.artifact_path,
            duration_seconds=monotonic() - started,
        )
    except Exception as exc:
        result = ExperimentResult(
            label=label,
            config=experiment,
            success=False,
            model_version=None,
            backtest_run_id=None,
            total_return=None,
            benchmark_symbol=None,
            benchmark_return=None,
            excess_return=None,
            max_drawdown=None,
            turnover_ratio=None,
            trade_count=None,
            average_positions=None,
            artifact_path=None,
            duration_seconds=monotonic() - started,
            error_message=str(exc),
        )
    return result


def _sorted_leaderboard(results: list[ExperimentResult]) -> list[ExperimentResult]:
    successes = sorted(
        (result for result in results if result.success), key=lambda item: item.ranking_key()
    )
    failures = sorted(
        (result for result in results if not result.success),
        key=lambda item: (item.error_message or "", item.label),
    )
    return [*successes, *failures]


def _best_result(results: list[ExperimentResult]) -> ExperimentResult | None:
    successful = [result for result in results if result.success]
    if not successful:
        return None
    return min(successful, key=lambda item: item.ranking_key())


def _suspected_profit_drags(
    *,
    market_status_snapshot: dict[str, Any],
    baseline: ExperimentResult,
    best_run: ExperimentResult | None,
) -> list[dict[str, str]]:
    drags: list[dict[str, str]] = []
    daily_readiness = dict(market_status_snapshot.get("daily_readiness", {}))
    if daily_readiness.get("promotion_state") == "promotion-blocked":
        drags.append(
            {
                "category": "data_gating",
                "detail": (
                    "The source runtime has provisional daily bars but no verified daily bars, "
                    "so the pre-change verified-only daily pipeline could not train, backtest, "
                    "or promote models."
                ),
            }
        )

    if best_run is None or not best_run.success:
        return drags

    if best_run.config.model_family != baseline.config.model_family:
        drags.append(
            {
                "category": "model_family",
                "detail": (
                    f"Switching from {baseline.config.model_family} to "
                    f"{best_run.config.model_family} improved total return."
                ),
            }
        )
    if best_run.config.rebalance_interval_days != baseline.config.rebalance_interval_days:
        drags.append(
            {
                "category": "rebalance_frequency",
                "detail": (
                    f"Using a {best_run.config.rebalance_interval_days}-day rebalance "
                    "interval outperformed the baseline "
                    f"{baseline.config.rebalance_interval_days}-day cadence."
                ),
            }
        )

    portfolio_changes: list[str] = []
    if best_run.config.risk_on_target_positions != baseline.config.risk_on_target_positions:
        portfolio_changes.append(
            f"risk_on_target_positions={best_run.config.risk_on_target_positions}"
        )
    if abs(best_run.config.turnover_penalty - baseline.config.turnover_penalty) > 1e-9:
        portfolio_changes.append(f"turnover_penalty={best_run.config.turnover_penalty:.2f}")
    if (
        abs(best_run.config.risk_off_gross_exposure - baseline.config.risk_off_gross_exposure)
        > 1e-9
    ):
        portfolio_changes.append(
            f"risk_off_gross_exposure={best_run.config.risk_off_gross_exposure:.2f}"
        )
    if best_run.config.defensive_etf_symbol != baseline.config.defensive_etf_symbol:
        portfolio_changes.append(
            f"defensive_etf_symbol={best_run.config.defensive_etf_symbol or 'none'}"
        )
    if portfolio_changes:
        drags.append(
            {
                "category": "portfolio_risk_settings",
                "detail": (
                    "Portfolio sizing and risk settings were profit-relevant. "
                    + ", ".join(portfolio_changes)
                    + " beat the baseline configuration."
                ),
            }
        )

    if not drags:
        drags.append(
            {
                "category": "implementation_mismatch",
                "detail": (
                    "The main drag was the prior backtest and promotion pipeline mismatch: "
                    "research could not run on provisional daily data, and the legacy backtest "
                    "did not fully match execution-path portfolio construction."
                ),
            }
        )
    return drags


def run_research_optimization(
    *,
    source_app_home: Path | None = None,
    output_path: Path | None = None,
    isolated_root: Path | None = None,
    as_of_date: date | None = None,
) -> OptimizationRunSummary:
    source_home = source_app_home or _default_source_app_home()
    isolated_app_home = _copy_source_app_home(source_home, isolated_root=isolated_root)
    config = _initialize_isolated_config(isolated_app_home)
    initialize_database(config)
    _prepare_research_config(config)

    effective_as_of_date = as_of_date or _latest_daily_trade_date(config, "research")
    _ensure_sufficient_history(config, effective_as_of_date)
    trained_models: dict[str, str] = {}
    baseline = _run_experiment(
        config,
        label="baseline",
        experiment=_baseline_config(config),
        as_of_date=effective_as_of_date,
        trained_models=trained_models,
    )
    sweep_results = [
        _run_experiment(
            config,
            label=f"experiment-{index + 1:03d}",
            experiment=experiment,
            as_of_date=effective_as_of_date,
            trained_models=trained_models,
        )
        for index, experiment in enumerate(_sweep_configs())
    ]

    leaderboard = _sorted_leaderboard(sweep_results)
    best_run = _best_result(sweep_results)
    market_status_snapshot = market_data_status(config)
    suspected_profit_drags = _suspected_profit_drags(
        market_status_snapshot=market_status_snapshot,
        baseline=baseline,
        best_run=best_run,
    )

    artifact_path = output_path or _default_output_path()
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at": datetime.now(UTC).isoformat(),
        "source_app_home": str(source_home),
        "isolated_app_home": str(isolated_app_home),
        "as_of_date": effective_as_of_date.isoformat(),
        "market_data_status": market_status_snapshot,
        "baseline": baseline.to_dict(),
        "best_run": None if best_run is None else best_run.to_dict(),
        "winning_configuration": None if best_run is None else best_run.config.to_dict(),
        "leaderboard": [result.to_dict() for result in leaderboard],
        "suspected_profit_drags": suspected_profit_drags,
    }
    artifact_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )

    return OptimizationRunSummary(
        output_path=artifact_path,
        source_app_home=source_home,
        isolated_app_home=isolated_app_home,
        as_of_date=effective_as_of_date,
        baseline=baseline,
        best_run=best_run,
        leaderboard=tuple(leaderboard),
        report_payload=payload,
    )
