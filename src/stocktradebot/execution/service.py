from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from stocktradebot import __version__
from stocktradebot.broker import (
    BrokerAdapter,
    BrokerOrderRequest,
    broker_status,
    build_broker_adapter,
)
from stocktradebot.broker.types import BrokerAccountSnapshotData, BrokerPositionData
from stocktradebot.config import AppConfig
from stocktradebot.execution.types import (
    ApprovalSummary,
    FillSummary,
    ModeTransitionSummary,
    OrderIntentSummary,
    PositionSummary,
    SimulationRunSummary,
    TradingOperationSummary,
)
from stocktradebot.features import build_dataset_snapshot
from stocktradebot.models.baseline import score_features
from stocktradebot.models.types import DatasetArtifactRow, LinearModelArtifact
from stocktradebot.portfolio import PortfolioCandidate, construct_target_portfolio
from stocktradebot.risk import FillRiskInput, evaluate_posttrade_risk, evaluate_pretrade_risk
from stocktradebot.storage import (
    AppState,
    BrokerAccountSnapshot,
    BrokerOrder,
    BrokerPositionSnapshot,
    CanonicalDailyBar,
    DataQualityIncident,
    ExecutionFill,
    FreezeEvent,
    ModelRegistryEntry,
    ModeTransitionEvent,
    OrderApproval,
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


@dataclass(slots=True, frozen=True)
class _ExecutionPlan:
    effective_as_of_date: date
    decision_date: date
    dataset_snapshot_id: int
    model_entry: ModelRegistryEntry
    model: LinearModelArtifact
    target_portfolio: Any
    latest_rows: tuple[DatasetArtifactRow, ...]
    bars: dict[str, CanonicalDailyBar]
    candidate_map: dict[str, PortfolioCandidate]
    score_map: dict[str, float]


@dataclass(slots=True, frozen=True)
class _OrderPlan:
    symbol: str
    side: str
    requested_shares: float
    requested_notional: float
    target_weight: float
    reference_price: float
    order_type: str
    time_in_force: str
    limit_price: float | None
    expected_spread_bps: float
    expected_slippage_bps: float
    score: float | None


@dataclass(slots=True, frozen=True)
class _BrokerSync:
    snapshot_id: int
    account: BrokerAccountSnapshotData
    positions: tuple[BrokerPositionData, ...]


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
    file_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
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


def _latest_model_entry(session: Session, model_version: str | None) -> ModelRegistryEntry:
    if model_version is not None:
        model_entry = session.scalar(
            select(ModelRegistryEntry).where(ModelRegistryEntry.version == model_version)
        )
    else:
        model_entry = session.scalar(
            select(ModelRegistryEntry).order_by(
                ModelRegistryEntry.created_at.desc(),
                ModelRegistryEntry.id.desc(),
            )
        )
    if model_entry is None:
        raise RuntimeError("No trained model is available. Run train first.")
    return model_entry


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


def _global_open_incident_count(session: Session) -> int:
    return int(
        session.scalar(
            select(func.count())
            .select_from(DataQualityIncident)
            .where(DataQualityIncident.resolution_status == "open")
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


def _latest_transition(session: Session) -> ModeTransitionEvent | None:
    return session.scalar(
        select(ModeTransitionEvent).order_by(
            ModeTransitionEvent.created_at.desc(),
            ModeTransitionEvent.id.desc(),
        )
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
    mode_state.current_mode = "frozen"
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
            if mode_state.current_mode == "frozen":
                mode_state.current_mode = "simulation"
            session.commit()


def _current_weights_from_local_positions(
    config: AppConfig,
    *,
    bars: dict[str, CanonicalDailyBar],
    holdings: dict[str, float],
    cash_balance: float,
    score_map: dict[str, float],
) -> tuple[float, dict[str, float], list[PositionSummary]]:
    start_nav = cash_balance
    for symbol, shares in holdings.items():
        bar = bars.get(symbol)
        if bar is None:
            continue
        start_nav += shares * bar.close

    current_weights: dict[str, float] = {}
    positions: list[PositionSummary] = []
    if start_nav <= 0:
        return start_nav, current_weights, positions

    for symbol, shares in sorted(holdings.items()):
        bar = bars.get(symbol)
        if bar is None:
            continue
        market_value = shares * bar.close
        weight = market_value / start_nav
        current_weights[symbol] = weight
        positions.append(
            _position_summary(
                symbol=symbol,
                shares=shares,
                target_weight=weight,
                actual_weight=weight,
                price=bar.close,
                market_value=market_value,
                score=score_map.get(symbol),
                sector=_sector_for_symbol(config, symbol),
                metadata={"source": "carried-position"},
            )
        )
    return start_nav, current_weights, positions


def _current_weights_from_broker_positions(
    config: AppConfig,
    *,
    account: BrokerAccountSnapshotData,
    positions: tuple[BrokerPositionData, ...],
    score_map: dict[str, float],
) -> tuple[float, dict[str, float], dict[str, float], list[PositionSummary]]:
    start_nav = account.net_liquidation
    current_weights: dict[str, float] = {}
    holdings: dict[str, float] = {}
    position_summaries: list[PositionSummary] = []
    for position in sorted(positions, key=lambda item: item.symbol):
        if abs(position.quantity) <= 1e-9:
            continue
        holdings[position.symbol] = position.quantity
        weight = 0.0 if start_nav <= 0 else position.market_value / start_nav
        current_weights[position.symbol] = weight
        position_summaries.append(
            _position_summary(
                symbol=position.symbol,
                shares=position.quantity,
                target_weight=weight,
                actual_weight=weight,
                price=position.market_price,
                market_value=position.market_value,
                score=score_map.get(position.symbol),
                sector=_sector_for_symbol(config, position.symbol),
                metadata={
                    "source": "broker-sync",
                    "average_cost": position.average_cost,
                    "unrealized_pnl": position.unrealized_pnl,
                    "realized_pnl": position.realized_pnl,
                },
            )
        )
    return start_nav, current_weights, holdings, position_summaries


def _target_positions_from_plan(
    config: AppConfig,
    *,
    target_portfolio: Any,
    start_nav: float,
) -> tuple[dict[str, float], list[PositionSummary]]:
    target_weights = {
        position.symbol: position.target_weight for position in target_portfolio.positions
    }
    target_positions: list[PositionSummary] = []
    for position in target_portfolio.positions:
        price = float(position.metadata["price"])
        target_shares = 0.0 if price == 0 else start_nav * position.target_weight / price
        market_value = target_shares * price
        target_positions.append(
            _position_summary(
                symbol=position.symbol,
                shares=target_shares,
                target_weight=position.target_weight,
                actual_weight=position.target_weight,
                price=price,
                market_value=market_value,
                score=position.score,
                sector=position.sector,
                metadata=position.metadata,
            )
        )
    return target_weights, sorted(target_positions, key=lambda item: item.symbol)


def _build_order_plans(
    config: AppConfig,
    *,
    start_nav: float,
    current_holdings: dict[str, float],
    target_weights: dict[str, float],
    bars: dict[str, CanonicalDailyBar],
    candidate_map: dict[str, PortfolioCandidate],
) -> list[_OrderPlan]:
    order_plans: list[_OrderPlan] = []
    all_symbols = sorted(set(current_holdings) | set(target_weights))
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
            dollar_volume_20d=None if candidate is None else candidate.dollar_volume_20d,
        )
        slippage_bps = _execution_slippage_bps(
            config,
            realized_vol_20d=None if candidate is None else candidate.realized_vol_20d,
            dollar_volume_20d=None if candidate is None else candidate.dollar_volume_20d,
        )
        side = "buy" if share_delta > 0 else "sell"
        order_type = _order_type(
            realized_vol_20d=None if candidate is None else candidate.realized_vol_20d,
            dollar_volume_20d=None if candidate is None else candidate.dollar_volume_20d,
        )
        limit_price = bar.close * (
            1.0 + (1.0 if side == "buy" else -1.0) * expected_spread / 20_000.0
        )
        order_plans.append(
            _OrderPlan(
                symbol=symbol,
                side=side,
                requested_shares=abs(share_delta),
                requested_notional=abs(requested_notional),
                target_weight=target_weight,
                reference_price=bar.close,
                order_type=order_type,
                time_in_force="day",
                limit_price=limit_price,
                expected_spread_bps=expected_spread,
                expected_slippage_bps=slippage_bps,
                score=None if candidate is None else candidate.score,
            )
        )
    return order_plans


def _create_simulation_run(session: Session, *, mode: str, as_of_date: date) -> int:
    simulation_run = SimulationRun(
        status="running",
        mode=mode,
        as_of_date=as_of_date,
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
    return simulation_run.id


def _persist_broker_sync(
    session: Session,
    *,
    simulation_run_id: int,
    mode: str,
    adapter: BrokerAdapter,
) -> _BrokerSync:
    account = adapter.sync_account_state()
    positions = adapter.sync_positions()
    snapshot = BrokerAccountSnapshot(
        simulation_run_id=simulation_run_id,
        broker_name=adapter.name,
        mode=mode,
        account_id=account.account_id,
        net_liquidation=account.net_liquidation,
        cash_balance=account.cash_balance,
        buying_power=account.buying_power,
        available_funds=account.available_funds,
        cushion=account.cushion,
        payload_json=json.dumps(account.payload, sort_keys=True, default=str),
    )
    session.add(snapshot)
    session.commit()

    for position in positions:
        session.add(
            BrokerPositionSnapshot(
                snapshot_id=snapshot.id,
                symbol=position.symbol,
                quantity=position.quantity,
                market_price=position.market_price,
                market_value=position.market_value,
                average_cost=position.average_cost,
                unrealized_pnl=position.unrealized_pnl,
                realized_pnl=position.realized_pnl,
                currency=position.currency,
                payload_json=json.dumps(position.payload, sort_keys=True, default=str),
            )
        )
    session.commit()
    return _BrokerSync(snapshot_id=snapshot.id, account=account, positions=positions)


def _build_execution_plan(
    session: Session,
    config: AppConfig,
    *,
    as_of_date: date,
    model_version: str | None,
    current_weights: dict[str, float],
    allow_research_model: bool,
) -> _ExecutionPlan:
    dataset_summary = build_dataset_snapshot(config, as_of_date=as_of_date)
    dataset_rows = _load_dataset_rows(config, dataset_summary.artifact_path)
    decision_date, latest_rows = _latest_rows(dataset_rows, as_of_date)
    if not latest_rows:
        raise RuntimeError("No feature rows are available for the latest decision date.")

    model_entry = _latest_model_entry(session, model_version)
    if not allow_research_model and model_entry.promotion_status != "candidate":
        raise RuntimeError(
            "Live trading requires a candidate model. Continue paper trading and retrain first."
        )
    model = _load_model_artifact(config, model_entry.artifact_path)

    candidate_symbols = {row.symbol for row in latest_rows}
    if config.portfolio.defensive_etf_symbol:
        candidate_symbols.add(config.portfolio.defensive_etf_symbol)
    candidate_symbols.update(current_weights)

    bars = _load_price_bars(session, symbols=sorted(candidate_symbols), trade_date=decision_date)
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
        raise RuntimeError("No verified prices are available for the latest decision date.")

    candidate_map = {
        item.row.symbol: PortfolioCandidate(
            symbol=item.row.symbol,
            score=item.score,
            price=item.bar.close,
            asset_type="etf" if item.row.symbol in set(config.universe.curated_etfs) else "stock",
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
                    (
                        row.features.get("regime_return_20d")
                        for row in latest_rows
                        if row.features.get("regime_return_20d") is not None
                    ),
                    None,
                ),
                regime_vol_20d=next(
                    (
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
    return _ExecutionPlan(
        effective_as_of_date=as_of_date,
        decision_date=decision_date,
        dataset_snapshot_id=dataset_summary.snapshot_id,
        model_entry=model_entry,
        model=model,
        target_portfolio=target_portfolio,
        latest_rows=tuple(latest_rows),
        bars=bars,
        candidate_map=candidate_map,
        score_map={item.row.symbol: item.score for item in scored_rows},
    )


def _load_order_intents_for_run(session: Session, simulation_run_id: int) -> list[OrderIntent]:
    return list(
        session.scalars(
            select(OrderIntent)
            .where(OrderIntent.simulation_run_id == simulation_run_id)
            .order_by(OrderIntent.id.asc())
        ).all()
    )


def _load_broker_orders_for_run(session: Session, simulation_run_id: int) -> list[BrokerOrder]:
    return list(
        session.scalars(
            select(BrokerOrder)
            .where(BrokerOrder.simulation_run_id == simulation_run_id)
            .order_by(BrokerOrder.id.asc())
        ).all()
    )


def _load_approvals_for_run(session: Session, simulation_run_id: int) -> list[OrderApproval]:
    return list(
        session.scalars(
            select(OrderApproval)
            .where(OrderApproval.simulation_run_id == simulation_run_id)
            .order_by(OrderApproval.id.asc())
        ).all()
    )


def _approval_summary(approval: OrderApproval) -> ApprovalSummary:
    return ApprovalSummary(
        approval_id=approval.id,
        order_intent_id=approval.order_intent_id,
        symbol=approval.symbol,
        mode=approval.mode,
        status=approval.status,
        reason=approval.reason,
        broker_order_id=approval.broker_order_id,
        created_at=approval.created_at,
        decided_at=approval.decided_at,
        metadata=json.loads(approval.metadata_json),
    )


def _persist_order_intent(
    session: Session,
    *,
    simulation_run_id: int,
    order_plan: _OrderPlan,
    status: str,
    metadata: dict[str, Any],
) -> OrderIntent:
    order = OrderIntent(
        simulation_run_id=simulation_run_id,
        symbol=order_plan.symbol,
        side=order_plan.side,
        status=status,
        order_type=order_plan.order_type,
        time_in_force=order_plan.time_in_force,
        requested_shares=order_plan.requested_shares,
        requested_notional=order_plan.requested_notional,
        limit_price=order_plan.limit_price,
        reference_price=order_plan.reference_price,
        expected_slippage_bps=order_plan.expected_slippage_bps,
        target_weight=order_plan.target_weight,
        metadata_json=json.dumps(metadata, sort_keys=True, default=str),
    )
    session.add(order)
    session.commit()
    return order


def _simulation_fill_status(*, requested_shares: float, filled_shares: float) -> str:
    if filled_shares <= 1e-9:
        return "unfilled"
    if filled_shares + 1e-9 < requested_shares:
        return "partial"
    return "filled"


def _slippage_bps_for_fill(*, side: str, reference_price: float, fill_price: float) -> float:
    if reference_price <= 0:
        return 0.0
    signed_difference = (fill_price / reference_price - 1.0) * 10_000.0
    return signed_difference if side == "buy" else -signed_difference


def _simulation_fill(
    session: Session,
    *,
    config: AppConfig,
    simulation_run_id: int,
    order: OrderIntent,
    order_plan: _OrderPlan,
    bar: CanonicalDailyBar,
) -> tuple[ExecutionFill, OrderIntentSummary, FillSummary, float, float]:
    max_fill_notional = abs(order_plan.requested_notional)
    if config.execution.partial_fill_enabled:
        max_fill_notional = min(
            abs(order_plan.requested_notional),
            bar.close * bar.volume * config.execution.max_participation_rate,
        )
    fill_ratio = (
        0.0
        if abs(order_plan.requested_notional) < 1e-9
        else max_fill_notional / abs(order_plan.requested_notional)
    )
    fill_ratio = max(0.0, min(fill_ratio, 1.0))
    filled_shares = order_plan.requested_shares * fill_ratio
    executed_price = bar.close * (
        1.0
        + (1.0 if order_plan.side == "buy" else -1.0) * order_plan.expected_slippage_bps / 10_000.0
    )
    commission = filled_shares * executed_price * config.execution.commission_bps / 10_000.0
    fill_status = _simulation_fill_status(
        requested_shares=order_plan.requested_shares,
        filled_shares=filled_shares,
    )
    fill = ExecutionFill(
        simulation_run_id=simulation_run_id,
        order_intent_id=order.id,
        symbol=order_plan.symbol,
        side=order_plan.side,
        fill_status=fill_status,
        filled_shares=filled_shares,
        filled_notional=filled_shares * executed_price,
        fill_price=executed_price,
        commission=commission,
        slippage_bps=order_plan.expected_slippage_bps,
        expected_spread_bps=order_plan.expected_spread_bps,
        metadata_json=json.dumps(
            {
                "fill_ratio": fill_ratio,
                "requested_shares": order_plan.requested_shares,
                "source": "simulation",
            },
            sort_keys=True,
        ),
    )
    session.add(fill)
    session.commit()

    order.status = fill_status
    order.completed_at = utc_now()
    session.commit()

    order_summary = OrderIntentSummary(
        order_id=order.id,
        symbol=order_plan.symbol,
        side=order_plan.side,
        status=fill_status,
        order_type=order_plan.order_type,
        requested_shares=order_plan.requested_shares,
        requested_notional=order_plan.requested_notional,
        reference_price=order_plan.reference_price,
        limit_price=order_plan.limit_price,
        expected_slippage_bps=order_plan.expected_slippage_bps,
        metadata={
            "expected_spread_bps": order_plan.expected_spread_bps,
            "target_weight": order_plan.target_weight,
            "source": "simulation",
        },
    )
    fill_summary = FillSummary(
        fill_id=fill.id,
        order_intent_id=order.id,
        symbol=order_plan.symbol,
        side=order_plan.side,
        fill_status=fill_status,
        filled_shares=filled_shares,
        filled_notional=filled_shares * executed_price,
        fill_price=executed_price,
        commission=commission,
        slippage_bps=order_plan.expected_slippage_bps,
        expected_spread_bps=order_plan.expected_spread_bps,
        metadata={"fill_ratio": fill_ratio, "source": "simulation"},
    )
    return fill, order_summary, fill_summary, filled_shares, executed_price


def _broker_order_request(config: AppConfig, order_plan: _OrderPlan) -> BrokerOrderRequest:
    return BrokerOrderRequest(
        symbol=order_plan.symbol,
        side=order_plan.side,
        quantity=order_plan.requested_shares,
        order_type=order_plan.order_type,
        time_in_force=order_plan.time_in_force.upper(),
        limit_price=order_plan.limit_price,
        exchange=config.broker.default_exchange,
        currency=config.broker.default_currency,
    )


def _broker_fill_status(*, requested_shares: float, filled_shares: float) -> str:
    return _simulation_fill_status(requested_shares=requested_shares, filled_shares=filled_shares)


def _persist_broker_preview(
    session: Session,
    *,
    config: AppConfig,
    simulation_run_id: int,
    mode: str,
    adapter: BrokerAdapter,
    order: OrderIntent,
    order_plan: _OrderPlan,
    approval_status: str,
) -> tuple[BrokerOrder, tuple[str, ...], float | None]:
    preview = adapter.preview_order(_broker_order_request(config, order_plan))
    broker_order = BrokerOrder(
        simulation_run_id=simulation_run_id,
        order_intent_id=order.id,
        broker_name=adapter.name,
        mode=mode,
        account_id=adapter.account_id,
        broker_order_id=None,
        broker_status="previewed",
        approval_status=approval_status,
        symbol=order_plan.symbol,
        side=order_plan.side,
        order_type=order_plan.order_type,
        time_in_force=order_plan.time_in_force,
        requested_shares=order_plan.requested_shares,
        filled_shares=0.0,
        limit_price=order_plan.limit_price,
        average_fill_price=None,
        preview_commission=preview.estimated_commission,
        warnings_json=json.dumps(list(preview.warnings), sort_keys=True),
        payload_json=json.dumps(preview.raw, sort_keys=True, default=str),
    )
    session.add(broker_order)
    session.commit()
    return broker_order, preview.warnings, preview.estimated_commission


def _submit_broker_order(
    session: Session,
    *,
    config: AppConfig,
    simulation_run_id: int,
    order: OrderIntent,
    order_plan: _OrderPlan,
    broker_order: BrokerOrder,
    adapter: BrokerAdapter,
) -> tuple[ExecutionFill, OrderIntentSummary, FillSummary]:
    result = adapter.submit_order(_broker_order_request(config, order_plan))
    filled_shares = result.filled_quantity
    fill_status = _broker_fill_status(
        requested_shares=order_plan.requested_shares,
        filled_shares=filled_shares,
    )
    fill_price = result.average_fill_price or order_plan.reference_price
    commission = result.commission or broker_order.preview_commission or 0.0
    slippage_bps = _slippage_bps_for_fill(
        side=order_plan.side,
        reference_price=order_plan.reference_price,
        fill_price=fill_price,
    )
    fill = ExecutionFill(
        simulation_run_id=simulation_run_id,
        order_intent_id=order.id,
        symbol=order_plan.symbol,
        side=order_plan.side,
        fill_status=fill_status,
        filled_shares=filled_shares,
        filled_notional=filled_shares * fill_price,
        fill_price=fill_price,
        commission=commission,
        slippage_bps=slippage_bps,
        expected_spread_bps=order_plan.expected_spread_bps,
        metadata_json=json.dumps(
            {
                "source": adapter.name,
                "warnings": list(result.warnings),
            },
            sort_keys=True,
        ),
    )
    session.add(fill)
    session.commit()

    order.status = fill_status
    order.completed_at = utc_now()
    session.commit()

    broker_order.broker_order_id = result.broker_order_id
    broker_order.broker_status = result.status
    broker_order.approval_status = "approved"
    broker_order.filled_shares = filled_shares
    broker_order.average_fill_price = fill_price
    broker_order.payload_json = json.dumps(result.raw, sort_keys=True, default=str)
    broker_order.warnings_json = json.dumps(list(result.warnings), sort_keys=True)
    session.commit()

    order_summary = OrderIntentSummary(
        order_id=order.id,
        symbol=order_plan.symbol,
        side=order_plan.side,
        status=fill_status,
        order_type=order_plan.order_type,
        requested_shares=order_plan.requested_shares,
        requested_notional=order_plan.requested_notional,
        reference_price=order_plan.reference_price,
        limit_price=order_plan.limit_price,
        expected_slippage_bps=order_plan.expected_slippage_bps,
        metadata={
            "expected_spread_bps": order_plan.expected_spread_bps,
            "target_weight": order_plan.target_weight,
            "broker_order_id": result.broker_order_id,
            "source": adapter.name,
        },
    )
    fill_summary = FillSummary(
        fill_id=fill.id,
        order_intent_id=order.id,
        symbol=order_plan.symbol,
        side=order_plan.side,
        fill_status=fill_status,
        filled_shares=filled_shares,
        filled_notional=filled_shares * fill_price,
        fill_price=fill_price,
        commission=commission,
        slippage_bps=slippage_bps,
        expected_spread_bps=order_plan.expected_spread_bps,
        metadata={
            "broker_order_id": result.broker_order_id,
            "warnings": list(result.warnings),
            "source": adapter.name,
        },
    )
    return fill, order_summary, fill_summary


def _positions_after_simulation(
    *,
    current_holdings: dict[str, float],
    cash_balance: float,
    fill_summaries: list[FillSummary],
) -> tuple[dict[str, float], float]:
    positions_after = dict(current_holdings)
    cash_after = cash_balance
    for fill_summary in fill_summaries:
        signed_delta = (
            fill_summary.filled_shares
            if fill_summary.side == "buy"
            else -fill_summary.filled_shares
        )
        if fill_summary.side == "buy":
            cash_after -= (
                fill_summary.filled_shares * fill_summary.fill_price + fill_summary.commission
            )
        else:
            cash_after += (
                fill_summary.filled_shares * fill_summary.fill_price - fill_summary.commission
            )
        positions_after[fill_summary.symbol] = (
            positions_after.get(fill_summary.symbol, 0.0) + signed_delta
        )
        if abs(positions_after[fill_summary.symbol]) <= 1e-9:
            positions_after.pop(fill_summary.symbol, None)
        if fill_summary.fill_status == "unfilled":
            positions_after[fill_summary.symbol] = current_holdings.get(fill_summary.symbol, 0.0)
    return positions_after, cash_after


def _post_positions_from_local_holdings(
    config: AppConfig,
    *,
    bars: dict[str, CanonicalDailyBar],
    holdings: dict[str, float],
    target_weights: dict[str, float],
    end_nav: float,
    score_map: dict[str, float],
) -> list[PositionSummary]:
    positions: list[PositionSummary] = []
    if end_nav <= 0:
        return positions
    for symbol, shares in sorted(holdings.items()):
        bar = bars.get(symbol)
        if bar is None:
            continue
        market_value = shares * bar.close
        positions.append(
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
    return positions


def _post_positions_from_broker(
    config: AppConfig,
    *,
    positions: tuple[BrokerPositionData, ...],
    target_weights: dict[str, float],
    nav: float,
    score_map: dict[str, float],
) -> list[PositionSummary]:
    summaries: list[PositionSummary] = []
    for position in sorted(positions, key=lambda item: item.symbol):
        if abs(position.quantity) <= 1e-9:
            continue
        actual_weight = 0.0 if nav <= 0 else position.market_value / nav
        summaries.append(
            _position_summary(
                symbol=position.symbol,
                shares=position.quantity,
                target_weight=target_weights.get(position.symbol, 0.0),
                actual_weight=actual_weight,
                price=position.market_price,
                market_value=position.market_value,
                score=score_map.get(position.symbol),
                sector=_sector_for_symbol(config, position.symbol),
                metadata={
                    "source": "broker-post-trade",
                    "average_cost": position.average_cost,
                    "unrealized_pnl": position.unrealized_pnl,
                    "realized_pnl": position.realized_pnl,
                },
            )
        )
    return summaries


def _complete_run(
    session: Session,
    *,
    config: AppConfig,
    simulation_run_id: int,
    status: str,
    mode: str,
    decision_date: date | None,
    model_entry: ModelRegistryEntry | None,
    dataset_snapshot_id: int | None,
    regime: str | None,
    start_nav: float,
    end_nav: float,
    cash_start: float,
    cash_end: float,
    gross_exposure_target: float,
    gross_exposure_actual: float,
    artifact_prefix: str,
    payload: dict[str, Any],
    keep_open: bool = False,
) -> str:
    artifact_path = _write_json_artifact(
        config.report_artifacts_dir,
        prefix=f"{artifact_prefix}-{simulation_run_id}",
        payload=payload,
        config=config,
    )
    run = session.get(SimulationRun, simulation_run_id)
    if run is None:
        raise RuntimeError("Execution run state was lost.")
    run.status = status
    run.mode = mode
    run.decision_date = decision_date
    run.model_entry_id = None if model_entry is None else model_entry.id
    run.dataset_snapshot_id = dataset_snapshot_id
    run.regime = regime
    run.start_nav = start_nav
    run.end_nav = end_nav
    run.cash_start = cash_start
    run.cash_end = cash_end
    run.gross_exposure_target = gross_exposure_target
    run.gross_exposure_actual = gross_exposure_actual
    run.artifact_path = artifact_path
    run.summary_json = json.dumps(payload, sort_keys=True, default=str)
    run.completed_at = None if keep_open else utc_now()
    session.commit()
    return artifact_path


def _paper_safe_day_count(session: Session) -> int:
    safe_runs = 0
    runs = session.scalars(
        select(SimulationRun)
        .where(SimulationRun.mode == "paper")
        .order_by(SimulationRun.created_at.asc(), SimulationRun.id.asc())
    ).all()
    for run in runs:
        if run.status != "completed":
            continue
        summary = json.loads(run.summary_json)
        if summary.get("freeze_triggered") is False:
            safe_runs += 1
    return safe_runs


def _combined_safe_live_day_count(session: Session) -> int:
    safe_runs = 0
    runs = session.scalars(
        select(SimulationRun).where(
            SimulationRun.mode.in_(("paper", "live-manual", "live-autonomous"))
        )
    ).all()
    for run in runs:
        if run.status != "completed":
            continue
        summary = json.loads(run.summary_json)
        if summary.get("freeze_triggered") is False:
            safe_runs += 1
    return safe_runs


def _live_gate_checks(
    session: Session,
    config: AppConfig,
    *,
    profile: str,
    ack_disable_approvals: bool,
    adapter: BrokerAdapter | None,
) -> tuple[bool, list[dict[str, Any]]]:
    target_mode = "live-manual" if profile == "manual" else "live-autonomous"
    checks: list[dict[str, Any]] = []

    checks.append(
        {
            "name": "broker-enabled",
            "ok": config.broker.enabled,
            "detail": "broker integration enabled" if config.broker.enabled else "broker disabled",
        }
    )
    if not config.broker.enabled:
        return False, checks

    account_id = config.broker.account_id_for_mode(target_mode)
    checks.append(
        {
            "name": "account-configured",
            "ok": account_id is not None,
            "detail": f"account {account_id}"
            if account_id
            else f"missing account for {target_mode}",
        }
    )
    if account_id is None:
        return False, checks

    active_freeze = _active_freeze(session)
    checks.append(
        {
            "name": "freeze-clear",
            "ok": active_freeze is None,
            "detail": "no active freeze" if active_freeze is None else active_freeze.reason,
        }
    )
    if active_freeze is not None:
        return False, checks

    latest_model = session.scalar(
        select(ModelRegistryEntry).order_by(
            ModelRegistryEntry.created_at.desc(),
            ModelRegistryEntry.id.desc(),
        )
    )
    model_ok = latest_model is not None and latest_model.promotion_status == "candidate"
    checks.append(
        {
            "name": "candidate-model",
            "ok": model_ok,
            "detail": (
                "candidate model ready"
                if model_ok
                else "latest model is not candidate-promoted yet"
            ),
        }
    )

    paper_days = _paper_safe_day_count(session)
    checks.append(
        {
            "name": "paper-safe-days",
            "ok": paper_days >= config.broker.live_manual_min_paper_days,
            "detail": (
                f"{paper_days} safe paper day(s), requires "
                f"{config.broker.live_manual_min_paper_days}"
            ),
        }
    )

    connectivity_ok = False
    connectivity_detail = "broker adapter not requested"
    if adapter is not None:
        connectivity_ok, connectivity_detail = adapter.connectivity()
    checks.append(
        {
            "name": "broker-connectivity",
            "ok": connectivity_ok,
            "detail": connectivity_detail,
        }
    )

    if profile == "autonomous":
        safe_days = _combined_safe_live_day_count(session)
        checks.append(
            {
                "name": "autonomous-safe-days",
                "ok": safe_days >= config.broker.live_autonomous_min_safe_days,
                "detail": (
                    f"{safe_days} safe paper/live-manual day(s), requires "
                    f"{config.broker.live_autonomous_min_safe_days}"
                ),
            }
        )
        open_incidents = _global_open_incident_count(session)
        checks.append(
            {
                "name": "autonomous-incidents",
                "ok": open_incidents <= config.broker.max_open_incidents_for_autonomous,
                "detail": (
                    f"{open_incidents} open incident(s), allows "
                    f"{config.broker.max_open_incidents_for_autonomous}"
                ),
            }
        )
        ack_ok = (not config.broker.require_live_autonomous_ack) or ack_disable_approvals
        checks.append(
            {
                "name": "autonomous-ack",
                "ok": ack_ok,
                "detail": (
                    "autonomous acknowledgement received"
                    if ack_ok
                    else "explicit acknowledgement is required before autonomous live mode"
                ),
            }
        )

    allowed = all(check["ok"] for check in checks)
    return allowed, checks


def _allowed_mode_transition(current_mode: str, target_mode: str) -> bool:
    allowed_transitions = {
        ("simulation", "paper"),
        ("paper", "simulation"),
        ("live-manual", "simulation"),
        ("paper", "live-manual"),
        ("live-autonomous", "paper"),
        ("live-autonomous", "simulation"),
        ("live-manual", "paper"),
        ("live-manual", "live-autonomous"),
        ("live-autonomous", "live-manual"),
        ("frozen", "simulation"),
        ("frozen", "paper"),
        ("frozen", "live-manual"),
    }
    return current_mode == target_mode or (current_mode, target_mode) in allowed_transitions


def _assert_transition_not_blocked_by_freeze(session: Session, *, current_mode: str) -> None:
    if current_mode != "frozen":
        return
    active_freeze = _active_freeze(session)
    if active_freeze is not None:
        raise RuntimeError(
            f"Cannot leave frozen mode until the active freeze is cleared: {active_freeze.reason}"
        )


def _persist_mode_transition(
    session: Session,
    *,
    previous_mode: str,
    new_mode: str,
    live_profile: str,
    source: str,
    reason: str,
    metadata: dict[str, Any],
) -> ModeTransitionEvent:
    transition = ModeTransitionEvent(
        previous_mode=previous_mode,
        new_mode=new_mode,
        live_profile=live_profile,
        source=source,
        reason=reason,
        metadata_json=json.dumps(metadata, sort_keys=True, default=str),
    )
    session.add(transition)
    session.commit()
    return transition


def _update_mode_state(
    session: Session,
    *,
    new_mode: str,
    requested_mode: str | None,
    live_profile: str,
    metadata: dict[str, Any],
) -> SystemModeState:
    mode_state = _current_mode_state(session)
    mode_state.current_mode = new_mode
    mode_state.requested_mode = requested_mode
    mode_state.live_profile = live_profile
    mode_state.metadata_json = json.dumps(metadata, sort_keys=True, default=str)
    session.commit()
    return mode_state


def _mode_transition_summary(
    *,
    previous_mode: str,
    current_mode: str,
    requested_mode: str,
    live_profile: str,
    status: str,
    armed: bool,
    reason: str,
    metadata: dict[str, Any],
) -> ModeTransitionSummary:
    return ModeTransitionSummary(
        previous_mode=previous_mode,
        current_mode=current_mode,
        requested_mode=requested_mode,
        live_profile=live_profile,
        status=status,
        armed=armed,
        reason=reason,
        metadata=metadata,
    )


def enter_paper_mode(
    config: AppConfig,
    *,
    source: str = "cli",
    reason: str = "paper mode requested",
    adapter: BrokerAdapter | None = None,
) -> ModeTransitionSummary:
    if not database_exists(config) or not database_is_reachable(config):
        raise RuntimeError("Database is not ready. Run init first.")
    if not config.broker.enabled:
        raise RuntimeError("Broker integration is disabled in config.")

    engine = create_db_engine(config)
    try:
        with Session(engine) as session:
            _clear_if_missing_active_freeze(session)
            mode_state = _current_mode_state(session)
            current_mode = mode_state.current_mode
            _assert_transition_not_blocked_by_freeze(session, current_mode=current_mode)
            if not _allowed_mode_transition(current_mode, "paper"):
                raise RuntimeError(f"Cannot transition from {current_mode} to paper.")

            status_adapter = adapter or build_broker_adapter(config, mode="paper")
            connectivity_ok, detail = status_adapter.connectivity()
            if not connectivity_ok:
                raise RuntimeError(detail)

            _persist_mode_transition(
                session,
                previous_mode=current_mode,
                new_mode="paper",
                live_profile=mode_state.live_profile,
                source=source,
                reason=reason,
                metadata={"detail": detail},
            )
            _update_mode_state(
                session,
                new_mode="paper",
                requested_mode=None,
                live_profile=mode_state.live_profile,
                metadata={"detail": detail, "source": source},
            )
            record_audit_event(config, "mode", "paper mode entered")
            return _mode_transition_summary(
                previous_mode=current_mode,
                current_mode="paper",
                requested_mode="paper",
                live_profile=mode_state.live_profile,
                status="entered",
                armed=True,
                reason=reason,
                metadata={"detail": detail},
            )
    finally:
        engine.dispose()


def enter_simulation_mode(
    config: AppConfig,
    *,
    source: str = "cli",
    reason: str = "simulation mode requested",
) -> ModeTransitionSummary:
    if not database_exists(config) or not database_is_reachable(config):
        raise RuntimeError("Database is not ready. Run init first.")

    engine = create_db_engine(config)
    try:
        with Session(engine) as session:
            _clear_if_missing_active_freeze(session)
            mode_state = _current_mode_state(session)
            current_mode = mode_state.current_mode
            _assert_transition_not_blocked_by_freeze(session, current_mode=current_mode)
            if not _allowed_mode_transition(current_mode, "simulation"):
                raise RuntimeError(f"Cannot transition from {current_mode} to simulation.")

            metadata = {"source": source}
            _persist_mode_transition(
                session,
                previous_mode=current_mode,
                new_mode="simulation",
                live_profile=mode_state.live_profile,
                source=source,
                reason=reason,
                metadata=metadata,
            )
            _update_mode_state(
                session,
                new_mode="simulation",
                requested_mode=None,
                live_profile=mode_state.live_profile,
                metadata=metadata,
            )
            record_audit_event(config, "mode", "simulation mode entered")
            return _mode_transition_summary(
                previous_mode=current_mode,
                current_mode="simulation",
                requested_mode="simulation",
                live_profile=mode_state.live_profile,
                status="entered",
                armed=True,
                reason=reason,
                metadata=metadata,
            )
    finally:
        engine.dispose()


def arm_live_mode(
    config: AppConfig,
    *,
    profile: str = "manual",
    ack_disable_approvals: bool = False,
    source: str = "cli",
    reason: str = "live mode requested",
    adapter: BrokerAdapter | None = None,
) -> ModeTransitionSummary:
    if not database_exists(config) or not database_is_reachable(config):
        raise RuntimeError("Database is not ready. Run init first.")

    target_mode = "live-manual" if profile == "manual" else "live-autonomous"
    engine = create_db_engine(config)
    try:
        with Session(engine) as session:
            _clear_if_missing_active_freeze(session)
            mode_state = _current_mode_state(session)
            previous_mode = mode_state.current_mode
            _assert_transition_not_blocked_by_freeze(session, current_mode=previous_mode)
            if not _allowed_mode_transition(previous_mode, target_mode):
                raise RuntimeError(f"Cannot transition from {previous_mode} to {target_mode}.")

            status_adapter = adapter or build_broker_adapter(config, mode=target_mode)
            allowed, checks = _live_gate_checks(
                session,
                config,
                profile=profile,
                ack_disable_approvals=ack_disable_approvals,
                adapter=status_adapter,
            )
            metadata = {"checks": checks, "source": source}
            if not allowed:
                mode_state.requested_mode = target_mode
                mode_state.metadata_json = json.dumps(metadata, sort_keys=True, default=str)
                session.commit()
                record_audit_event(config, "mode", f"{target_mode} arm blocked")
                return _mode_transition_summary(
                    previous_mode=previous_mode,
                    current_mode=previous_mode,
                    requested_mode=target_mode,
                    live_profile=profile,
                    status="blocked",
                    armed=False,
                    reason=reason,
                    metadata=metadata,
                )

            _persist_mode_transition(
                session,
                previous_mode=previous_mode,
                new_mode=target_mode,
                live_profile=profile,
                source=source,
                reason=reason,
                metadata=metadata,
            )
            _update_mode_state(
                session,
                new_mode=target_mode,
                requested_mode=None,
                live_profile=profile,
                metadata=metadata,
            )
            record_audit_event(config, "mode", f"{target_mode} armed")
            return _mode_transition_summary(
                previous_mode=previous_mode,
                current_mode=target_mode,
                requested_mode=target_mode,
                live_profile=profile,
                status="armed",
                armed=True,
                reason=reason,
                metadata=metadata,
            )
    finally:
        engine.dispose()


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
            simulation_run_id = _create_simulation_run(
                session,
                mode="simulation",
                as_of_date=effective_as_of_date,
            )

        try:
            with Session(engine) as session:
                _clear_if_missing_active_freeze(session)
                active_freeze = _active_freeze(session)
                previous_snapshot, previous_positions = _load_latest_post_trade_snapshot(session)
                current_holdings = {
                    position.symbol: position.shares
                    for position in previous_positions
                    if abs(position.shares) > 1e-9
                }
                cash_balance = (
                    config.model_training.initial_capital
                    if previous_snapshot is None
                    else previous_snapshot.cash_balance
                )
                current_weights = {
                    position.symbol: position.actual_weight for position in previous_positions
                }
                plan = _build_execution_plan(
                    session,
                    config,
                    as_of_date=effective_as_of_date,
                    model_version=model_version,
                    current_weights=current_weights,
                    allow_research_model=config.risk.allow_research_models_in_simulation,
                )
                start_nav, current_weights, pre_trade_positions = (
                    _current_weights_from_local_positions(
                        config,
                        bars=plan.bars,
                        holdings=current_holdings,
                        cash_balance=cash_balance,
                        score_map=plan.score_map,
                    )
                )
                target_weights, target_positions = _target_positions_from_plan(
                    config,
                    target_portfolio=plan.target_portfolio,
                    start_nav=start_nav,
                )
                order_plans = _build_order_plans(
                    config,
                    start_nav=start_nav,
                    current_holdings=current_holdings,
                    target_weights=target_weights,
                    bars=plan.bars,
                    candidate_map=plan.candidate_map,
                )
                open_incident_count = _open_incident_count(
                    session,
                    symbols=sorted({row.symbol for row in plan.latest_rows}),
                    as_of_date=plan.decision_date,
                )
                pretrade_risk = evaluate_pretrade_risk(
                    config,
                    mode="simulation",
                    active_freeze_reason=None if active_freeze is None else active_freeze.reason,
                    start_nav=start_nav,
                    previous_nav=None if previous_snapshot is None else previous_snapshot.nav,
                    high_water_mark=_high_water_mark(session),
                    open_incident_count=open_incident_count,
                    kill_switch_active=_kill_switch_active(session),
                )
                run = session.get(SimulationRun, simulation_run_id)
                if run is None:
                    raise RuntimeError("Simulation run state was lost.")
                run.decision_date = plan.decision_date
                run.model_entry_id = plan.model_entry.id
                run.dataset_snapshot_id = plan.dataset_snapshot_id
                run.regime = plan.target_portfolio.regime
                run.start_nav = start_nav
                run.cash_start = cash_balance
                session.commit()

                pre_trade_snapshot_id = _persist_snapshot(
                    session,
                    simulation_run_id=simulation_run_id,
                    snapshot_type="pre-trade",
                    trade_date=plan.decision_date,
                    nav=start_nav,
                    cash_balance=cash_balance,
                    turnover_ratio=0.0,
                    positions=pre_trade_positions,
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
                    payload = {
                        "run_id": simulation_run_id,
                        "status": "blocked",
                        "mode": "simulation",
                        "decision_date": _serialize_date(plan.decision_date),
                        "model_version": plan.model_entry.version,
                        "dataset_snapshot_id": plan.dataset_snapshot_id,
                        "risk_checks": list(pretrade_risk.checks),
                        "code_version": __version__,
                    }
                    artifact_path = _complete_run(
                        session,
                        config=config,
                        simulation_run_id=simulation_run_id,
                        status="blocked",
                        mode="simulation",
                        decision_date=plan.decision_date,
                        model_entry=plan.model_entry,
                        dataset_snapshot_id=plan.dataset_snapshot_id,
                        regime=plan.target_portfolio.regime,
                        start_nav=start_nav,
                        end_nav=start_nav,
                        cash_start=cash_balance,
                        cash_end=cash_balance,
                        gross_exposure_target=0.0,
                        gross_exposure_actual=0.0,
                        artifact_prefix="simulation",
                        payload=payload,
                    )
                    record_audit_event(
                        config,
                        "simulation",
                        f"simulation {simulation_run_id} blocked by freeze: {freeze.reason}",
                    )
                    return SimulationRunSummary(
                        run_id=simulation_run_id,
                        mode="simulation",
                        status="blocked",
                        as_of_date=effective_as_of_date,
                        decision_date=plan.decision_date,
                        model_version=plan.model_entry.version,
                        dataset_snapshot_id=plan.dataset_snapshot_id,
                        regime=plan.target_portfolio.regime,
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

                target_snapshot_id = _persist_snapshot(
                    session,
                    simulation_run_id=simulation_run_id,
                    snapshot_type="target",
                    trade_date=plan.decision_date,
                    nav=start_nav,
                    cash_balance=max(start_nav * plan.target_portfolio.cash_weight, 0.0),
                    turnover_ratio=plan.target_portfolio.turnover_ratio,
                    positions=target_positions,
                )

                order_summaries: list[OrderIntentSummary] = []
                fill_summaries: list[FillSummary] = []
                for order_plan in order_plans:
                    bar = plan.bars[order_plan.symbol]
                    order = _persist_order_intent(
                        session,
                        simulation_run_id=simulation_run_id,
                        order_plan=order_plan,
                        status="created",
                        metadata={
                            "expected_spread_bps": order_plan.expected_spread_bps,
                            "score": order_plan.score,
                        },
                    )
                    _, order_summary, fill_summary, _, _ = _simulation_fill(
                        session,
                        config=config,
                        simulation_run_id=simulation_run_id,
                        order=order,
                        order_plan=order_plan,
                        bar=bar,
                    )
                    order_summaries.append(order_summary)
                    fill_summaries.append(fill_summary)

                positions_after, cash_after = _positions_after_simulation(
                    current_holdings=current_holdings,
                    cash_balance=cash_balance,
                    fill_summaries=fill_summaries,
                )
                end_nav = cash_after
                for symbol, shares in positions_after.items():
                    end_bar = plan.bars.get(symbol)
                    if end_bar is not None:
                        end_nav += shares * end_bar.close

                post_positions = _post_positions_from_local_holdings(
                    config,
                    bars=plan.bars,
                    holdings=positions_after,
                    target_weights=target_weights,
                    end_nav=end_nav,
                    score_map=plan.score_map,
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
                    trade_date=plan.decision_date,
                    nav=end_nav,
                    cash_balance=cash_after,
                    turnover_ratio=plan.target_portfolio.turnover_ratio,
                    positions=post_positions,
                )
                gross_exposure_actual = (
                    0.0
                    if end_nav <= 0
                    else sum(abs(item.market_value) for item in post_positions) / end_nav
                )
                payload = {
                    "run_id": simulation_run_id,
                    "status": "completed",
                    "mode": "simulation",
                    "as_of_date": _serialize_date(effective_as_of_date),
                    "decision_date": _serialize_date(plan.decision_date),
                    "model_version": plan.model_entry.version,
                    "dataset_snapshot_id": plan.dataset_snapshot_id,
                    "regime": plan.target_portfolio.regime,
                    "start_nav": start_nav,
                    "end_nav": end_nav,
                    "cash_start": cash_balance,
                    "cash_end": cash_after,
                    "gross_exposure_target": plan.target_portfolio.target_gross_exposure,
                    "gross_exposure_actual": gross_exposure_actual,
                    "turnover_ratio": plan.target_portfolio.turnover_ratio,
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
                artifact_path = _complete_run(
                    session,
                    config=config,
                    simulation_run_id=simulation_run_id,
                    status="completed",
                    mode="simulation",
                    decision_date=plan.decision_date,
                    model_entry=plan.model_entry,
                    dataset_snapshot_id=plan.dataset_snapshot_id,
                    regime=plan.target_portfolio.regime,
                    start_nav=start_nav,
                    end_nav=end_nav,
                    cash_start=cash_balance,
                    cash_end=cash_after,
                    gross_exposure_target=plan.target_portfolio.target_gross_exposure,
                    gross_exposure_actual=gross_exposure_actual,
                    artifact_prefix="simulation",
                    payload=payload,
                )
                record_audit_event(
                    config,
                    "simulation",
                    (
                        "simulation "
                        f"{simulation_run_id} completed for {plan.decision_date.isoformat()}"
                    ),
                )
                return SimulationRunSummary(
                    run_id=simulation_run_id,
                    mode="simulation",
                    status="completed",
                    as_of_date=effective_as_of_date,
                    decision_date=plan.decision_date,
                    model_version=plan.model_entry.version,
                    dataset_snapshot_id=plan.dataset_snapshot_id,
                    regime=plan.target_portfolio.regime,
                    start_nav=start_nav,
                    end_nav=end_nav,
                    cash_start=cash_balance,
                    cash_end=cash_after,
                    gross_exposure_target=plan.target_portfolio.target_gross_exposure,
                    gross_exposure_actual=gross_exposure_actual,
                    turnover_ratio=plan.target_portfolio.turnover_ratio,
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
                run = session.get(SimulationRun, simulation_run_id)
                if run is not None:
                    run.status = "failed"
                    run.error_message = str(exc)
                    run.completed_at = utc_now()
                    session.commit()
            raise
    finally:
        engine.dispose()


def paper_trade_day(
    config: AppConfig,
    *,
    as_of_date: date | None = None,
    model_version: str | None = None,
    adapter: BrokerAdapter | None = None,
    _run_mode: str = "paper",
    _allow_research_model: bool = True,
    _ensure_mode: bool = True,
) -> SimulationRunSummary:
    if not database_exists(config) or not database_is_reachable(config):
        raise RuntimeError("Database is not ready. Run init first.")
    if not config.broker.enabled:
        raise RuntimeError("Broker integration is disabled in config.")

    effective_as_of_date = as_of_date or datetime.now(UTC).date()
    status_adapter = adapter or build_broker_adapter(config, mode=_run_mode)
    connectivity_ok, detail = status_adapter.connectivity()
    if not connectivity_ok:
        raise RuntimeError(detail)

    if _ensure_mode:
        enter_paper_mode(
            config,
            source="paper",
            reason="paper trading run requested",
            adapter=status_adapter,
        )

    engine = create_db_engine(config)
    try:
        with Session(engine) as session:
            simulation_run_id = _create_simulation_run(
                session,
                mode=_run_mode,
                as_of_date=effective_as_of_date,
            )

        try:
            with Session(engine) as session:
                _clear_if_missing_active_freeze(session)
                active_freeze = _active_freeze(session)
                pre_sync = _persist_broker_sync(
                    session,
                    simulation_run_id=simulation_run_id,
                    mode=_run_mode,
                    adapter=status_adapter,
                )
                _, current_weights, current_holdings, pre_trade_positions = (
                    _current_weights_from_broker_positions(
                        config,
                        account=pre_sync.account,
                        positions=pre_sync.positions,
                        score_map={},
                    )
                )
                plan = _build_execution_plan(
                    session,
                    config,
                    as_of_date=effective_as_of_date,
                    model_version=model_version,
                    current_weights=current_weights,
                    allow_research_model=_allow_research_model,
                )
                start_nav, current_weights, current_holdings, pre_trade_positions = (
                    _current_weights_from_broker_positions(
                        config,
                        account=pre_sync.account,
                        positions=pre_sync.positions,
                        score_map=plan.score_map,
                    )
                )
                target_weights, target_positions = _target_positions_from_plan(
                    config,
                    target_portfolio=plan.target_portfolio,
                    start_nav=start_nav,
                )
                order_plans = _build_order_plans(
                    config,
                    start_nav=start_nav,
                    current_holdings=current_holdings,
                    target_weights=target_weights,
                    bars=plan.bars,
                    candidate_map=plan.candidate_map,
                )
                previous_snapshot, _ = _load_latest_post_trade_snapshot(session)
                pretrade_risk = evaluate_pretrade_risk(
                    config,
                    mode=_run_mode,
                    active_freeze_reason=None if active_freeze is None else active_freeze.reason,
                    start_nav=start_nav,
                    previous_nav=None if previous_snapshot is None else previous_snapshot.nav,
                    high_water_mark=_high_water_mark(session),
                    open_incident_count=_open_incident_count(
                        session,
                        symbols=sorted({row.symbol for row in plan.latest_rows}),
                        as_of_date=plan.decision_date,
                    ),
                    kill_switch_active=_kill_switch_active(session),
                )
                run = session.get(SimulationRun, simulation_run_id)
                if run is None:
                    raise RuntimeError("Paper run state was lost.")
                run.decision_date = plan.decision_date
                run.model_entry_id = plan.model_entry.id
                run.dataset_snapshot_id = plan.dataset_snapshot_id
                run.regime = plan.target_portfolio.regime
                run.start_nav = start_nav
                run.cash_start = pre_sync.account.cash_balance
                session.commit()

                pre_trade_snapshot_id = _persist_snapshot(
                    session,
                    simulation_run_id=simulation_run_id,
                    snapshot_type="pre-trade",
                    trade_date=plan.decision_date,
                    nav=start_nav,
                    cash_balance=pre_sync.account.cash_balance,
                    turnover_ratio=0.0,
                    positions=pre_trade_positions,
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
                    payload = {
                        "run_id": simulation_run_id,
                        "status": "blocked",
                        "mode": _run_mode,
                        "decision_date": _serialize_date(plan.decision_date),
                        "model_version": plan.model_entry.version,
                        "dataset_snapshot_id": plan.dataset_snapshot_id,
                        "risk_checks": list(pretrade_risk.checks),
                        "broker_sync_snapshot_id": pre_sync.snapshot_id,
                        "code_version": __version__,
                    }
                    artifact_path = _complete_run(
                        session,
                        config=config,
                        simulation_run_id=simulation_run_id,
                        status="blocked",
                        mode=_run_mode,
                        decision_date=plan.decision_date,
                        model_entry=plan.model_entry,
                        dataset_snapshot_id=plan.dataset_snapshot_id,
                        regime=plan.target_portfolio.regime,
                        start_nav=start_nav,
                        end_nav=start_nav,
                        cash_start=pre_sync.account.cash_balance,
                        cash_end=pre_sync.account.cash_balance,
                        gross_exposure_target=0.0,
                        gross_exposure_actual=0.0,
                        artifact_prefix=_run_mode,
                        payload=payload,
                    )
                    return SimulationRunSummary(
                        run_id=simulation_run_id,
                        mode=_run_mode,
                        status="blocked",
                        as_of_date=effective_as_of_date,
                        decision_date=plan.decision_date,
                        model_version=plan.model_entry.version,
                        dataset_snapshot_id=plan.dataset_snapshot_id,
                        regime=plan.target_portfolio.regime,
                        start_nav=start_nav,
                        end_nav=start_nav,
                        cash_start=pre_sync.account.cash_balance,
                        cash_end=pre_sync.account.cash_balance,
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

                target_snapshot_id = _persist_snapshot(
                    session,
                    simulation_run_id=simulation_run_id,
                    snapshot_type="target",
                    trade_date=plan.decision_date,
                    nav=start_nav,
                    cash_balance=max(start_nav * plan.target_portfolio.cash_weight, 0.0),
                    turnover_ratio=plan.target_portfolio.turnover_ratio,
                    positions=target_positions,
                )
                order_summaries: list[OrderIntentSummary] = []
                fill_summaries: list[FillSummary] = []
                for order_plan in order_plans:
                    order = _persist_order_intent(
                        session,
                        simulation_run_id=simulation_run_id,
                        order_plan=order_plan,
                        status="previewed",
                        metadata={
                            "expected_spread_bps": order_plan.expected_spread_bps,
                            "score": order_plan.score,
                            "source": status_adapter.name,
                        },
                    )
                    broker_order, _, _ = _persist_broker_preview(
                        session,
                        config=config,
                        simulation_run_id=simulation_run_id,
                        mode=_run_mode,
                        adapter=status_adapter,
                        order=order,
                        order_plan=order_plan,
                        approval_status="not-required",
                    )
                    _, order_summary, fill_summary = _submit_broker_order(
                        session,
                        config=config,
                        simulation_run_id=simulation_run_id,
                        order=order,
                        order_plan=order_plan,
                        broker_order=broker_order,
                        adapter=status_adapter,
                    )
                    order_summaries.append(order_summary)
                    fill_summaries.append(fill_summary)

                post_sync = _persist_broker_sync(
                    session,
                    simulation_run_id=simulation_run_id,
                    mode=_run_mode,
                    adapter=status_adapter,
                )
                post_positions = _post_positions_from_broker(
                    config,
                    positions=post_sync.positions,
                    target_weights=target_weights,
                    nav=post_sync.account.net_liquidation,
                    score_map=plan.score_map,
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
                    trade_date=plan.decision_date,
                    nav=post_sync.account.net_liquidation,
                    cash_balance=post_sync.account.cash_balance,
                    turnover_ratio=plan.target_portfolio.turnover_ratio,
                    positions=post_positions,
                )
                gross_exposure_actual = (
                    0.0
                    if post_sync.account.net_liquidation <= 0
                    else sum(abs(item.market_value) for item in post_positions)
                    / post_sync.account.net_liquidation
                )
                payload = {
                    "run_id": simulation_run_id,
                    "status": "completed",
                    "mode": _run_mode,
                    "as_of_date": _serialize_date(effective_as_of_date),
                    "decision_date": _serialize_date(plan.decision_date),
                    "model_version": plan.model_entry.version,
                    "dataset_snapshot_id": plan.dataset_snapshot_id,
                    "regime": plan.target_portfolio.regime,
                    "start_nav": start_nav,
                    "end_nav": post_sync.account.net_liquidation,
                    "cash_start": pre_sync.account.cash_balance,
                    "cash_end": post_sync.account.cash_balance,
                    "gross_exposure_target": plan.target_portfolio.target_gross_exposure,
                    "gross_exposure_actual": gross_exposure_actual,
                    "turnover_ratio": plan.target_portfolio.turnover_ratio,
                    "broker_sync_snapshot_ids": {
                        "pre": pre_sync.snapshot_id,
                        "post": post_sync.snapshot_id,
                    },
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
                artifact_path = _complete_run(
                    session,
                    config=config,
                    simulation_run_id=simulation_run_id,
                    status="completed",
                    mode=_run_mode,
                    decision_date=plan.decision_date,
                    model_entry=plan.model_entry,
                    dataset_snapshot_id=plan.dataset_snapshot_id,
                    regime=plan.target_portfolio.regime,
                    start_nav=start_nav,
                    end_nav=post_sync.account.net_liquidation,
                    cash_start=pre_sync.account.cash_balance,
                    cash_end=post_sync.account.cash_balance,
                    gross_exposure_target=plan.target_portfolio.target_gross_exposure,
                    gross_exposure_actual=gross_exposure_actual,
                    artifact_prefix=_run_mode,
                    payload=payload,
                )
                record_audit_event(
                    config,
                    _run_mode,
                    (
                        f"{_run_mode} run {simulation_run_id} completed for "
                        f"{plan.decision_date.isoformat()}"
                    ),
                )
                return SimulationRunSummary(
                    run_id=simulation_run_id,
                    mode=_run_mode,
                    status="completed",
                    as_of_date=effective_as_of_date,
                    decision_date=plan.decision_date,
                    model_version=plan.model_entry.version,
                    dataset_snapshot_id=plan.dataset_snapshot_id,
                    regime=plan.target_portfolio.regime,
                    start_nav=start_nav,
                    end_nav=post_sync.account.net_liquidation,
                    cash_start=pre_sync.account.cash_balance,
                    cash_end=post_sync.account.cash_balance,
                    gross_exposure_target=plan.target_portfolio.target_gross_exposure,
                    gross_exposure_actual=gross_exposure_actual,
                    turnover_ratio=plan.target_portfolio.turnover_ratio,
                    target_snapshot_id=target_snapshot_id,
                    post_trade_snapshot_id=post_trade_snapshot_id,
                    order_count=len(order_summaries),
                    fill_count=len(fill_summaries),
                    freeze_triggered=freeze_triggered,
                    artifact_path=artifact_path,
                    metadata={
                        "pre_trade_snapshot_id": pre_trade_snapshot_id,
                        "broker_sync_snapshot_ids": {
                            "pre": pre_sync.snapshot_id,
                            "post": post_sync.snapshot_id,
                        },
                    },
                )
        except Exception as exc:
            with Session(engine) as session:
                run = session.get(SimulationRun, simulation_run_id)
                if run is not None:
                    run.status = "failed"
                    run.error_message = str(exc)
                    run.completed_at = utc_now()
                    session.commit()
            raise
    finally:
        engine.dispose()


def prepare_live_trading_day(
    config: AppConfig,
    *,
    as_of_date: date | None = None,
    model_version: str | None = None,
    adapter: BrokerAdapter | None = None,
) -> TradingOperationSummary:
    if not database_exists(config) or not database_is_reachable(config):
        raise RuntimeError("Database is not ready. Run init first.")

    effective_as_of_date = as_of_date or datetime.now(UTC).date()
    engine = create_db_engine(config)
    try:
        with Session(engine) as session:
            mode_state = _current_mode_state(session)
            if mode_state.current_mode != "live-manual":
                raise RuntimeError("System is not in live-manual mode. Arm live mode first.")
            status_adapter = adapter or build_broker_adapter(config, mode="live-manual")
            allowed, checks = _live_gate_checks(
                session,
                config,
                profile="manual",
                ack_disable_approvals=False,
                adapter=status_adapter,
            )
            if not allowed:
                return TradingOperationSummary(
                    action="prepare-live-run",
                    mode="live-manual",
                    status="blocked",
                    message="Live-manual gates are not satisfied.",
                    run_id=None,
                    metadata={"checks": checks},
                )
            simulation_run_id = _create_simulation_run(
                session,
                mode="live-manual",
                as_of_date=effective_as_of_date,
            )

        with Session(engine) as session:
            pre_sync = _persist_broker_sync(
                session,
                simulation_run_id=simulation_run_id,
                mode="live-manual",
                adapter=status_adapter,
            )
            _, current_weights, current_holdings, pre_trade_positions = (
                _current_weights_from_broker_positions(
                    config,
                    account=pre_sync.account,
                    positions=pre_sync.positions,
                    score_map={},
                )
            )
            plan = _build_execution_plan(
                session,
                config,
                as_of_date=effective_as_of_date,
                model_version=model_version,
                current_weights=current_weights,
                allow_research_model=False,
            )
            start_nav, _, current_holdings, pre_trade_positions = (
                _current_weights_from_broker_positions(
                    config,
                    account=pre_sync.account,
                    positions=pre_sync.positions,
                    score_map=plan.score_map,
                )
            )
            target_weights, target_positions = _target_positions_from_plan(
                config,
                target_portfolio=plan.target_portfolio,
                start_nav=start_nav,
            )
            order_plans = _build_order_plans(
                config,
                start_nav=start_nav,
                current_holdings=current_holdings,
                target_weights=target_weights,
                bars=plan.bars,
                candidate_map=plan.candidate_map,
            )
            active_freeze = _active_freeze(session)
            previous_snapshot, _ = _load_latest_post_trade_snapshot(session)
            pretrade_risk = evaluate_pretrade_risk(
                config,
                mode="live-manual",
                active_freeze_reason=(None if active_freeze is None else active_freeze.reason),
                start_nav=start_nav,
                previous_nav=None if previous_snapshot is None else previous_snapshot.nav,
                high_water_mark=_high_water_mark(session),
                open_incident_count=_open_incident_count(
                    session,
                    symbols=sorted({row.symbol for row in plan.latest_rows}),
                    as_of_date=plan.decision_date,
                ),
                kill_switch_active=_kill_switch_active(session),
            )
            if not pretrade_risk.allowed:
                return TradingOperationSummary(
                    action="prepare-live-run",
                    mode="live-manual",
                    status="blocked",
                    message="Live-manual pretrade risk checks failed.",
                    run_id=simulation_run_id,
                    metadata={"checks": list(pretrade_risk.checks)},
                )

            run = session.get(SimulationRun, simulation_run_id)
            if run is None:
                raise RuntimeError("Live-manual run state was lost.")
            run.decision_date = plan.decision_date
            run.model_entry_id = plan.model_entry.id
            run.dataset_snapshot_id = plan.dataset_snapshot_id
            run.regime = plan.target_portfolio.regime
            run.start_nav = start_nav
            run.cash_start = pre_sync.account.cash_balance
            session.commit()

            _persist_snapshot(
                session,
                simulation_run_id=simulation_run_id,
                snapshot_type="pre-trade",
                trade_date=plan.decision_date,
                nav=start_nav,
                cash_balance=pre_sync.account.cash_balance,
                turnover_ratio=0.0,
                positions=pre_trade_positions,
            )
            _persist_snapshot(
                session,
                simulation_run_id=simulation_run_id,
                snapshot_type="target",
                trade_date=plan.decision_date,
                nav=start_nav,
                cash_balance=max(start_nav * plan.target_portfolio.cash_weight, 0.0),
                turnover_ratio=plan.target_portfolio.turnover_ratio,
                positions=target_positions,
            )
            approval_summaries: list[ApprovalSummary] = []
            order_summaries: list[OrderIntentSummary] = []
            for order_plan in order_plans:
                order = _persist_order_intent(
                    session,
                    simulation_run_id=simulation_run_id,
                    order_plan=order_plan,
                    status="pending-approval",
                    metadata={
                        "expected_spread_bps": order_plan.expected_spread_bps,
                        "score": order_plan.score,
                        "source": status_adapter.name,
                    },
                )
                broker_order, preview_warnings, preview_commission = _persist_broker_preview(
                    session,
                    config=config,
                    simulation_run_id=simulation_run_id,
                    mode="live-manual",
                    adapter=status_adapter,
                    order=order,
                    order_plan=order_plan,
                    approval_status="pending",
                )
                approval = OrderApproval(
                    simulation_run_id=simulation_run_id,
                    order_intent_id=order.id,
                    broker_order_id=broker_order.id,
                    symbol=order_plan.symbol,
                    mode="live-manual",
                    status="pending",
                    requested_by=config.broker.operator_name,
                    decided_by=None,
                    reason=None,
                    metadata_json=json.dumps(
                        {
                            "preview_warnings": list(preview_warnings),
                            "preview_commission": preview_commission,
                        },
                        sort_keys=True,
                        default=str,
                    ),
                )
                session.add(approval)
                session.commit()
                approval_summaries.append(_approval_summary(approval))
                order_summaries.append(
                    OrderIntentSummary(
                        order_id=order.id,
                        symbol=order_plan.symbol,
                        side=order_plan.side,
                        status="pending-approval",
                        order_type=order_plan.order_type,
                        requested_shares=order_plan.requested_shares,
                        requested_notional=order_plan.requested_notional,
                        reference_price=order_plan.reference_price,
                        limit_price=order_plan.limit_price,
                        expected_slippage_bps=order_plan.expected_slippage_bps,
                        metadata={
                            "broker_order_id": broker_order.id,
                            "preview_warnings": list(preview_warnings),
                            "preview_commission": preview_commission,
                        },
                    )
                )

            payload = {
                "run_id": simulation_run_id,
                "status": "pending-approval",
                "mode": "live-manual",
                "as_of_date": _serialize_date(effective_as_of_date),
                "decision_date": _serialize_date(plan.decision_date),
                "model_version": plan.model_entry.version,
                "dataset_snapshot_id": plan.dataset_snapshot_id,
                "regime": plan.target_portfolio.regime,
                "start_nav": start_nav,
                "cash_start": pre_sync.account.cash_balance,
                "broker_sync_snapshot_id": pre_sync.snapshot_id,
                "turnover_ratio": plan.target_portfolio.turnover_ratio,
                "risk_checks": list(pretrade_risk.checks),
                "orders": [asdict(order) for order in order_summaries],
                "approvals": [asdict(summary) for summary in approval_summaries],
                "freeze_triggered": False,
                "code_version": __version__,
            }
            _complete_run(
                session,
                config=config,
                simulation_run_id=simulation_run_id,
                status="pending-approval",
                mode="live-manual",
                decision_date=plan.decision_date,
                model_entry=plan.model_entry,
                dataset_snapshot_id=plan.dataset_snapshot_id,
                regime=plan.target_portfolio.regime,
                start_nav=start_nav,
                end_nav=start_nav,
                cash_start=pre_sync.account.cash_balance,
                cash_end=pre_sync.account.cash_balance,
                gross_exposure_target=plan.target_portfolio.target_gross_exposure,
                gross_exposure_actual=0.0,
                artifact_prefix="live-manual",
                payload=payload,
                keep_open=True,
            )
            record_audit_event(config, "live", f"live-manual run {simulation_run_id} prepared")
            return TradingOperationSummary(
                action="prepare-live-run",
                mode="live-manual",
                status="pending-approval",
                message="Live-manual order previews are ready for approval.",
                run_id=simulation_run_id,
                approvals=tuple(approval_summaries),
                metadata={"checks": checks},
            )
    finally:
        engine.dispose()


def approve_live_trading_run(
    config: AppConfig,
    *,
    run_id: int | None = None,
    approve_all: bool = False,
    approve_symbols: list[str] | None = None,
    reject_symbols: list[str] | None = None,
    adapter: BrokerAdapter | None = None,
) -> TradingOperationSummary:
    if not database_exists(config) or not database_is_reachable(config):
        raise RuntimeError("Database is not ready. Run init first.")
    if not approve_all and not approve_symbols and not reject_symbols:
        raise RuntimeError(
            "Select approvals with --approve-all, --approve-symbol, or --reject-symbol."
        )

    approved_symbol_set = {symbol.upper() for symbol in approve_symbols or []}
    rejected_symbol_set = {symbol.upper() for symbol in reject_symbols or []}
    status_adapter = adapter or build_broker_adapter(config, mode="live-manual")

    engine = create_db_engine(config)
    try:
        with Session(engine) as session:
            if run_id is None:
                run = session.scalar(
                    select(SimulationRun)
                    .where(
                        SimulationRun.mode == "live-manual",
                        SimulationRun.status.in_(("pending-approval", "partially-approved")),
                    )
                    .order_by(SimulationRun.created_at.desc(), SimulationRun.id.desc())
                )
            else:
                run = session.get(SimulationRun, run_id)
            if run is None or run.mode != "live-manual":
                raise RuntimeError("No pending live-manual run was found.")

            order_intents = {
                order.id: order for order in _load_order_intents_for_run(session, run.id)
            }
            broker_orders = {
                broker_order.id: broker_order
                for broker_order in _load_broker_orders_for_run(session, run.id)
            }
            approvals = _load_approvals_for_run(session, run.id)
            order_summaries: list[ApprovalSummary] = []
            fill_summaries: list[FillSummary] = []
            target_weights = {order.symbol: order.target_weight for order in order_intents.values()}

            for approval in approvals:
                if approval.status != "pending":
                    order_summaries.append(_approval_summary(approval))
                    continue
                decision = None
                if approve_all or approval.symbol.upper() in approved_symbol_set:
                    decision = "approved"
                elif approval.symbol.upper() in rejected_symbol_set:
                    decision = "rejected"
                else:
                    order_summaries.append(_approval_summary(approval))
                    continue

                approval.status = decision
                approval.decided_by = config.broker.operator_name
                approval.reason = (
                    "approved via CLI" if decision == "approved" else "rejected via CLI"
                )
                approval.decided_at = utc_now()
                session.commit()

                order = order_intents[approval.order_intent_id]
                broker_order = broker_orders[approval.broker_order_id or -1]
                if decision == "rejected":
                    order.status = "rejected"
                    order.completed_at = utc_now()
                    broker_order.approval_status = "rejected"
                    broker_order.broker_status = "not-submitted"
                    session.commit()
                    order_summaries.append(_approval_summary(approval))
                    continue

                plan = _OrderPlan(
                    symbol=order.symbol,
                    side=order.side,
                    requested_shares=order.requested_shares,
                    requested_notional=order.requested_notional,
                    target_weight=order.target_weight,
                    reference_price=order.reference_price,
                    order_type=order.order_type,
                    time_in_force=order.time_in_force,
                    limit_price=order.limit_price,
                    expected_spread_bps=json.loads(order.metadata_json).get(
                        "expected_spread_bps",
                        0.0,
                    ),
                    expected_slippage_bps=order.expected_slippage_bps,
                    score=json.loads(order.metadata_json).get("score"),
                )
                _, _, fill_summary = _submit_broker_order(
                    session,
                    config=config,
                    simulation_run_id=run.id,
                    order=order,
                    order_plan=plan,
                    broker_order=broker_order,
                    adapter=status_adapter,
                )
                fill_summaries.append(fill_summary)
                order_summaries.append(_approval_summary(approval))

            pending_remaining = sum(1 for approval in approvals if approval.status == "pending")
            post_sync = _persist_broker_sync(
                session,
                simulation_run_id=run.id,
                mode="live-manual",
                adapter=status_adapter,
            )
            summary_payload = json.loads(run.summary_json)
            plan_score_map = {
                order.symbol: json.loads(order.metadata_json).get("score")
                for order in order_intents.values()
            }
            post_positions = _post_positions_from_broker(
                config,
                positions=post_sync.positions,
                target_weights=target_weights,
                nav=post_sync.account.net_liquidation,
                score_map=plan_score_map,
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

            _persist_snapshot(
                session,
                simulation_run_id=run.id,
                snapshot_type="post-trade",
                trade_date=run.decision_date or run.as_of_date,
                nav=post_sync.account.net_liquidation,
                cash_balance=post_sync.account.cash_balance,
                turnover_ratio=float(summary_payload.get("turnover_ratio", 0.0)),
                positions=post_positions,
            )
            status = "completed" if pending_remaining == 0 else "partially-approved"
            message = (
                "Live-manual approvals completed."
                if pending_remaining == 0
                else f"{pending_remaining} approval(s) remain pending."
            )
            summary_payload["status"] = status
            summary_payload["cash_end"] = post_sync.account.cash_balance
            summary_payload["end_nav"] = post_sync.account.net_liquidation
            summary_payload["fills"] = [asdict(fill) for fill in fill_summaries]
            summary_payload["approvals"] = [asdict(summary) for summary in order_summaries]
            summary_payload["freeze_triggered"] = freeze_triggered
            _complete_run(
                session,
                config=config,
                simulation_run_id=run.id,
                status=status,
                mode="live-manual",
                decision_date=run.decision_date,
                model_entry=None
                if run.model_entry_id is None
                else session.get(ModelRegistryEntry, run.model_entry_id),
                dataset_snapshot_id=run.dataset_snapshot_id,
                regime=run.regime,
                start_nav=run.start_nav,
                end_nav=post_sync.account.net_liquidation,
                cash_start=run.cash_start,
                cash_end=post_sync.account.cash_balance,
                gross_exposure_target=run.gross_exposure_target,
                gross_exposure_actual=(
                    0.0
                    if post_sync.account.net_liquidation <= 0
                    else sum(abs(item.market_value) for item in post_positions)
                    / post_sync.account.net_liquidation
                ),
                artifact_prefix="live-manual",
                payload=summary_payload,
                keep_open=pending_remaining > 0,
            )
            record_audit_event(config, "live", f"live-manual approvals processed for run {run.id}")
            return TradingOperationSummary(
                action="approve-live-run",
                mode="live-manual",
                status=status,
                message=message,
                run_id=run.id,
                approvals=tuple(order_summaries),
                metadata={"fill_count": len(fill_summaries)},
            )
    finally:
        engine.dispose()


def run_live_trading_day(
    config: AppConfig,
    *,
    as_of_date: date | None = None,
    model_version: str | None = None,
    ack_disable_approvals: bool = False,
    adapter: BrokerAdapter | None = None,
) -> SimulationRunSummary:
    if not database_exists(config) or not database_is_reachable(config):
        raise RuntimeError("Database is not ready. Run init first.")

    effective_as_of_date = as_of_date or datetime.now(UTC).date()
    engine = create_db_engine(config)
    try:
        with Session(engine) as session:
            mode_state = _current_mode_state(session)
            if mode_state.current_mode != "live-autonomous":
                raise RuntimeError("System is not in live-autonomous mode.")

    finally:
        engine.dispose()

    status_adapter = adapter or build_broker_adapter(config, mode="live-autonomous")
    arm_summary = arm_live_mode(
        config,
        profile="autonomous",
        ack_disable_approvals=ack_disable_approvals,
        source="live",
        reason="live-autonomous run requested",
        adapter=status_adapter,
    )
    if not arm_summary.armed:
        raise RuntimeError("Live-autonomous mode is not armed under current gates.")

    return paper_trade_day(
        config,
        as_of_date=effective_as_of_date,
        model_version=model_version,
        adapter=status_adapter,
        _run_mode="live-autonomous",
        _allow_research_model=False,
        _ensure_mode=False,
    )


def paper_status(
    config: AppConfig,
    *,
    adapter: BrokerAdapter | None = None,
) -> dict[str, Any]:
    snapshot = simulation_status(config)
    broker_snapshot = broker_status(config, adapter=adapter)
    return {
        "mode_state": snapshot["mode_state"],
        "latest_run": (
            snapshot["latest_run"]
            if snapshot["latest_run"] and snapshot["latest_run"]["mode"] == "paper"
            else None
        ),
        "broker": broker_snapshot,
        "paper_safe_days": snapshot["paper_safe_days"],
        "active_freeze": snapshot["active_freeze"],
    }


def live_status(
    config: AppConfig,
    *,
    adapter: BrokerAdapter | None = None,
) -> dict[str, Any]:
    snapshot = simulation_status(config)
    broker_snapshot = broker_status(config, adapter=adapter)
    engine = create_db_engine(config)
    try:
        with Session(engine) as session:
            manual_checks_allowed, manual_checks = _live_gate_checks(
                session,
                config,
                profile="manual",
                ack_disable_approvals=False,
                adapter=adapter,
            )
            autonomous_allowed, autonomous_checks = _live_gate_checks(
                session,
                config,
                profile="autonomous",
                ack_disable_approvals=config.broker.require_live_autonomous_ack is False,
                adapter=adapter,
            )
    finally:
        engine.dispose()
    return {
        "mode_state": snapshot["mode_state"],
        "latest_run": snapshot["latest_run"],
        "latest_approvals": snapshot["latest_approvals"],
        "broker": broker_snapshot,
        "gates": {
            "manual": {"allowed": manual_checks_allowed, "checks": manual_checks},
            "autonomous": {"allowed": autonomous_allowed, "checks": autonomous_checks},
        },
        "safe_day_counts": {
            "paper": snapshot["paper_safe_days"],
            "paper_and_live": snapshot["paper_and_live_safe_days"],
        },
        "active_freeze": snapshot["active_freeze"],
    }


def simulation_status(config: AppConfig) -> dict[str, Any]:
    if not database_exists(config) or not database_is_reachable(config):
        return {
            "mode_state": None,
            "active_freeze": None,
            "latest_run": None,
            "latest_target_snapshot": None,
            "latest_orders": [],
            "latest_fills": [],
            "latest_broker_account_snapshot": None,
            "latest_broker_orders": [],
            "latest_approvals": [],
            "latest_mode_transition": None,
            "paper_safe_days": 0,
            "paper_and_live_safe_days": 0,
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
            latest_account_snapshot = session.scalar(
                select(BrokerAccountSnapshot).order_by(
                    BrokerAccountSnapshot.captured_at.desc(),
                    BrokerAccountSnapshot.id.desc(),
                )
            )
            latest_transition = _latest_transition(session)
            latest_orders: list[OrderIntent] = []
            latest_fills: list[ExecutionFill] = []
            latest_broker_orders: list[BrokerOrder] = []
            latest_approvals: list[OrderApproval] = []
            target_positions: list[dict[str, Any]] = []
            broker_positions: list[dict[str, Any]] = []

            if latest_run is not None:
                latest_orders = _load_order_intents_for_run(session, latest_run.id)
                latest_fills = list(
                    session.scalars(
                        select(ExecutionFill)
                        .where(ExecutionFill.simulation_run_id == latest_run.id)
                        .order_by(ExecutionFill.id.asc())
                    ).all()
                )
                latest_broker_orders = _load_broker_orders_for_run(session, latest_run.id)
                latest_approvals = _load_approvals_for_run(session, latest_run.id)

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

            if latest_account_snapshot is not None:
                broker_positions = [
                    {
                        "symbol": position.symbol,
                        "quantity": position.quantity,
                        "market_price": position.market_price,
                        "market_value": position.market_value,
                        "average_cost": position.average_cost,
                        "unrealized_pnl": position.unrealized_pnl,
                        "realized_pnl": position.realized_pnl,
                        "currency": position.currency,
                        "payload": json.loads(position.payload_json),
                    }
                    for position in session.scalars(
                        select(BrokerPositionSnapshot).where(
                            BrokerPositionSnapshot.snapshot_id == latest_account_snapshot.id
                        )
                    ).all()
                ]

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
                "latest_broker_account_snapshot": (
                    {
                        "id": latest_account_snapshot.id,
                        "simulation_run_id": latest_account_snapshot.simulation_run_id,
                        "broker_name": latest_account_snapshot.broker_name,
                        "mode": latest_account_snapshot.mode,
                        "account_id": latest_account_snapshot.account_id,
                        "net_liquidation": latest_account_snapshot.net_liquidation,
                        "cash_balance": latest_account_snapshot.cash_balance,
                        "buying_power": latest_account_snapshot.buying_power,
                        "available_funds": latest_account_snapshot.available_funds,
                        "cushion": latest_account_snapshot.cushion,
                        "payload": json.loads(latest_account_snapshot.payload_json),
                        "captured_at": _serialize_datetime(latest_account_snapshot.captured_at),
                        "positions": broker_positions,
                    }
                    if latest_account_snapshot is not None
                    else None
                ),
                "latest_broker_orders": [
                    {
                        "id": order.id,
                        "simulation_run_id": order.simulation_run_id,
                        "order_intent_id": order.order_intent_id,
                        "broker_name": order.broker_name,
                        "mode": order.mode,
                        "account_id": order.account_id,
                        "broker_order_id": order.broker_order_id,
                        "broker_status": order.broker_status,
                        "approval_status": order.approval_status,
                        "symbol": order.symbol,
                        "side": order.side,
                        "order_type": order.order_type,
                        "time_in_force": order.time_in_force,
                        "requested_shares": order.requested_shares,
                        "filled_shares": order.filled_shares,
                        "limit_price": order.limit_price,
                        "average_fill_price": order.average_fill_price,
                        "preview_commission": order.preview_commission,
                        "warnings": json.loads(order.warnings_json),
                        "payload": json.loads(order.payload_json),
                        "created_at": _serialize_datetime(order.created_at),
                        "updated_at": _serialize_datetime(order.updated_at),
                    }
                    for order in latest_broker_orders
                ],
                "latest_approvals": [
                    {
                        "approval_id": approval.id,
                        "order_intent_id": approval.order_intent_id,
                        "broker_order_id": approval.broker_order_id,
                        "symbol": approval.symbol,
                        "mode": approval.mode,
                        "status": approval.status,
                        "requested_by": approval.requested_by,
                        "decided_by": approval.decided_by,
                        "reason": approval.reason,
                        "metadata": json.loads(approval.metadata_json),
                        "created_at": _serialize_datetime(approval.created_at),
                        "decided_at": _serialize_datetime(approval.decided_at),
                    }
                    for approval in latest_approvals
                ],
                "latest_mode_transition": (
                    {
                        "id": latest_transition.id,
                        "previous_mode": latest_transition.previous_mode,
                        "new_mode": latest_transition.new_mode,
                        "live_profile": latest_transition.live_profile,
                        "source": latest_transition.source,
                        "reason": latest_transition.reason,
                        "metadata": json.loads(latest_transition.metadata_json),
                        "created_at": _serialize_datetime(latest_transition.created_at),
                    }
                    if latest_transition is not None
                    else None
                ),
                "paper_safe_days": _paper_safe_day_count(session),
                "paper_and_live_safe_days": _combined_safe_live_day_count(session),
            }
    finally:
        engine.dispose()
