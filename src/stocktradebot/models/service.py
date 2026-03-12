from __future__ import annotations

import json
import math
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from stocktradebot import __version__
from stocktradebot.config import AppConfig
from stocktradebot.data.universe import resolve_curated_etfs
from stocktradebot.features import build_dataset_snapshot
from stocktradebot.models.baseline import (
    deserialize_model_artifact,
    fit_model_artifact,
    rank_rows,
    serialize_model_artifact,
)
from stocktradebot.models.types import (
    BacktestRunSummary,
    DatasetArtifactRow,
    LinearModelArtifact,
    TrainingRunSummary,
    ValidationRunSummary,
)
from stocktradebot.portfolio import PortfolioCandidate, construct_target_portfolio
from stocktradebot.storage import (
    BacktestRun,
    CanonicalDailyBar,
    DatasetSnapshot,
    ModelRegistryEntry,
    ModelTrainingRun,
    SimulationRun,
    ValidationRun,
    create_db_engine,
    database_exists,
    database_is_reachable,
)


@dataclass(slots=True)
class _BacktestComputation:
    summary: BacktestRunSummary
    report_payload: dict[str, Any]
    event_rows: list[dict[str, Any]]


@dataclass(slots=True)
class _ValidationComputation:
    summary: ValidationRunSummary
    report_payload: dict[str, Any]
    candidate_model: LinearModelArtifact
    candidate_backtest: _BacktestComputation


