from __future__ import annotations

import base64
import math
import pickle
from collections.abc import Sequence
from datetime import date
from typing import Any

import sklearn.ensemble as sklearn_ensemble  # type: ignore[import-not-found,import-untyped]

from stocktradebot.models.types import DatasetArtifactRow, LinearModelArtifact

HistGradientBoostingRegressor = sklearn_ensemble.HistGradientBoostingRegressor
GradientBoostingEstimator = Any


def _mean(values: Sequence[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _stddev(values: Sequence[float]) -> float:
    if len(values) < 2:
        return 0.0
    average = _mean(values)
    variance = sum((value - average) ** 2 for value in values) / len(values)
    return math.sqrt(variance)


def _correlation(values: Sequence[float], target: Sequence[float]) -> float:
    if len(values) != len(target) or len(values) < 2:
        return 0.0
    value_mean = _mean(values)
    target_mean = _mean(target)
    centered_values = [value - value_mean for value in values]
    centered_target = [current_target - target_mean for current_target in target]
    numerator = sum(
        current_value * current_target
        for current_value, current_target in zip(centered_values, centered_target, strict=True)
    )
    denominator = math.sqrt(
        sum(current_value**2 for current_value in centered_values)
        * sum(current_target**2 for current_target in centered_target)
    )
    if denominator == 0:
        return 0.0
    return numerator / denominator


def _build_feature_statistics(
    rows: Sequence[DatasetArtifactRow],
    feature_names: Sequence[str],
) -> tuple[dict[str, float], dict[str, float], dict[str, float]]:
    feature_means: dict[str, float] = {}
    feature_stds: dict[str, float] = {}
    feature_imputes: dict[str, float] = {}
    for feature_name in feature_names:
        available_values = [
            float(value)
            for value in (row.features.get(feature_name) for row in rows)
            if value is not None
        ]
        mean_value = _mean(available_values)
        std_value = _stddev(available_values) or 1.0
        feature_means[feature_name] = mean_value
        feature_stds[feature_name] = std_value
        feature_imputes[feature_name] = mean_value
    return feature_means, feature_stds, feature_imputes


def _standardized_vector(
    feature_names: Sequence[str],
    feature_means: dict[str, float],
    feature_stds: dict[str, float],
    feature_imputes: dict[str, float],
    features: dict[str, float | None],
) -> list[float]:
    vector: list[float] = []
    for feature_name in feature_names:
        raw_value = features.get(feature_name)
        value = feature_imputes[feature_name] if raw_value is None else float(raw_value)
        vector.append((value - feature_means[feature_name]) / feature_stds[feature_name])
    return vector


def _training_targets(rows: Sequence[DatasetArtifactRow], label_name: str) -> list[float]:
    targets = [
        float(label_value)
        for label_value in (row.labels.get(label_name) for row in rows)
        if label_value is not None
    ]
    if len(targets) != len(rows):
        raise RuntimeError(f"Training rows are missing target label '{label_name}'.")
    return targets


def _serialize_estimator(estimator: GradientBoostingEstimator) -> str:
    return base64.b64encode(pickle.dumps(estimator)).decode("ascii")


def _deserialize_estimator(model: LinearModelArtifact) -> GradientBoostingEstimator:
    if model.serialized_model is None:
        raise RuntimeError("Model artifact is missing its serialized estimator.")
    payload = base64.b64decode(model.serialized_model.encode("ascii"))
    estimator = pickle.loads(payload)
    if not isinstance(estimator, HistGradientBoostingRegressor):
        raise RuntimeError("Serialized model payload was not a gradient boosting regressor.")
    return estimator


def serialize_model_artifact(model: LinearModelArtifact) -> dict[str, Any]:
    return {
        "version": model.version,
        "family": model.family,
        "dataset_snapshot_id": model.dataset_snapshot_id,
        "feature_set_version": model.feature_set_version,
        "label_version": model.label_version,
        "label_name": model.label_name,
        "feature_names": list(model.feature_names),
        "feature_means": model.feature_means,
        "feature_stds": model.feature_stds,
        "feature_imputes": model.feature_imputes,
        "feature_weights": model.feature_weights,
        "training_start_date": model.training_start_date.isoformat(),
        "training_end_date": model.training_end_date.isoformat(),
        "training_row_count": model.training_row_count,
        "holdout_start_date": model.holdout_start_date.isoformat(),
        "holdout_end_date": model.holdout_end_date.isoformat(),
        "serialized_model": model.serialized_model,
        "serialized_format": model.serialized_format,
        "component_payloads": model.component_payloads,
        "metadata": model.metadata,
    }


def deserialize_model_artifact(payload: dict[str, Any]) -> LinearModelArtifact:
    return LinearModelArtifact(
        version=str(payload["version"]),
        family=str(payload["family"]),
        dataset_snapshot_id=int(payload["dataset_snapshot_id"]),
        feature_set_version=str(payload["feature_set_version"]),
        label_version=str(payload["label_version"]),
        label_name=str(payload["label_name"]),
        feature_names=tuple(str(name) for name in payload["feature_names"]),
        feature_means={key: float(value) for key, value in dict(payload["feature_means"]).items()},
        feature_stds={key: float(value) for key, value in dict(payload["feature_stds"]).items()},
        feature_imputes={
            key: float(value) for key, value in dict(payload["feature_imputes"]).items()
        },
        feature_weights={
            key: float(value) for key, value in dict(payload.get("feature_weights", {})).items()
        },
        training_start_date=date.fromisoformat(str(payload["training_start_date"])),
        training_end_date=date.fromisoformat(str(payload["training_end_date"])),
        training_row_count=int(payload["training_row_count"]),
        holdout_start_date=date.fromisoformat(str(payload["holdout_start_date"])),
        holdout_end_date=date.fromisoformat(str(payload["holdout_end_date"])),
        serialized_model=(
            None if payload.get("serialized_model") is None else str(payload["serialized_model"])
        ),
        serialized_format=(
            None if payload.get("serialized_format") is None else str(payload["serialized_format"])
        ),
        component_payloads=dict(payload.get("component_payloads", {})),
        metadata=dict(payload.get("metadata", {})),
    )


def fit_linear_correlation_model(
    *,
    rows: Sequence[DatasetArtifactRow],
    dataset_snapshot_id: int,
    feature_set_version: str,
    label_version: str,
    model_family: str,
    label_name: str,
    model_version: str,
    holdout_start_date: date,
    holdout_end_date: date,
) -> LinearModelArtifact:
    if not rows:
        raise RuntimeError("Cannot train a model without dataset rows.")

    feature_names = tuple(sorted(rows[0].features.keys()))
    target_values = _training_targets(rows, label_name)
    feature_means, feature_stds, feature_imputes = _build_feature_statistics(rows, feature_names)

    feature_weights: dict[str, float] = {}
    for feature_name in feature_names:
        normalized_values = [
            _standardized_vector(
                (feature_name,),
                feature_means,
                feature_stds,
                feature_imputes,
                row.features,
            )[0]
            for row in rows
        ]
        missing_count = sum(1 for row in rows if row.features.get(feature_name) is None)
        missing_penalty = 1.0 - missing_count / len(rows)
        feature_weights[feature_name] = (
            _correlation(normalized_values, target_values) * missing_penalty
        )

    weight_scale = sum(abs(weight) for weight in feature_weights.values())
    if weight_scale > 0:
        feature_weights = {
            feature_name: weight / weight_scale for feature_name, weight in feature_weights.items()
        }

    training_dates = sorted({row.trade_date for row in rows})
    return LinearModelArtifact(
        version=model_version,
        family=model_family,
        dataset_snapshot_id=dataset_snapshot_id,
        feature_set_version=feature_set_version,
        label_version=label_version,
        label_name=label_name,
        feature_names=feature_names,
        feature_means=feature_means,
        feature_stds=feature_stds,
        feature_imputes=feature_imputes,
        feature_weights=feature_weights,
        training_start_date=training_dates[0],
        training_end_date=training_dates[-1],
        training_row_count=len(rows),
        holdout_start_date=holdout_start_date,
        holdout_end_date=holdout_end_date,
        metadata={
            "non_zero_weight_count": sum(
                1 for weight in feature_weights.values() if abs(weight) > 1e-12
            )
        },
    )


def fit_gradient_boosting_model(
    *,
    rows: Sequence[DatasetArtifactRow],
    dataset_snapshot_id: int,
    feature_set_version: str,
    label_version: str,
    model_family: str,
    label_name: str,
    model_version: str,
    holdout_start_date: date,
    holdout_end_date: date,
) -> LinearModelArtifact:
    if not rows:
        raise RuntimeError("Cannot train a model without dataset rows.")

    feature_names = tuple(sorted(rows[0].features.keys()))
    target_values = _training_targets(rows, label_name)
    feature_means, feature_stds, feature_imputes = _build_feature_statistics(rows, feature_names)
    feature_matrix = [
        _standardized_vector(
            feature_names,
            feature_means,
            feature_stds,
            feature_imputes,
            row.features,
        )
        for row in rows
    ]
    estimator = HistGradientBoostingRegressor(
        learning_rate=0.05,
        max_depth=3,
        max_bins=63,
        max_iter=60,
        min_samples_leaf=10,
        random_state=0,
    )
    estimator.fit(feature_matrix, target_values)

    training_dates = sorted({row.trade_date for row in rows})
    return LinearModelArtifact(
        version=model_version,
        family=model_family,
        dataset_snapshot_id=dataset_snapshot_id,
        feature_set_version=feature_set_version,
        label_version=label_version,
        label_name=label_name,
        feature_names=feature_names,
        feature_means=feature_means,
        feature_stds=feature_stds,
        feature_imputes=feature_imputes,
        feature_weights={},
        training_start_date=training_dates[0],
        training_end_date=training_dates[-1],
        training_row_count=len(rows),
        holdout_start_date=holdout_start_date,
        holdout_end_date=holdout_end_date,
        serialized_model=_serialize_estimator(estimator),
        serialized_format="pickle-base64",
        metadata={"max_iter": estimator.max_iter, "n_iter_": estimator.n_iter_},
    )


def fit_rank_ensemble_model(
    *,
    rows: Sequence[DatasetArtifactRow],
    dataset_snapshot_id: int,
    feature_set_version: str,
    label_version: str,
    label_name: str,
    model_version: str,
    holdout_start_date: date,
    holdout_end_date: date,
) -> LinearModelArtifact:
    linear_model = fit_linear_correlation_model(
        rows=rows,
        dataset_snapshot_id=dataset_snapshot_id,
        feature_set_version=feature_set_version,
        label_version=label_version,
        model_family="linear-correlation-v1",
        label_name=label_name,
        model_version=f"{model_version}-linear",
        holdout_start_date=holdout_start_date,
        holdout_end_date=holdout_end_date,
    )
    boosting_model = fit_gradient_boosting_model(
        rows=rows,
        dataset_snapshot_id=dataset_snapshot_id,
        feature_set_version=feature_set_version,
        label_version=label_version,
        model_family="gradient-boosting-v1",
        label_name=label_name,
        model_version=f"{model_version}-boosting",
        holdout_start_date=holdout_start_date,
        holdout_end_date=holdout_end_date,
    )
    return LinearModelArtifact(
        version=model_version,
        family="rank-ensemble-v1",
        dataset_snapshot_id=dataset_snapshot_id,
        feature_set_version=feature_set_version,
        label_version=label_version,
        label_name=label_name,
        feature_names=linear_model.feature_names,
        feature_means=linear_model.feature_means,
        feature_stds=linear_model.feature_stds,
        feature_imputes=linear_model.feature_imputes,
        feature_weights={},
        training_start_date=linear_model.training_start_date,
        training_end_date=linear_model.training_end_date,
        training_row_count=linear_model.training_row_count,
        holdout_start_date=holdout_start_date,
        holdout_end_date=holdout_end_date,
        component_payloads={
            "linear": serialize_model_artifact(linear_model),
            "boosting": serialize_model_artifact(boosting_model),
        },
        metadata={"components": ["linear", "boosting"]},
    )


def fit_model_artifact(
    *,
    rows: Sequence[DatasetArtifactRow],
    dataset_snapshot_id: int,
    feature_set_version: str,
    label_version: str,
    model_family: str,
    label_name: str,
    model_version: str,
    holdout_start_date: date,
    holdout_end_date: date,
) -> LinearModelArtifact:
    if model_family == "linear-correlation-v1":
        return fit_linear_correlation_model(
            rows=rows,
            dataset_snapshot_id=dataset_snapshot_id,
            feature_set_version=feature_set_version,
            label_version=label_version,
            model_family=model_family,
            label_name=label_name,
            model_version=model_version,
            holdout_start_date=holdout_start_date,
            holdout_end_date=holdout_end_date,
        )
    if model_family == "gradient-boosting-v1":
        return fit_gradient_boosting_model(
            rows=rows,
            dataset_snapshot_id=dataset_snapshot_id,
            feature_set_version=feature_set_version,
            label_version=label_version,
            model_family=model_family,
            label_name=label_name,
            model_version=model_version,
            holdout_start_date=holdout_start_date,
            holdout_end_date=holdout_end_date,
        )
    if model_family == "rank-ensemble-v1":
        return fit_rank_ensemble_model(
            rows=rows,
            dataset_snapshot_id=dataset_snapshot_id,
            feature_set_version=feature_set_version,
            label_version=label_version,
            label_name=label_name,
            model_version=model_version,
            holdout_start_date=holdout_start_date,
            holdout_end_date=holdout_end_date,
        )
    raise RuntimeError(f"Unsupported model family '{model_family}'.")


def score_features_raw(
    model: LinearModelArtifact,
    features: dict[str, float | None],
) -> float:
    vector = _standardized_vector(
        model.feature_names,
        model.feature_means,
        model.feature_stds,
        model.feature_imputes,
        features,
    )
    if model.family == "linear-correlation-v1" or (
        model.serialized_model is None and not model.component_payloads
    ):
        return sum(
            value * model.feature_weights.get(feature_name, 0.0)
            for feature_name, value in zip(model.feature_names, vector, strict=True)
        )
    if model.family == "gradient-boosting-v1":
        estimator = _deserialize_estimator(model)
        return float(estimator.predict([vector])[0])
    if model.family == "rank-ensemble-v1":
        linear_model = deserialize_model_artifact(dict(model.component_payloads["linear"]))
        boosting_model = deserialize_model_artifact(dict(model.component_payloads["boosting"]))
        return (
            score_features_raw(linear_model, features)
            + score_features_raw(boosting_model, features)
        ) / 2.0
    raise RuntimeError(f"Unsupported model family '{model.family}'.")


def rank_rows(
    model: LinearModelArtifact,
    rows: Sequence[DatasetArtifactRow],
) -> list[tuple[DatasetArtifactRow, float]]:
    if model.family != "rank-ensemble-v1":
        return [(row, score_features_raw(model, row.features)) for row in rows]

    linear_model = deserialize_model_artifact(dict(model.component_payloads["linear"]))
    boosting_model = deserialize_model_artifact(dict(model.component_payloads["boosting"]))
    linear_scores = [(row, score_features_raw(linear_model, row.features)) for row in rows]
    boosting_scores = [(row, score_features_raw(boosting_model, row.features)) for row in rows]

    def _normalized_rank_pairs(
        scored_rows: list[tuple[DatasetArtifactRow, float]],
    ) -> dict[tuple[str, date], float]:
        ordered = sorted(scored_rows, key=lambda item: (item[1], item[0].symbol), reverse=True)
        count = len(ordered)
        if count <= 1:
            return {(row.symbol, row.trade_date): 1.0 for row, _score in ordered}
        return {
            (row.symbol, row.trade_date): 1.0 - index / (count - 1)
            for index, (row, _score) in enumerate(ordered)
        }

    linear_ranks = _normalized_rank_pairs(linear_scores)
    boosting_ranks = _normalized_rank_pairs(boosting_scores)
    return [
        (
            row,
            (
                linear_ranks[(row.symbol, row.trade_date)]
                + boosting_ranks[(row.symbol, row.trade_date)]
            )
            / 2.0,
        )
        for row in rows
    ]


def score_features(
    model: LinearModelArtifact,
    features: dict[str, float | None],
) -> float:
    return score_features_raw(model, features)
