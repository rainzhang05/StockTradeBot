from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import distinct, func, or_, select
from sqlalchemy.orm import Session

from stocktradebot.config import AppConfig
from stocktradebot.data import backfill_market_data, market_data_status
from stocktradebot.models import backtest_model, train_model
from stocktradebot.storage import (
    BackfillRun,
    BacktestRun,
    CanonicalDailyBar,
    DatasetSnapshot,
    ModelRegistryEntry,
    UniverseSnapshot,
    ValidationRun,
    create_db_engine,
    database_exists,
    database_is_reachable,
    initialize_database,
)

STRATEGY_MODE_KEYS = ("conservative", "balanced", "growth", "aggressive")
FULL_HISTORY_MIN_TRADE_DATES = 750
FULL_HISTORY_MIN_UNIVERSE_SNAPSHOTS = 24
DATA_STALENESS_GRACE_DAYS = 7


@dataclass(slots=True, frozen=True)
class StrategyModeDefinition:
    key: str
    label: str
    level: int
    description: str
    config_patch: dict[str, Any] | None = None
    classification: str = "planned"

    @property
    def is_defined(self) -> bool:
        return self.config_patch is not None


def _strategy_mode_catalog() -> tuple[StrategyModeDefinition, ...]:
    return (
        StrategyModeDefinition(
            key="conservative",
            label="Conservative",
            level=1,
            description="Reserved for a future lower-volatility strategy profile.",
        ),
        StrategyModeDefinition(
            key="balanced",
            label="Balanced",
            level=2,
            description="Reserved for a future middle-risk strategy profile.",
        ),
        StrategyModeDefinition(
            key="growth",
            label="Growth",
            level=3,
            description=(
                "Current winning strategy profile: diversified long-only equities with "
                "turnover control, sector caps, and risk-off throttling. This sits above "
                "balanced but below a future fully aggressive profile."
            ),
            classification="current-winner",
            config_patch={
                "model_training": {
                    "quality_scope": "research",
                    "model_family": "linear-correlation-v1",
                    "feature_set_version": "daily-alpha-v2",
                    "label_version": "forward-return-v1",
                    "target_label_name": "ranking_label_5d",
                    "rebalance_interval_days": 3,
                },
                "portfolio": {
                    "risk_on_target_positions": 20,
                    "turnover_penalty": 0.10,
                    "risk_off_gross_exposure": 0.35,
                    "defensive_etf_symbol": None,
                },
            },
        ),
        StrategyModeDefinition(
            key="aggressive",
            label="Aggressive",
            level=4,
            description="Reserved for a future higher-risk, higher-variance strategy profile.",
        ),
    )


