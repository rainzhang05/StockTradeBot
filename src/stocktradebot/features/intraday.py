from __future__ import annotations

import json
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from typing import TypedDict

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from stocktradebot import __version__
from stocktradebot.config import AppConfig
from stocktradebot.data.models import DatasetSnapshotSummary, IntradayCanonicalBarRecord
from stocktradebot.features.service import (
    _bar_return,
    _fundamentals_as_of,
    _load_fundamentals,
    _load_universe_snapshots,
    _mean,
    _snapshot_for_trade_date,
    _stddev,
)
from stocktradebot.intraday import get_frequency_spec
from stocktradebot.storage import (
    CanonicalIntradayBar,
    DatasetSnapshot,
    FeatureSetVersion,
    FundamentalObservation,
    LabelVersion,
    create_db_engine,
)

FeatureValueMap = dict[str, float | None]
LabelValueMap = dict[str, float | None]


class IntradayFeatureRow(TypedDict):
    symbol: str
    trade_date: date
    decision_at: datetime
    frequency: str
    universe_snapshot_id: int | None
    fundamentals_available_at: datetime | None
    features: FeatureValueMap


def _require_float(value: float | None, *, field_name: str) -> float:
    if value is None:
        raise RuntimeError(f"Intraday dataset is missing required field '{field_name}'.")
    return float(value)


def _feature_definition(frequency: str) -> dict[str, object]:
    spec = get_frequency_spec(frequency)
    return {
        "version": spec.feature_set_version,
        "frequency": spec.name,
        "features": {
            "momentum_5bar": {
                "formula": "close_t / close_t-5 - 1",
                "null_policy": "requires 5 bars",
            },
            "momentum_20bar": {
                "formula": "close_t / close_t-20 - 1",
                "null_policy": "requires 20 bars",
            },
            "momentum_60bar": {
                "formula": "close_t / close_t-60 - 1",
                "null_policy": "requires 60 bars",
            },
            "mean_reversion_3bar": {
                "formula": "-1 * (close_t / close_t-3 - 1)",
                "null_policy": "requires 3 bars",
            },
            "realized_vol_20bar": {
                "formula": "stddev(returns_20bar)",
                "null_policy": "requires 20 bars",
            },
            "downside_vol_20bar": {
                "formula": "stddev(min(return,0) over 20 bars)",
                "null_policy": "requires 20 bars",
            },
            "max_drawdown_20bar": {
                "formula": "rolling wealth max drawdown over 20 bars",
                "null_policy": "requires 20 bars",
            },
            "dollar_volume_20bar": {
                "formula": "mean(close * volume over 20 bars)",
                "null_policy": "requires 20 bars",
            },
            "volume_ratio_20bar": {
                "formula": "volume_t / mean(volume over 20 bars)",
                "null_policy": "requires 20 bars",
            },
            "benchmark_relative_20bar": {
                "formula": "symbol_return_20bar - benchmark_return_20bar",
                "null_policy": "null if benchmark unavailable",
            },
            "regime_return_20bar": {
                "formula": "benchmark_return_20bar",
                "null_policy": "null if benchmark unavailable",
            },
            "regime_vol_20bar": {
                "formula": "benchmark_vol_20bar",
                "null_policy": "null if benchmark unavailable",
            },
            "cross_sectional_strength_20bar": {
                "formula": "zscore of 20-bar return within active universe",
                "null_policy": "requires at least two valid rows on the timestamp",
            },
            "earnings_yield": {
                "formula": "net_income_ttm / market_cap",
                "null_policy": "null if shares or income unavailable",
            },
            "sales_yield": {
                "formula": "revenue_ttm / market_cap",
                "null_policy": "null if shares or revenue unavailable",
            },
            "book_to_price": {
                "formula": "shareholders_equity / market_cap",
                "null_policy": "null if equity or shares unavailable",
            },
            "debt_to_equity": {
                "formula": "total_liabilities / shareholders_equity",
                "null_policy": "null if equity unavailable",
            },
            "asset_growth": {
                "formula": "(assets_now - assets_prev_year) / abs(assets_prev_year)",
                "null_policy": "null if prior-year assets unavailable",
            },
            "accrual_quality": {
                "formula": "(net_income_ttm - operating_cash_flow_ttm) / assets",
                "null_policy": "null if operating cash flow unavailable",
            },
            "free_cash_flow_yield": {
                "formula": "(operating_cash_flow_ttm - abs(capex_ttm)) / market_cap",
                "null_policy": "null if free cash flow unavailable",
            },
        },
    }


