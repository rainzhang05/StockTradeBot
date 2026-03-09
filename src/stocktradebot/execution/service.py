from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from stocktradebot import __version__
from stocktradebot.config import AppConfig
from stocktradebot.execution.types import (
    FillSummary,
    OrderIntentSummary,
    PositionSummary,
    SimulationRunSummary,
)
from stocktradebot.features import build_dataset_snapshot
from stocktradebot.models.baseline import score_features
from stocktradebot.models.types import DatasetArtifactRow, LinearModelArtifact
from stocktradebot.portfolio import PortfolioCandidate, construct_target_portfolio
from stocktradebot.risk import FillRiskInput, evaluate_posttrade_risk, evaluate_pretrade_risk
from stocktradebot.storage import (
    AppState,
    CanonicalDailyBar,
    DataQualityIncident,
    ExecutionFill,
    FreezeEvent,
    ModelRegistryEntry,
    OrderIntent,
    PortfolioSnapshot,
    PortfolioSnapshotPosition,
    SimulationRun,
    SystemModeState,
    create_db_engine,
    database_exists,
    database_is_reachable,
    record_audit_event,
    utc_now,
)


@dataclass(slots=True, frozen=True)
class _ScoredRow:
    row: DatasetArtifactRow
    bar: CanonicalDailyBar
    score: float


def _serialize_date(value: date | None) -> str | None:
    return None if value is None else value.isoformat()


def _serialize_datetime(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC).isoformat()
    return value.astimezone(UTC).isoformat()


def _timestamp_token() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")


def _write_json_artifact(
    base_dir: Path,
    *,
    prefix: str,
    payload: dict[str, Any],
    config: AppConfig,
) -> str:
    file_path = base_dir / f"{prefix}-{_timestamp_token()}.json"
    file_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return str(file_path.relative_to(config.app_home))


def _model_from_payload(payload: dict[str, Any]) -> LinearModelArtifact:
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
            key: float(value) for key, value in dict(payload["feature_weights"]).items()
        },
        training_start_date=date.fromisoformat(payload["training_start_date"]),
        training_end_date=date.fromisoformat(payload["training_end_date"]),
        training_row_count=int(payload["training_row_count"]),
        holdout_start_date=date.fromisoformat(payload["holdout_start_date"]),
        holdout_end_date=date.fromisoformat(payload["holdout_end_date"]),
        metadata=dict(payload.get("metadata", {})),
    )


def _load_model_artifact(config: AppConfig, artifact_path: str) -> LinearModelArtifact:
    payload = json.loads((config.app_home / artifact_path).read_text(encoding="utf-8"))
    return _model_from_payload(payload)


def _load_dataset_rows(config: AppConfig, artifact_path: str) -> list[DatasetArtifactRow]:
    rows: list[DatasetArtifactRow] = []
    for line in (config.app_home / artifact_path).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        raw_row = json.loads(line)
        rows.append(
            DatasetArtifactRow(
                symbol=str(raw_row["symbol"]),
                trade_date=date.fromisoformat(raw_row["trade_date"]),
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
            )
        )
    return rows


def _latest_rows(
    rows: list[DatasetArtifactRow],
    as_of_date: date,
) -> tuple[date, list[DatasetArtifactRow]]:
    eligible_dates = sorted({row.trade_date for row in rows if row.trade_date <= as_of_date})
    if not eligible_dates:
        raise RuntimeError("No dataset rows are available on or before the requested date.")
    decision_date = eligible_dates[-1]
    return decision_date, [row for row in rows if row.trade_date == decision_date]


def _load_price_bars(
    session: Session,
    *,
    symbols: list[str],
    trade_date: date,
) -> dict[str, CanonicalDailyBar]:
    bars = session.scalars(
        select(CanonicalDailyBar).where(
            CanonicalDailyBar.symbol.in_(tuple(symbols)),
            CanonicalDailyBar.trade_date == trade_date,
            CanonicalDailyBar.validation_tier == "verified",
        )
    ).all()
    return {bar.symbol: bar for bar in bars}


def _current_mode_state(session: Session) -> SystemModeState:
    state = session.get(SystemModeState, 1)
    if state is None:
        raise RuntimeError("Mode state is not initialized. Run init first.")
    return state


def _kill_switch_active(session: Session) -> bool:
    app_state = session.get(AppState, "kill_switch")
    return app_state is not None and app_state.value.lower() == "on"


def _load_latest_post_trade_snapshot(
    session: Session,
) -> tuple[PortfolioSnapshot | None, list[PortfolioSnapshotPosition]]:
    snapshot = session.scalar(
        select(PortfolioSnapshot)
        .where(PortfolioSnapshot.snapshot_type == "post-trade")
        .order_by(PortfolioSnapshot.created_at.desc(), PortfolioSnapshot.id.desc())
    )
    if snapshot is None:
        return None, []
    positions = session.scalars(
        select(PortfolioSnapshotPosition).where(
            PortfolioSnapshotPosition.snapshot_id == snapshot.id
        )
    ).all()
    return snapshot, list(positions)


