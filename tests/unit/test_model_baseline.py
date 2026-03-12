from __future__ import annotations

from datetime import date

from stocktradebot.models.baseline import (
    fit_linear_correlation_model,
    fit_model_artifact,
    rank_rows,
    score_features,
)
from stocktradebot.models.types import DatasetArtifactRow


def test_linear_correlation_model_prefers_rows_with_stronger_positive_signal() -> None:
    rows = [
        DatasetArtifactRow(
            symbol="AAA",
            trade_date=date(2026, 1, 2),
            universe_snapshot_id=1,
            features={"momentum_20d": -0.2, "earnings_yield": 0.01},
            labels={"ranking_label_5d": -1.0},
        ),
        DatasetArtifactRow(
            symbol="BBB",
            trade_date=date(2026, 1, 3),
            universe_snapshot_id=1,
            features={"momentum_20d": 0.0, "earnings_yield": 0.03},
            labels={"ranking_label_5d": 0.0},
        ),
        DatasetArtifactRow(
            symbol="CCC",
            trade_date=date(2026, 1, 4),
            universe_snapshot_id=1,
            features={"momentum_20d": 0.3, "earnings_yield": 0.06},
            labels={"ranking_label_5d": 1.0},
        ),
    ]

    model = fit_linear_correlation_model(
        rows=rows,
        dataset_snapshot_id=9,
        feature_set_version="daily-core-v1",
        label_version="forward-return-v1",
        model_family="linear-correlation-v1",
        label_name="ranking_label_5d",
        model_version="linear-correlation-v1-test",
        holdout_start_date=date(2026, 1, 5),
        holdout_end_date=date(2026, 1, 10),
    )

    low_score = score_features(
        model,
        {"momentum_20d": -0.1, "earnings_yield": 0.02},
    )
    high_score = score_features(
        model,
        {"momentum_20d": 0.4, "earnings_yield": 0.07},
    )

    assert model.training_row_count == 3
    assert model.feature_weights["momentum_20d"] > 0
    assert model.feature_weights["earnings_yield"] > 0
    assert high_score > low_score


def test_gradient_boosting_and_rank_ensemble_models_rank_stronger_rows_higher() -> None:
    rows = [
        DatasetArtifactRow(
            symbol=symbol,
            trade_date=date(2026, 1, 1 + index),
            universe_snapshot_id=1,
            features={
                "momentum_20d": -0.4 + index * 0.2,
                "earnings_yield": 0.01 + index * 0.01,
            },
            labels={"ranking_label_5d": -0.5 + index * 0.25},
        )
        for index, symbol in enumerate(("AAA", "BBB", "CCC", "DDD", "EEE"))
    ]

    boosting_model = fit_model_artifact(
        rows=rows,
        dataset_snapshot_id=12,
        feature_set_version="daily-core-v1",
        label_version="forward-return-v1",
        model_family="gradient-boosting-v1",
        label_name="ranking_label_5d",
        model_version="gradient-boosting-v1-test",
        holdout_start_date=date(2026, 1, 10),
        holdout_end_date=date(2026, 1, 20),
    )
    ensemble_model = fit_model_artifact(
        rows=rows,
        dataset_snapshot_id=12,
        feature_set_version="daily-core-v1",
        label_version="forward-return-v1",
        model_family="rank-ensemble-v1",
        label_name="ranking_label_5d",
        model_version="rank-ensemble-v1-test",
        holdout_start_date=date(2026, 1, 10),
        holdout_end_date=date(2026, 1, 20),
    )

    boosting_ranked = sorted(
        rank_rows(boosting_model, rows),
        key=lambda item: (item[1], item[0].symbol),
        reverse=True,
    )
    ensemble_ranked = sorted(
        rank_rows(ensemble_model, rows),
        key=lambda item: (item[1], item[0].symbol),
        reverse=True,
    )

    assert boosting_model.serialized_model is not None
    assert ensemble_model.component_payloads
    assert boosting_ranked[0][0].symbol == "EEE"
    assert boosting_ranked[-1][0].symbol == "AAA"
    assert ensemble_ranked[0][0].symbol == "EEE"
    assert ensemble_ranked[-1][0].symbol == "AAA"