def _label_definition(frequency: str) -> dict[str, object]:
    spec = get_frequency_spec(frequency)
    return {
        "version": spec.label_version,
        "frequency": spec.name,
        "labels": {
            "ranking_label_primary": {
                "formula": (
                    f"zscore of {spec.primary_horizon_bars}-bar forward total return "
                    "within active universe"
                ),
                "null_policy": f"requires future {spec.primary_horizon_bars} verified bars",
            },
            "forward_return_primary": {
                "formula": f"{spec.primary_horizon_bars}-bar forward total return",
                "null_policy": f"requires future {spec.primary_horizon_bars} verified bars",
            },
            "forward_return_secondary": {
                "formula": f"{spec.secondary_horizon_bars}-bar forward total return",
                "null_policy": f"requires future {spec.secondary_horizon_bars} verified bars",
            },
            "forward_max_drawdown_secondary": {
                "formula": (
                    f"minimum drawdown on the {spec.secondary_horizon_bars}-bar forward wealth path"
                ),
                "null_policy": f"requires future {spec.secondary_horizon_bars} verified bars",
            },
        },
    }


def _persist_feature_set(session: Session, definition: dict[str, object]) -> None:
    version = str(definition["version"])
    if session.get(FeatureSetVersion, version) is None:
        session.add(
            FeatureSetVersion(
                version=version, definition_json=json.dumps(definition, sort_keys=True)
            )
        )


def _persist_label_version(session: Session, definition: dict[str, object]) -> None:
    version = str(definition["version"])
    if session.get(LabelVersion, version) is None:
        session.add(
            LabelVersion(version=version, definition_json=json.dumps(definition, sort_keys=True))
        )


def _load_verified_intraday_bars(
    session: Session,
    *,
    symbols: list[str],
    frequency: str,
    start_date: date,
    end_date: date,
) -> list[IntradayCanonicalBarRecord]:
    rows = session.scalars(
        select(CanonicalIntradayBar).where(
            CanonicalIntradayBar.symbol.in_(tuple(symbols)),
            CanonicalIntradayBar.frequency == frequency,
            CanonicalIntradayBar.session_date >= start_date,
            CanonicalIntradayBar.session_date <= end_date,
            CanonicalIntradayBar.validation_tier == "verified",
        )
    ).all()
    return [
        IntradayCanonicalBarRecord(
            symbol=row.symbol,
            frequency=row.frequency,
            bar_start=row.bar_start,
            open=row.open,
            high=row.high,
            low=row.low,
            close=row.close,
            volume=row.volume,
            validation_tier=row.validation_tier,
            primary_provider=row.primary_provider,
            confirming_provider=row.confirming_provider,
            field_provenance=json.loads(row.field_provenance),
        )
        for row in rows
    ]


def _forward_total_return(
    bars: list[IntradayCanonicalBarRecord],
    start_index: int,
    horizon: int,
) -> float | None:
    end_index = start_index + horizon
    if end_index >= len(bars):
        return None
    start_close = bars[start_index].close
    if start_close == 0:
        return None
    return bars[end_index].close / start_close - 1.0


def _forward_max_drawdown(
    bars: list[IntradayCanonicalBarRecord],
    start_index: int,
    horizon: int,
) -> float | None:
    end_index = start_index + horizon
    if end_index >= len(bars):
        return None
    start_close = bars[start_index].close
    if start_close == 0:
        return None
    running_peak = 1.0
    worst_drawdown = 0.0
    for current_index in range(start_index + 1, end_index + 1):
        wealth = bars[current_index].close / start_close
        running_peak = max(running_peak, wealth)
        worst_drawdown = min(worst_drawdown, wealth / running_peak - 1.0)
    return worst_drawdown


def _write_dataset_artifact(
    config: AppConfig,
    *,
    frequency: str,
    feature_set_version: str,
    label_version: str,
    rows: list[dict[str, object]],
) -> str:
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    artifact_path = config.dataset_artifacts_dir / (
        f"dataset-intraday-{frequency}-{feature_set_version}-{label_version}-{timestamp}.jsonl"
    )
    payload = "\n".join(json.dumps(row, sort_keys=True, default=str) for row in rows)
    artifact_path.write_text(payload + ("\n" if payload else ""), encoding="utf-8")
    return str(artifact_path.relative_to(config.app_home))