def _open_incident_count(session: Session, *, symbols: list[str], as_of_date: date) -> int:
    return int(
        session.scalar(
            select(func.count())
            .select_from(DataQualityIncident)
            .where(
                DataQualityIncident.symbol.in_(tuple(symbols)),
                DataQualityIncident.resolution_status == "open",
                DataQualityIncident.trade_date <= as_of_date,
            )
        )
        or 0
    )


def _high_water_mark(session: Session) -> float | None:
    value = session.scalar(
        select(func.max(SimulationRun.end_nav)).where(SimulationRun.status == "completed")
    )
    return None if value is None else float(value)


def _active_freeze(session: Session) -> FreezeEvent | None:
    return session.scalar(
        select(FreezeEvent)
        .where(FreezeEvent.status == "active")
        .order_by(FreezeEvent.triggered_at.desc(), FreezeEvent.id.desc())
    )


def _sector_for_symbol(config: AppConfig, symbol: str) -> str | None:
    return config.portfolio.symbol_sectors.get(symbol)


def _expected_spread_bps(
    *,
    realized_vol_20d: float | None,
    dollar_volume_20d: float | None,
) -> float:
    volatility_component = 1.5 if realized_vol_20d is None else min(25.0, realized_vol_20d * 500.0)
    liquidity_component = 8.0
    if dollar_volume_20d is not None and dollar_volume_20d > 0:
        liquidity_component = max(1.0, min(15.0, 5_000_000.0 / dollar_volume_20d))
    return volatility_component + liquidity_component


def _execution_slippage_bps(
    config: AppConfig,
    *,
    realized_vol_20d: float | None,
    dollar_volume_20d: float | None,
) -> float:
    spread = _expected_spread_bps(
        realized_vol_20d=realized_vol_20d,
        dollar_volume_20d=dollar_volume_20d,
    )
    return config.execution.base_slippage_bps + spread * 0.35


def _order_type(
    *,
    realized_vol_20d: float | None,
    dollar_volume_20d: float | None,
) -> str:
    if realized_vol_20d is not None and realized_vol_20d >= 0.03:
        return "limit"
    if dollar_volume_20d is not None and dollar_volume_20d < 10_000_000:
        return "limit"
    return "marketable-limit"


def _position_summary(
    *,
    symbol: str,
    shares: float,
    target_weight: float,
    actual_weight: float,
    price: float,
    market_value: float,
    score: float | None,
    sector: str | None,
    metadata: dict[str, Any],
) -> PositionSummary:
    return PositionSummary(
        symbol=symbol,
        shares=shares,
        target_weight=target_weight,
        actual_weight=actual_weight,
        price=price,
        market_value=market_value,
        score=score,
        sector=sector,
        metadata=metadata,
    )


def _persist_snapshot(
    session: Session,
    *,
    simulation_run_id: int,
    snapshot_type: str,
    trade_date: date,
    nav: float,
    cash_balance: float,
    turnover_ratio: float,
    positions: list[PositionSummary],
) -> int:
    gross_exposure = (
        0.0 if nav <= 0 else sum(abs(position.market_value) for position in positions) / nav
    )
    net_exposure = 0.0 if nav <= 0 else sum(position.market_value for position in positions) / nav
    snapshot = PortfolioSnapshot(
        simulation_run_id=simulation_run_id,
        snapshot_type=snapshot_type,
        trade_date=trade_date,
        nav=nav,
        cash_balance=cash_balance,
        gross_exposure=gross_exposure,
        net_exposure=net_exposure,
        holding_count=len(positions),
        turnover_ratio=turnover_ratio,
        metadata_json=json.dumps(
            {"position_symbols": [position.symbol for position in positions]},
            sort_keys=True,
        ),
    )
    session.add(snapshot)
    session.commit()

    for position in positions:
        session.add(
            PortfolioSnapshotPosition(
                snapshot_id=snapshot.id,
                symbol=position.symbol,
                target_weight=position.target_weight,
                actual_weight=position.actual_weight,
                shares=position.shares,
                price=position.price,
                market_value=position.market_value,
                score=position.score,
                sector=position.sector,
                metadata_json=json.dumps(position.metadata, sort_keys=True),
            )
        )
    session.commit()
    return snapshot.id


def _create_freeze(
    session: Session,
    *,
    reason: str,
    freeze_type: str,
    source: str,
    details: dict[str, Any],
) -> FreezeEvent:
    freeze = FreezeEvent(
        status="active",
        freeze_type=freeze_type,
        source=source,
        reason=reason,
        details_json=json.dumps(details, sort_keys=True, default=str),
    )
    session.add(freeze)
    session.commit()

    mode_state = _current_mode_state(session)
    mode_state.is_frozen = True
    mode_state.active_freeze_event_id = freeze.id
    mode_state.freeze_reason = reason
    mode_state.metadata_json = json.dumps(
        {
            "freeze_type": freeze_type,
            "source": source,
            "details": details,
        },
        sort_keys=True,
        default=str,
    )
    session.commit()
    return freeze


