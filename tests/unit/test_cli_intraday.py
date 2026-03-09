from __future__ import annotations

from datetime import date

from typer.testing import CliRunner

from stocktradebot.cli import app
from stocktradebot.data.models import BackfillSummary, DatasetSnapshotSummary
from stocktradebot.models import IntradayValidationSummary

runner = CliRunner()


def test_intraday_cli_commands_return_intraday_summaries(isolated_app_home, monkeypatch) -> None:
    monkeypatch.setattr(
        "stocktradebot.cli.backfill_intraday_data",
        lambda *_args, **_kwargs: BackfillSummary(
            run_id=51,
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
            universe_snapshot_id=4,
            validation_counts={"verified": 26},
            providers_used=("alpha_vantage",),
            domain="intraday",
            frequency="15min",
            quality_report_path="artifacts/reports/intraday-quality.json",
        ),
    )
    monkeypatch.setattr(
        "stocktradebot.cli.build_intraday_dataset_snapshot",
        lambda *_args, **_kwargs: DatasetSnapshotSummary(
            snapshot_id=22,
            as_of_date=date(2026, 3, 11),
            universe_snapshot_id=4,
            feature_set_version="intraday-15min-core-v1",
            label_version="intraday-15min-forward-return-v1",
            row_count=300,
            null_statistics={},
            artifact_path="artifacts/datasets/intraday.jsonl",
            metadata={"symbol_count": 2},
            frequency="15min",
            as_of_timestamp="2026-03-11T15:45:00+00:00",
        ),
    )
    monkeypatch.setattr(
        "stocktradebot.cli.validate_intraday_research",
        lambda *_args, **_kwargs: IntradayValidationSummary(
            run_id=23,
            dataset_snapshot_id=22,
            frequency="15min",
            feature_set_version="intraday-15min-core-v1",
            label_version="intraday-15min-forward-return-v1",
            artifact_path="artifacts/reports/intraday-validation.json",
            fold_count=3,
            promotion_ready=True,
            promotion_reasons=(),
            metrics={"average_excess_return": 0.02},
            metadata={"latest_model_version": "intraday-v1"},
        ),
    )

    backfill_result = runner.invoke(
        app, ["intraday-backfill", "--frequency", "15min", "--symbol", "AAPL"]
    )
    dataset_result = runner.invoke(app, ["intraday-dataset", "--frequency", "15min"])
    validate_result = runner.invoke(app, ["intraday-validate", "--frequency", "15min"])

    assert backfill_result.exit_code == 0
    assert '"frequency": "15min"' in backfill_result.stdout
    assert dataset_result.exit_code == 0
    assert '"feature_set_version": "intraday-15min-core-v1"' in dataset_result.stdout
    assert validate_result.exit_code == 0
    assert '"fold_count": 3' in validate_result.stdout