def build_intraday_dataset_snapshot(
    config: AppConfig,
    *,
    frequency: str,
    as_of_date: date | None = None,
) -> DatasetSnapshotSummary:
    spec = get_frequency_spec(frequency)
    effective_as_of_date = as_of_date or datetime.now(UTC).date()
    start_date = effective_as_of_date - timedelta(days=spec.dataset_lookback_sessions * 3)

    engine = create_db_engine(config)
    try:
        with Session(engine) as session:
            snapshots = _load_universe_snapshots(session, as_of_date=effective_as_of_date)
            if not snapshots:
                raise RuntimeError("No universe snapshots are available. Run daily backfill first.")

            all_symbols = sorted({symbol for _, members in snapshots for symbol in members})
            benchmark_symbol = config.model_training.benchmark_symbol
            if benchmark_symbol not in all_symbols:
                all_symbols.append(benchmark_symbol)

            bars = _load_verified_intraday_bars(
                session,
                symbols=all_symbols,
                frequency=spec.name,
                start_date=start_date,
                end_date=effective_as_of_date,
            )
            if not bars:
                raise RuntimeError(
                    f"No verified intraday bars are available for frequency '{frequency}'."
                )

            fundamental_observations = _load_fundamentals(session, symbols=all_symbols)
            bars_by_symbol: dict[str, list[IntradayCanonicalBarRecord]] = defaultdict(list)
            for bar in sorted(bars, key=lambda current: (current.symbol, current.bar_start)):
                bars_by_symbol[bar.symbol].append(bar)
            fundamentals_by_symbol = defaultdict(list)
            for observation in sorted(
                fundamental_observations,
                key=lambda current: (current.symbol, current.metric_name, current.available_at),
            ):
                fundamentals_by_symbol[observation.symbol].append(observation)

            benchmark_bars = bars_by_symbol.get(benchmark_symbol, [])
            benchmark_returns: dict[datetime, float | None] = {}
            benchmark_vol: dict[datetime, float | None] = {}
            for index, bar in enumerate(benchmark_bars):
                if index < 20:
                    benchmark_returns[bar.bar_start] = None
                    benchmark_vol[bar.bar_start] = None
                    continue
                benchmark_returns[bar.bar_start] = (
                    bar.close / benchmark_bars[index - 20].close - 1.0
                )
                window = benchmark_bars[index - 19 : index + 1]
                returns = [
                    _bar_return(window[current].close, window[current + 1].close)
                    for current in range(len(window) - 1)
                ]
                benchmark_vol[bar.bar_start] = _stddev(returns)

            feature_rows: list[IntradayFeatureRow] = []
            label_rows: dict[tuple[str, datetime], LabelValueMap] = {}
            feature_definition = _feature_definition(spec.name)
            label_definition = _label_definition(spec.name)

            for symbol, symbol_bars in sorted(bars_by_symbol.items()):
                if symbol == benchmark_symbol:
                    continue
                for index, bar in enumerate(symbol_bars):
                    if index < spec.minimum_history_bars:
                        continue
                    universe_snapshot_id, active_symbols = _snapshot_for_trade_date(
                        snapshots,
                        bar.trade_date,
                    )
                    if symbol not in active_symbols:
                        continue
                    if index < 60:
                        continue

                    window_3 = symbol_bars[index - 3 : index + 1]
                    window_20 = symbol_bars[index - 20 : index + 1]
                    window_60 = symbol_bars[index - 60 : index + 1]
                    returns_20 = [
                        _bar_return(window_20[current].close, window_20[current + 1].close)
                        for current in range(len(window_20) - 1)
                    ]
                    negative_returns_20 = [
                        min(current_return, 0.0) for current_return in returns_20
                    ]
                    rolling_peak = window_20[0].close
                    worst_drawdown = 0.0
                    for current_bar in window_20[1:]:
                        rolling_peak = max(rolling_peak, current_bar.close)
                        worst_drawdown = min(worst_drawdown, current_bar.close / rolling_peak - 1.0)

                    fundamental_ratios, fundamentals_available_at = _fundamentals_as_of(
                        fundamentals_by_symbol[symbol],
                        as_of_datetime=bar.bar_start,
                        close=bar.close,
                    )
                    benchmark_return_20bar = benchmark_returns.get(bar.bar_start)
                    benchmark_vol_20bar = benchmark_vol.get(bar.bar_start)
                    symbol_return_20bar = bar.close / window_20[0].close - 1.0
                    feature_rows.append(
                        {
                            "symbol": symbol,
                            "trade_date": bar.trade_date,
                            "decision_at": bar.bar_start,
                            "frequency": spec.name,
                            "universe_snapshot_id": universe_snapshot_id,
                            "fundamentals_available_at": fundamentals_available_at,
                            "features": {
                                "momentum_5bar": bar.close / symbol_bars[index - 5].close - 1.0,
                                "momentum_20bar": symbol_return_20bar,
                                "momentum_60bar": bar.close / window_60[0].close - 1.0,
                                "mean_reversion_3bar": -(bar.close / window_3[0].close - 1.0),
                                "realized_vol_20bar": _stddev(returns_20),
                                "downside_vol_20bar": _stddev(negative_returns_20),
                                "max_drawdown_20bar": worst_drawdown,
                                "dollar_volume_20bar": _mean(
                                    [
                                        current_bar.close * current_bar.volume
                                        for current_bar in window_20
                                    ]
                                ),
                                "volume_ratio_20bar": bar.volume
                                / _mean([current_bar.volume for current_bar in window_20]),
                                "benchmark_relative_20bar": None
                                if benchmark_return_20bar is None
                                else symbol_return_20bar - benchmark_return_20bar,
                                "regime_return_20bar": benchmark_return_20bar,
                                "regime_vol_20bar": benchmark_vol_20bar,
                                "cross_sectional_strength_20bar": None,
                                **fundamental_ratios,
                            },
                        }
                    )
                    forward_primary = _forward_total_return(
                        symbol_bars, index, spec.primary_horizon_bars
                    )
                    forward_secondary = _forward_total_return(
                        symbol_bars, index, spec.secondary_horizon_bars
                    )
                    forward_drawdown = _forward_max_drawdown(
                        symbol_bars, index, spec.secondary_horizon_bars
                    )
                    if (
                        forward_primary is None
                        or forward_secondary is None
                        or forward_drawdown is None
                    ):
                        continue
                    label_rows[(symbol, bar.bar_start)] = {
                        "ranking_label_primary": None,
                        "forward_return_primary": forward_primary,
                        "forward_return_secondary": forward_secondary,
                        "forward_max_drawdown_secondary": forward_drawdown,
                    }

            filtered_feature_rows = [
                row for row in feature_rows if (row["symbol"], row["decision_at"]) in label_rows
            ]
            if not filtered_feature_rows:
                raise RuntimeError(
                    "No intraday feature-ready rows could be built. Run intraday backfill first."
                )

            rows_by_decision: dict[datetime, list[IntradayFeatureRow]] = defaultdict(list)
            for row in filtered_feature_rows:
                rows_by_decision[row["decision_at"]].append(row)

            artifact_rows: list[dict[str, object]] = []
            null_statistics: dict[str, int] = defaultdict(int)
            for decision_at, rows_for_timestamp in sorted(rows_by_decision.items()):
                strength_candidates = [
                    _require_float(
                        row["features"]["momentum_20bar"],
                        field_name="momentum_20bar",
                    )
                    for row in rows_for_timestamp
                    if row["features"]["momentum_20bar"] is not None
                ]
                strength_mean = _mean(strength_candidates)
                strength_std = _stddev(strength_candidates)
                label_candidates = [
                    _require_float(
                        label_rows[(row["symbol"], decision_at)]["forward_return_primary"],
                        field_name="forward_return_primary",
                    )
                    for row in rows_for_timestamp
                ]
                label_mean = _mean(label_candidates)
                label_std = _stddev(label_candidates)

                for row in rows_for_timestamp:
                    features = dict(row["features"])
                    momentum_20bar = features["momentum_20bar"]
                    if momentum_20bar is not None and strength_std > 0:
                        features["cross_sectional_strength_20bar"] = (
                            float(momentum_20bar) - strength_mean
                        ) / strength_std
                    else:
                        features["cross_sectional_strength_20bar"] = (
                            0.0 if momentum_20bar is not None else None
                        )

                    labels = dict(label_rows[(row["symbol"], decision_at)])
                    raw_label = _require_float(
                        labels["forward_return_primary"],
                        field_name="forward_return_primary",
                    )
                    labels["ranking_label_primary"] = (
                        0.0 if label_std == 0 else (raw_label - label_mean) / label_std
                    )

                    for key, value in features.items():
                        if value is None:
                            null_statistics[f"feature:{key}"] += 1
                    for key, value in labels.items():
                        if value is None:
                            null_statistics[f"label:{key}"] += 1

                    artifact_rows.append(
                        {
                            "symbol": row["symbol"],
                            "trade_date": row["trade_date"].isoformat(),
                            "decision_at": decision_at.isoformat(),
                            "frequency": spec.name,
                            "universe_snapshot_id": row["universe_snapshot_id"],
                            "feature_set_version": spec.feature_set_version,
                            "label_version": spec.label_version,
                            "fundamentals_available_at": (
                                None
                                if row["fundamentals_available_at"] is None
                                else row["fundamentals_available_at"].isoformat()
                            ),
                            "features": features,
                            "labels": labels,
                        }
                    )

            _persist_feature_set(session, feature_definition)
            _persist_label_version(session, label_definition)
            session.flush()

            artifact_path = _write_dataset_artifact(
                config,
                frequency=spec.name,
                feature_set_version=spec.feature_set_version,
                label_version=spec.label_version,
                rows=artifact_rows,
            )
            latest_snapshot_id, _ = _snapshot_for_trade_date(snapshots, effective_as_of_date)
            last_decision_at = max(rows_by_decision)
            dataset_snapshot = DatasetSnapshot(
                as_of_date=effective_as_of_date,
                as_of_timestamp=last_decision_at,
                frequency=spec.name,
                universe_snapshot_id=latest_snapshot_id,
                feature_set_version=spec.feature_set_version,
                label_version=spec.label_version,
                canonicalization_version=f"intraday-{spec.name}-v1",
                generation_code_version=__version__,
                row_count=len(artifact_rows),
                null_statistics_json=json.dumps(
                    dict(sorted(null_statistics.items())), sort_keys=True
                ),
                metadata_json=json.dumps(
                    {
                        "start_date": start_date.isoformat(),
                        "benchmark_symbol": benchmark_symbol,
                        "symbol_count": len({row["symbol"] for row in filtered_feature_rows}),
                    },
                    sort_keys=True,
                ),
                artifact_path=artifact_path,
            )
            session.add(dataset_snapshot)
            session.commit()

            return DatasetSnapshotSummary(
                snapshot_id=dataset_snapshot.id,
                as_of_date=effective_as_of_date,
                universe_snapshot_id=latest_snapshot_id,
                feature_set_version=spec.feature_set_version,
                label_version=spec.label_version,
                row_count=len(artifact_rows),
                null_statistics=dict(sorted(null_statistics.items())),
                artifact_path=artifact_path,
                metadata={
                    "start_date": start_date.isoformat(),
                    "benchmark_symbol": benchmark_symbol,
                    "symbol_count": len({row["symbol"] for row in artifact_rows}),
                },
                frequency=spec.name,
                as_of_timestamp=last_decision_at.isoformat(),
            )
    finally:
        engine.dispose()


