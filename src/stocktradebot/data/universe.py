from __future__ import annotations

from collections import defaultdict
from datetime import date
from statistics import median

from stocktradebot.config import AppConfig
from stocktradebot.data.models import (
    CanonicalBarRecord,
    UniverseSelectionRecord,
    UniverseSnapshotRecord,
)
from stocktradebot.data.seeds import DEFAULT_CURATED_ETFS, DEFAULT_STOCK_CANDIDATES


def resolve_stock_candidates(config: AppConfig) -> tuple[str, ...]:
    return tuple(config.universe.stock_candidates or DEFAULT_STOCK_CANDIDATES)


def resolve_curated_etfs(config: AppConfig) -> tuple[str, ...]:
    return tuple(config.universe.curated_etfs or DEFAULT_CURATED_ETFS)


def build_universe_snapshot(
    canonical_bars: list[CanonicalBarRecord],
    *,
    config: AppConfig,
    as_of_date: date,
) -> UniverseSnapshotRecord:
    by_symbol: dict[str, list[CanonicalBarRecord]] = defaultdict(list)
    for bar in canonical_bars:
        if bar.trade_date <= as_of_date and bar.validation_tier in {"verified", "provisional"}:
            by_symbol[bar.symbol].append(bar)

    selected_members: list[UniverseSelectionRecord] = []
    ranked_stocks: list[tuple[str, float, str]] = []
    for symbol in resolve_stock_candidates(config):
        symbol_bars = sorted(by_symbol.get(symbol, []), key=lambda bar: bar.trade_date)
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
        symbol_bars = sorted(by_symbol.get(symbol, []), key=lambda bar: bar.trade_date)
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
        },
        members=tuple(selected_members),
    )
