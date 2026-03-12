from __future__ import annotations

import json
import shutil
from dataclasses import dataclass, replace
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
from stocktradebot.models.types import BacktestRunSummary
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
STAGE_C_REBALANCE_INTERVALS: tuple[int, ...] = (1, 3, 5)
STAGE_C_RISK_ON_TARGET_POSITIONS: tuple[int, ...] = (10, 15, 20, 25)
STAGE_C_TURNOVER_PENALTIES: tuple[float, ...] = (0.05, 0.10, 0.20)
STAGE_C_RISK_OFF_GROSS_EXPOSURES: tuple[float, ...] = (0.00, 0.20, 0.35)
STAGE_C_DEFENSIVE_ETF_SYMBOLS: tuple[str | None, ...] = (None, "IEF")
MODEL_FAMILY_PRIORITY = {
    "linear-correlation-v1": 0,
    "gradient-boosting-v1": 1,
    "rank-ensemble-v1": 2,
}
LINEAR_STABILITY_WALK_FORWARD_EXCESS_THRESHOLD = 0.02
LINEAR_STABILITY_HOLDOUT_EXCESS_THRESHOLD = 0.01


def _timestamp_token() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")


def _metric(payload: dict[str, Any] | None, key: str) -> float | None:
    if payload is None:
        return None
    raw_value = payload.get(key)
    if raw_value is None:
        return None
    return float(raw_value)


def _family_priority(model_family: str) -> int:
    return MODEL_FAMILY_PRIORITY.get(model_family, len(MODEL_FAMILY_PRIORITY))


@dataclass(slots=True, frozen=True)
class ExperimentConfig:
    quality_scope: str
    model_family: str
    feature_set_version: str
    label_version: str
    target_label_name: str
    rebalance_interval_days: int
    risk_on_target_positions: int
    turnover_penalty: float
    risk_off_gross_exposure: float
    defensive_etf_symbol: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "quality_scope": self.quality_scope,
            "model_family": self.model_family,
            "feature_set_version": self.feature_set_version,
            "label_version": self.label_version,
            "target_label_name": self.target_label_name,
            "rebalance_interval_days": self.rebalance_interval_days,
            "risk_on_target_positions": self.risk_on_target_positions,
            "turnover_penalty": self.turnover_penalty,
            "risk_off_gross_exposure": self.risk_off_gross_exposure,
            "defensive_etf_symbol": self.defensive_etf_symbol or "none",
        }