def intraday_dataset_status(
    config: AppConfig, *, frequency: str | None = None
) -> dict[str, object]:
    engine = create_db_engine(config)
    try:
        with Session(engine) as session:
            query = select(DatasetSnapshot).where(DatasetSnapshot.frequency != "daily")
            if frequency is not None:
                query = query.where(DatasetSnapshot.frequency == frequency)
            latest_snapshot = session.scalar(
                query.order_by(DatasetSnapshot.created_at.desc(), DatasetSnapshot.id.desc())
            )
            versions = session.scalars(
                select(FeatureSetVersion).order_by(FeatureSetVersion.created_at.desc())
            ).all()
            label_versions = session.scalars(
                select(LabelVersion).order_by(LabelVersion.created_at.desc())
            ).all()
            fundamentals_count = session.scalar(
                select(func.count()).select_from(FundamentalObservation)
            )
    finally:
        engine.dispose()

    return {
        "latest_dataset_snapshot": (
            None
            if latest_snapshot is None
            else {
                "id": latest_snapshot.id,
                "as_of_date": latest_snapshot.as_of_date.isoformat(),
                "as_of_timestamp": (
                    None
                    if latest_snapshot.as_of_timestamp is None
                    else latest_snapshot.as_of_timestamp.isoformat()
                ),
                "frequency": latest_snapshot.frequency,
                "feature_set_version": latest_snapshot.feature_set_version,
                "label_version": latest_snapshot.label_version,
                "row_count": latest_snapshot.row_count,
                "artifact_path": latest_snapshot.artifact_path,
                "metadata": json.loads(latest_snapshot.metadata_json),
            }
        ),
        "feature_set_versions": [
            json.loads(version.definition_json)
            for version in versions
            if json.loads(version.definition_json).get("frequency") is not None
        ],
        "label_versions": [
            json.loads(version.definition_json)
            for version in label_versions
            if json.loads(version.definition_json).get("frequency") is not None
        ],
        "fundamentals_observation_count": fundamentals_count or 0,
    }
