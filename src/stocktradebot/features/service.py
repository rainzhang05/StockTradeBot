from __future__ import annotations

import json
import math
from collections import defaultdict
from collections.abc import Iterable, Sequence
from datetime import UTC, date, datetime, time

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from stocktradebot import __version__
from stocktradebot.config import AppConfig, normalize_quality_scope
from stocktradebot.data.models import (
    CanonicalBarRecord,
    CorporateActionRecord,
    DatasetSnapshotSummary,
    FeatureRowRecord,
    FundamentalObservationRecord,
    LabelRowRecord,
)
from stocktradebot.data.universe import resolve_symbol_sectors
from stocktradebot.storage import (
    CanonicalDailyBar,
    CorporateActionObservation,
    DatasetSnapshot,
    FeatureSetVersion,
    FeatureSnapshotRow,
    FundamentalObservation,
    LabelSnapshotRow,
    LabelVersion,
    UniverseSnapshot,
    UniverseSnapshotMember,
    create_db_engine,
    database_exists,
    database_is_reachable,
)

CANONICALIZATION_VERSION = "daily-bar-v1"
TRADING_DAY_DECISION_TIME = time(23, 59, 59, tzinfo=UTC)

FEATURE_SET_DEFINITION: dict[str, object] = {
    "version": "daily-core-v1",
    "features": {
        "momentum_5d": {"formula": "close_t / close_t-5 - 1", "null_policy": "requires 5 bars"},
        "momentum_20d": {
            "formula": "close_t / close_t-20 - 1",
            "null_policy": "requires 20 bars",
        },
        "momentum_60d": {
            "formula": "close_t / close_t-60 - 1",
            "null_policy": "requires 60 bars",
        },
        "mean_reversion_3d": {
            "formula": "-1 * (close_t / close_t-3 - 1)",
            "null_policy": "requires 3 bars",
        },
        "realized_vol_20d": {
            "formula": "stddev(daily_returns_20d)",
            "null_policy": "requires 20 bars",
        },
        "downside_vol_20d": {
            "formula": "stddev(min(return,0) over 20d)",
            "null_policy": "requires 20 bars",
        },
        "max_drawdown_20d": {
            "formula": "rolling wealth max drawdown over 20d",
            "null_policy": "requires 20 bars",
        },
        "dollar_volume_20d": {
            "formula": "mean(close * volume over 20d)",
            "null_policy": "requires 20 bars",
        },
        "volume_ratio_20d": {
            "formula": "volume_t / mean(volume over 20d)",
            "null_policy": "requires 20 bars",
        },
        "benchmark_relative_20d": {
            "formula": "symbol_return_20d - benchmark_return_20d",
            "null_policy": "null if benchmark unavailable",
        },
        "regime_return_20d": {
            "formula": "benchmark_return_20d",
            "null_policy": "null if benchmark unavailable",
        },
        "regime_vol_20d": {
            "formula": "benchmark_vol_20d",
            "null_policy": "null if benchmark unavailable",
        },
        "cross_sectional_strength_20d": {
            "formula": "zscore of 20d return within active universe",
            "null_policy": "requires at least two valid rows on the date",
        },
        "sector_relative_20d": {
            "formula": "symbol_return_20d - sector_median_return_20d",
            "null_policy": "null when sector metadata is unavailable",
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

LABEL_SET_DEFINITION: dict[str, object] = {
    "version": "forward-return-v1",
    "labels": {
        "ranking_label_5d": {
            "formula": "zscore of 5-trading-day forward total return within active universe",
            "null_policy": "requires future 5 verified bars",
        },
        "forward_return_5d": {
            "formula": "5-trading-day forward total return",
            "null_policy": "requires future 5 verified bars",
        },
        "forward_return_10d": {
            "formula": "10-trading-day forward total return",
            "null_policy": "requires future 10 verified bars",
        },
        "forward_max_drawdown_10d": {
            "formula": "minimum drawdown on the 10-trading-day forward wealth path",
            "null_policy": "requires future 10 verified bars",
        },
    },
}


def _mean(values: Sequence[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _stddev(values: Sequence[float]) -> float:
    if len(values) < 2:
        return 0.0
    average = _mean(values)
    variance = sum((value - average) ** 2 for value in values) / len(values)
    return math.sqrt(variance)


def _safe_ratio(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator is None or denominator == 0:
        return None
    return numerator / denominator


def _trade_datetime(trade_date: date) -> datetime:
    return datetime.combine(trade_date, TRADING_DAY_DECISION_TIME)


def _ensure_utc(timestamp: datetime) -> datetime:
    if timestamp.tzinfo is None:
        return timestamp.replace(tzinfo=UTC)
    return timestamp.astimezone(UTC)


def _bar_return(previous_close: float, current_close: float) -> float:
    if previous_close == 0:
        return 0.0
    return current_close / previous_close - 1.0


def _allowed_validation_tiers(quality_scope: str) -> tuple[str, ...]:
    if quality_scope == "promotion":
        return ("verified",)
    return ("verified", "provisional")


def _load_canonical_bars(
    session: Session,
    *,
    symbols: Sequence[str],
    start_date: date,
    end_date: date,
    quality_scope: str,
) -> list[CanonicalBarRecord]:
    allowed_tiers = _allowed_validation_tiers(quality_scope)
    rows = session.scalars(
        select(CanonicalDailyBar).where(
            CanonicalDailyBar.symbol.in_(tuple(symbols)),
            CanonicalDailyBar.trade_date >= start_date,
            CanonicalDailyBar.trade_date <= end_date,
            CanonicalDailyBar.validation_tier.in_(allowed_tiers),
        )
    ).all()
    return [
        CanonicalBarRecord(
            symbol=row.symbol,
            trade_date=row.trade_date,
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


def _load_corporate_actions(
    session: Session,
    *,
    symbols: Sequence[str],
    start_date: date,
    end_date: date,
) -> list[CorporateActionRecord]:
    rows = session.scalars(
        select(CorporateActionObservation).where(
            CorporateActionObservation.symbol.in_(tuple(symbols)),
            CorporateActionObservation.ex_date >= start_date,
            CorporateActionObservation.ex_date <= end_date,
        )
    ).all()

    grouped: dict[tuple[str, date, str], list[float]] = defaultdict(list)
    for row in rows:
        grouped[(row.symbol, row.ex_date, row.action_type)].append(row.value)

    normalized: list[CorporateActionRecord] = []
    for (symbol, ex_date, action_type), values in sorted(grouped.items()):
        representative_value = sorted(values)[len(values) // 2]
        normalized.append(
            CorporateActionRecord(
                provider="canonicalized",
                symbol=symbol,
                ex_date=ex_date,
                action_type=action_type,
                value=representative_value,
            )
        )
    return normalized


def _load_fundamentals(
    session: Session,
    *,
    symbols: Sequence[str],
) -> list[FundamentalObservationRecord]:
    rows = session.scalars(
        select(FundamentalObservation).where(FundamentalObservation.symbol.in_(tuple(symbols)))
    ).all()
    return [
        FundamentalObservationRecord(
            provider=row.provider,
            symbol=row.symbol,
            metric_name=row.metric_name,
            source_concept=row.source_concept,
            fiscal_period_end=row.fiscal_period_end,
            fiscal_period_type=row.fiscal_period_type,
            filed_at=_ensure_utc(row.filed_at),
            available_at=_ensure_utc(row.available_at),
            unit=row.unit,
            value=row.value,
            form_type=row.form_type,
            accession=row.accession,
        )
        for row in rows
    ]


def _load_universe_snapshots(
    session: Session,
    *,
    as_of_date: date,
) -> list[tuple[UniverseSnapshot, set[str]]]:
    snapshots = session.scalars(
        select(UniverseSnapshot)
        .where(UniverseSnapshot.effective_date <= as_of_date)
        .order_by(UniverseSnapshot.effective_date.asc(), UniverseSnapshot.id.asc())
    ).all()
    if not snapshots:
        return []

    snapshot_ids = [snapshot.id for snapshot in snapshots]
    members = session.scalars(
        select(UniverseSnapshotMember).where(UniverseSnapshotMember.snapshot_id.in_(snapshot_ids))
    ).all()
    member_map: dict[int, set[str]] = defaultdict(set)
    for member in members:
        member_map[member.snapshot_id].add(member.symbol)

    return [(snapshot, member_map[snapshot.id]) for snapshot in snapshots]


def _snapshot_for_trade_date(
    snapshots: Sequence[tuple[UniverseSnapshot, set[str]]],
    trade_date: date,
) -> tuple[int | None, set[str]]:
    active_snapshot_id: int | None = None
    active_symbols: set[str] = set()
    earliest_snapshot_id: int | None = None
    earliest_symbols: set[str] = set()
    for snapshot, members in snapshots:
        if earliest_snapshot_id is None:
            earliest_snapshot_id = snapshot.id
            earliest_symbols = members
        if snapshot.effective_date <= trade_date:
            active_snapshot_id = snapshot.id
            active_symbols = members
        else:
            break
    if active_snapshot_id is None:
        return earliest_snapshot_id, earliest_symbols
    return active_snapshot_id, active_symbols


def _dedupe_metric_history(
    observations: Iterable[FundamentalObservationRecord],
) -> list[FundamentalObservationRecord]:
    latest_per_period: dict[tuple[date, str], FundamentalObservationRecord] = {}
    for observation in observations:
        key = (observation.fiscal_period_end, observation.metric_name)
        current = latest_per_period.get(key)
        if current is None or observation.available_at > current.available_at:
            latest_per_period[key] = observation
    return sorted(
        latest_per_period.values(),
        key=lambda observation: (observation.fiscal_period_end, observation.available_at),
    )


def _ttm_value(
    observations: Sequence[FundamentalObservationRecord],
    *,
    as_of_datetime: datetime,
) -> float | None:
    eligible = _dedupe_metric_history(
        observation for observation in observations if observation.available_at <= as_of_datetime
    )
    quarterly = [observation for observation in eligible if observation.fiscal_period_type != "FY"]
    if len(quarterly) >= 4:
        return sum(observation.value for observation in quarterly[-4:])
    annual = [observation for observation in eligible if observation.fiscal_period_type == "FY"]
    if annual:
        return annual[-1].value
    return eligible[-1].value if eligible else None


def _latest_value(
    observations: Sequence[FundamentalObservationRecord],
    *,
    as_of_datetime: datetime,
) -> tuple[float | None, datetime | None]:
    eligible = [
        observation for observation in observations if observation.available_at <= as_of_datetime
    ]
    if not eligible:
        return None, None
    latest = max(eligible, key=lambda observation: observation.available_at)
    return latest.value, latest.available_at


def _prior_year_value(
    observations: Sequence[FundamentalObservationRecord],
    *,
    as_of_datetime: datetime,
) -> float | None:
    eligible = _dedupe_metric_history(
        observation for observation in observations if observation.available_at <= as_of_datetime
    )
    if len(eligible) < 2:
        return None
    latest = eligible[-1]
    candidates = [
        observation
        for observation in eligible[:-1]
        if (latest.fiscal_period_end - observation.fiscal_period_end).days >= 300
    ]
    return candidates[-1].value if candidates else None


def _fundamentals_as_of(
    observations: Sequence[FundamentalObservationRecord],
    *,
    trade_date: date | None = None,
    as_of_datetime: datetime | None = None,
    close: float,
) -> tuple[dict[str, float | None], datetime | None]:
    if as_of_datetime is None:
        if trade_date is None:
            raise ValueError("trade_date or as_of_datetime is required")
        as_of_datetime = _trade_datetime(trade_date)
    as_of_datetime = _ensure_utc(as_of_datetime)
    by_metric: dict[str, list[FundamentalObservationRecord]] = defaultdict(list)
    for observation in observations:
        by_metric[observation.metric_name].append(observation)

    revenue_ttm = _ttm_value(by_metric["revenue"], as_of_datetime=as_of_datetime)
    net_income_ttm = _ttm_value(by_metric["net_income"], as_of_datetime=as_of_datetime)
    operating_cash_flow_ttm = _ttm_value(
        by_metric["operating_cash_flow"],
        as_of_datetime=as_of_datetime,
    )
    capital_expenditures_ttm = _ttm_value(
        by_metric["capital_expenditures"],
        as_of_datetime=as_of_datetime,
    )
    total_assets, assets_available_at = _latest_value(
        by_metric["total_assets"],
        as_of_datetime=as_of_datetime,
    )
    total_liabilities, liabilities_available_at = _latest_value(
        by_metric["total_liabilities"],
        as_of_datetime=as_of_datetime,
    )
    shareholders_equity, equity_available_at = _latest_value(
        by_metric["shareholders_equity"],
        as_of_datetime=as_of_datetime,
    )
    shares_outstanding, shares_available_at = _latest_value(
        by_metric["shares_outstanding"],
        as_of_datetime=as_of_datetime,
    )
    prior_assets = _prior_year_value(by_metric["total_assets"], as_of_datetime=as_of_datetime)

    market_cap = close * shares_outstanding if shares_outstanding is not None else None
    free_cash_flow_ttm = None
    if operating_cash_flow_ttm is not None and capital_expenditures_ttm is not None:
        free_cash_flow_ttm = operating_cash_flow_ttm - abs(capital_expenditures_ttm)

    availability_candidates = [
        available_at
        for available_at in (
            assets_available_at,
            liabilities_available_at,
            equity_available_at,
            shares_available_at,
        )
        if available_at is not None
    ]
    fundamentals_available_at = max(availability_candidates) if availability_candidates else None

    return (
        {
            "earnings_yield": _safe_ratio(net_income_ttm, market_cap),
            "sales_yield": _safe_ratio(revenue_ttm, market_cap),
            "book_to_price": _safe_ratio(shareholders_equity, market_cap),
            "debt_to_equity": _safe_ratio(total_liabilities, shareholders_equity),
            "asset_growth": (
                None
                if total_assets is None or prior_assets is None or prior_assets == 0
                else (total_assets - prior_assets) / abs(prior_assets)
            ),
            "accrual_quality": (
                None
                if total_assets is None
                or total_assets == 0
                or net_income_ttm is None
                or operating_cash_flow_ttm is None
                else (net_income_ttm - operating_cash_flow_ttm) / total_assets
            ),
            "free_cash_flow_yield": _safe_ratio(free_cash_flow_ttm, market_cap),
        },
        fundamentals_available_at,
    )


def _forward_total_return(
    bars: Sequence[CanonicalBarRecord],
    actions_by_date: dict[date, list[CorporateActionRecord]],
    start_index: int,
    horizon: int,
) -> float | None:
    end_index = start_index + horizon
    if end_index >= len(bars):
        return None

    start_close = bars[start_index].close
    if start_close == 0:
        return None

    split_factor = 1.0
    dividend_value = 0.0
    end_date = bars[end_index].trade_date
    for action_date, actions in actions_by_date.items():
        if bars[start_index].trade_date < action_date <= end_date:
            for action in actions:
                if action.action_type == "split":
                    split_factor *= action.value
                elif action.action_type == "dividend":
                    dividend_value += action.value

    wealth_end = bars[end_index].close * split_factor + dividend_value
    return wealth_end / start_close - 1.0


def _forward_max_drawdown(
    bars: Sequence[CanonicalBarRecord],
    actions_by_date: dict[date, list[CorporateActionRecord]],
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
        total_return = _forward_total_return(
            bars,
            actions_by_date,
            start_index,
            current_index - start_index,
        )
        if total_return is None:
            return None
        wealth = 1.0 + total_return
        running_peak = max(running_peak, wealth)
        drawdown = wealth / running_peak - 1.0
        worst_drawdown = min(worst_drawdown, drawdown)
    return worst_drawdown


def _persist_feature_set(session: Session, version: str) -> None:
    if session.get(FeatureSetVersion, version) is None:
        session.add(
            FeatureSetVersion(
                version=version,
                definition_json=json.dumps(FEATURE_SET_DEFINITION, sort_keys=True),
            )
        )


def _persist_label_version(session: Session, version: str) -> None:
    if session.get(LabelVersion, version) is None:
        session.add(
            LabelVersion(
                version=version,
                definition_json=json.dumps(LABEL_SET_DEFINITION, sort_keys=True),
            )
        )


def _write_dataset_artifact(
    config: AppConfig,
    *,
    as_of_date: date,
    quality_scope: str,
    feature_set_version: str,
    label_version: str,
    rows: Sequence[dict[str, object]],
) -> str:
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    artifact_path = config.dataset_artifacts_dir / (
        "dataset-"
        f"{as_of_date.isoformat()}-{quality_scope}-{feature_set_version}-{label_version}-{timestamp}.jsonl"
    )
    payload = "\n".join(json.dumps(row, sort_keys=True, default=str) for row in rows)
    artifact_path.write_text(payload + ("\n" if payload else ""), encoding="utf-8")
    return str(artifact_path.relative_to(config.app_home))


def build_dataset_snapshot(
    config: AppConfig,
    *,
    as_of_date: date | None = None,
    quality_scope: str | None = None,
) -> DatasetSnapshotSummary:
    effective_as_of_date = as_of_date or datetime.now(UTC).date()
    effective_quality_scope = normalize_quality_scope(
        quality_scope or config.model_training.quality_scope
    )
    start_date = date.fromordinal(
        effective_as_of_date.toordinal() - config.model_training.dataset_lookback_days
    )

    engine = create_db_engine(config)
    try:
        with Session(engine) as session:
            snapshots = _load_universe_snapshots(session, as_of_date=effective_as_of_date)
            if not snapshots:
                raise RuntimeError("No universe snapshots are available. Run backfill first.")

            all_symbols = sorted({symbol for _, members in snapshots for symbol in members})
            benchmark_symbol = config.model_training.benchmark_symbol
            if benchmark_symbol not in all_symbols:
                all_symbols = sorted({*all_symbols, benchmark_symbol})

            bars = _load_canonical_bars(
                session,
                symbols=all_symbols,
                start_date=start_date,
                end_date=effective_as_of_date,
                quality_scope=effective_quality_scope,
            )
            if not bars:
                raise RuntimeError(
                    "No canonical daily bars are available for the requested quality scope."
                )

            actions = _load_corporate_actions(
                session,
                symbols=all_symbols,
                start_date=start_date,
                end_date=effective_as_of_date,
            )
            fundamental_observations = _load_fundamentals(session, symbols=all_symbols)

            bars_by_symbol: dict[str, list[CanonicalBarRecord]] = defaultdict(list)
            for bar in sorted(
                bars,
                key=lambda current_bar: (current_bar.symbol, current_bar.trade_date),
            ):
                bars_by_symbol[bar.symbol].append(bar)
            actions_by_symbol: dict[str, dict[date, list[CorporateActionRecord]]] = defaultdict(
                lambda: defaultdict(list)
            )
            for action in actions:
                actions_by_symbol[action.symbol][action.ex_date].append(action)
            fundamentals_by_symbol: dict[str, list[FundamentalObservationRecord]] = defaultdict(
                list
            )
            for observation in sorted(
                fundamental_observations,
                key=lambda current_observation: (
                    current_observation.symbol,
                    current_observation.metric_name,
                    current_observation.available_at,
                ),
            ):
                fundamentals_by_symbol[observation.symbol].append(observation)

            benchmark_bars = bars_by_symbol.get(benchmark_symbol, [])
            benchmark_returns = {
                bar.trade_date: (
                    None
                    if index < 20
                    else benchmark_bars[index].close / benchmark_bars[index - 20].close - 1.0
                )
                for index, bar in enumerate(benchmark_bars)
            }
            benchmark_vol: dict[date, float | None] = {}
            for index, bar in enumerate(benchmark_bars):
                if index < 20:
                    benchmark_vol[bar.trade_date] = None
                    continue
                window = benchmark_bars[index - 19 : index + 1]
                returns = [
                    _bar_return(window[current].close, window[current + 1].close)
                    for current in range(len(window) - 1)
                ]
                benchmark_vol[bar.trade_date] = _stddev(returns)

            feature_rows: list[FeatureRowRecord] = []
            label_rows: list[LabelRowRecord] = []
            symbol_sectors = resolve_symbol_sectors(config)

            for symbol, symbol_bars in sorted(bars_by_symbol.items()):
                if symbol == benchmark_symbol:
                    continue
                for index, bar in enumerate(symbol_bars):
                    if bar.trade_date > effective_as_of_date:
                        continue
                    if index < config.model_training.min_feature_history_days:
                        continue

                    universe_snapshot_id, active_symbols = _snapshot_for_trade_date(
                        snapshots,
                        bar.trade_date,
                    )
                    if symbol not in active_symbols:
                        continue

                    window_3 = symbol_bars[index - 3 : index + 1]
                    window_20 = symbol_bars[index - 20 : index + 1]
                    window_60 = symbol_bars[index - 60 : index + 1]
                    if len(window_60) < 61 or len(window_20) < 21 or len(window_3) < 4:
                        continue

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
                        trade_date=bar.trade_date,
                        close=bar.close,
                    )
                    benchmark_return_20d = benchmark_returns.get(bar.trade_date)
                    benchmark_vol_20d = benchmark_vol.get(bar.trade_date)
                    symbol_return_20d = bar.close / window_20[0].close - 1.0

                    feature_rows.append(
                        FeatureRowRecord(
                            feature_set_version=config.model_training.feature_set_version,
                            symbol=symbol,
                            trade_date=bar.trade_date,
                            universe_snapshot_id=universe_snapshot_id,
                            values={
                                "momentum_5d": bar.close / symbol_bars[index - 5].close - 1.0,
                                "momentum_20d": symbol_return_20d,
                                "momentum_60d": bar.close / window_60[0].close - 1.0,
                                "mean_reversion_3d": -(bar.close / window_3[0].close - 1.0),
                                "realized_vol_20d": _stddev(returns_20),
                                "downside_vol_20d": _stddev(negative_returns_20),
                                "max_drawdown_20d": worst_drawdown,
                                "dollar_volume_20d": _mean(
                                    [
                                        current_bar.close * current_bar.volume
                                        for current_bar in window_20
                                    ]
                                ),
                                "volume_ratio_20d": bar.volume
                                / _mean([current_bar.volume for current_bar in window_20]),
                                "benchmark_relative_20d": (
                                    None
                                    if benchmark_return_20d is None
                                    else symbol_return_20d - benchmark_return_20d
                                ),
                                "regime_return_20d": benchmark_return_20d,
                                "regime_vol_20d": benchmark_vol_20d,
                                "cross_sectional_strength_20d": None,
                                "sector_relative_20d": None,
                                **fundamental_ratios,
                            },
                            fundamentals_available_at=fundamentals_available_at,
                        )
                    )

                    forward_return_5d = _forward_total_return(
                        symbol_bars,
                        actions_by_symbol[symbol],
                        index,
                        5,
                    )
                    forward_return_10d = _forward_total_return(
                        symbol_bars,
                        actions_by_symbol[symbol],
                        index,
                        10,
                    )
                    forward_max_drawdown_10d = _forward_max_drawdown(
                        symbol_bars,
                        actions_by_symbol[symbol],
                        index,
                        10,
                    )
                    if (
                        forward_return_5d is None
                        or forward_return_10d is None
                        or forward_max_drawdown_10d is None
                    ):
                        continue
                    label_rows.append(
                        LabelRowRecord(
                            label_version=config.model_training.label_version,
                            symbol=symbol,
                            trade_date=bar.trade_date,
                            values={
                                "ranking_label_5d": None,
                                "forward_return_5d": forward_return_5d,
                                "forward_return_10d": forward_return_10d,
                                "forward_max_drawdown_10d": forward_max_drawdown_10d,
                            },
                        )
                    )

            labels_by_key = {(row.symbol, row.trade_date): row for row in label_rows}
            final_feature_rows = [
                row for row in feature_rows if (row.symbol, row.trade_date) in labels_by_key
            ]
            if not final_feature_rows:
                raise RuntimeError(
                    "No feature-ready rows could be built. "
                    "Verified bars or forward labels are missing."
                )

            rows_by_date: dict[date, list[FeatureRowRecord]] = defaultdict(list)
            for row in final_feature_rows:
                rows_by_date[row.trade_date].append(row)

            updated_feature_rows: list[FeatureRowRecord] = []
            updated_label_rows: list[LabelRowRecord] = []
            for _trade_date_value, rows_for_date in rows_by_date.items():
                strengths = [
                    row.values["momentum_20d"]
                    for row in rows_for_date
                    if row.values["momentum_20d"] is not None
                ]
                strength_values = [float(value) for value in strengths if value is not None]
                strength_mean = _mean(strength_values) if strength_values else 0.0
                strength_std = _stddev(strength_values) if strength_values else 0.0
                sector_returns: dict[str, list[float]] = defaultdict(list)
                for row in rows_for_date:
                    sector = symbol_sectors.get(row.symbol)
                    momentum_20d = row.values["momentum_20d"]
                    if sector is not None and momentum_20d is not None:
                        sector_returns[sector].append(float(momentum_20d))

                label_candidates: list[float] = []
                for row in rows_for_date:
                    forward_return = labels_by_key[(row.symbol, row.trade_date)].values[
                        "forward_return_5d"
                    ]
                    if forward_return is not None:
                        label_candidates.append(float(forward_return))
                label_mean = _mean(label_candidates)
                label_std = _stddev(label_candidates)

                for row in rows_for_date:
                    row_values = dict(row.values)
                    momentum_20d = row_values["momentum_20d"]
                    sector = symbol_sectors.get(row.symbol)
                    if momentum_20d is not None and strength_std > 0:
                        row_values["cross_sectional_strength_20d"] = (
                            float(momentum_20d) - strength_mean
                        ) / strength_std
                    else:
                        row_values["cross_sectional_strength_20d"] = (
                            0.0 if momentum_20d is not None else None
                        )
                    if sector is not None and momentum_20d is not None:
                        peer_returns = sector_returns.get(sector, [])
                        row_values["sector_relative_20d"] = (
                            float(momentum_20d) - _mean(peer_returns) if peer_returns else None
                        )
                    else:
                        row_values["sector_relative_20d"] = None
                    updated_feature_rows.append(
                        FeatureRowRecord(
                            feature_set_version=row.feature_set_version,
                            symbol=row.symbol,
                            trade_date=row.trade_date,
                            universe_snapshot_id=row.universe_snapshot_id,
                            values=row_values,
                            fundamentals_available_at=row.fundamentals_available_at,
                        )
                    )

                    current_label_row = labels_by_key[(row.symbol, row.trade_date)]
                    label_values = dict(current_label_row.values)
                    raw_5d_value = label_values["forward_return_5d"]
                    raw_5d = 0.0 if raw_5d_value is None else float(raw_5d_value)
                    label_values["ranking_label_5d"] = (
                        0.0 if label_std == 0 else (raw_5d - label_mean) / label_std
                    )
                    updated_label_rows.append(
                        LabelRowRecord(
                            label_version=current_label_row.label_version,
                            symbol=current_label_row.symbol,
                            trade_date=current_label_row.trade_date,
                            values=label_values,
                        )
                    )

            feature_row_lookup = {(row.symbol, row.trade_date): row for row in updated_feature_rows}
            label_row_lookup = {(row.symbol, row.trade_date): row for row in updated_label_rows}
            final_keys = sorted(feature_row_lookup.keys())
            artifact_rows: list[dict[str, object]] = []
            null_statistics: dict[str, int] = defaultdict(int)
            for symbol, trade_date_value in final_keys:
                feature_row = feature_row_lookup[(symbol, trade_date_value)]
                label_row = label_row_lookup[(symbol, trade_date_value)]
                for key, value in feature_row.values.items():
                    if value is None:
                        null_statistics[f"feature:{key}"] += 1
                for key, value in label_row.values.items():
                    if value is None:
                        null_statistics[f"label:{key}"] += 1
                artifact_rows.append(
                    {
                        "symbol": symbol,
                        "trade_date": trade_date_value.isoformat(),
                        "universe_snapshot_id": feature_row.universe_snapshot_id,
                        "feature_set_version": feature_row.feature_set_version,
                        "label_version": label_row.label_version,
                        "fundamentals_available_at": (
                            feature_row.fundamentals_available_at.isoformat()
                            if feature_row.fundamentals_available_at is not None
                            else None
                        ),
                        "features": feature_row.values,
                        "labels": label_row.values,
                    }
                )

            _persist_feature_set(session, config.model_training.feature_set_version)
            _persist_label_version(session, config.model_training.label_version)
            session.flush()

            for row in updated_feature_rows:
                session.merge(
                    FeatureSnapshotRow(
                        feature_set_version=row.feature_set_version,
                        symbol=row.symbol,
                        trade_date=row.trade_date,
                        universe_snapshot_id=row.universe_snapshot_id,
                        values_json=json.dumps(row.values, sort_keys=True),
                        fundamentals_available_at=row.fundamentals_available_at,
                    )
                )
            for label_snapshot_row in updated_label_rows:
                session.merge(
                    LabelSnapshotRow(
                        label_version=label_snapshot_row.label_version,
                        symbol=label_snapshot_row.symbol,
                        trade_date=label_snapshot_row.trade_date,
                        values_json=json.dumps(label_snapshot_row.values, sort_keys=True),
                    )
                )

            artifact_path = _write_dataset_artifact(
                config,
                as_of_date=effective_as_of_date,
                quality_scope=effective_quality_scope,
                feature_set_version=config.model_training.feature_set_version,
                label_version=config.model_training.label_version,
                rows=artifact_rows,
            )
            latest_snapshot_id, _ = _snapshot_for_trade_date(snapshots, effective_as_of_date)
            dataset_snapshot = DatasetSnapshot(
                as_of_date=effective_as_of_date,
                universe_snapshot_id=latest_snapshot_id,
                feature_set_version=config.model_training.feature_set_version,
                label_version=config.model_training.label_version,
                canonicalization_version=CANONICALIZATION_VERSION,
                quality_scope=effective_quality_scope,
                generation_code_version=__version__,
                row_count=len(artifact_rows),
                null_statistics_json=json.dumps(
                    dict(sorted(null_statistics.items())),
                    sort_keys=True,
                ),
                metadata_json=json.dumps(
                    {
                        "start_date": start_date.isoformat(),
                        "benchmark_symbol": benchmark_symbol,
                        "symbol_count": len({symbol for symbol, _ in final_keys}),
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
                feature_set_version=config.model_training.feature_set_version,
                label_version=config.model_training.label_version,
                quality_scope=effective_quality_scope,
                row_count=len(artifact_rows),
                null_statistics=dict(sorted(null_statistics.items())),
                artifact_path=artifact_path,
                metadata={
                    "start_date": start_date.isoformat(),
                    "benchmark_symbol": benchmark_symbol,
                    "symbol_count": len({symbol for symbol, _ in final_keys}),
                },
            )
    finally:
        engine.dispose()


def dataset_status(config: AppConfig) -> dict[str, object]:
    if not database_exists(config) or not database_is_reachable(config):
        return {
            "latest_dataset_snapshot": None,
            "feature_set_versions": [],
            "label_versions": [],
            "fundamentals_observation_count": 0,
        }

    engine = create_db_engine(config)
    try:
        with Session(engine) as session:
            latest_snapshot = session.scalar(
                select(DatasetSnapshot).order_by(
                    DatasetSnapshot.as_of_date.desc(),
                    DatasetSnapshot.id.desc(),
                )
            )
            feature_versions = session.scalars(
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
            {
                "id": latest_snapshot.id,
                "as_of_date": latest_snapshot.as_of_date.isoformat(),
                "universe_snapshot_id": latest_snapshot.universe_snapshot_id,
                "feature_set_version": latest_snapshot.feature_set_version,
                "label_version": latest_snapshot.label_version,
                "quality_scope": latest_snapshot.quality_scope,
                "row_count": latest_snapshot.row_count,
                "artifact_path": latest_snapshot.artifact_path,
                "null_statistics": json.loads(latest_snapshot.null_statistics_json),
                "metadata": json.loads(latest_snapshot.metadata_json),
                "created_at": latest_snapshot.created_at.isoformat(),
            }
            if latest_snapshot is not None
            else None
        ),
        "feature_set_versions": [
            {
                "version": version.version,
                "definition": json.loads(version.definition_json),
                "created_at": version.created_at.isoformat(),
            }
            for version in feature_versions
        ],
        "label_versions": [
            {
                "version": version.version,
                "definition": json.loads(version.definition_json),
                "created_at": version.created_at.isoformat(),
            }
            for version in label_versions
        ],
        "fundamentals_observation_count": fundamentals_count or 0,
    }
