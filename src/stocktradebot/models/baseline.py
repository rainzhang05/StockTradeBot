from __future__ import annotations

import math
from collections.abc import Sequence
from datetime import date

from stocktradebot.models.types import DatasetArtifactRow, LinearModelArtifact


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
    targets = [
        float(label_value)
        for label_value in (row.labels.get(label_name) for row in rows)
        if label_value is not None
    ]
    if len(targets) != len(rows):
        raise RuntimeError(f"Training rows are missing target label '{label_name}'.")

    feature_means: dict[str, float] = {}
    feature_stds: dict[str, float] = {}
    feature_imputes: dict[str, float] = {}
    feature_weights: dict[str, float] = {}
    target_values = [float(target_value) for target_value in targets]

    normalized_by_feature: dict[str, list[float]] = {}
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

        normalized_values = [
            ((mean_value if raw_value is None else float(raw_value)) - mean_value) / std_value
            for raw_value in (row.features.get(feature_name) for row in rows)
        ]
        normalized_by_feature[feature_name] = normalized_values

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


def score_features(
    model: LinearModelArtifact,
    features: dict[str, float | None],
) -> float:
    score = 0.0
    for feature_name in model.feature_names:
        value = features.get(feature_name)
        imputed_value = model.feature_imputes[feature_name] if value is None else float(value)
        standardized_value = (
            imputed_value - model.feature_means[feature_name]
        ) / model.feature_stds[feature_name]
        score += standardized_value * model.feature_weights.get(feature_name, 0.0)
    return score
