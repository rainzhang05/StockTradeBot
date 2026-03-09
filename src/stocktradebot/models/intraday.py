from __future__ import annotations

import json
from collections import defaultdict
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, TypedDict

from sqlalchemy import select
from sqlalchemy.orm import Session

from stocktradebot import __version__
from stocktradebot.config import AppConfig
from stocktradebot.features.intraday import build_intraday_dataset_snapshot
from stocktradebot.intraday import get_frequency_spec
from stocktradebot.models.baseline import fit_linear_correlation_model, score_features
from stocktradebot.models.types import (
    DatasetArtifactRow,
    IntradayValidationSummary,
    LinearModelArtifact,
)
from stocktradebot.storage import (
    BackfillRun,
    DatasetSnapshot,
    ModelTrainingRun,
    ValidationRun,
    create_db_engine,
)


class IntradayEvaluation(TypedDict):
    event_rows: list[dict[str, object]]
    average_selected_return: float
    average_universe_return: float
    average_excess_return: float
    hit_rate: float


class IntradayFoldPayload(TypedDict):
    fold_index: int
    decision_count: int
    holdout_start: str
    holdout_end: str
    average_selected_return: float
    average_universe_return: float
    average_excess_return: float
    hit_rate: float
    model_version: str


def _required_label(row: DatasetArtifactRow, label_name: str) -> float:
    label_value = row.labels.get(label_name)
    if label_value is None:
        raise RuntimeError(f"Intraday validation row is missing label '{label_name}'.")
    return float(label_value)


def _write_json_artifact(
    base_dir: Path,
    *,
    prefix: str,
    payload: dict[str, object],
    config: AppConfig,
) -> str:
    path = base_dir / f"{prefix}-{datetime.now(UTC).strftime('%Y%m%dT%H%M%S%fZ')}.json"
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return str(path.relative_to(config.app_home))


def _load_dataset_rows(config: AppConfig, snapshot: DatasetSnapshot) -> list[DatasetArtifactRow]:
    artifact_path = config.app_home / snapshot.artifact_path
    rows: list[DatasetArtifactRow] = []
    for line in artifact_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        raw_row = json.loads(line)
        decision_at = raw_row.get("decision_at")
        rows.append(
            DatasetArtifactRow(
                symbol=str(raw_row["symbol"]),
                trade_date=date.fromisoformat(str(raw_row["trade_date"])),
                universe_snapshot_id=raw_row.get("universe_snapshot_id"),
                features={
                    key: None if value is None else float(value)
                    for key, value in dict(raw_row["features"]).items()
                },
                labels={
                    key: None if value is None else float(value)
                    for key, value in dict(raw_row["labels"]).items()
                },
                fundamentals_available_at=raw_row.get("fundamentals_available_at"),
                decision_at=None
                if decision_at is None
                else datetime.fromisoformat(str(decision_at)),
                frequency=str(raw_row.get("frequency", snapshot.frequency)),
            )
        )
    return rows


def _build_walk_forward_folds(
    rows: list[DatasetArtifactRow], frequency: str
) -> list[tuple[list[DatasetArtifactRow], list[DatasetArtifactRow]]]:
    spec = get_frequency_spec(frequency)
    decision_points = sorted({row.decision_key for row in rows})
    folds: list[tuple[list[DatasetArtifactRow], list[DatasetArtifactRow]]] = []
    for test_start_index in range(
        spec.training_window_bars,
        len(decision_points) - spec.validation_window_bars + 1,
        spec.walk_forward_step_bars,
    ):
        train_keys = set(
            decision_points[test_start_index - spec.training_window_bars : test_start_index]
        )
        test_keys = set(
            decision_points[test_start_index : test_start_index + spec.validation_window_bars]
        )
        train_rows = [row for row in rows if row.decision_key in train_keys]
        test_rows = [row for row in rows if row.decision_key in test_keys]
        if len(train_rows) < 50 or not test_rows:
            continue
        folds.append((train_rows, test_rows))
    return folds