def _merge_dict(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in patch.items():
        existing = merged.get(key)
        if isinstance(existing, dict) and isinstance(value, dict):
            merged[key] = _merge_dict(existing, value)
        else:
            merged[key] = value
    return merged


def _config_with_patch(config: AppConfig, patch: dict[str, Any]) -> AppConfig:
    return AppConfig.from_dict(_merge_dict(config.to_dict(), patch), app_home=config.app_home)


def _config_matches_patch(config: AppConfig, patch: dict[str, Any]) -> bool:
    current = config.to_dict()

    def matches(base: dict[str, Any], target: dict[str, Any]) -> bool:
        for key, value in target.items():
            if key not in base:
                return False
            base_value = base[key]
            if isinstance(value, dict):
                if not isinstance(base_value, dict):
                    return False
                if not matches(base_value, value):
                    return False
            elif base_value != value:
                return False
        return True

    return matches(current, patch)


def _serialize_date(value: date | None) -> str | None:
    return None if value is None else value.isoformat()


def _serialize_datetime(value: datetime | None) -> str | None:
    return None if value is None else value.isoformat()


def _shared_resource_snapshot(
    config: AppConfig,
    *,
    as_of_date: date,
) -> dict[str, Any]:
    market_status = market_data_status(config, incident_limit=0)
    if not database_exists(config) or not database_is_reachable(config):
        return {
            "as_of_date": as_of_date.isoformat(),
            "data_status": "missing",
            "data_summary": "The local database is not initialized yet.",
            "latest_trade_date": None,
            "latest_verified_trade_date": None,
            "distinct_trade_dates": 0,
            "universe_snapshot_count": 0,
            "latest_universe_effective_date": None,
            "stock_universe_size": 0,
            "etf_universe_size": 0,
            "daily_readiness": market_status.get("daily_readiness", {}),
            "fundamentals_status": "disabled",
            "fundamentals_summary": "SEC fundamentals are disabled.",
            "full_history_ready": False,
            "repair_recommendation": "run-full-history-repair",
        }

    engine = create_db_engine(config)
    try:
        with Session(engine) as session:
            latest_trade_date = session.scalar(select(func.max(CanonicalDailyBar.trade_date)))
            latest_verified_trade_date = session.scalar(
                select(func.max(CanonicalDailyBar.trade_date)).where(
                    CanonicalDailyBar.validation_tier == "verified"
                )
            )
            distinct_trade_dates = session.scalar(
                select(func.count(distinct(CanonicalDailyBar.trade_date)))
            )
            universe_snapshot_count = session.scalar(
                select(func.count()).select_from(UniverseSnapshot)
            )
            latest_universe = session.scalar(
                select(UniverseSnapshot).order_by(
                    UniverseSnapshot.effective_date.desc(),
                    UniverseSnapshot.id.desc(),
                )
            )
            fundamentals_value = market_status.get("fundamentals_observation_count", 0)
            fundamentals_count = (
                int(fundamentals_value) if isinstance(fundamentals_value, int | float) else 0
            )
            latest_completed_run = session.scalar(
                select(BackfillRun)
                .where(BackfillRun.domain == "daily", BackfillRun.status == "completed")
                .order_by(BackfillRun.id.desc())
            )
    finally:
        engine.dispose()

    fresh_cutoff = as_of_date - timedelta(days=DATA_STALENESS_GRACE_DAYS)
    full_history_ready = bool(
        (distinct_trade_dates or 0) >= FULL_HISTORY_MIN_TRADE_DATES
        and (universe_snapshot_count or 0) >= FULL_HISTORY_MIN_UNIVERSE_SNAPSHOTS
        and latest_universe is not None
        and latest_universe.stock_count >= 300
    )

    if latest_trade_date is None or latest_universe is None:
        data_status = "missing"
        data_summary = "No daily research history is available yet."
        repair_recommendation = "run-full-history-repair"
    elif latest_trade_date < fresh_cutoff:
        data_status = "stale"
        data_summary = (
            f"Daily data stops at {latest_trade_date.isoformat()}, which is older than the "
            f"{DATA_STALENESS_GRACE_DAYS}-day freshness window."
        )
        repair_recommendation = "refresh-data"
    elif not full_history_ready:
        data_status = "partial"
        data_summary = (
            "The local runtime can trade, but the long-range daily history or monthly "
            "universe snapshots are still incomplete."
        )
        repair_recommendation = "run-full-history-repair"
    else:
        data_status = "ready"
        data_summary = (
            f"Daily data is current through {latest_trade_date.isoformat()} with a 300-stock "
            "universe and multi-year history."
        )
        repair_recommendation = "refresh-defined-modes"

    if not config.fundamentals_provider.enabled:
        fundamentals_status = "disabled"
        fundamentals_summary = "SEC fundamentals are disabled in setup."
    elif fundamentals_count > 0:
        fundamentals_status = "ready"
        fundamentals_summary = f"{fundamentals_count} SEC-derived observations are available."
    else:
        fundamentals_status = "missing"
        fundamentals_summary = "SEC fundamentals are enabled but no observations are stored yet."

    latest_run_summary = (
        None
        if latest_completed_run is None
        else json.loads(latest_completed_run.summary_json or "{}")
    )

    return {
        "as_of_date": as_of_date.isoformat(),
        "data_status": data_status,
        "data_summary": data_summary,
        "latest_trade_date": _serialize_date(latest_trade_date),
        "latest_verified_trade_date": _serialize_date(latest_verified_trade_date),
        "distinct_trade_dates": int(distinct_trade_dates or 0),
        "universe_snapshot_count": int(universe_snapshot_count or 0),
        "latest_universe_effective_date": (
            latest_universe.effective_date.isoformat() if latest_universe is not None else None
        ),
        "stock_universe_size": 0 if latest_universe is None else latest_universe.stock_count,
        "etf_universe_size": 0 if latest_universe is None else latest_universe.etf_count,
        "daily_readiness": market_status.get("daily_readiness", {}),
        "fundamentals_status": fundamentals_status,
        "fundamentals_summary": fundamentals_summary,
        "full_history_ready": full_history_ready,
        "repair_recommendation": repair_recommendation,
        "latest_completed_backfill": (
            None
            if latest_completed_run is None
            else {
                "id": latest_completed_run.id,
                "as_of_date": latest_completed_run.as_of_date.isoformat(),
                "completed_at": _serialize_datetime(latest_completed_run.completed_at),
                "summary": latest_run_summary,
            }
        ),
    }


def _resource_status(
    *,
    item: dict[str, Any] | None,
    latest_trade_date: date | None,
    summary_name: str,
) -> tuple[str, str]:
    if item is None:
        return "missing", f"No {summary_name} has been created yet."

    as_of_text = item.get("as_of_date")
    if latest_trade_date is not None and as_of_text is not None:
        try:
            as_of_date = date.fromisoformat(str(as_of_text))
        except ValueError:
            as_of_date = None
        if as_of_date is not None and as_of_date < latest_trade_date:
            return (
                "stale",
                f"The latest {summary_name} is from {as_of_date.isoformat()}, older than the "
                f"latest daily data on {latest_trade_date.isoformat()}.",
            )
    return "ready", f"{summary_name.capitalize()} is ready."


def strategy_mode_workspace(
    config: AppConfig,
    *,
    as_of_date: date | None = None,
) -> dict[str, Any]:
    effective_as_of_date = as_of_date or datetime.now(UTC).date()
    definitions = _strategy_mode_catalog()
    shared_resources = _shared_resource_snapshot(config, as_of_date=effective_as_of_date)
    latest_trade_date = (
        None
        if shared_resources["latest_trade_date"] is None
        else date.fromisoformat(str(shared_resources["latest_trade_date"]))
    )
    active_mode_key = next(
        (
            definition.key
            for definition in definitions
            if definition.config_patch is not None
            and _config_matches_patch(config, definition.config_patch)
        ),
        None,
    )

    if not database_exists(config) or not database_is_reachable(config):
        modes = []
        for definition in definitions:
            mode_status = "empty" if not definition.is_defined else "repair-needed"
            modes.append(
                {
                    "key": definition.key,
                    "label": definition.label,
                    "level": definition.level,
                    "defined": definition.is_defined,
                    "is_active": definition.key == active_mode_key,
                    "classification": definition.classification,
                    "description": definition.description,
                    "overall_status": mode_status,
                    "status_summary": (
                        "Strategy profile is not defined yet."
                        if not definition.is_defined
                        else "Initialize the runtime and repair resources to prepare this mode."
                    ),
                    "definition": None
                    if definition.config_patch is None
                    else definition.config_patch,
                    "resources": {
                        "dataset": {
                            "status": "missing",
                            "summary": "No dataset available.",
                            "snapshot": None,
                        },
                        "model": {
                            "status": "missing",
                            "summary": "No model available.",
                            "entry": None,
                        },
                        "backtest": {
                            "status": "missing",
                            "summary": "No backtest available.",
                            "run": None,
                        },
                    },
                }
            )
        return {
            "catalog_version": "strategy-modes-v1",
            "active_mode_key": active_mode_key,
            "defined_mode_count": sum(1 for definition in definitions if definition.is_defined),
            "empty_mode_count": sum(1 for definition in definitions if not definition.is_defined),
            "shared_resources": shared_resources,
            "modes": modes,
        }

    engine = create_db_engine(config)
    try:
        with Session(engine) as session:
            modes = []
            for definition in definitions:
                if definition.config_patch is None:
                    modes.append(
                        {
                            "key": definition.key,
                            "label": definition.label,
                            "level": definition.level,
                            "defined": False,
                            "is_active": False,
                            "classification": definition.classification,
                            "description": definition.description,
                            "overall_status": "empty",
                            "status_summary": "Strategy profile is not defined yet.",
                            "definition": None,
                            "resources": {
                                "dataset": {
                                    "status": "missing",
                                    "summary": "No strategy definition is available yet.",
                                    "snapshot": None,
                                },
                                "model": {
                                    "status": "missing",
                                    "summary": "No strategy definition is available yet.",
                                    "entry": None,
                                },
                                "backtest": {
                                    "status": "missing",
                                    "summary": "No strategy definition is available yet.",
                                    "run": None,
                                },
                            },
                        }
                    )
                    continue

                profile_config = _config_with_patch(config, definition.config_patch)
                quality_scope = profile_config.model_training.quality_scope
                feature_set_version = profile_config.model_training.feature_set_version
                label_version = profile_config.model_training.label_version
                model_family = profile_config.model_training.model_family

                dataset_row = session.execute(
                    select(DatasetSnapshot)
                    .where(
                        DatasetSnapshot.frequency == "daily",
                        DatasetSnapshot.quality_scope == quality_scope,
                        DatasetSnapshot.feature_set_version == feature_set_version,
                        DatasetSnapshot.label_version == label_version,
                    )
                    .order_by(DatasetSnapshot.as_of_date.desc(), DatasetSnapshot.id.desc())
                ).scalar_one_or_none()

                model_join = session.execute(
                    select(ModelRegistryEntry, DatasetSnapshot)
                    .join(
                        DatasetSnapshot,
                        ModelRegistryEntry.dataset_snapshot_id == DatasetSnapshot.id,
                    )
                    .where(
                        ModelRegistryEntry.frequency == "daily",
                        ModelRegistryEntry.quality_scope == quality_scope,
                        ModelRegistryEntry.family == model_family,
                        ModelRegistryEntry.feature_set_version == feature_set_version,
                        ModelRegistryEntry.label_version == label_version,
                    )
                    .order_by(
                        DatasetSnapshot.as_of_date.desc(), ModelRegistryEntry.created_at.desc()
                    )
                ).first()

                validation_join = session.execute(
                    select(ValidationRun, DatasetSnapshot)
                    .join(DatasetSnapshot, ValidationRun.dataset_snapshot_id == DatasetSnapshot.id)
                    .where(
                        ValidationRun.frequency == "daily",
                        ValidationRun.quality_scope == quality_scope,
                        DatasetSnapshot.feature_set_version == feature_set_version,
                        DatasetSnapshot.label_version == label_version,
                    )
                    .order_by(DatasetSnapshot.as_of_date.desc(), ValidationRun.created_at.desc())
                ).first()

                backtest_join = session.execute(
                    select(BacktestRun, DatasetSnapshot)
                    .join(DatasetSnapshot, BacktestRun.dataset_snapshot_id == DatasetSnapshot.id)
                    .join(
                        ModelRegistryEntry,
                        BacktestRun.model_entry_id == ModelRegistryEntry.id,
                        isouter=True,
                    )
                    .where(
                        BacktestRun.frequency == "daily",
                        BacktestRun.quality_scope == quality_scope,
                        DatasetSnapshot.feature_set_version == feature_set_version,
                        DatasetSnapshot.label_version == label_version,
                        or_(
                            ModelRegistryEntry.family == model_family,
                            BacktestRun.model_entry_id.is_(None),
                        ),
                    )
                    .order_by(DatasetSnapshot.as_of_date.desc(), BacktestRun.created_at.desc())
                ).first()

                dataset_snapshot = (
                    None
                    if dataset_row is None
                    else {
                        "id": dataset_row.id,
                        "as_of_date": dataset_row.as_of_date.isoformat(),
                        "quality_scope": dataset_row.quality_scope,
                        "created_at": _serialize_datetime(dataset_row.created_at),
                        "row_count": dataset_row.row_count,
                    }
                )
                model_entry = None
                if model_join is not None:
                    model_row, model_dataset = model_join
                    model_entry = {
                        "id": model_row.id,
                        "version": model_row.version,
                        "family": model_row.family,
                        "quality_scope": model_row.quality_scope,
                        "created_at": _serialize_datetime(model_row.created_at),
                        "as_of_date": model_dataset.as_of_date.isoformat(),
                    }
                validation_summary = None
                if validation_join is not None:
                    validation_row, validation_dataset = validation_join
                    validation_summary = {
                        "id": validation_row.id,
                        "status": validation_row.status,
                        "quality_scope": validation_row.quality_scope,
                        "created_at": _serialize_datetime(validation_row.created_at),
                        "as_of_date": validation_dataset.as_of_date.isoformat(),
                    }
                backtest_run = None
                if backtest_join is not None:
                    backtest_row, backtest_dataset = backtest_join
                    backtest_run = {
                        "id": backtest_row.id,
                        "status": backtest_row.status,
                        "quality_scope": backtest_row.quality_scope,
                        "start_date": backtest_row.start_date.isoformat(),
                        "end_date": backtest_row.end_date.isoformat(),
                        "created_at": _serialize_datetime(backtest_row.created_at),
                        "as_of_date": backtest_dataset.as_of_date.isoformat(),
                    }

                dataset_status, dataset_summary = _resource_status(
                    item=dataset_snapshot,
                    latest_trade_date=latest_trade_date,
                    summary_name="dataset",
                )
                model_status, model_summary = _resource_status(
                    item=model_entry,
                    latest_trade_date=latest_trade_date,
                    summary_name="model",
                )
                backtest_status, backtest_summary = _resource_status(
                    item=backtest_run,
                    latest_trade_date=latest_trade_date,
                    summary_name="backtest",
                )

                if shared_resources["data_status"] in {"missing", "stale", "partial"}:
                    overall_status = "repair-needed"
                    status_summary = shared_resources["data_summary"]
                elif dataset_status == "missing":
                    overall_status = "repair-needed"
                    status_summary = "This mode still needs a daily dataset snapshot."
                elif model_status == "missing":
                    overall_status = "repair-needed"
                    status_summary = "This mode still needs a trained model."
                elif backtest_status == "missing":
                    overall_status = "repair-needed"
                    status_summary = "This mode still needs a reproducible backtest."
                elif "stale" in {dataset_status, model_status, backtest_status}:
                    overall_status = "stale"
                    status_summary = (
                        "Resources exist, but they lag the most recent daily data and "
                        "should be refreshed."
                    )
                else:
                    overall_status = "ready"
                    status_summary = (
                        "Data, dataset, model, and backtest resources are ready for "
                        "this strategy mode."
                    )

                modes.append(
                    {
                        "key": definition.key,
                        "label": definition.label,
                        "level": definition.level,
                        "defined": True,
                        "is_active": definition.key == active_mode_key,
                        "classification": definition.classification,
                        "description": definition.description,
                        "overall_status": overall_status,
                        "status_summary": status_summary,
                        "definition": definition.config_patch,
                        "resources": {
                            "dataset": {
                                "status": dataset_status,
                                "summary": dataset_summary,
                                "snapshot": dataset_snapshot,
                            },
                            "model": {
                                "status": model_status,
                                "summary": model_summary,
                                "entry": model_entry,
                            },
                            "validation": {
                                "status": ("missing" if validation_summary is None else "ready"),
                                "summary": (
                                    "No validation run is stored yet."
                                    if validation_summary is None
                                    else "Validation run is available."
                                ),
                                "run": validation_summary,
                            },
                            "backtest": {
                                "status": backtest_status,
                                "summary": backtest_summary,
                                "run": backtest_run,
                            },
                        },
                    }
                )
    finally:
        engine.dispose()

    return {
        "catalog_version": "strategy-modes-v1",
        "active_mode_key": active_mode_key,
        "defined_mode_count": sum(1 for definition in definitions if definition.is_defined),
        "empty_mode_count": sum(1 for definition in definitions if not definition.is_defined),
        "shared_resources": shared_resources,
        "modes": modes,
    }


def repair_strategy_mode_resources(
    config: AppConfig,
    *,
    as_of_date: date | None = None,
) -> dict[str, Any]:
    effective_as_of_date = as_of_date or datetime.now(UTC).date()
    initialize_database(config)
    before = strategy_mode_workspace(config, as_of_date=effective_as_of_date)
    shared = before["shared_resources"]
    requires_full_history = bool(
        shared["data_status"] in {"missing", "partial"}
        or not shared["full_history_ready"]
        or shared["stock_universe_size"] < 300
    )

    backfill_summary = backfill_market_data(
        config,
        as_of_date=effective_as_of_date,
        lookback_days=max(config.model_training.dataset_lookback_days, 180),
        full_history=requires_full_history,
        historical_snapshots=requires_full_history,
    )

    mode_results: list[dict[str, Any]] = []
    for definition in _strategy_mode_catalog():
        if definition.config_patch is None:
            mode_results.append(
                {
                    "key": definition.key,
                    "label": definition.label,
                    "status": "skipped",
                    "reason": "mode-not-defined",
                }
            )
            continue

        profile_config = _config_with_patch(config, definition.config_patch)
        training_summary = train_model(
            profile_config,
            as_of_date=effective_as_of_date,
            quality_scope=profile_config.model_training.quality_scope,
        )
        backtest_summary = backtest_model(
            profile_config,
            model_version=training_summary.model_version,
        )
        mode_results.append(
            {
                "key": definition.key,
                "label": definition.label,
                "status": "completed",
                "quality_scope": training_summary.quality_scope,
                "dataset_snapshot_id": training_summary.dataset_snapshot_id,
                "model_version": training_summary.model_version,
                "training_run_id": training_summary.run_id,
                "validation_run_id": training_summary.validation_run_id,
                "backtest_run_id": backtest_summary.run_id,
                "backtest_total_return": backtest_summary.total_return,
                "backtest_excess_return": backtest_summary.excess_return,
            }
        )

    after = strategy_mode_workspace(config, as_of_date=effective_as_of_date)
    return {
        "status": "completed",
        "as_of_date": effective_as_of_date.isoformat(),
        "performed_full_history_backfill": requires_full_history,
        "backfill_run": {
            "run_id": backfill_summary.run_id,
            "as_of_date": backfill_summary.as_of_date.isoformat(),
            "primary_provider": backfill_summary.primary_provider,
            "secondary_provider": backfill_summary.secondary_provider,
            "requested_symbols": list(backfill_summary.requested_symbols),
            "canonical_count": backfill_summary.canonical_count,
            "incident_count": backfill_summary.incident_count,
            "validation_counts": backfill_summary.validation_counts,
            "coverage_report_path": backfill_summary.coverage_report_path,
            "historical_snapshot_count": backfill_summary.historical_snapshot_count,
        },
        "mode_results": mode_results,
        "before": before,
        "after": after,
    }