def _clear_if_missing_active_freeze(session: Session) -> None:
    mode_state = _current_mode_state(session)
    if mode_state.is_frozen and mode_state.active_freeze_event_id is not None:
        freeze = session.get(FreezeEvent, mode_state.active_freeze_event_id)
        if freeze is None or freeze.status != "active":
            mode_state.is_frozen = False
            mode_state.active_freeze_event_id = None
            mode_state.freeze_reason = None
            mode_state.metadata_json = "{}"
            session.commit()


def simulate_trading_day(
    config: AppConfig,
    *,
    as_of_date: date | None = None,
    model_version: str | None = None,
) -> SimulationRunSummary:
    if not database_exists(config) or not database_is_reachable(config):
        raise RuntimeError("Database is not ready. Run init first.")

    effective_as_of_date = as_of_date or datetime.now(UTC).date()
    engine = create_db_engine(config)
    try:
        with Session(engine) as session:
            mode_state = _current_mode_state(session)
            simulation_run = SimulationRun(
                status="running",
                mode=mode_state.current_mode,
                as_of_date=effective_as_of_date,
                decision_date=None,
                model_entry_id=None,
                dataset_snapshot_id=None,
                regime=None,
                gross_exposure_target=0.0,
                gross_exposure_actual=0.0,
                start_nav=0.0,
                end_nav=0.0,
                cash_start=0.0,
                cash_end=0.0,
                artifact_path=None,
                summary_json="{}",
                error_message=None,
            )
            session.add(simulation_run)
            session.commit()
            simulation_run_id = simulation_run.id

        try:
            dataset_summary = build_dataset_snapshot(config, as_of_date=effective_as_of_date)
            dataset_rows = _load_dataset_rows(config, dataset_summary.artifact_path)
            decision_date, latest_rows = _latest_rows(dataset_rows, effective_as_of_date)
            if not latest_rows:
                raise RuntimeError("No feature rows are available for the latest decision date.")

            with Session(engine) as session:
                model_query = select(ModelRegistryEntry).order_by(
                    ModelRegistryEntry.created_at.desc()
                )
                if model_version is not None:
                    model_query = select(ModelRegistryEntry).where(
                        ModelRegistryEntry.version == model_version
                    )
                model_entry = session.scalar(model_query)
                if model_entry is None:
                    raise RuntimeError("No trained model is available. Run train first.")
                if (
                    model_entry.promotion_status != "candidate"
                    and not config.risk.allow_research_models_in_simulation
                ):
                    raise RuntimeError(
                        "Simulation requires a candidate model under current policy."
                    )

                mode_state = _current_mode_state(session)
                _clear_if_missing_active_freeze(session)
                active_freeze = _active_freeze(session)
                previous_snapshot, previous_positions = _load_latest_post_trade_snapshot(session)
                current_holdings = {
                    position.symbol: position.shares
                    for position in previous_positions
                    if abs(position.shares) > 1e-9
                }
                previous_nav = None if previous_snapshot is None else previous_snapshot.nav
                cash_balance = (
                    config.model_training.initial_capital
                    if previous_snapshot is None
                    else previous_snapshot.cash_balance
                )
                high_water_mark = _high_water_mark(session)

                model = _load_model_artifact(config, model_entry.artifact_path)
                candidate_symbols = {row.symbol for row in latest_rows}
                if config.portfolio.defensive_etf_symbol:
                    candidate_symbols.add(config.portfolio.defensive_etf_symbol)
                candidate_symbols.update(current_holdings)
                bars = _load_price_bars(
                    session,
                    symbols=sorted(candidate_symbols),
                    trade_date=decision_date,
                )

                scored_rows: list[_ScoredRow] = []
                for row in latest_rows:
                    bar = bars.get(row.symbol)
                    if bar is None:
                        continue
                    scored_rows.append(
                        _ScoredRow(
                            row=row,
                            bar=bar,
                            score=score_features(model, row.features),
                        )
                    )
                if not scored_rows:
                    raise RuntimeError(
                        "No verified prices are available for the latest decision date."
                    )

                start_nav = cash_balance
                current_weights: dict[str, float] = {}
                pre_trade_positions: list[PositionSummary] = []
                score_map = {item.row.symbol: item.score for item in scored_rows}
                for symbol, shares in current_holdings.items():
                    bar = bars.get(symbol)
                    if bar is None:
                        continue
                    market_value = shares * bar.close
                    start_nav += market_value
                if start_nav > 0:
                    for symbol, shares in current_holdings.items():
                        bar = bars.get(symbol)
                        if bar is None:
                            continue
                        market_value = shares * bar.close
                        current_weights[symbol] = market_value / start_nav
                        pre_trade_positions.append(
                            _position_summary(
                                symbol=symbol,
                                shares=shares,
                                target_weight=current_weights[symbol],
                                actual_weight=current_weights[symbol],
                                price=bar.close,
                                market_value=market_value,
                                score=score_map.get(symbol),
                                sector=_sector_for_symbol(config, symbol),
                                metadata={"source": "carried-position"},
                            )
                        )

                candidate_map = {
                    item.row.symbol: PortfolioCandidate(
                        symbol=item.row.symbol,
                        score=item.score,
                        price=item.bar.close,
                        asset_type="etf"
                        if item.row.symbol in set(config.universe.curated_etfs)
                        else "stock",
                        realized_vol_20d=item.row.features.get("realized_vol_20d"),
                        dollar_volume_20d=item.row.features.get("dollar_volume_20d"),
                        regime_return_20d=item.row.features.get("regime_return_20d"),
                        regime_vol_20d=item.row.features.get("regime_vol_20d"),
                    )
                    for item in scored_rows
                }
                if config.portfolio.defensive_etf_symbol:
                    defensive_symbol = config.portfolio.defensive_etf_symbol
                    if defensive_symbol not in candidate_map and defensive_symbol in bars:
                        defensive_bar = bars[defensive_symbol]
                        candidate_map[defensive_symbol] = PortfolioCandidate(
                            symbol=defensive_symbol,
                            score=0.01,
                            price=defensive_bar.close,
                            asset_type="etf",
                            realized_vol_20d=None,
                            dollar_volume_20d=float(defensive_bar.close * defensive_bar.volume),
                            regime_return_20d=next(
                                iter(
                                    row.features.get("regime_return_20d")
                                    for row in latest_rows
                                    if row.features.get("regime_return_20d") is not None
                                ),
                                None,
                            ),
                            regime_vol_20d=next(
                                iter(
                                    row.features.get("regime_vol_20d")
                                    for row in latest_rows
                                    if row.features.get("regime_vol_20d") is not None
                                ),
                                None,
                            ),
                        )

                target_portfolio = construct_target_portfolio(
                    config,
                    candidates=list(candidate_map.values()),
                    current_weights=current_weights,
                )
                open_incident_count = _open_incident_count(
                    session,
                    symbols=sorted({row.symbol for row in latest_rows}),
                    as_of_date=decision_date,
                )
                pretrade_risk = evaluate_pretrade_risk(
                    config,
                    mode=mode_state.current_mode,
                    active_freeze_reason=None if active_freeze is None else active_freeze.reason,
                    start_nav=start_nav,
                    previous_nav=previous_nav,
                    high_water_mark=high_water_mark,
                    open_incident_count=open_incident_count,
                    kill_switch_active=_kill_switch_active(session),
                )

                current_run = session.get(SimulationRun, simulation_run_id)
                if current_run is None:
                    raise RuntimeError("Simulation run state was lost.")
                current_run.decision_date = decision_date
                current_run.model_entry_id = model_entry.id
                current_run.dataset_snapshot_id = dataset_summary.snapshot_id
                current_run.regime = target_portfolio.regime
                current_run.start_nav = start_nav
                current_run.cash_start = cash_balance
                session.commit()

                pre_trade_snapshot_id = _persist_snapshot(
                    session,
                    simulation_run_id=simulation_run_id,
                    snapshot_type="pre-trade",
                    trade_date=decision_date,
                    nav=start_nav,
                    cash_balance=cash_balance,
                    turnover_ratio=0.0,
                    positions=sorted(pre_trade_positions, key=lambda position: position.symbol),
                )

                if not pretrade_risk.allowed:
                    freeze = pretrade_risk.freeze
                    assert freeze is not None
                    if freeze.freeze_type != "existing-freeze":
                        _create_freeze(
                            session,
                            reason=freeze.reason,
                            freeze_type=freeze.freeze_type,
                            source=freeze.source,
                            details=freeze.details,
                        )
                    artifact_payload = {
                        "run_id": simulation_run_id,
                        "status": "blocked",
                        "mode": mode_state.current_mode,
                        "decision_date": _serialize_date(decision_date),
                        "model_version": model_entry.version,
                        "dataset_snapshot_id": dataset_summary.snapshot_id,
                        "risk_checks": list(pretrade_risk.checks),
                        "code_version": __version__,
                    }
                    artifact_path = _write_json_artifact(
                        config.report_artifacts_dir,
                        prefix=f"simulation-{simulation_run_id}",
                        payload=artifact_payload,
                        config=config,
                    )
                    current_run.status = "blocked"
                    current_run.end_nav = start_nav
                    current_run.cash_end = cash_balance
                    current_run.artifact_path = artifact_path
                    current_run.summary_json = json.dumps(artifact_payload, sort_keys=True)
                    current_run.completed_at = utc_now()
                    session.commit()
                    record_audit_event(
                        config,
                        "simulation",
                        f"simulation {simulation_run_id} blocked by freeze: {freeze.reason}",
                    )
                    return SimulationRunSummary(
                        run_id=simulation_run_id,
                        mode=mode_state.current_mode,
                        status="blocked",
                        as_of_date=effective_as_of_date,
                        decision_date=decision_date,
                        model_version=model_entry.version,
                        dataset_snapshot_id=dataset_summary.snapshot_id,
                        regime=target_portfolio.regime,
                        start_nav=start_nav,
                        end_nav=start_nav,
                        cash_start=cash_balance,
                        cash_end=cash_balance,
                        gross_exposure_target=0.0,
                        gross_exposure_actual=0.0,
                        turnover_ratio=0.0,
                        target_snapshot_id=pre_trade_snapshot_id,
                        post_trade_snapshot_id=pre_trade_snapshot_id,
                        order_count=0,
                        fill_count=0,
                        freeze_triggered=True,
                        artifact_path=artifact_path,
                        metadata={"risk_checks": list(pretrade_risk.checks)},
                    )

                target_positions: list[PositionSummary] = []
                target_weights = {
                    position.symbol: position.target_weight
                    for position in target_portfolio.positions
                }
                for position in target_portfolio.positions:
                    position_price = float(position.metadata["price"])
                    target_shares = (
                        0.0
                        if position_price == 0
                        else start_nav * position.target_weight / position_price
                    )
                    market_value = target_shares * position_price
                    target_positions.append(
                        _position_summary(
                            symbol=position.symbol,
                            shares=target_shares,
                            target_weight=position.target_weight,
                            actual_weight=position.target_weight,
                            price=position_price,
                            market_value=market_value,
                            score=position.score,
                            sector=position.sector,
                            metadata=position.metadata,
                        )
                    )
                target_snapshot_id = _persist_snapshot(
                    session,
                    simulation_run_id=simulation_run_id,
                    snapshot_type="target",
                    trade_date=decision_date,
                    nav=start_nav,
                    cash_balance=max(start_nav * target_portfolio.cash_weight, 0.0),
                    turnover_ratio=target_portfolio.turnover_ratio,
                    positions=sorted(target_positions, key=lambda position: position.symbol),
                )

                positions_after = dict(current_holdings)
                cash_after = cash_balance
                order_summaries: list[OrderIntentSummary] = []
                fill_summaries: list[FillSummary] = []
                current_symbols = set(current_holdings)
                all_symbols = sorted(current_symbols | set(target_weights))

                for symbol in all_symbols:
                    bar = bars.get(symbol)
                    if bar is None or bar.close == 0:
                        continue
                    current_shares = current_holdings.get(symbol, 0.0)
                    target_weight = target_weights.get(symbol, 0.0)
                    target_shares = start_nav * target_weight / bar.close
                    share_delta = target_shares - current_shares
                    requested_notional = share_delta * bar.close
                    if abs(requested_notional) < 1e-6:
                        continue

                    candidate = candidate_map.get(symbol)
                    expected_spread = _expected_spread_bps(
                        realized_vol_20d=None if candidate is None else candidate.realized_vol_20d,
                        dollar_volume_20d=None
                        if candidate is None
                        else candidate.dollar_volume_20d,
                    )
                    slippage_bps = _execution_slippage_bps(
                        config,
                        realized_vol_20d=None if candidate is None else candidate.realized_vol_20d,
                        dollar_volume_20d=None
                        if candidate is None
                        else candidate.dollar_volume_20d,
                    )
                    side = "buy" if share_delta > 0 else "sell"
                    order_type = _order_type(
                        realized_vol_20d=None if candidate is None else candidate.realized_vol_20d,
                        dollar_volume_20d=None
                        if candidate is None
                        else candidate.dollar_volume_20d,
                    )
                    limit_price = bar.close * (
                        1.0 + (1.0 if side == "buy" else -1.0) * expected_spread / 20_000.0
                    )
                    order = OrderIntent(
                        simulation_run_id=simulation_run_id,
                        symbol=symbol,
                        side=side,
                        status="created",
                        order_type=order_type,
                        time_in_force="day",
                        requested_shares=abs(share_delta),
                        requested_notional=abs(requested_notional),
                        limit_price=limit_price,
                        reference_price=bar.close,
                        expected_slippage_bps=slippage_bps,
                        target_weight=target_weight,
                        metadata_json=json.dumps(
                            {
                                "expected_spread_bps": expected_spread,
                                "score": None if candidate is None else candidate.score,
                            },
                            sort_keys=True,
                        ),
                    )
                    session.add(order)
                    session.commit()

                    max_fill_notional = abs(requested_notional)
                    if config.execution.partial_fill_enabled:
                        max_fill_notional = min(
                            abs(requested_notional),
                            bar.close * bar.volume * config.execution.max_participation_rate,
                        )
                    fill_ratio = (
                        0.0
                        if abs(requested_notional) < 1e-9
                        else max_fill_notional / abs(requested_notional)
                    )
                    fill_ratio = max(0.0, min(fill_ratio, 1.0))
                    filled_shares = abs(share_delta) * fill_ratio
                    executed_price = bar.close * (
                        1.0 + (1.0 if side == "buy" else -1.0) * slippage_bps / 10_000.0
                    )
                    commission = (
                        filled_shares * executed_price * config.execution.commission_bps / 10_000.0
                    )
                    fill_status = (
                        "unfilled"
                        if filled_shares <= 1e-9
                        else ("partial" if fill_ratio < 0.999999 else "filled")
                    )
                    signed_share_delta = filled_shares if side == "buy" else -filled_shares
                    if side == "buy":
                        cash_after -= filled_shares * executed_price + commission
                    else:
                        cash_after += filled_shares * executed_price - commission
                    positions_after[symbol] = positions_after.get(symbol, 0.0) + signed_share_delta
                    if abs(positions_after[symbol]) <= 1e-9:
                        positions_after.pop(symbol, None)

                    fill = ExecutionFill(
                        simulation_run_id=simulation_run_id,
                        order_intent_id=order.id,
                        symbol=symbol,
                        side=side,
                        fill_status=fill_status,
                        filled_shares=filled_shares,
                        filled_notional=filled_shares * executed_price,
                        fill_price=executed_price,
                        commission=commission,
                        slippage_bps=slippage_bps,
                        expected_spread_bps=expected_spread,
                        metadata_json=json.dumps(
                            {
                                "fill_ratio": fill_ratio,
                                "requested_shares": abs(share_delta),
                            },
                            sort_keys=True,
                        ),
                    )
                    session.add(fill)
                    session.commit()

                    order.status = fill_status
                    order.completed_at = utc_now()
                    session.commit()

                    order_summaries.append(
                        OrderIntentSummary(
                            order_id=order.id,
                            symbol=symbol,
                            side=side,
                            status=fill_status,
                            order_type=order_type,
                            requested_shares=abs(share_delta),
                            requested_notional=abs(requested_notional),
                            reference_price=bar.close,
                            limit_price=limit_price,
                            expected_slippage_bps=slippage_bps,
                            metadata={
                                "expected_spread_bps": expected_spread,
                                "target_weight": target_weight,
                            },
                        )
                    )
                    fill_summaries.append(
                        FillSummary(
                            fill_id=fill.id,
                            order_intent_id=order.id,
                            symbol=symbol,
                            side=side,
                            fill_status=fill_status,
                            filled_shares=filled_shares,
                            filled_notional=filled_shares * executed_price,
                            fill_price=executed_price,
                            commission=commission,
                            slippage_bps=slippage_bps,
                            expected_spread_bps=expected_spread,
                            metadata={"fill_ratio": fill_ratio},
                        )
                    )

                post_positions: list[PositionSummary] = []
                end_nav = cash_after
                for symbol, shares in sorted(positions_after.items()):
                    bar = bars.get(symbol)
                    if bar is None:
                        continue
                    market_value = shares * bar.close
                    end_nav += market_value
                for symbol, shares in sorted(positions_after.items()):
                    bar = bars.get(symbol)
                    if bar is None or end_nav <= 0:
                        continue
                    market_value = shares * bar.close
                    post_positions.append(
                        _position_summary(
                            symbol=symbol,
                            shares=shares,
                            target_weight=target_weights.get(symbol, 0.0),
                            actual_weight=market_value / end_nav,
                            price=bar.close,
                            market_value=market_value,
                            score=score_map.get(symbol),
                            sector=_sector_for_symbol(config, symbol),
                            metadata={"source": "post-trade"},
                        )
                    )

                posttrade_risk = evaluate_posttrade_risk(
                    config,
                    fills=[
                        FillRiskInput(
                            symbol=fill.symbol,
                            slippage_bps=fill.slippage_bps,
                            expected_spread_bps=fill.expected_spread_bps,
                            fill_status=fill.fill_status,
                        )
                        for fill in fill_summaries
                    ],
                )
                freeze_triggered = False
                if not posttrade_risk.allowed:
                    freeze = posttrade_risk.freeze
                    assert freeze is not None
                    _create_freeze(
                        session,
                        reason=freeze.reason,
                        freeze_type=freeze.freeze_type,
                        source=freeze.source,
                        details=freeze.details,
                    )
                    freeze_triggered = True

                post_trade_snapshot_id = _persist_snapshot(
                    session,
                    simulation_run_id=simulation_run_id,
                    snapshot_type="post-trade",
                    trade_date=decision_date,
                    nav=end_nav,
                    cash_balance=cash_after,
                    turnover_ratio=target_portfolio.turnover_ratio,
                    positions=post_positions,
                )

                artifact_payload = {
                    "run_id": simulation_run_id,
                    "status": "completed",
                    "mode": mode_state.current_mode,
                    "as_of_date": _serialize_date(effective_as_of_date),
                    "decision_date": _serialize_date(decision_date),
                    "model_version": model_entry.version,
                    "dataset_snapshot_id": dataset_summary.snapshot_id,
                    "regime": target_portfolio.regime,
                    "start_nav": start_nav,
                    "end_nav": end_nav,
                    "cash_start": cash_balance,
                    "cash_end": cash_after,
                    "gross_exposure_target": target_portfolio.target_gross_exposure,
                    "gross_exposure_actual": (
                        0.0
                        if end_nav <= 0
                        else sum(abs(position.market_value) for position in post_positions)
                        / end_nav
                    ),
                    "turnover_ratio": target_portfolio.turnover_ratio,
                    "risk_checks": {
                        "pretrade": list(pretrade_risk.checks),
                        "posttrade": list(posttrade_risk.checks),
                    },
                    "positions": {
                        "pre_trade": [asdict(position) for position in pre_trade_positions],
                        "target": [asdict(position) for position in target_positions],
                        "post_trade": [asdict(position) for position in post_positions],
                    },
                    "orders": [asdict(order) for order in order_summaries],
                    "fills": [asdict(fill) for fill in fill_summaries],
                    "freeze_triggered": freeze_triggered,
                    "code_version": __version__,
                }
                artifact_path = _write_json_artifact(
                    config.report_artifacts_dir,
                    prefix=f"simulation-{simulation_run_id}",
                    payload=artifact_payload,
                    config=config,
                )
                current_run.status = "completed"
                current_run.gross_exposure_target = target_portfolio.target_gross_exposure
                current_run.gross_exposure_actual = (
                    0.0
                    if end_nav <= 0
                    else sum(abs(position.market_value) for position in post_positions) / end_nav
                )
                current_run.end_nav = end_nav
                current_run.cash_end = cash_after
                current_run.artifact_path = artifact_path
                current_run.summary_json = json.dumps(artifact_payload, sort_keys=True, default=str)
                current_run.completed_at = utc_now()
                session.commit()

                record_audit_event(
                    config,
                    "simulation",
                    f"simulation {simulation_run_id} completed for {decision_date.isoformat()}",
                )
                return SimulationRunSummary(
                    run_id=simulation_run_id,
                    mode=mode_state.current_mode,
                    status="completed",
                    as_of_date=effective_as_of_date,
                    decision_date=decision_date,
                    model_version=model_entry.version,
                    dataset_snapshot_id=dataset_summary.snapshot_id,
                    regime=target_portfolio.regime,
                    start_nav=start_nav,
                    end_nav=end_nav,
                    cash_start=cash_balance,
                    cash_end=cash_after,
                    gross_exposure_target=target_portfolio.target_gross_exposure,
                    gross_exposure_actual=current_run.gross_exposure_actual,
                    turnover_ratio=target_portfolio.turnover_ratio,
                    target_snapshot_id=target_snapshot_id,
                    post_trade_snapshot_id=post_trade_snapshot_id,
                    order_count=len(order_summaries),
                    fill_count=len(fill_summaries),
                    freeze_triggered=freeze_triggered,
                    artifact_path=artifact_path,
                    metadata={
                        "pre_trade_snapshot_id": pre_trade_snapshot_id,
                        "risk_checks": {
                            "pretrade": list(pretrade_risk.checks),
                            "posttrade": list(posttrade_risk.checks),
                        },
                    },
                )
        except Exception as exc:
            with Session(engine) as session:
                current_run = session.get(SimulationRun, simulation_run_id)
                if current_run is not None:
                    current_run.status = "failed"
                    current_run.error_message = str(exc)
                    current_run.completed_at = utc_now()
                    session.commit()
            raise
    finally:
        engine.dispose()


