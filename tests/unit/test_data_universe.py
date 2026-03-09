from __future__ import annotations

from datetime import date

from stocktradebot.config import AppConfig
from stocktradebot.data.models import CanonicalBarRecord
from stocktradebot.data.universe import build_universe_snapshot


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