@dataclass(slots=True, frozen=True)
class ExperimentResult:
    label: str
    stage: str
    config: ExperimentConfig
    success: bool
    model_version: str | None
    walk_forward_backtest_run_id: int | None
    holdout_backtest_run_id: int | None
    walk_forward_metrics: dict[str, Any] | None
    holdout_metrics: dict[str, Any] | None
    duration_seconds: float
    error_message: str | None = None

    @property
    def total_return(self) -> float | None:
        return self.walk_forward_total_return

    @property
    def benchmark_return(self) -> float | None:
        return self.walk_forward_benchmark_return

    @property
    def excess_return(self) -> float | None:
        return self.walk_forward_excess_return

    @property
    def max_drawdown(self) -> float | None:
        return self.walk_forward_max_drawdown

    @property
    def turnover_ratio(self) -> float | None:
        return self.walk_forward_turnover_ratio

    @property
    def trade_count(self) -> int | None:
        if self.walk_forward_metrics is None:
            return None
        raw_value = self.walk_forward_metrics.get("trade_count")
        return None if raw_value is None else int(raw_value)

    @property
    def average_positions(self) -> float | None:
        return _metric(self.walk_forward_metrics, "average_positions")

    @property
    def walk_forward_total_return(self) -> float | None:
        return _metric(self.walk_forward_metrics, "total_return")

    @property
    def walk_forward_benchmark_return(self) -> float | None:
        return _metric(self.walk_forward_metrics, "benchmark_return")

    @property
    def walk_forward_excess_return(self) -> float | None:
        return _metric(self.walk_forward_metrics, "excess_return")

    @property
    def walk_forward_max_drawdown(self) -> float | None:
        return _metric(self.walk_forward_metrics, "max_drawdown")

    @property
    def walk_forward_turnover_ratio(self) -> float | None:
        return _metric(self.walk_forward_metrics, "turnover_ratio")

    @property
    def holdout_total_return(self) -> float | None:
        return _metric(self.holdout_metrics, "total_return")

    @property
    def holdout_benchmark_return(self) -> float | None:
        return _metric(self.holdout_metrics, "benchmark_return")

    @property
    def holdout_excess_return(self) -> float | None:
        return _metric(self.holdout_metrics, "excess_return")

    def ranking_key(self) -> tuple[float, float, float, float, int, str]:
        walk_forward_excess = self.walk_forward_excess_return
        holdout_excess = self.holdout_excess_return
        max_drawdown = self.walk_forward_max_drawdown
        turnover = self.walk_forward_turnover_ratio
        return (
            float("inf") if walk_forward_excess is None else -walk_forward_excess,
            float("inf") if holdout_excess is None else -holdout_excess,
            float("inf") if max_drawdown is None else abs(max_drawdown),
            float("inf") if turnover is None else turnover,
            _family_priority(self.config.model_family),
            self.label,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "stage": self.stage,
            "config": self.config.to_dict(),
            "success": self.success,
            "model_version": self.model_version,
            "walk_forward_backtest_run_id": self.walk_forward_backtest_run_id,
            "holdout_backtest_run_id": self.holdout_backtest_run_id,
            "walk_forward_metrics": self.walk_forward_metrics,
            "holdout_metrics": self.holdout_metrics,
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
    stage_winners: dict[str, ExperimentResult | None]
    best_run: ExperimentResult | None
    leaderboard: tuple[ExperimentResult, ...]
    report_payload: dict[str, Any]
    applied_source_config: dict[str, Any] | None = None


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
    if available_trade_dates >= required_trade_dates and available_snapshot_dates >= 12:
        return
    backfill_market_data(
        config,
        as_of_date=as_of_date,
        lookback_days=required_trade_dates,
        full_history=True,
        historical_snapshots=True,
    )


def _load_backtest_report(
    config: AppConfig,
    backtest_run_id: int,
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


def _backtest_summary_to_metrics(summary: BacktestRunSummary) -> dict[str, Any]:
    return {
        "run_id": summary.run_id,
        "mode": summary.mode,
        "start_date": summary.start_date.isoformat(),
        "end_date": summary.end_date.isoformat(),
        "benchmark_symbol": summary.benchmark_symbol,
        "quality_scope": summary.quality_scope,
        "total_return": summary.total_return,
        "benchmark_return": summary.benchmark_return,
        "excess_return": summary.excess_return,
        "annualized_return": summary.annualized_return,
        "annualized_volatility": summary.annualized_volatility,
        "sharpe_ratio": summary.sharpe_ratio,
        "max_drawdown": summary.max_drawdown,
        "turnover_ratio": summary.turnover_ratio,
        "trade_count": summary.trade_count,
        "average_positions": summary.average_positions,
        "artifact_path": summary.artifact_path,
        "metadata": summary.metadata,
    }


def _backtest_payload_to_metrics(
    *,
    artifact_path: str | None,
    payload: dict[str, Any],
) -> dict[str, Any]:
    metrics = dict(payload.get("metrics", {}))
    return {
        "run_id": payload.get("run_id"),
        "mode": payload.get("mode"),
        "start_date": payload.get("start_date"),
        "end_date": payload.get("end_date"),
        "benchmark_symbol": payload.get("benchmark_symbol"),
        "quality_scope": payload.get("quality_scope"),
        "total_return": metrics.get("total_return"),
        "benchmark_return": metrics.get("benchmark_return"),
        "excess_return": metrics.get("excess_return"),
        "annualized_return": metrics.get("annualized_return"),
        "annualized_volatility": metrics.get("annualized_volatility"),
        "sharpe_ratio": metrics.get("sharpe_ratio"),
        "max_drawdown": metrics.get("max_drawdown"),
        "turnover_ratio": metrics.get("turnover_ratio"),
        "trade_count": payload.get("trade_count"),
        "average_positions": metrics.get("average_positions"),
        "artifact_path": artifact_path,
        "metadata": {
            "regime_summary": payload.get("regime_summary"),
            "event_count": len(payload.get("event_rows", [])),
        },
    }


def _baseline_config(config: AppConfig) -> ExperimentConfig:
    return ExperimentConfig(
        quality_scope="research",
        model_family=config.model_training.model_family,
        feature_set_version=config.model_training.feature_set_version,
        label_version=config.model_training.label_version,
        target_label_name=config.model_training.target_label_name,
        rebalance_interval_days=config.model_training.rebalance_interval_days,
        risk_on_target_positions=config.portfolio.risk_on_target_positions,
        turnover_penalty=config.portfolio.turnover_penalty,
        risk_off_gross_exposure=config.portfolio.risk_off_gross_exposure,
        defensive_etf_symbol=config.portfolio.defensive_etf_symbol,
    )


def _stage_a_configs(baseline: ExperimentConfig) -> list[ExperimentConfig]:
    return [
        ExperimentConfig(
            quality_scope="research",
            model_family="linear-correlation-v1",
            feature_set_version="daily-core-v1",
            label_version="forward-return-v1",
            target_label_name="ranking_label_5d",
            rebalance_interval_days=baseline.rebalance_interval_days,
            risk_on_target_positions=baseline.risk_on_target_positions,
            turnover_penalty=baseline.turnover_penalty,
            risk_off_gross_exposure=baseline.risk_off_gross_exposure,
            defensive_etf_symbol=baseline.defensive_etf_symbol,
        ),
        ExperimentConfig(
            quality_scope="research",
            model_family="linear-correlation-v1",
            feature_set_version="daily-alpha-v2",
            label_version="forward-return-v1",
            target_label_name="ranking_label_5d",
            rebalance_interval_days=baseline.rebalance_interval_days,
            risk_on_target_positions=baseline.risk_on_target_positions,
            turnover_penalty=baseline.turnover_penalty,
            risk_off_gross_exposure=baseline.risk_off_gross_exposure,
            defensive_etf_symbol=baseline.defensive_etf_symbol,
        ),
        ExperimentConfig(
            quality_scope="research",
            model_family="linear-correlation-v1",
            feature_set_version="daily-alpha-v2",
            label_version="forward-excess-v2",
            target_label_name="ranking_label_5d_excess",
            rebalance_interval_days=baseline.rebalance_interval_days,
            risk_on_target_positions=baseline.risk_on_target_positions,
            turnover_penalty=baseline.turnover_penalty,
            risk_off_gross_exposure=baseline.risk_off_gross_exposure,
            defensive_etf_symbol=baseline.defensive_etf_symbol,
        ),
    ]


def _stage_b_configs(
    baseline: ExperimentConfig,
    stage_a_winner: ExperimentResult | None,
) -> list[ExperimentConfig]:
    if stage_a_winner is None:
        return []
    return [
        ExperimentConfig(
            quality_scope="research",
            model_family=model_family,
            feature_set_version=stage_a_winner.config.feature_set_version,
            label_version=stage_a_winner.config.label_version,
            target_label_name=stage_a_winner.config.target_label_name,
            rebalance_interval_days=baseline.rebalance_interval_days,
            risk_on_target_positions=baseline.risk_on_target_positions,
            turnover_penalty=baseline.turnover_penalty,
            risk_off_gross_exposure=baseline.risk_off_gross_exposure,
            defensive_etf_symbol=baseline.defensive_etf_symbol,
        )
        for model_family in MODEL_FAMILIES
    ]


def _stage_c_configs(stage_b_winner: ExperimentResult | None) -> list[ExperimentConfig]:
    if stage_b_winner is None:
        return []
    return [
        ExperimentConfig(
            quality_scope="research",
            model_family=stage_b_winner.config.model_family,
            feature_set_version=stage_b_winner.config.feature_set_version,
            label_version=stage_b_winner.config.label_version,
            target_label_name=stage_b_winner.config.target_label_name,
            rebalance_interval_days=rebalance_interval_days,
            risk_on_target_positions=risk_on_target_positions,
            turnover_penalty=turnover_penalty,
            risk_off_gross_exposure=risk_off_gross_exposure,
            defensive_etf_symbol=defensive_etf_symbol,
        )
        for (
            rebalance_interval_days,
            risk_on_target_positions,
            turnover_penalty,
            risk_off_gross_exposure,
            defensive_etf_symbol,
        ) in product(
            STAGE_C_REBALANCE_INTERVALS,
            STAGE_C_RISK_ON_TARGET_POSITIONS,
            STAGE_C_TURNOVER_PENALTIES,
            STAGE_C_RISK_OFF_GROSS_EXPOSURES,
            STAGE_C_DEFENSIVE_ETF_SYMBOLS,
        )
    ]


def _apply_experiment_config(config: AppConfig, experiment: ExperimentConfig) -> None:
    config.model_training.quality_scope = experiment.quality_scope
    config.model_training.model_family = experiment.model_family
    config.model_training.feature_set_version = experiment.feature_set_version
    config.model_training.label_version = experiment.label_version
    config.model_training.target_label_name = experiment.target_label_name
    config.model_training.rebalance_interval_days = experiment.rebalance_interval_days
    config.model_training.target_portfolio_size = experiment.risk_on_target_positions
    config.portfolio.risk_on_target_positions = experiment.risk_on_target_positions
    config.portfolio.turnover_penalty = experiment.turnover_penalty
    config.portfolio.risk_off_gross_exposure = experiment.risk_off_gross_exposure
    config.portfolio.defensive_etf_symbol = experiment.defensive_etf_symbol
    config.save()


def _clone_cached_result(
    cached_result: ExperimentResult,
    *,
    label: str,
    stage: str,
) -> ExperimentResult:
    return replace(cached_result, label=label, stage=stage)


def _run_experiment(
    config: AppConfig,
    *,
    label: str,
    stage: str,
    experiment: ExperimentConfig,
    as_of_date: date,
    trained_models: dict[ExperimentConfig, ExperimentResult] | None = None,
) -> ExperimentResult:
    model_cache = {} if trained_models is None else trained_models
    cached_result = model_cache.get(experiment)
    if cached_result is not None:
        return _clone_cached_result(cached_result, label=label, stage=stage)

    _apply_experiment_config(config, experiment)
    started = monotonic()
    try:
        training_summary = train_model(
            config,
            as_of_date=as_of_date,
            quality_scope=experiment.quality_scope,
        )
        walk_forward_artifact_path, walk_forward_payload = _load_backtest_report(
            config,
            training_summary.backtest_run_id,
        )
        holdout_summary = backtest_model(config, model_version=training_summary.model_version)
        result = ExperimentResult(
            label=label,
            stage=stage,
            config=experiment,
            success=True,
            model_version=training_summary.model_version,
            walk_forward_backtest_run_id=training_summary.backtest_run_id,
            holdout_backtest_run_id=holdout_summary.run_id,
            walk_forward_metrics=_backtest_payload_to_metrics(
                artifact_path=walk_forward_artifact_path,
                payload=walk_forward_payload,
            ),
            holdout_metrics=_backtest_summary_to_metrics(holdout_summary),
            duration_seconds=monotonic() - started,
        )
    except Exception as exc:
        result = ExperimentResult(
            label=label,
            stage=stage,
            config=experiment,
            success=False,
            model_version=None,
            walk_forward_backtest_run_id=None,
            holdout_backtest_run_id=None,
            walk_forward_metrics=None,
            holdout_metrics=None,
            duration_seconds=monotonic() - started,
            error_message=str(exc),
        )

    model_cache[experiment] = result
    return result


def _run_stage(
    config: AppConfig,
    *,
    stage: str,
    configs: list[ExperimentConfig],
    as_of_date: date,
    experiment_cache: dict[ExperimentConfig, ExperimentResult],
) -> list[ExperimentResult]:
    return [
        _run_experiment(
            config,
            label=f"{stage}-{index + 1:03d}",
            stage=stage,
            experiment=experiment,
            as_of_date=as_of_date,
            trained_models=experiment_cache,
        )
        for index, experiment in enumerate(configs)
    ]


def _sorted_leaderboard(results: list[ExperimentResult]) -> list[ExperimentResult]:
    successes = sorted(
        (result for result in results if result.success),
        key=lambda item: item.ranking_key(),
    )
    failures = sorted(
        (result for result in results if not result.success),
        key=lambda item: (item.stage, item.error_message or "", item.label),
    )
    return [*successes, *failures]


def _best_result(results: list[ExperimentResult]) -> ExperimentResult | None:
    successful = [result for result in results if result.success]
    if not successful:
        return None
    return min(successful, key=lambda item: item.ranking_key())


def _best_linear_result(results: list[ExperimentResult]) -> ExperimentResult | None:
    linear_results = [
        result
        for result in results
        if result.success and result.config.model_family == "linear-correlation-v1"
    ]
    if not linear_results:
        return None
    return min(linear_results, key=lambda item: item.ranking_key())


def _select_stage_b_winner(
    results: list[ExperimentResult],
) -> tuple[ExperimentResult | None, dict[str, Any]]:
    best_candidate = _best_result(results)
    if best_candidate is None:
        return None, {"applied": False, "reason": "no_successful_stage_b_results"}

    best_linear = _best_linear_result(results)
    if (
        best_candidate.config.model_family != "linear-correlation-v1"
        and best_linear is not None
        and best_candidate.walk_forward_excess_return is not None
        and best_linear.walk_forward_excess_return is not None
        and best_candidate.holdout_excess_return is not None
        and best_linear.holdout_excess_return is not None
    ):
        walk_forward_gap = (
            best_candidate.walk_forward_excess_return - best_linear.walk_forward_excess_return
        )
        holdout_gap = best_candidate.holdout_excess_return - best_linear.holdout_excess_return
        if (
            walk_forward_gap <= LINEAR_STABILITY_WALK_FORWARD_EXCESS_THRESHOLD
            and holdout_gap <= LINEAR_STABILITY_HOLDOUT_EXCESS_THRESHOLD
        ):
            return (
                best_linear,
                {
                    "applied": True,
                    "reason": "preferred_linear_family_for_stability",
                    "candidate_model_family": best_candidate.config.model_family,
                    "preferred_model_family": best_linear.config.model_family,
                    "walk_forward_excess_gap": walk_forward_gap,
                    "holdout_excess_gap": holdout_gap,
                },
            )

    return (
        best_candidate,
        {
            "applied": False,
            "reason": "best_candidate_retained",
            "candidate_model_family": best_candidate.config.model_family,
            "preferred_model_family": best_candidate.config.model_family,
        },
    )


def _load_provider_coverage_summary(
    config: AppConfig,
    market_status_snapshot: dict[str, Any],
) -> dict[str, Any] | None:
    latest_run = dict(market_status_snapshot.get("latest_run") or {})
    summary = dict(latest_run.get("summary") or {})
    coverage_report_path = summary.get("coverage_report_path")
    if not coverage_report_path:
        return None
    artifact_path = config.app_home / str(coverage_report_path)
    if not artifact_path.exists():
        return {
            "coverage_report_path": coverage_report_path,
            "status": "missing",
        }
    payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    return {
        "coverage_report_path": coverage_report_path,
        "status": "available",
        "as_of_date": payload.get("as_of_date"),
        "primary_provider": payload.get("primary_provider"),
        "secondary_provider": payload.get("secondary_provider"),
        "fallback_providers": payload.get("research_fallback_providers"),
        "validation_counts": payload.get("validation_counts"),
        "missing_symbols": payload.get("missing_symbols"),
        "symbols_without_primary_bars": payload.get("symbols_without_primary_bars"),
        "fallback_only_symbols": payload.get("fallback_only_symbols"),
        "providers": payload.get("providers"),
    }


def _wins_activation_gate(
    winner: ExperimentResult | None,
    baseline: ExperimentResult,
) -> tuple[bool, str]:
    if winner is None or not winner.success:
        return False, "no_successful_winner"
    if (
        baseline.walk_forward_excess_return is None
        or baseline.holdout_excess_return is None
        or winner.walk_forward_excess_return is None
        or winner.holdout_excess_return is None
    ):
        return False, "required_excess_return_metrics_missing"
    if winner.walk_forward_excess_return <= baseline.walk_forward_excess_return:
        return False, "walk_forward_excess_return_did_not_improve"
    if winner.holdout_excess_return <= baseline.holdout_excess_return:
        return False, "holdout_excess_return_did_not_improve"
    return True, "winner_beats_baseline_on_both_required_checks"


def _apply_winner_to_source_config(
    source_app_home: Path,
    winner: ExperimentResult,
) -> dict[str, Any]:
    source_config = initialize_config(source_app_home)
    experiment = winner.config
    _apply_experiment_config(source_config, experiment)
    return {
        "quality_scope": source_config.model_training.quality_scope,
        "model_family": source_config.model_training.model_family,
        "feature_set_version": source_config.model_training.feature_set_version,
        "label_version": source_config.model_training.label_version,
        "target_label_name": source_config.model_training.target_label_name,
        "rebalance_interval_days": source_config.model_training.rebalance_interval_days,
        "risk_on_target_positions": source_config.portfolio.risk_on_target_positions,
        "turnover_penalty": source_config.portfolio.turnover_penalty,
        "risk_off_gross_exposure": source_config.portfolio.risk_off_gross_exposure,
        "defensive_etf_symbol": source_config.portfolio.defensive_etf_symbol,
    }


def _suspected_profit_drags(
    *,
    market_status_snapshot: dict[str, Any],
    baseline: ExperimentResult,
    final_winner: ExperimentResult | None,
) -> list[dict[str, str]]:
    drags: list[dict[str, str]] = []
    daily_readiness = dict(market_status_snapshot.get("daily_readiness", {}))
    if daily_readiness.get("promotion_state") == "promotion-blocked":
        drags.append(
            {
                "category": "data_gating",
                "detail": (
                    "The source runtime still depends on research-only daily data, so promotion "
                    "and live-eligible model advancement remain blocked even though research "
                    "can run."
                ),
            }
        )

    if final_winner is None or not final_winner.success:
        return drags

    if (
        final_winner.config.feature_set_version != baseline.config.feature_set_version
        or final_winner.config.label_version != baseline.config.label_version
        or final_winner.config.target_label_name != baseline.config.target_label_name
    ):
        drags.append(
            {
                "category": "alpha_stack",
                "detail": (
                    "Feature and label quality were profit-relevant. "
                    f"{final_winner.config.feature_set_version} with "
                    f"{final_winner.config.label_version}/{final_winner.config.target_label_name} "
                    "outperformed the baseline alpha stack."
                ),
            }
        )

    if final_winner.config.model_family != baseline.config.model_family:
        drags.append(
            {
                "category": "model_family",
                "detail": (
                    f"Model-family selection mattered. Switching from "
                    f"{baseline.config.model_family} to {final_winner.config.model_family} "
                    "improved the optimization objective."
                ),
            }
        )

    if final_winner.config.rebalance_interval_days != baseline.config.rebalance_interval_days:
        drags.append(
            {
                "category": "rebalance_frequency",
                "detail": (
                    f"A {final_winner.config.rebalance_interval_days}-day rebalance cadence "
                    f"beat the baseline {baseline.config.rebalance_interval_days}-day cadence."
                ),
            }
        )

    portfolio_changes: list[str] = []
    if final_winner.config.risk_on_target_positions != baseline.config.risk_on_target_positions:
        portfolio_changes.append(
            f"risk_on_target_positions={final_winner.config.risk_on_target_positions}"
        )
    if abs(final_winner.config.turnover_penalty - baseline.config.turnover_penalty) > 1e-9:
        portfolio_changes.append(f"turnover_penalty={final_winner.config.turnover_penalty:.2f}")
    if (
        abs(final_winner.config.risk_off_gross_exposure - baseline.config.risk_off_gross_exposure)
        > 1e-9
    ):
        portfolio_changes.append(
            f"risk_off_gross_exposure={final_winner.config.risk_off_gross_exposure:.2f}"
        )
    if final_winner.config.defensive_etf_symbol != baseline.config.defensive_etf_symbol:
        portfolio_changes.append(
            f"defensive_etf_symbol={final_winner.config.defensive_etf_symbol or 'none'}"
        )
    if portfolio_changes:
        drags.append(
            {
                "category": "portfolio_risk_settings",
                "detail": (
                    "Portfolio sizing and risk controls were profit-relevant. "
                    + ", ".join(portfolio_changes)
                    + " beat the baseline configuration."
                ),
            }
        )

    if not drags:
        drags.append(
            {
                "category": "baseline_strategy",
                "detail": (
                    "No single drag clearly dominated the baseline; measured profit appears to be "
                    "coming from the combined interaction of the existing alpha stack, portfolio "
                    "construction, and data constraints."
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
    source_config = initialize_config(source_home)
    baseline_config = _baseline_config(source_config)

    isolated_app_home = _copy_source_app_home(source_home, isolated_root=isolated_root)
    config = _initialize_isolated_config(isolated_app_home)
    initialize_database(config)
    _prepare_research_config(config)

    effective_as_of_date = as_of_date or _latest_daily_trade_date(config, "research")
    _ensure_sufficient_history(config, effective_as_of_date)
    market_status_snapshot = market_data_status(config)
    provider_coverage_summary = _load_provider_coverage_summary(config, market_status_snapshot)

    experiment_cache: dict[ExperimentConfig, ExperimentResult] = {}
    baseline = _run_experiment(
        config,
        label="baseline",
        stage="baseline",
        experiment=baseline_config,
        as_of_date=effective_as_of_date,
        trained_models=experiment_cache,
    )

    stage_a_results = _run_stage(
        config,
        stage="stage-a",
        configs=_stage_a_configs(baseline_config),
        as_of_date=effective_as_of_date,
        experiment_cache=experiment_cache,
    )
    stage_a_winner = _best_result(stage_a_results)

    stage_b_results = _run_stage(
        config,
        stage="stage-b",
        configs=_stage_b_configs(baseline_config, stage_a_winner),
        as_of_date=effective_as_of_date,
        experiment_cache=experiment_cache,
    )
    stage_b_winner, stability_rule = _select_stage_b_winner(stage_b_results)

    stage_c_results = _run_stage(
        config,
        stage="stage-c",
        configs=_stage_c_configs(stage_b_winner),
        as_of_date=effective_as_of_date,
        experiment_cache=experiment_cache,
    )
    stage_c_winner = _best_result(stage_c_results)
    final_winner = stage_c_winner or stage_b_winner or stage_a_winner

    leaderboard = _sorted_leaderboard([*stage_a_results, *stage_b_results, *stage_c_results])
    activation_allowed, activation_reason = _wins_activation_gate(final_winner, baseline)
    applied_source_config = (
        None
        if not activation_allowed or final_winner is None
        else _apply_winner_to_source_config(source_home, final_winner)
    )
    suspected_profit_drags = _suspected_profit_drags(
        market_status_snapshot=market_status_snapshot,
        baseline=baseline,
        final_winner=final_winner,
    )

    artifact_path = output_path or _default_output_path()
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at": datetime.now(UTC).isoformat(),
        "source_app_home": str(source_home),
        "isolated_app_home": str(isolated_app_home),
        "as_of_date": effective_as_of_date.isoformat(),
        "market_data_status": market_status_snapshot,
        "provider_coverage_summary": provider_coverage_summary,
        "baseline": baseline.to_dict(),
        "stage_winners": {
            "stage_a": None if stage_a_winner is None else stage_a_winner.to_dict(),
            "stage_b": None if stage_b_winner is None else stage_b_winner.to_dict(),
            "stage_c": None if stage_c_winner is None else stage_c_winner.to_dict(),
        },
        "stage_b_stability_rule": stability_rule,
        "best_run": None if final_winner is None else final_winner.to_dict(),
        "final_winner": None if final_winner is None else final_winner.to_dict(),
        "winning_configuration": None if final_winner is None else final_winner.config.to_dict(),
        "leaderboard": [result.to_dict() for result in leaderboard],
        "activation": {
            "activated": activation_allowed and applied_source_config is not None,
            "reason": activation_reason,
            "baseline_walk_forward_excess_return": baseline.walk_forward_excess_return,
            "baseline_holdout_excess_return": baseline.holdout_excess_return,
            "winner_walk_forward_excess_return": (
                None if final_winner is None else final_winner.walk_forward_excess_return
            ),
            "winner_holdout_excess_return": (
                None if final_winner is None else final_winner.holdout_excess_return
            ),
            "applied_source_config": applied_source_config,
        },
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
        stage_winners={
            "stage_a": stage_a_winner,
            "stage_b": stage_b_winner,
            "stage_c": stage_c_winner,
        },
        best_run=final_winner,
        leaderboard=tuple(leaderboard),
        report_payload=payload,
        applied_source_config=applied_source_config,
    )
