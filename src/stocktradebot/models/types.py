from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any


@dataclass(slots=True, frozen=True)
class DatasetArtifactRow:
    symbol: str
    trade_date: date
    universe_snapshot_id: int | None
    features: dict[str, float | None]
    labels: dict[str, float | None]
    fundamentals_available_at: str | None = None


@dataclass(slots=True, frozen=True)
class LinearModelArtifact:
    version: str
    family: str
    dataset_snapshot_id: int
    feature_set_version: str
    label_version: str
    label_name: str
    feature_names: tuple[str, ...]
    feature_means: dict[str, float]
    feature_stds: dict[str, float]
    feature_imputes: dict[str, float]
    feature_weights: dict[str, float]
    training_start_date: date
    training_end_date: date
    training_row_count: int
    holdout_start_date: date
    holdout_end_date: date
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True, frozen=True)
class BacktestRunSummary:
    run_id: int
    model_version: str | None
    dataset_snapshot_id: int
    mode: str
    start_date: date
    end_date: date
    benchmark_symbol: str
    total_return: float
    benchmark_return: float
    excess_return: float
    annualized_return: float
    annualized_volatility: float
    sharpe_ratio: float
    max_drawdown: float
    turnover_ratio: float
    trade_count: int
    average_positions: float
    artifact_path: str
    metadata: dict[str, Any]


@dataclass(slots=True, frozen=True)
class ValidationRunSummary:
    run_id: int
    dataset_snapshot_id: int
    fold_count: int
    artifact_path: str
    average_total_return: float
    average_benchmark_return: float
    average_excess_return: float
    latest_fold_total_return: float
    latest_fold_excess_return: float
    promotion_ready: bool
    promotion_reasons: tuple[str, ...]
    metadata: dict[str, Any]


@dataclass(slots=True, frozen=True)
class TrainingRunSummary:
    run_id: int
    dataset_snapshot_id: int
    model_entry_id: int
    model_version: str
    validation_run_id: int
    backtest_run_id: int
    feature_set_version: str
    label_version: str
    artifact_path: str
    promotion_status: str
    promotion_reasons: tuple[str, ...]
    metrics: dict[str, float]
    benchmark_metrics: dict[str, float]
    metadata: dict[str, Any]
