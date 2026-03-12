from __future__ import annotations

from bisect import bisect_right
from calendar import monthrange
from collections import defaultdict
from collections.abc import Mapping, Sequence
from datetime import date
from statistics import median

from stocktradebot.config import AppConfig
from stocktradebot.data.models import (
    CanonicalBarRecord,
    UniverseSelectionRecord,
    UniverseSnapshotRecord,
)
from stocktradebot.data.seeds import (
    DEFAULT_CURATED_ETFS,
    DEFAULT_STOCK_CANDIDATES,
    DEFAULT_SYMBOL_SECTORS,
)

ELIGIBLE_VALIDATION_TIERS = {"verified", "provisional"}


def resolve_stock_candidates(config: AppConfig) -> tuple[str, ...]:
    return tuple(config.universe.stock_candidates or DEFAULT_STOCK_CANDIDATES)


def resolve_curated_etfs(config: AppConfig) -> tuple[str, ...]:
    return tuple(config.universe.curated_etfs or DEFAULT_CURATED_ETFS)


def resolve_symbol_sectors(config: AppConfig) -> dict[str, str]:
    merged = dict(DEFAULT_SYMBOL_SECTORS)
    merged.update(
        {symbol.upper(): sector for symbol, sector in config.portfolio.symbol_sectors.items()}
    )
    return merged


def _eligible_symbol_history(
    canonical_bars: Sequence[CanonicalBarRecord],
    *,
    as_of_date: date,
) -> dict[str, list[CanonicalBarRecord]]:
    by_symbol: dict[str, list[CanonicalBarRecord]] = defaultdict(list)
    for bar in canonical_bars:
        if bar.trade_date <= as_of_date and bar.validation_tier in ELIGIBLE_VALIDATION_TIERS:
            by_symbol[bar.symbol].append(bar)
    for symbol_bars in by_symbol.values():
        symbol_bars.sort(key=lambda bar: bar.trade_date)
    return by_symbol


def _build_snapshot_from_history(
    symbol_history: Mapping[str, Sequence[CanonicalBarRecord]],
    *,
    config: AppConfig,
    as_of_date: date,
) -> UniverseSnapshotRecord:
    selected_members: list[UniverseSelectionRecord] = []
    ranked_stocks: list[tuple[str, float, str]] = []
    for symbol in resolve_stock_candidates(config):
        symbol_bars = list(symbol_history.get(symbol, ()))
        if len(symbol_bars) < config.universe.min_history_days:
            continue
        lookback_bars = symbol_bars[-config.universe.liquidity_lookback_days :]
        latest_bar = lookback_bars[-1]
        if latest_bar.close < config.universe.min_price:
            continue
        liquidity_score = median(bar.close * bar.volume for bar in lookback_bars)
        ranked_stocks.append((symbol, float(liquidity_score), latest_bar.validation_tier))

    ranked_stocks.sort(key=lambda item: item[1], reverse=True)
    for rank, (symbol, liquidity_score, validation_tier) in enumerate(
        ranked_stocks[: config.universe.max_stocks],
        start=1,
    ):
        selected_members.append(
            UniverseSelectionRecord(
                symbol=symbol,
                asset_type="stock",
                rank=rank,
                liquidity_score=liquidity_score,
                inclusion_reason="liquidity_rank",
                latest_validation_tier=validation_tier,
            )
        )

    for symbol in resolve_curated_etfs(config):
        symbol_bars = list(symbol_history.get(symbol, ()))
        if not symbol_bars:
            continue
        selected_members.append(
            UniverseSelectionRecord(
                symbol=symbol,
                asset_type="etf",
                rank=None,
                liquidity_score=None,
                inclusion_reason="curated_etf",
                latest_validation_tier=symbol_bars[-1].validation_tier,
            )
        )

    selected_members.sort(
        key=lambda member: (member.asset_type != "stock", member.rank or 9999, member.symbol)
    )
    return UniverseSnapshotRecord(
        effective_date=as_of_date,
        selection_version="phase2-v1",
        summary={
            "max_stocks": config.universe.max_stocks,
            "min_price": config.universe.min_price,
            "min_history_days": config.universe.min_history_days,
            "liquidity_lookback_days": config.universe.liquidity_lookback_days,
            "monthly_refresh_day": config.universe.monthly_refresh_day,
        },
        members=tuple(selected_members),
    )


def build_universe_snapshot(
    canonical_bars: list[CanonicalBarRecord],
    *,
    config: AppConfig,
    as_of_date: date,
) -> UniverseSnapshotRecord:
    return _build_snapshot_from_history(
        _eligible_symbol_history(canonical_bars, as_of_date=as_of_date),
        config=config,
        as_of_date=as_of_date,
    )


def historical_universe_refresh_dates(
    canonical_bars: Sequence[CanonicalBarRecord],
    *,
    as_of_date: date,
    refresh_day: int,
) -> tuple[date, ...]:
    by_month: dict[tuple[int, int], list[date]] = defaultdict(list)
    for bar in canonical_bars:
        if bar.trade_date <= as_of_date and bar.validation_tier in ELIGIBLE_VALIDATION_TIERS:
            by_month[(bar.trade_date.year, bar.trade_date.month)].append(bar.trade_date)

    selected_dates: list[date] = []
    for (year, month), month_dates in sorted(by_month.items()):
        unique_dates = sorted(set(month_dates))
        month_target = date(year, month, min(max(refresh_day, 1), monthrange(year, month)[1]))
        chosen_date = next(
            (item for item in unique_dates if item >= month_target), unique_dates[-1]
        )
        selected_dates.append(chosen_date)

    return tuple(sorted(set(selected_dates)))


def build_historical_universe_snapshots(
    canonical_bars: Sequence[CanonicalBarRecord],
    *,
    config: AppConfig,
    as_of_date: date,
) -> tuple[UniverseSnapshotRecord, ...]:
    refresh_dates = list(
        historical_universe_refresh_dates(
            canonical_bars,
            as_of_date=as_of_date,
            refresh_day=config.universe.monthly_refresh_day,
        )
    )
    if refresh_dates and refresh_dates[-1] != as_of_date:
        refresh_dates.append(as_of_date)
    if not refresh_dates:
        return ()

    symbol_history = _eligible_symbol_history(canonical_bars, as_of_date=as_of_date)
    indexed_history = {
        symbol: (
            tuple(bar.trade_date for bar in bars),
            tuple(bars),
        )
        for symbol, bars in symbol_history.items()
    }

    snapshots: list[UniverseSnapshotRecord] = []
    for refresh_date in refresh_dates:
        snapshot_history: dict[str, Sequence[CanonicalBarRecord]] = {}
        for symbol, (trade_dates, bars) in indexed_history.items():
            end_index = bisect_right(trade_dates, refresh_date)
            if end_index == 0:
                continue
            snapshot_history[symbol] = bars[:end_index]
        snapshots.append(
            _build_snapshot_from_history(
                snapshot_history,
                config=config,
                as_of_date=refresh_date,
            )
        )

    return tuple(snapshots)