def _evaluate_model(
    model: LinearModelArtifact,
    rows: list[DatasetArtifactRow],
    config: AppConfig,
) -> IntradayEvaluation:
    rows_by_decision: dict[datetime, list[DatasetArtifactRow]] = defaultdict(list)
    for row in rows:
        rows_by_decision[row.decision_key].append(row)

    selected_returns: list[float] = []
    universe_returns: list[float] = []
    hit_count = 0
    event_rows: list[dict[str, object]] = []

    for decision_at, rows_for_decision in sorted(rows_by_decision.items()):
        scored = sorted(
            rows_for_decision,
            key=lambda row: (score_features(model, row.features), row.symbol),
            reverse=True,
        )
        selected = scored[: min(len(scored), config.model_training.target_portfolio_size)]
        if not selected:
            continue
        selected_return = sum(
            _required_label(row, "forward_return_primary") for row in selected
        ) / len(selected)
        universe_return = sum(
            _required_label(row, "forward_return_primary") for row in scored
        ) / len(scored)
        selected_returns.append(selected_return)
        universe_returns.append(universe_return)
        if selected_return > universe_return:
            hit_count += 1
        event_rows.append(
            {
                "decision_at": decision_at.isoformat(),
                "selected_symbols": [row.symbol for row in selected],
                "selected_return": selected_return,
                "universe_return": universe_return,
                "excess_return": selected_return - universe_return,
            }
        )

    average_selected_return = (
        0.0 if not selected_returns else sum(selected_returns) / len(selected_returns)
    )
    average_universe_return = (
        0.0 if not universe_returns else sum(universe_returns) / len(universe_returns)
    )
    return {
        "event_rows": event_rows,
        "average_selected_return": average_selected_return,
        "average_universe_return": average_universe_return,
        "average_excess_return": average_selected_return - average_universe_return,
        "hit_rate": 0.0 if not selected_returns else hit_count / len(selected_returns),
    }


