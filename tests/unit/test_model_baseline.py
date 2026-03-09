from __future__ import annotations

from datetime import date

from stocktradebot.models.baseline import fit_linear_correlation_model, score_features
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
