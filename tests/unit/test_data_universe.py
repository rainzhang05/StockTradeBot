from __future__ import annotations

from datetime import date

from stocktradebot.config import AppConfig
from stocktradebot.data.models import CanonicalBarRecord
from stocktradebot.data.universe import (
    build_historical_universe_snapshots,
    build_universe_snapshot,
    historical_universe_refresh_dates,
    resolve_stock_candidates,
    resolve_symbol_sectors,
)


def test_build_universe_snapshot_ranks_stocks_and_keeps_curated_etfs(tmp_path) -> None:
    config = AppConfig.default(tmp_path / "app-home")
    config.universe.stock_candidates = ["AAPL", "MSFT"]
    config.universe.curated_etfs = ["SPY"]
    config.universe.max_stocks = 1
    config.universe.min_history_days = 2
    config.universe.liquidity_lookback_days = 2

    canonical_bars = [
        CanonicalBarRecord(
            symbol="AAPL",
            trade_date=date(2026, 3, 5),
            open=100.0,
            high=101.0,
            low=99.0,
            close=100.0,
            volume=2_000_000,
            validation_tier="verified",
            primary_provider="stooq",
            confirming_provider="alpha_vantage",
            field_provenance={
                "open": "stooq",
                "high": "stooq",
                "low": "stooq",
                "close": "stooq",
                "volume": "stooq",
            },
        ),
        CanonicalBarRecord(
            symbol="AAPL",
            trade_date=date(2026, 3, 6),
            open=101.0,
            high=102.0,
            low=100.0,
            close=101.0,
            volume=2_100_000,
            validation_tier="verified",
            primary_provider="stooq",
            confirming_provider="alpha_vantage",
            field_provenance={
                "open": "stooq",
                "high": "stooq",
                "low": "stooq",
                "close": "stooq",
                "volume": "stooq",
            },
        ),
        CanonicalBarRecord(
            symbol="MSFT",
            trade_date=date(2026, 3, 5),
            open=200.0,
            high=202.0,
            low=198.0,
            close=200.0,
            volume=500_000,
            validation_tier="provisional",
            primary_provider="stooq",
            confirming_provider=None,
            field_provenance={
                "open": "stooq",
                "high": "stooq",
                "low": "stooq",
                "close": "stooq",
                "volume": "stooq",
            },
        ),
        CanonicalBarRecord(
            symbol="MSFT",
            trade_date=date(2026, 3, 6),
            open=201.0,
            high=203.0,
            low=199.0,
            close=201.0,
            volume=550_000,
            validation_tier="provisional",
            primary_provider="stooq",
            confirming_provider=None,
            field_provenance={
                "open": "stooq",
                "high": "stooq",
                "low": "stooq",
                "close": "stooq",
                "volume": "stooq",
            },
        ),
        CanonicalBarRecord(
            symbol="SPY",
            trade_date=date(2026, 3, 6),
            open=500.0,
            high=505.0,
            low=498.0,
            close=504.0,
            volume=10_000_000,
            validation_tier="verified",
            primary_provider="stooq",
            confirming_provider="alpha_vantage",
            field_provenance={
                "open": "stooq",
                "high": "stooq",
                "low": "stooq",
                "close": "stooq",
                "volume": "stooq",
            },
        ),
    ]

    snapshot = build_universe_snapshot(canonical_bars, config=config, as_of_date=date(2026, 3, 6))

    assert snapshot.stock_count == 1
    assert snapshot.etf_count == 1
    assert snapshot.members[0].symbol == "AAPL"
    assert snapshot.members[0].asset_type == "stock"
    assert snapshot.members[1].symbol == "SPY"
    assert snapshot.members[1].asset_type == "etf"


def test_historical_universe_refresh_dates_use_monthly_trade_dates(tmp_path) -> None:
    config = AppConfig.default(tmp_path / "app-home")
    config.universe.monthly_refresh_day = 1

    canonical_bars = [
        CanonicalBarRecord(
            symbol="AAPL",
            trade_date=date(2026, 1, 2),
            open=100.0,
            high=101.0,
            low=99.0,
            close=100.0,
            volume=2_000_000,
            validation_tier="verified",
            primary_provider="stooq",
            confirming_provider=None,
            field_provenance={},
        ),
        CanonicalBarRecord(
            symbol="AAPL",
            trade_date=date(2026, 2, 2),
            open=101.0,
            high=102.0,
            low=100.0,
            close=101.0,
            volume=2_100_000,
            validation_tier="verified",
            primary_provider="stooq",
            confirming_provider=None,
            field_provenance={},
        ),
        CanonicalBarRecord(
            symbol="AAPL",
            trade_date=date(2026, 3, 2),
            open=102.0,
            high=103.0,
            low=101.0,
            close=102.0,
            volume=2_200_000,
            validation_tier="provisional",
            primary_provider="stooq",
            confirming_provider=None,
            field_provenance={},
        ),
    ]

    refresh_dates = historical_universe_refresh_dates(
        canonical_bars,
        as_of_date=date(2026, 3, 2),
        refresh_day=config.universe.monthly_refresh_day,
    )

    assert refresh_dates == (
        date(2026, 1, 2),
        date(2026, 2, 2),
        date(2026, 3, 2),
    )