def validate_intraday_research(
    config: AppConfig,
    *,
    frequency: str,
    as_of_date: date | None = None,
) -> IntradayValidationSummary:
    spec = get_frequency_spec(frequency)
    effective_as_of_date = as_of_date or datetime.now(UTC).date()
    engine = create_db_engine(config)
    try:
        with Session(engine) as session:
            training_run = ModelTrainingRun(
                status="running",
                as_of_date=effective_as_of_date,
                frequency=spec.name,
                dataset_snapshot_id=None,
                model_family=f"intraday-linear-correlation-{spec.name}-v1",
                model_version=None,
                summary_json="{}",
            )
            session.add(training_run)
            session.commit()
            training_run_id = training_run.id

        try:
            dataset_summary = build_intraday_dataset_snapshot(
                config,
                frequency=spec.name,
                as_of_date=effective_as_of_date,
            )
            with Session(engine) as session:
                training_run_row = session.get(ModelTrainingRun, training_run_id)
                if training_run_row is None:
                    raise RuntimeError("Intraday validation run state was lost.")
                training_run_row.dataset_snapshot_id = dataset_summary.snapshot_id
                session.commit()
                snapshot_row = session.get(DatasetSnapshot, dataset_summary.snapshot_id)
                if snapshot_row is None:
                    raise RuntimeError("Intraday dataset snapshot was not found.")
                rows = _load_dataset_rows(config, snapshot_row)
                folds = _build_walk_forward_folds(rows, spec.name)
                if not folds:
                    raise RuntimeError(
                        "No intraday walk-forward folds are available. "
                        "Expand the intraday history first."
                    )

                fold_payloads: list[IntradayFoldPayload] = []
                latest_excess_return = 0.0
                latest_model_version = ""
                for fold_index, (train_rows, test_rows) in enumerate(folds, start=1):
                    test_keys = sorted({row.decision_key for row in test_rows})
                    model_version = (
                        f"intraday-linear-correlation-{spec.name}-"
                        f"{datetime.now(UTC).strftime('%Y%m%dT%H%M%S%fZ')}"
                    )
                    model = fit_linear_correlation_model(
                        rows=train_rows,
                        dataset_snapshot_id=snapshot_row.id,
                        feature_set_version=snapshot_row.feature_set_version,
                        label_version=snapshot_row.label_version,
                        model_family=f"intraday-linear-correlation-{spec.name}-v1",
                        label_name=spec.target_label_name,
                        model_version=model_version,
                        holdout_start_date=test_keys[0].date(),
                        holdout_end_date=test_keys[-1].date(),
                    )
                    evaluation = _evaluate_model(model, test_rows, config)
                    latest_excess_return = evaluation["average_excess_return"]
                    latest_model_version = model_version
                    fold_payloads.append(
                        {
                            "fold_index": fold_index,
                            "decision_count": len(test_keys),
                            "holdout_start": test_keys[0].isoformat(),
                            "holdout_end": test_keys[-1].isoformat(),
                            "average_selected_return": evaluation["average_selected_return"],
                            "average_universe_return": evaluation["average_universe_return"],
                            "average_excess_return": evaluation["average_excess_return"],
                            "hit_rate": evaluation["hit_rate"],
                            "model_version": model_version,
                        }
                    )

                latest_quality_run = session.scalar(
                    select(BackfillRun)
                    .where(BackfillRun.domain == "intraday", BackfillRun.frequency == spec.name)
                    .order_by(BackfillRun.id.desc())
                )
                quality_report: dict[str, Any] = {}
                if latest_quality_run is not None:
                    quality_report = json.loads(latest_quality_run.summary_json)
                promotion_reasons: list[str] = []
                if len(fold_payloads) < config.model_training.min_validation_folds:
                    promotion_reasons.append("insufficient_walk_forward_history")
                if latest_excess_return <= 0:
                    promotion_reasons.append(
                        "latest_intraday_fold_did_not_beat_cross_sectional_baseline"
                    )
                quality_report_path = quality_report.get("quality_report_path")
                quality_ready = False
                quality_metrics: dict[str, Any] = {}
                if quality_report_path:
                    quality_metrics = json.loads(
                        (config.app_home / quality_report_path).read_text(encoding="utf-8")
                    )
                    quality_ready = bool(quality_metrics.get("promotion_ready"))
                if not quality_ready:
                    promotion_reasons.append("intraday_data_quality_not_promotion_ready")

                report_payload = {
                    "dataset_snapshot_id": snapshot_row.id,
                    "frequency": spec.name,
                    "feature_set_version": snapshot_row.feature_set_version,
                    "label_version": snapshot_row.label_version,
                    "fold_count": len(fold_payloads),
                    "folds": fold_payloads,
                    "latest_model_version": latest_model_version,
                    "quality_metrics": quality_metrics,
                    "promotion_ready": not promotion_reasons,
                    "promotion_reasons": promotion_reasons,
                    "code_version": __version__,
                }
                artifact_path = _write_json_artifact(
                    config.report_artifacts_dir,
                    prefix=f"intraday-validation-{spec.name}-{snapshot_row.id}",
                    payload=report_payload,
                    config=config,
                )
                validation_run = ValidationRun(
                    status="completed",
                    frequency=spec.name,
                    dataset_snapshot_id=snapshot_row.id,
                    model_entry_id=None,
                    fold_count=len(fold_payloads),
                    artifact_path=artifact_path,
                    summary_json=json.dumps(report_payload, sort_keys=True),
                    error_message=None,
                    completed_at=datetime.now(UTC),
                )
                session.add(validation_run)
                session.commit()

                training_run_row = session.get(ModelTrainingRun, training_run_id)
                if training_run_row is None:
                    raise RuntimeError("Intraday validation run state was lost.")
                training_run_row.status = "completed"
                training_run_row.model_version = latest_model_version
                training_run_row.summary_json = json.dumps(
                    {
                        "validation_run_id": validation_run.id,
                        "artifact_path": artifact_path,
                        "promotion_ready": not promotion_reasons,
                        "promotion_reasons": promotion_reasons,
                    },
                    sort_keys=True,
                )
                training_run_row.completed_at = datetime.now(UTC)
                session.commit()

                average_selected_return = (
                    0.0
                    if not fold_payloads
                    else sum(float(fold["average_selected_return"]) for fold in fold_payloads)
                    / len(fold_payloads)
                )
                average_universe_return = (
                    0.0
                    if not fold_payloads
                    else sum(float(fold["average_universe_return"]) for fold in fold_payloads)
                    / len(fold_payloads)
                )
                average_excess_return = average_selected_return - average_universe_return
                average_hit_rate = (
                    0.0
                    if not fold_payloads
                    else sum(float(fold["hit_rate"]) for fold in fold_payloads) / len(fold_payloads)
                )
                return IntradayValidationSummary(
                    run_id=validation_run.id,
                    dataset_snapshot_id=snapshot_row.id,
                    frequency=spec.name,
                    feature_set_version=snapshot_row.feature_set_version,
                    label_version=snapshot_row.label_version,
                    artifact_path=artifact_path,
                    fold_count=len(fold_payloads),
                    promotion_ready=not promotion_reasons,
                    promotion_reasons=tuple(promotion_reasons),
                    metrics={
                        "average_selected_return": average_selected_return,
                        "average_universe_return": average_universe_return,
                        "average_excess_return": average_excess_return,
                        "average_hit_rate": average_hit_rate,
                    },
                    metadata={
                        "latest_model_version": latest_model_version,
                        "quality_metrics": quality_metrics,
                    },
                )
        except Exception as exc:
            with Session(engine) as session:
                training_run_row = session.get(ModelTrainingRun, training_run_id)
                if training_run_row is not None:
                    training_run_row.status = "failed"
                    training_run_row.error_message = str(exc)
                    training_run_row.completed_at = datetime.now(UTC)
                    session.commit()
            raise
    finally:
        engine.dispose()