def _mean(values: Sequence[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _stddev(values: Sequence[float]) -> float:
    if len(values) < 2:
        return 0.0
    average = _mean(values)
    variance = sum((value - average) ** 2 for value in values) / len(values)
    return math.sqrt(variance)


def _serialize_date(value: date) -> str:
    return value.isoformat()


def _serialize_datetime(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC).isoformat()
    return value.astimezone(UTC).isoformat()


def _timestamp_token() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")


def _build_model_version(model_family: str) -> str:
    return f"{model_family}-{_timestamp_token()}"


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


def _load_dataset_snapshot_row(
    session: Session,
    snapshot_id: int,
) -> DatasetSnapshot:
    dataset_snapshot = session.get(DatasetSnapshot, snapshot_id)
    if dataset_snapshot is None:
        raise RuntimeError(f"Dataset snapshot {snapshot_id} was not found.")
    return dataset_snapshot


def _load_dataset_rows(
    config: AppConfig,
    dataset_snapshot: DatasetSnapshot,
) -> list[DatasetArtifactRow]:
    artifact_path = config.app_home / dataset_snapshot.artifact_path
    if not artifact_path.exists():
        raise RuntimeError(f"Dataset artifact is missing: {artifact_path}")

    rows: list[DatasetArtifactRow] = []
    for line in artifact_path.read_text(encoding="utf-8").splitlines():
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


def _allowed_validation_tiers(quality_scope: str) -> tuple[str, ...]:
    return ("verified",) if quality_scope == "promotion" else ("verified", "provisional")


def _execution_symbols(
    config: AppConfig,
    rows: Sequence[DatasetArtifactRow],
) -> list[str]:
    symbols = {row.symbol for row in rows}
    symbols.add(config.model_training.benchmark_symbol)
    if config.portfolio.defensive_etf_symbol:
        symbols.add(config.portfolio.defensive_etf_symbol)
    return sorted(symbols)


def _load_execution_bars(
    session: Session,
    *,
    symbols: Sequence[str],
    start_date: date,
    end_date: date,
    quality_scope: str,
) -> dict[str, dict[date, CanonicalDailyBar]]:
    allowed_tiers = _allowed_validation_tiers(quality_scope)
    rows = session.scalars(
        select(CanonicalDailyBar).where(
            CanonicalDailyBar.symbol.in_(tuple(symbols)),
            CanonicalDailyBar.trade_date >= start_date,
            CanonicalDailyBar.trade_date <= end_date,
            CanonicalDailyBar.validation_tier.in_(allowed_tiers),
        )
    ).all()
    bars_by_symbol: dict[str, dict[date, CanonicalDailyBar]] = defaultdict(dict)
    for row in rows:
        bars_by_symbol[row.symbol][row.trade_date] = row
    return bars_by_symbol


def _group_rows_by_date(
    rows: Iterable[DatasetArtifactRow],
) -> dict[date, list[DatasetArtifactRow]]:
    grouped: dict[date, list[DatasetArtifactRow]] = defaultdict(list)
    for row in rows:
        grouped[row.trade_date].append(row)
    return grouped


def _classify_regime(row: DatasetArtifactRow) -> str:
    regime_return = row.features.get("regime_return_20d")
    regime_vol = row.features.get("regime_vol_20d")
    if regime_return is None or regime_vol is None:
        return "unknown"
    if regime_return <= -0.03 or regime_vol >= 0.03:
        return "risk-off"
    if regime_return >= 0.03 and regime_vol <= 0.02:
        return "risk-on"
    return "neutral"


def _build_backtest_metrics(
    *,
    nav_history: Sequence[float],
    daily_returns: Sequence[float],
    benchmark_returns: Sequence[float],
    turnover_values: Sequence[float],
    position_counts: Sequence[int],
) -> dict[str, float]:
    total_return = 0.0 if not nav_history else nav_history[-1] / nav_history[0] - 1.0
    annualized_return = (
        (1.0 + total_return) ** (252 / len(daily_returns)) - 1.0 if daily_returns else 0.0
    )
    daily_volatility = _stddev(daily_returns)
    annualized_volatility = daily_volatility * math.sqrt(252)
    sharpe_ratio = (
        (_mean(daily_returns) / daily_volatility) * math.sqrt(252) if daily_volatility > 0 else 0.0
    )
    benchmark_total_return = 1.0
    for daily_return in benchmark_returns:
        benchmark_total_return *= 1.0 + daily_return
    benchmark_total_return -= 1.0

    running_peak = nav_history[0] if nav_history else 1.0
    max_drawdown = 0.0
    for nav in nav_history[1:]:
        running_peak = max(running_peak, nav)
        if running_peak > 0:
            max_drawdown = min(max_drawdown, nav / running_peak - 1.0)

    return {
        "total_return": total_return,
        "benchmark_return": benchmark_total_return,
        "excess_return": total_return - benchmark_total_return,
        "annualized_return": annualized_return,
        "annualized_volatility": annualized_volatility,
        "sharpe_ratio": sharpe_ratio,
        "max_drawdown": max_drawdown,
        "turnover_ratio": _mean(turnover_values),
        "average_positions": _mean([float(count) for count in position_counts]),
    }


def _nav_and_weights_for_date(
    *,
    cash_balance: float,
    holdings: dict[str, float],
    bars_by_symbol: dict[str, dict[date, CanonicalDailyBar]],
    trade_date: date,
) -> tuple[float, dict[str, float]]:
    nav = cash_balance
    values: dict[str, float] = {}
    for symbol, shares in holdings.items():
        bar = bars_by_symbol.get(symbol, {}).get(trade_date)
        if bar is None:
            continue
        values[symbol] = shares * bar.close
        nav += values[symbol]
    if nav <= 0:
        return nav, {}
    return nav, {symbol: value / nav for symbol, value in values.items()}


def _apply_order_plans(
    *,
    config: AppConfig,
    order_plans: Sequence[Any],
    holdings: dict[str, float],
    cash_balance: float,
    trade_date: date,
    bars_by_symbol: dict[str, dict[date, CanonicalDailyBar]],
) -> tuple[dict[str, float], float, int]:
    updated_holdings = dict(holdings)
    updated_cash = cash_balance
    filled_order_count = 0
    for order_plan in order_plans:
        bar = bars_by_symbol.get(order_plan.symbol, {}).get(trade_date)
        if bar is None:
            continue
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
        if filled_shares <= 1e-9:
            continue
        executed_price = bar.close * (
            1.0
            + (1.0 if order_plan.side == "buy" else -1.0)
            * order_plan.expected_slippage_bps
            / 10_000
        )
        commission = filled_shares * executed_price * config.execution.commission_bps / 10_000
        signed_delta = filled_shares if order_plan.side == "buy" else -filled_shares
        if order_plan.side == "buy":
            updated_cash -= filled_shares * executed_price + commission
        else:
            updated_cash += filled_shares * executed_price - commission
        updated_holdings[order_plan.symbol] = (
            updated_holdings.get(order_plan.symbol, 0.0) + signed_delta
        )
        if abs(updated_holdings[order_plan.symbol]) <= 1e-9:
            updated_holdings.pop(order_plan.symbol, None)
        filled_order_count += 1
    return updated_holdings, updated_cash, filled_order_count


def _run_event_backtest(
    *,
    config: AppConfig,
    dataset_snapshot_id: int,
    quality_scope: str,
    model: LinearModelArtifact,
    benchmark_symbol: str,
    rows: Sequence[DatasetArtifactRow],
    bars_by_symbol: dict[str, dict[date, CanonicalDailyBar]],
    run_id: int,
    mode: str,
) -> _BacktestComputation:
    from stocktradebot.execution.service import _build_order_plans

    rows_by_date = _group_rows_by_date(rows)
    evaluation_dates = sorted(rows_by_date)
    if not evaluation_dates:
        raise RuntimeError("No dataset rows are available for backtesting.")

    holdings: dict[str, float] = {}
    cash = config.model_training.initial_capital
    nav_history = [config.model_training.initial_capital]
    daily_returns: list[float] = []
    benchmark_returns: list[float] = []
    turnover_values: list[float] = []
    position_counts: list[int] = []
    event_rows: list[dict[str, Any]] = []
    regime_returns: dict[str, list[float]] = defaultdict(list)
    trade_count = 0
    curated_etfs = set(resolve_curated_etfs(config))
    rebalance_interval = config.model_training.rebalance_interval_days

    for index, trade_date in enumerate(evaluation_dates):
        visible_rows = [
            row
            for row in rows_by_date[trade_date]
            if trade_date in bars_by_symbol.get(row.symbol, {})
        ]
        start_nav, current_weights = _nav_and_weights_for_date(
            cash_balance=cash,
            holdings=holdings,
            bars_by_symbol=bars_by_symbol,
            trade_date=trade_date,
        )
        regime = "unknown"
        selected_symbols: list[str] = []
        turnover_ratio = 0.0
        rebalance_executed = False

        if visible_rows and index % rebalance_interval == 0:
            ranked_rows = sorted(
                rank_rows(model, visible_rows),
                key=lambda item: (item[1], item[0].symbol),
                reverse=True,
            )
            candidate_map = {
                row.symbol: PortfolioCandidate(
                    symbol=row.symbol,
                    score=score,
                    price=bars_by_symbol[row.symbol][trade_date].close,
                    asset_type="etf" if row.symbol in curated_etfs else "stock",
                    realized_vol_20d=row.features.get("realized_vol_20d"),
                    dollar_volume_20d=row.features.get("dollar_volume_20d"),
                    regime_return_20d=row.features.get("regime_return_20d"),
                    regime_vol_20d=row.features.get("regime_vol_20d"),
                )
                for row, score in ranked_rows
            }
            defensive_symbol = config.portfolio.defensive_etf_symbol
            if (
                defensive_symbol
                and defensive_symbol in bars_by_symbol
                and trade_date in bars_by_symbol[defensive_symbol]
            ):
                if defensive_symbol not in candidate_map:
                    reference_row = visible_rows[0]
                    defensive_bar = bars_by_symbol[defensive_symbol][trade_date]
                    candidate_map[defensive_symbol] = PortfolioCandidate(
                        symbol=defensive_symbol,
                        score=0.01,
                        price=defensive_bar.close,
                        asset_type="etf",
                        realized_vol_20d=None,
                        dollar_volume_20d=float(defensive_bar.close * defensive_bar.volume),
                        regime_return_20d=reference_row.features.get("regime_return_20d"),
                        regime_vol_20d=reference_row.features.get("regime_vol_20d"),
                    )

            target_portfolio = construct_target_portfolio(
                config,
                candidates=list(candidate_map.values()),
                current_weights=current_weights,
            )
            target_weights = {
                position.symbol: position.target_weight for position in target_portfolio.positions
            }
            rebalance_bars = {
                symbol: bar_by_date[trade_date]
                for symbol, bar_by_date in bars_by_symbol.items()
                if trade_date in bar_by_date and (symbol in target_weights or symbol in holdings)
            }
            order_plans = _build_order_plans(
                config,
                start_nav=start_nav,
                current_holdings=holdings,
                target_weights=target_weights,
                bars=rebalance_bars,
                candidate_map=candidate_map,
            )
            holdings, cash, filled_order_count = _apply_order_plans(
                config=config,
                order_plans=order_plans,
                holdings=holdings,
                cash_balance=cash,
                trade_date=trade_date,
                bars_by_symbol=bars_by_symbol,
            )
            trade_count += filled_order_count
            regime = target_portfolio.regime
            selected_symbols = [position.symbol for position in target_portfolio.positions]
            turnover_ratio = target_portfolio.turnover_ratio
            rebalance_executed = True

        close_nav, _end_weights = _nav_and_weights_for_date(
            cash_balance=cash,
            holdings=holdings,
            bars_by_symbol=bars_by_symbol,
            trade_date=trade_date,
        )
        prior_nav = nav_history[-1]
        daily_return = close_nav / prior_nav - 1.0 if prior_nav > 0 else 0.0
        nav_history.append(close_nav)
        daily_returns.append(daily_return)
        turnover_values.append(turnover_ratio)
        position_counts.append(len(holdings))

        benchmark_current = bars_by_symbol.get(benchmark_symbol, {}).get(trade_date)
        if index == 0:
            benchmark_daily_return = 0.0
        else:
            benchmark_previous = bars_by_symbol.get(benchmark_symbol, {}).get(
                evaluation_dates[index - 1]
            )
            benchmark_daily_return = (
                0.0
                if benchmark_previous is None
                or benchmark_current is None
                or benchmark_previous.close == 0
                else benchmark_current.close / benchmark_previous.close - 1.0
            )
        benchmark_returns.append(benchmark_daily_return)

        regime_returns[regime].append(daily_return)
        event_rows.append(
            {
                "trade_date": _serialize_date(trade_date),
                "selected_symbols": selected_symbols,
                "portfolio_nav": close_nav,
                "daily_return": daily_return,
                "benchmark_daily_return": benchmark_daily_return,
                "turnover_ratio": turnover_ratio,
                "position_count": len(holdings),
                "regime": regime,
                "rebalanced": rebalance_executed,
            }
        )

    metrics = _build_backtest_metrics(
        nav_history=nav_history,
        daily_returns=daily_returns,
        benchmark_returns=benchmark_returns,
        turnover_values=turnover_values,
        position_counts=position_counts,
    )
    start_date = evaluation_dates[0]
    end_date = evaluation_dates[-1]
    regime_summary = {
        regime: {
            "days": len(values),
            "average_daily_return": _mean(values),
            "compounded_return": (
                math.prod(1.0 + value for value in values) - 1.0 if values else 0.0
            ),
        }
        for regime, values in sorted(regime_returns.items())
    }
    artifact_payload = {
        "mode": mode,
        "run_id": run_id,
        "model_version": model.version,
        "dataset_snapshot_id": dataset_snapshot_id,
        "benchmark_symbol": benchmark_symbol,
        "start_date": _serialize_date(start_date),
        "end_date": _serialize_date(end_date),
        "quality_scope": quality_scope,
        "metrics": metrics,
        "trade_count": trade_count,
        "regime_summary": regime_summary,
        "event_rows": event_rows,
        "code_version": __version__,
    }
    return _BacktestComputation(
        summary=BacktestRunSummary(
            run_id=run_id,
            model_version=model.version,
            dataset_snapshot_id=dataset_snapshot_id,
            mode=mode,
            start_date=start_date,
            end_date=end_date,
            benchmark_symbol=benchmark_symbol,
            total_return=metrics["total_return"],
            benchmark_return=metrics["benchmark_return"],
            excess_return=metrics["excess_return"],
            annualized_return=metrics["annualized_return"],
            annualized_volatility=metrics["annualized_volatility"],
            sharpe_ratio=metrics["sharpe_ratio"],
            max_drawdown=metrics["max_drawdown"],
            turnover_ratio=metrics["turnover_ratio"],
            trade_count=trade_count,
            average_positions=metrics["average_positions"],
            artifact_path="",
            metadata={
                "regime_summary": regime_summary,
                "event_count": len(event_rows),
                "rebalance_interval_days": config.model_training.rebalance_interval_days,
            },
            quality_scope=quality_scope,
        ),
        report_payload=artifact_payload,
        event_rows=event_rows,
    )


def _build_walk_forward_folds(
    rows: Sequence[DatasetArtifactRow],
    config: AppConfig,
) -> list[tuple[list[DatasetArtifactRow], list[DatasetArtifactRow]]]:
    unique_dates = sorted({row.trade_date for row in rows})
    training_window = config.model_training.training_window_days
    validation_window = config.model_training.validation_window_days
    step = max(config.model_training.walk_forward_step_days, validation_window)
    folds: list[tuple[list[DatasetArtifactRow], list[DatasetArtifactRow]]] = []

    for test_start_index in range(training_window, len(unique_dates) - validation_window + 1, step):
        train_dates = set(unique_dates[test_start_index - training_window : test_start_index])
        test_dates = set(unique_dates[test_start_index : test_start_index + validation_window])
        train_rows = [row for row in rows if row.trade_date in train_dates]
        test_rows = [row for row in rows if row.trade_date in test_dates]
        if len(train_rows) < config.model_training.min_training_rows or not test_rows:
            continue
        folds.append((train_rows, test_rows))

    return folds


def _promotion_reasons(
    *,
    quality_scope: str,
    fold_count: int,
    latest_excess_return: float,
    paper_safe_days: int,
    config: AppConfig,
) -> tuple[bool, tuple[str, ...], str]:
    reasons: list[str] = []
    if quality_scope != "promotion":
        reasons.append("research_scope_models_are_not_promotable")
    if fold_count < config.model_training.min_validation_folds:
        reasons.append("insufficient_walk_forward_history")
    if latest_excess_return <= 0:
        reasons.append("latest_out_of_sample_segment_did_not_beat_benchmark")
    if paper_safe_days < config.broker.live_manual_min_paper_days:
        reasons.append("paper_trading_history_below_required_30_days")
    promotion_ready = not reasons
    return promotion_ready, tuple(reasons), "research-only" if reasons else "candidate"


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


def _model_artifact_payload(model: LinearModelArtifact) -> dict[str, Any]:
    return serialize_model_artifact(model)


def _model_from_payload(payload: dict[str, Any]) -> LinearModelArtifact:
    return deserialize_model_artifact(payload)


def _load_model_artifact(config: AppConfig, artifact_path: str) -> LinearModelArtifact:
    payload = json.loads((config.app_home / artifact_path).read_text(encoding="utf-8"))
    return _model_from_payload(payload)


def _compute_validation(
    *,
    config: AppConfig,
    dataset_snapshot: DatasetSnapshot,
    dataset_rows: Sequence[DatasetArtifactRow],
    bars_by_symbol: dict[str, dict[date, CanonicalDailyBar]],
    paper_safe_days: int,
) -> _ValidationComputation:
    folds = _build_walk_forward_folds(dataset_rows, config)
    if not folds:
        raise RuntimeError("No walk-forward folds are available. Expand the dataset history first.")

    fold_payloads: list[dict[str, Any]] = []
    fold_summaries: list[BacktestRunSummary] = []
    latest_model: LinearModelArtifact | None = None
    latest_backtest: _BacktestComputation | None = None

    for fold_index, (train_rows, test_rows) in enumerate(folds, start=1):
        test_dates = sorted({row.trade_date for row in test_rows})
        if not test_dates:
            continue
        model = fit_model_artifact(
            rows=train_rows,
            dataset_snapshot_id=dataset_snapshot.id,
            feature_set_version=dataset_snapshot.feature_set_version,
            label_version=dataset_snapshot.label_version,
            model_family=config.model_training.model_family,
            label_name=config.model_training.target_label_name,
            model_version=_build_model_version(config.model_training.model_family),
            holdout_start_date=test_dates[0],
            holdout_end_date=test_dates[-1],
        )
        backtest = _run_event_backtest(
            config=config,
            dataset_snapshot_id=dataset_snapshot.id,
            quality_scope=dataset_snapshot.quality_scope,
            model=model,
            benchmark_symbol=config.model_training.benchmark_symbol,
            rows=test_rows,
            bars_by_symbol=bars_by_symbol,
            run_id=fold_index,
            mode="walk-forward-fold",
        )
        fold_summaries.append(backtest.summary)
        fold_payloads.append(
            {
                "fold_index": fold_index,
                "training_start_date": _serialize_date(model.training_start_date),
                "training_end_date": _serialize_date(model.training_end_date),
                "holdout_start_date": _serialize_date(model.holdout_start_date),
                "holdout_end_date": _serialize_date(model.holdout_end_date),
                "training_row_count": model.training_row_count,
                "metrics": {
                    "total_return": backtest.summary.total_return,
                    "benchmark_return": backtest.summary.benchmark_return,
                    "excess_return": backtest.summary.excess_return,
                    "annualized_return": backtest.summary.annualized_return,
                    "annualized_volatility": backtest.summary.annualized_volatility,
                    "sharpe_ratio": backtest.summary.sharpe_ratio,
                    "max_drawdown": backtest.summary.max_drawdown,
                    "turnover_ratio": backtest.summary.turnover_ratio,
                },
            }
        )
        latest_model = model
        latest_backtest = backtest

    if latest_model is None or latest_backtest is None:
        raise RuntimeError("Walk-forward validation did not produce a candidate model.")

    average_total_return = _mean([summary.total_return for summary in fold_summaries])
    average_benchmark_return = _mean([summary.benchmark_return for summary in fold_summaries])
    average_excess_return = _mean([summary.excess_return for summary in fold_summaries])
    latest_fold_total_return = fold_summaries[-1].total_return
    latest_fold_excess_return = fold_summaries[-1].excess_return
    promotion_ready, promotion_reasons, _promotion_status = _promotion_reasons(
        quality_scope=dataset_snapshot.quality_scope,
        fold_count=len(fold_summaries),
        latest_excess_return=latest_fold_excess_return,
        paper_safe_days=paper_safe_days,
        config=config,
    )
    report_payload = {
        "dataset_snapshot_id": dataset_snapshot.id,
        "feature_set_version": dataset_snapshot.feature_set_version,
        "label_version": dataset_snapshot.label_version,
        "quality_scope": dataset_snapshot.quality_scope,
        "fold_count": len(fold_summaries),
        "average_total_return": average_total_return,
        "average_benchmark_return": average_benchmark_return,
        "average_excess_return": average_excess_return,
        "latest_fold_total_return": latest_fold_total_return,
        "latest_fold_excess_return": latest_fold_excess_return,
        "promotion_ready": promotion_ready,
        "promotion_reasons": list(promotion_reasons),
        "folds": fold_payloads,
        "code_version": __version__,
    }
    return _ValidationComputation(
        summary=ValidationRunSummary(
            run_id=0,
            dataset_snapshot_id=dataset_snapshot.id,
            fold_count=len(fold_summaries),
            artifact_path="",
            average_total_return=average_total_return,
            average_benchmark_return=average_benchmark_return,
            average_excess_return=average_excess_return,
            latest_fold_total_return=latest_fold_total_return,
            latest_fold_excess_return=latest_fold_excess_return,
            promotion_ready=promotion_ready,
            promotion_reasons=promotion_reasons,
            metadata={
                "folds": fold_payloads,
                "candidate_model_version": latest_model.version,
            },
            quality_scope=dataset_snapshot.quality_scope,
        ),
        report_payload=report_payload,
        candidate_model=latest_model,
        candidate_backtest=latest_backtest,
    )


def train_model(
    config: AppConfig,
    *,
    as_of_date: date | None = None,
    quality_scope: str | None = None,
) -> TrainingRunSummary:
    effective_as_of_date = as_of_date or datetime.now(UTC).date()
    engine = create_db_engine(config)
    try:
        with Session(engine) as session:
            training_run = ModelTrainingRun(
                status="running",
                as_of_date=effective_as_of_date,
                dataset_snapshot_id=None,
                model_family=config.model_training.model_family,
                model_version=None,
                summary_json="{}",
            )
            session.add(training_run)
            session.commit()
            training_run_id = training_run.id

        try:
            dataset_summary = build_dataset_snapshot(
                config,
                as_of_date=effective_as_of_date,
                quality_scope=quality_scope,
            )
            with Session(engine) as session:
                current_training_run = session.get(ModelTrainingRun, training_run_id)
                if current_training_run is None:
                    raise RuntimeError("Training run state was lost.")
                current_training_run.dataset_snapshot_id = dataset_summary.snapshot_id
                session.commit()
                dataset_snapshot = _load_dataset_snapshot_row(session, dataset_summary.snapshot_id)

            dataset_rows = _load_dataset_rows(config, dataset_snapshot)
            if len(dataset_rows) < config.model_training.min_training_rows:
                raise RuntimeError("Not enough dataset rows are available for model training.")

            with Session(engine) as session:
                bars_by_symbol = _load_execution_bars(
                    session,
                    symbols=_execution_symbols(config, dataset_rows),
                    start_date=min(row.trade_date for row in dataset_rows),
                    end_date=max(row.trade_date for row in dataset_rows) + timedelta(days=7),
                    quality_scope=dataset_snapshot.quality_scope,
                )
                paper_safe_days = _paper_safe_day_count(session)

            validation = _compute_validation(
                config=config,
                dataset_snapshot=dataset_snapshot,
                dataset_rows=dataset_rows,
                bars_by_symbol=bars_by_symbol,
                paper_safe_days=paper_safe_days,
            )
            validation_artifact_path = _write_json_artifact(
                config.report_artifacts_dir,
                prefix=f"validation-{dataset_snapshot.id}-{dataset_snapshot.quality_scope}",
                payload=validation.report_payload,
                config=config,
            )
            model_artifact_path = _write_json_artifact(
                config.model_artifacts_dir,
                prefix=f"model-{validation.candidate_model.version}-{dataset_snapshot.quality_scope}",
                payload=_model_artifact_payload(validation.candidate_model),
                config=config,
            )
            backtest_artifact_path = _write_json_artifact(
                config.report_artifacts_dir,
                prefix=(
                    f"backtest-{validation.candidate_model.version}-{dataset_snapshot.quality_scope}"
                ),
                payload=validation.candidate_backtest.report_payload,
                config=config,
            )

            promotion_ready, promotion_reasons, promotion_status = _promotion_reasons(
                quality_scope=dataset_snapshot.quality_scope,
                fold_count=validation.summary.fold_count,
                latest_excess_return=validation.summary.latest_fold_excess_return,
                paper_safe_days=paper_safe_days,
                config=config,
            )
            benchmark_metrics = {
                "benchmark_return": validation.candidate_backtest.summary.benchmark_return,
                "excess_return": validation.candidate_backtest.summary.excess_return,
            }
            metrics = {
                "total_return": validation.candidate_backtest.summary.total_return,
                "annualized_return": validation.candidate_backtest.summary.annualized_return,
                "annualized_volatility": (
                    validation.candidate_backtest.summary.annualized_volatility
                ),
                "sharpe_ratio": validation.candidate_backtest.summary.sharpe_ratio,
                "max_drawdown": validation.candidate_backtest.summary.max_drawdown,
                "turnover_ratio": validation.candidate_backtest.summary.turnover_ratio,
            }

            with Session(engine) as session:
                validation_run = ValidationRun(
                    status="completed",
                    dataset_snapshot_id=dataset_snapshot.id,
                    quality_scope=dataset_snapshot.quality_scope,
                    model_entry_id=None,
                    fold_count=validation.summary.fold_count,
                    artifact_path=validation_artifact_path,
                    summary_json=json.dumps(validation.report_payload, sort_keys=True),
                    error_message=None,
                    completed_at=datetime.now(UTC),
                )
                session.add(validation_run)
                session.commit()

                model_entry = ModelRegistryEntry(
                    version=validation.candidate_model.version,
                    family=validation.candidate_model.family,
                    dataset_snapshot_id=dataset_snapshot.id,
                    quality_scope=dataset_snapshot.quality_scope,
                    feature_set_version=dataset_snapshot.feature_set_version,
                    label_version=dataset_snapshot.label_version,
                    training_start_date=validation.candidate_model.training_start_date,
                    training_end_date=validation.candidate_model.training_end_date,
                    training_row_count=validation.candidate_model.training_row_count,
                    artifact_path=model_artifact_path,
                    metrics_json=json.dumps(metrics, sort_keys=True),
                    benchmark_metrics_json=json.dumps(benchmark_metrics, sort_keys=True),
                    promotion_status=promotion_status,
                    promotion_reasons_json=json.dumps(list(promotion_reasons), sort_keys=True),
                )
                session.add(model_entry)
                session.commit()

                backtest_run = BacktestRun(
                    status="completed",
                    mode="candidate-holdout",
                    dataset_snapshot_id=dataset_snapshot.id,
                    quality_scope=dataset_snapshot.quality_scope,
                    model_entry_id=model_entry.id,
                    benchmark_symbol=config.model_training.benchmark_symbol,
                    start_date=validation.candidate_backtest.summary.start_date,
                    end_date=validation.candidate_backtest.summary.end_date,
                    artifact_path=backtest_artifact_path,
                    summary_json=json.dumps(
                        validation.candidate_backtest.report_payload, sort_keys=True
                    ),
                    error_message=None,
                    completed_at=datetime.now(UTC),
                )
                session.add(backtest_run)
                session.commit()

                validation_run.model_entry_id = model_entry.id
                current_training_run = session.get(ModelTrainingRun, training_run_id)
                if current_training_run is None:
                    raise RuntimeError("Training run state was lost.")
                current_training_run.status = "completed"
                current_training_run.model_version = model_entry.version
                current_training_run.summary_json = json.dumps(
                    {
                        "dataset_snapshot_id": dataset_snapshot.id,
                        "validation_run_id": validation_run.id,
                        "backtest_run_id": backtest_run.id,
                        "metrics": metrics,
                        "benchmark_metrics": benchmark_metrics,
                        "quality_scope": dataset_snapshot.quality_scope,
                        "promotion_status": promotion_status,
                        "promotion_reasons": list(promotion_reasons),
                    },
                    sort_keys=True,
                )
                current_training_run.completed_at = datetime.now(UTC)
                session.commit()

                return TrainingRunSummary(
                    run_id=current_training_run.id,
                    dataset_snapshot_id=dataset_snapshot.id,
                    model_entry_id=model_entry.id,
                    model_version=model_entry.version,
                    validation_run_id=validation_run.id,
                    backtest_run_id=backtest_run.id,
                    feature_set_version=dataset_snapshot.feature_set_version,
                    label_version=dataset_snapshot.label_version,
                    artifact_path=model_artifact_path,
                    promotion_status=promotion_status,
                    promotion_reasons=promotion_reasons,
                    metrics=metrics,
                    benchmark_metrics=benchmark_metrics,
                    metadata={
                        "validation_artifact_path": validation_artifact_path,
                        "backtest_artifact_path": backtest_artifact_path,
                        "fold_count": validation.summary.fold_count,
                    },
                    quality_scope=dataset_snapshot.quality_scope,
                )
        except Exception as exc:
            with Session(engine) as session:
                current_training_run = session.get(ModelTrainingRun, training_run_id)
                if current_training_run is not None:
                    current_training_run.status = "failed"
                    current_training_run.error_message = str(exc)
                    current_training_run.completed_at = datetime.now(UTC)
                    session.commit()
            raise
    finally:
        engine.dispose()


def backtest_model(
    config: AppConfig,
    *,
    model_version: str | None = None,
) -> BacktestRunSummary:
    if not database_exists(config) or not database_is_reachable(config):
        raise RuntimeError("Database is not ready. Run init first.")

    engine = create_db_engine(config)
    try:
        with Session(engine) as session:
            model_query = select(ModelRegistryEntry).order_by(ModelRegistryEntry.created_at.desc())
            if model_version is not None:
                model_query = select(ModelRegistryEntry).where(
                    ModelRegistryEntry.version == model_version
                )
            model_entry = session.scalar(model_query)
            if model_entry is None:
                raise RuntimeError("No trained model is available. Run train first.")
            dataset_snapshot = _load_dataset_snapshot_row(session, model_entry.dataset_snapshot_id)
            dataset_snapshot_id = dataset_snapshot.id
            model_quality_scope = model_entry.quality_scope
            model = _load_model_artifact(config, model_entry.artifact_path)
            dataset_rows = [
                row
                for row in _load_dataset_rows(config, dataset_snapshot)
                if model.holdout_start_date <= row.trade_date <= model.holdout_end_date
            ]
            if not dataset_rows:
                raise RuntimeError("The model holdout window is missing from the dataset artifact.")
            backtest_run = BacktestRun(
                status="running",
                mode="static-model",
                dataset_snapshot_id=dataset_snapshot.id,
                quality_scope=model_quality_scope,
                model_entry_id=model_entry.id,
                benchmark_symbol=config.model_training.benchmark_symbol,
                start_date=model.holdout_start_date,
                end_date=model.holdout_end_date,
                artifact_path=None,
                summary_json="{}",
                error_message=None,
            )
            session.add(backtest_run)
            session.commit()
            backtest_run_id = backtest_run.id

        try:
            with Session(engine) as session:
                bars_by_symbol = _load_execution_bars(
                    session,
                    symbols=_execution_symbols(config, dataset_rows),
                    start_date=model.holdout_start_date,
                    end_date=model.holdout_end_date + timedelta(days=7),
                    quality_scope=model_quality_scope,
                )
            backtest = _run_event_backtest(
                config=config,
                dataset_snapshot_id=dataset_snapshot_id,
                quality_scope=model_quality_scope,
                model=model,
                benchmark_symbol=config.model_training.benchmark_symbol,
                rows=dataset_rows,
                bars_by_symbol=bars_by_symbol,
                run_id=backtest_run_id,
                mode="static-model",
            )
            artifact_path = _write_json_artifact(
                config.report_artifacts_dir,
                prefix=f"backtest-{model.version}-{model_quality_scope}",
                payload=backtest.report_payload,
                config=config,
            )
            with Session(engine) as session:
                current_backtest_run = session.get(BacktestRun, backtest_run_id)
                if current_backtest_run is None:
                    raise RuntimeError("Backtest run state was lost.")
                current_backtest_run.status = "completed"
                current_backtest_run.artifact_path = artifact_path
                current_backtest_run.summary_json = json.dumps(
                    backtest.report_payload, sort_keys=True
                )
                current_backtest_run.completed_at = datetime.now(UTC)
                session.commit()

            return BacktestRunSummary(
                **{
                    **asdict(backtest.summary),
                    "artifact_path": artifact_path,
                }
            )
        except Exception as exc:
            with Session(engine) as session:
                current_backtest_run = session.get(BacktestRun, backtest_run_id)
                if current_backtest_run is not None:
                    current_backtest_run.status = "failed"
                    current_backtest_run.error_message = str(exc)
                    current_backtest_run.completed_at = datetime.now(UTC)
                    session.commit()
            raise
    finally:
        engine.dispose()


def model_status(config: AppConfig) -> dict[str, object]:
    if not database_exists(config) or not database_is_reachable(config):
        return {
            "latest_training_run": None,
            "latest_model": None,
            "latest_validation_run": None,
            "latest_backtest_run": None,
        }

    engine = create_db_engine(config)
    try:
        with Session(engine) as session:
            latest_training_run = session.scalar(
                select(ModelTrainingRun).order_by(ModelTrainingRun.created_at.desc())
            )
            latest_model = session.scalar(
                select(ModelRegistryEntry).order_by(ModelRegistryEntry.created_at.desc())
            )
            latest_validation_run = session.scalar(
                select(ValidationRun).order_by(ValidationRun.created_at.desc())
            )
            latest_backtest_run = session.scalar(
                select(BacktestRun).order_by(BacktestRun.created_at.desc())
            )
    finally:
        engine.dispose()

    return {
        "latest_training_run": (
            {
                "id": latest_training_run.id,
                "status": latest_training_run.status,
                "as_of_date": _serialize_date(latest_training_run.as_of_date),
                "dataset_snapshot_id": latest_training_run.dataset_snapshot_id,
                "model_family": latest_training_run.model_family,
                "model_version": latest_training_run.model_version,
                "summary": json.loads(latest_training_run.summary_json),
                "error_message": latest_training_run.error_message,
                "created_at": _serialize_datetime(latest_training_run.created_at),
                "completed_at": _serialize_datetime(latest_training_run.completed_at),
            }
            if latest_training_run is not None
            else None
        ),
        "latest_model": (
            {
                "id": latest_model.id,
                "version": latest_model.version,
                "family": latest_model.family,
                "dataset_snapshot_id": latest_model.dataset_snapshot_id,
                "quality_scope": latest_model.quality_scope,
                "feature_set_version": latest_model.feature_set_version,
                "label_version": latest_model.label_version,
                "training_start_date": _serialize_date(latest_model.training_start_date),
                "training_end_date": _serialize_date(latest_model.training_end_date),
                "training_row_count": latest_model.training_row_count,
                "artifact_path": latest_model.artifact_path,
                "metrics": json.loads(latest_model.metrics_json),
                "benchmark_metrics": json.loads(latest_model.benchmark_metrics_json),
                "promotion_status": latest_model.promotion_status,
                "promotion_reasons": json.loads(latest_model.promotion_reasons_json),
                "created_at": _serialize_datetime(latest_model.created_at),
            }
            if latest_model is not None
            else None
        ),
        "latest_validation_run": (
            {
                "id": latest_validation_run.id,
                "status": latest_validation_run.status,
                "dataset_snapshot_id": latest_validation_run.dataset_snapshot_id,
                "quality_scope": latest_validation_run.quality_scope,
                "model_entry_id": latest_validation_run.model_entry_id,
                "fold_count": latest_validation_run.fold_count,
                "artifact_path": latest_validation_run.artifact_path,
                "summary": json.loads(latest_validation_run.summary_json),
                "error_message": latest_validation_run.error_message,
                "created_at": _serialize_datetime(latest_validation_run.created_at),
                "completed_at": _serialize_datetime(latest_validation_run.completed_at),
            }
            if latest_validation_run is not None
            else None
        ),
        "latest_backtest_run": (
            {
                "id": latest_backtest_run.id,
                "status": latest_backtest_run.status,
                "mode": latest_backtest_run.mode,
                "dataset_snapshot_id": latest_backtest_run.dataset_snapshot_id,
                "quality_scope": latest_backtest_run.quality_scope,
                "model_entry_id": latest_backtest_run.model_entry_id,
                "benchmark_symbol": latest_backtest_run.benchmark_symbol,
                "start_date": _serialize_date(latest_backtest_run.start_date),
                "end_date": _serialize_date(latest_backtest_run.end_date),
                "artifact_path": latest_backtest_run.artifact_path,
                "summary": json.loads(latest_backtest_run.summary_json),
                "error_message": latest_backtest_run.error_message,
                "created_at": _serialize_datetime(latest_backtest_run.created_at),
                "completed_at": _serialize_datetime(latest_backtest_run.completed_at),
            }
            if latest_backtest_run is not None
            else None
        ),
    }