def test_build_historical_universe_snapshots_uses_prior_month_history(tmp_path) -> None:
    config = AppConfig.default(tmp_path / "app-home")
    config.universe.stock_candidates = ["AAPL", "MSFT"]
    config.universe.curated_etfs = ["SPY"]
    config.universe.max_stocks = 2
    config.universe.min_history_days = 1
    config.universe.liquidity_lookback_days = 1
    config.universe.monthly_refresh_day = 1

    canonical_bars = [
        CanonicalBarRecord(
            symbol="AAPL",
            trade_date=date(2026, 1, 2),
            open=100.0,
            high=101.0,
            low=99.0,
            close=100.0,
            volume=2_000_000,
            validation_tier="verified",
            primary_provider="stooq",
            confirming_provider=None,
            field_provenance={},
        ),
        CanonicalBarRecord(
            symbol="MSFT",
            trade_date=date(2026, 1, 2),
            open=200.0,
            high=202.0,
            low=198.0,
            close=200.0,
            volume=1_000_000,
            validation_tier="verified",
            primary_provider="stooq",
            confirming_provider=None,
            field_provenance={},
        ),
        CanonicalBarRecord(
            symbol="SPY",
            trade_date=date(2026, 1, 2),
            open=500.0,
            high=501.0,
            low=499.0,
            close=500.0,
            volume=10_000_000,
            validation_tier="verified",
            primary_provider="stooq",
            confirming_provider=None,
            field_provenance={},
        ),
        CanonicalBarRecord(
            symbol="AAPL",
            trade_date=date(2026, 2, 2),
            open=101.0,
            high=102.0,
            low=100.0,
            close=101.0,
            volume=2_100_000,
            validation_tier="verified",
            primary_provider="stooq",
            confirming_provider=None,
            field_provenance={},
        ),
        CanonicalBarRecord(
            symbol="MSFT",
            trade_date=date(2026, 2, 2),
            open=201.0,
            high=203.0,
            low=199.0,
            close=201.0,
            volume=1_100_000,
            validation_tier="verified",
            primary_provider="stooq",
            confirming_provider=None,
            field_provenance={},
        ),
        CanonicalBarRecord(
            symbol="SPY",
            trade_date=date(2026, 2, 2),
            open=501.0,
            high=503.0,
            low=500.0,
            close=502.0,
            volume=10_500_000,
            validation_tier="verified",
            primary_provider="stooq",
            confirming_provider=None,
            field_provenance={},
        ),
    ]

    snapshots = build_historical_universe_snapshots(
        canonical_bars,
        config=config,
        as_of_date=date(2026, 2, 2),
    )

    assert [snapshot.effective_date for snapshot in snapshots] == [
        date(2026, 1, 2),
        date(2026, 2, 2),
    ]
    assert [member.symbol for member in snapshots[0].members] == ["AAPL", "MSFT", "SPY"]
    assert [member.symbol for member in snapshots[1].members] == ["MSFT", "AAPL", "SPY"]


def test_build_historical_universe_snapshots_appends_current_as_of_date(tmp_path) -> None:
    config = AppConfig.default(tmp_path / "app-home")
    config.universe.stock_candidates = ["AAPL"]
    config.universe.curated_etfs = ["SPY"]
    config.universe.max_stocks = 1
    config.universe.min_history_days = 1
    config.universe.liquidity_lookback_days = 1
    config.universe.monthly_refresh_day = 1

    canonical_bars = [
        CanonicalBarRecord(
            symbol="AAPL",
            trade_date=date(2026, 3, 2),
            open=100.0,
            high=101.0,
            low=99.0,
            close=100.0,
            volume=2_000_000,
            validation_tier="verified",
            primary_provider="stooq",
            confirming_provider=None,
            field_provenance={},
        ),
        CanonicalBarRecord(
            symbol="AAPL",
            trade_date=date(2026, 3, 11),
            open=101.0,
            high=102.0,
            low=100.0,
            close=101.0,
            volume=2_100_000,
            validation_tier="provisional",
            primary_provider="stooq",
            confirming_provider=None,
            field_provenance={},
        ),
        CanonicalBarRecord(
            symbol="SPY",
            trade_date=date(2026, 3, 11),
            open=500.0,
            high=501.0,
            low=499.0,
            close=500.0,
            volume=10_000_000,
            validation_tier="provisional",
            primary_provider="stooq",
            confirming_provider=None,
            field_provenance={},
        ),
    ]

    snapshots = build_historical_universe_snapshots(
        canonical_bars,
        config=config,
        as_of_date=date(2026, 3, 11),
    )

    assert [snapshot.effective_date for snapshot in snapshots] == [
        date(2026, 3, 2),
        date(2026, 3, 11),
    ]


def test_default_bundled_universe_contains_300_stocks_with_sector_coverage(tmp_path) -> None:
    config = AppConfig.default(tmp_path / "app-home")

    candidates = resolve_stock_candidates(config)
    sectors = resolve_symbol_sectors(config)

    assert len(candidates) == 300
    assert len(set(candidates)) == 300
    assert all(symbol in sectors for symbol in candidates)