def intraday_validation_status(
    config: AppConfig, *, frequency: str | None = None
) -> dict[str, object]:
    engine = create_db_engine(config)
    try:
        with Session(engine) as session:
            training_query = select(ModelTrainingRun).where(ModelTrainingRun.frequency != "daily")
            validation_query = select(ValidationRun).where(ValidationRun.frequency != "daily")
            if frequency is not None:
                training_query = training_query.where(ModelTrainingRun.frequency == frequency)
                validation_query = validation_query.where(ValidationRun.frequency == frequency)
            latest_training_run = session.scalar(
                training_query.order_by(
                    ModelTrainingRun.created_at.desc(), ModelTrainingRun.id.desc()
                )
            )
            latest_validation_run = session.scalar(
                validation_query.order_by(ValidationRun.created_at.desc(), ValidationRun.id.desc())
            )
    finally:
        engine.dispose()

    return {
        "latest_training_run": (
            None
            if latest_training_run is None
            else {
                "id": latest_training_run.id,
                "status": latest_training_run.status,
                "as_of_date": latest_training_run.as_of_date.isoformat(),
                "frequency": latest_training_run.frequency,
                "model_version": latest_training_run.model_version,
                "summary": json.loads(latest_training_run.summary_json),
            }
        ),
        "latest_validation_run": (
            None
            if latest_validation_run is None
            else {
                "id": latest_validation_run.id,
                "status": latest_validation_run.status,
                "frequency": latest_validation_run.frequency,
                "fold_count": latest_validation_run.fold_count,
                "artifact_path": latest_validation_run.artifact_path,
                "summary": json.loads(latest_validation_run.summary_json),
            }
        ),
    }