def simulation_status(config: AppConfig) -> dict[str, Any]:
    if not database_exists(config) or not database_is_reachable(config):
        return {
            "mode_state": None,
            "active_freeze": None,
            "latest_run": None,
            "latest_target_snapshot": None,
            "latest_orders": [],
            "latest_fills": [],
        }

    engine = create_db_engine(config)
    try:
        with Session(engine) as session:
            mode_state = _current_mode_state(session)
            active_freeze = _active_freeze(session)
            latest_run = session.scalar(
                select(SimulationRun).order_by(
                    SimulationRun.created_at.desc(), SimulationRun.id.desc()
                )
            )
            latest_target_snapshot = session.scalar(
                select(PortfolioSnapshot)
                .where(PortfolioSnapshot.snapshot_type == "target")
                .order_by(PortfolioSnapshot.created_at.desc(), PortfolioSnapshot.id.desc())
            )
            latest_orders: list[OrderIntent] = []
            latest_fills: list[ExecutionFill] = []
            target_positions: list[dict[str, Any]] = []
            if latest_run is not None:
                latest_orders = list(
                    session.scalars(
                        select(OrderIntent)
                        .where(OrderIntent.simulation_run_id == latest_run.id)
                        .order_by(OrderIntent.id.asc())
                    ).all()
                )
                latest_fills = list(
                    session.scalars(
                        select(ExecutionFill)
                        .where(ExecutionFill.simulation_run_id == latest_run.id)
                        .order_by(ExecutionFill.id.asc())
                    ).all()
                )
            if latest_target_snapshot is not None:
                target_positions = [
                    {
                        "symbol": position.symbol,
                        "target_weight": position.target_weight,
                        "actual_weight": position.actual_weight,
                        "shares": position.shares,
                        "price": position.price,
                        "market_value": position.market_value,
                        "score": position.score,
                        "sector": position.sector,
                        "metadata": json.loads(position.metadata_json),
                    }
                    for position in session.scalars(
                        select(PortfolioSnapshotPosition).where(
                            PortfolioSnapshotPosition.snapshot_id == latest_target_snapshot.id
                        )
                    ).all()
                ]
    finally:
        engine.dispose()

    return {
        "mode_state": {
            "current_mode": mode_state.current_mode,
            "requested_mode": mode_state.requested_mode,
            "live_profile": mode_state.live_profile,
            "is_frozen": mode_state.is_frozen,
            "active_freeze_event_id": mode_state.active_freeze_event_id,
            "freeze_reason": mode_state.freeze_reason,
            "metadata": json.loads(mode_state.metadata_json),
            "updated_at": _serialize_datetime(mode_state.updated_at),
        },
        "active_freeze": (
            {
                "id": active_freeze.id,
                "status": active_freeze.status,
                "freeze_type": active_freeze.freeze_type,
                "source": active_freeze.source,
                "reason": active_freeze.reason,
                "details": json.loads(active_freeze.details_json),
                "triggered_at": _serialize_datetime(active_freeze.triggered_at),
                "cleared_at": _serialize_datetime(active_freeze.cleared_at),
            }
            if active_freeze is not None
            else None
        ),
        "latest_run": (
            {
                "id": latest_run.id,
                "status": latest_run.status,
                "mode": latest_run.mode,
                "as_of_date": _serialize_date(latest_run.as_of_date),
                "decision_date": _serialize_date(latest_run.decision_date),
                "model_entry_id": latest_run.model_entry_id,
                "dataset_snapshot_id": latest_run.dataset_snapshot_id,
                "regime": latest_run.regime,
                "gross_exposure_target": latest_run.gross_exposure_target,
                "gross_exposure_actual": latest_run.gross_exposure_actual,
                "start_nav": latest_run.start_nav,
                "end_nav": latest_run.end_nav,
                "cash_start": latest_run.cash_start,
                "cash_end": latest_run.cash_end,
                "artifact_path": latest_run.artifact_path,
                "summary": json.loads(latest_run.summary_json),
                "error_message": latest_run.error_message,
                "created_at": _serialize_datetime(latest_run.created_at),
                "completed_at": _serialize_datetime(latest_run.completed_at),
            }
            if latest_run is not None
            else None
        ),
        "latest_target_snapshot": (
            {
                "id": latest_target_snapshot.id,
                "simulation_run_id": latest_target_snapshot.simulation_run_id,
                "trade_date": _serialize_date(latest_target_snapshot.trade_date),
                "nav": latest_target_snapshot.nav,
                "cash_balance": latest_target_snapshot.cash_balance,
                "gross_exposure": latest_target_snapshot.gross_exposure,
                "net_exposure": latest_target_snapshot.net_exposure,
                "holding_count": latest_target_snapshot.holding_count,
                "turnover_ratio": latest_target_snapshot.turnover_ratio,
                "positions": target_positions,
            }
            if latest_target_snapshot is not None
            else None
        ),
        "latest_orders": [
            {
                "id": order.id,
                "symbol": order.symbol,
                "side": order.side,
                "status": order.status,
                "order_type": order.order_type,
                "requested_shares": order.requested_shares,
                "requested_notional": order.requested_notional,
                "limit_price": order.limit_price,
                "reference_price": order.reference_price,
                "expected_slippage_bps": order.expected_slippage_bps,
                "target_weight": order.target_weight,
                "metadata": json.loads(order.metadata_json),
                "created_at": _serialize_datetime(order.created_at),
                "completed_at": _serialize_datetime(order.completed_at),
            }
            for order in latest_orders
        ],
        "latest_fills": [
            {
                "id": fill.id,
                "order_intent_id": fill.order_intent_id,
                "symbol": fill.symbol,
                "side": fill.side,
                "fill_status": fill.fill_status,
                "filled_shares": fill.filled_shares,
                "filled_notional": fill.filled_notional,
                "fill_price": fill.fill_price,
                "commission": fill.commission,
                "slippage_bps": fill.slippage_bps,
                "expected_spread_bps": fill.expected_spread_bps,
                "metadata": json.loads(fill.metadata_json),
                "filled_at": _serialize_datetime(fill.filled_at),
            }
            for fill in latest_fills
        ],
    }
