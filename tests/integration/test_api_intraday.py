from __future__ import annotations

from datetime import date

from fastapi.testclient import TestClient

from stocktradebot.api import create_app
from stocktradebot.config import initialize_config
from stocktradebot.data.models import BackfillSummary, DatasetSnapshotSummary
from stocktradebot.models import IntradayValidationSummary
from stocktradebot.storage import initialize_database


def test_intraday_api_endpoints_expose_phase9_workflow(isolated_app_home, monkeypatch) -> None:
    config = initialize_config(isolated_app_home)
    initialize_database(config)
    client = TestClient(create_app(config))

    monkeypatch.setattr(
        "stocktradebot.api.app.backfill_intraday_data",
        lambda *_args, **_kwargs: BackfillSummary(
            run_id=41,
            as_of_date=date(2026, 3, 11),
            requested_symbols=("AAPL",),
            primary_provider="alpha_vantage",
            secondary_provider=None,
            payload_count=1,
            observation_count=26,
            fundamentals_payload_count=0,
            fundamentals_observation_count=0,
            canonical_count=26,
            incident_count=0,
            universe_snapshot_id=7,
            validation_counts={"verified": 26},
            providers_used=("alpha_vantage",),
            domain="intraday",
            frequency="15min",
            quality_report_path="artifacts/reports/intraday-quality.json",
        ),
    )
    monkeypatch.setattr(
        "stocktradebot.api.app.build_intraday_dataset_snapshot",
        lambda *_args, **_kwargs: DatasetSnapshotSummary(
            snapshot_id=12,
            as_of_date=date(2026, 3, 11),
            universe_snapshot_id=7,
            feature_set_version="intraday-15min-core-v1",
            label_version="intraday-15min-forward-return-v1",
            row_count=400,
            null_statistics={},
            artifact_path="artifacts/datasets/intraday.jsonl",
            metadata={"symbol_count": 2},
            frequency="15min",
            as_of_timestamp="2026-03-11T15:45:00+00:00",
        ),
    )
    monkeypatch.setattr(
        "stocktradebot.api.app.validate_intraday_research",
        lambda *_args, **_kwargs: IntradayValidationSummary(
            run_id=14,
            dataset_snapshot_id=12,
            frequency="15min",
            feature_set_version="intraday-15min-core-v1",
            label_version="intraday-15min-forward-return-v1",
            artifact_path="artifacts/reports/intraday-validation.json",
            fold_count=3,
            promotion_ready=True,
            promotion_reasons=(),
            metrics={"average_excess_return": 0.01},
            metadata={"latest_model_version": "intraday-model-v1"},
        ),
    )

    backfill = client.post(
        "/api/v1/market-data/intraday/backfill",
        params={"frequency": "15min", "as_of": "2026-03-11", "symbol": ["AAPL"]},
    )
    dataset = client.post(
        "/api/v1/models/intraday/datasets/build",
        params={"frequency": "15min", "as_of": "2026-03-11"},
    )
    validation = client.post(
        "/api/v1/models/intraday/validate",
        params={"frequency": "15min", "as_of": "2026-03-11"},
    )

    assert backfill.status_code == 200
    assert backfill.json()["backfill_run"]["frequency"] == "15min"
    assert dataset.status_code == 200
    assert dataset.json()["snapshot"]["feature_set_version"] == "intraday-15min-core-v1"
    assert validation.status_code == 200
    assert validation.json()["validation_run"]["fold_count"] == 3
