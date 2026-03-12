from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from stocktradebot.config import initialize_config
from stocktradebot.data.models import CorporateActionRecord, DailyBarRecord, ProviderHistoryPayload
from stocktradebot.data.service import backfill_market_data, market_data_status
from stocktradebot.storage import (
    CorporateActionObservation,
    UniverseSnapshot,
    create_db_engine,
    initialize_database,
)


class FakeProvider:
    def __init__(
        self,
        name: str,
        *,
        bars_by_symbol: dict[str, tuple[DailyBarRecord, ...]],
        actions_by_symbol: dict[str, tuple[CorporateActionRecord, ...]] | None = None,
    ) -> None:
        self.name = name
        self.bars_by_symbol = bars_by_symbol
        self.actions_by_symbol = actions_by_symbol or {}

    def fetch_daily_history(
        self,
        symbol: str,
        start_date: date,
        end_date: date,
    ) -> ProviderHistoryPayload:
        bars = tuple(
            bar
            for bar in self.bars_by_symbol.get(symbol, ())
            if start_date <= bar.trade_date <= end_date
        )
        actions = tuple(
            action
            for action in self.actions_by_symbol.get(symbol, ())
            if start_date <= action.ex_date <= end_date
        )
        return ProviderHistoryPayload(
            provider=self.name,
            symbol=symbol,
            domain="daily_prices",
            requested_at=datetime(2026, 3, 9, 12, 0, tzinfo=UTC),
            request_url=f"https://example.test/{self.name}/{symbol}",
            payload_format="json",
            raw_payload=json.dumps({"provider": self.name, "symbol": symbol}),
            bars=bars,
            corporate_actions=actions,
        )


def _bars(
    provider: str,
    symbol: str,
    first_close: float,
    second_close: float,
) -> tuple[DailyBarRecord, ...]:
    return (
        DailyBarRecord(
            provider=provider,
            symbol=symbol,
            trade_date=date(2026, 3, 5),
            open=first_close - 1.0,
            high=first_close + 1.5,
            low=first_close - 2.0,
            close=first_close,
            volume=1_000_000,
        ),
        DailyBarRecord(
            provider=provider,
            symbol=symbol,
            trade_date=date(2026, 3, 6),
            open=second_close - 1.0,
            high=second_close + 1.5,
            low=second_close - 2.0,
            close=second_close,
            volume=1_100_000,
        ),
    )


def test_backfill_market_data_persists_payloads_and_universe(isolated_app_home: Path) -> None:
    config = initialize_config(isolated_app_home)
    config.universe.stock_candidates = ["AAPL", "MSFT", "NVDA"]
    config.universe.curated_etfs = ["SPY"]
    config.universe.min_history_days = 2
    config.universe.liquidity_lookback_days = 2
    config.universe.max_stocks = 2
    config.save()
    initialize_database(config)

    providers = [
        FakeProvider(
            "stooq",
            bars_by_symbol={
                "AAPL": _bars("stooq", "AAPL", 100.0, 101.0),
                "MSFT": _bars("stooq", "MSFT", 200.0, 201.0),
                "NVDA": _bars("stooq", "NVDA", 300.0, 301.0),
                "SPY": _bars("stooq", "SPY", 500.0, 501.0),
            },
        ),
        FakeProvider(
            "alpha_vantage",
            bars_by_symbol={
                "AAPL": _bars("alpha_vantage", "AAPL", 100.1, 101.1),
                "NVDA": _bars("alpha_vantage", "NVDA", 310.0, 311.0),
                "SPY": _bars("alpha_vantage", "SPY", 500.05, 501.1),
            },
            actions_by_symbol={
                "AAPL": (
                    CorporateActionRecord(
                        provider="alpha_vantage",
                        symbol="AAPL",
                        ex_date=date(2026, 3, 6),
                        action_type="dividend",
                        value=0.24,
                    ),
                )
            },
        ),
    ]

    summary = backfill_market_data(
        config,
        as_of_date=date(2026, 3, 6),
        lookback_days=5,
        symbols=["AAPL", "MSFT", "NVDA", "SPY"],
        providers=providers,
        primary_provider="stooq",
        secondary_provider="alpha_vantage",
    )

    assert summary.canonical_count == 8
    assert summary.fundamentals_payload_count == 0
    assert summary.fundamentals_observation_count == 0
    assert summary.validation_counts == {"provisional": 2, "quarantined": 2, "verified": 4}
    assert summary.incident_count == 2
    assert summary.universe_snapshot_id is not None
    raw_payload_files = list(config.raw_payload_dir.glob("*/*/*/*"))
    assert len(raw_payload_files) == 8

    status = market_data_status(config)
    assert status["latest_run"]["status"] == "completed"
    assert status["fundamentals_observation_count"] == 0
    assert status["validation_counts"] == {"provisional": 2, "quarantined": 2, "verified": 4}
    assert status["daily_readiness"]["research_state"] == "research-capable"
    assert status["daily_readiness"]["promotion_state"] == "promotion-ready"
    assert status["latest_universe_snapshot"]["stock_count"] == 2
    assert status["latest_universe_snapshot"]["etf_count"] == 1
    assert len(status["recent_incidents"]) == 2

    engine = create_db_engine(config)
    try:
        with Session(engine) as session:
            actions = session.scalars(select(CorporateActionObservation)).all()
    finally:
        engine.dispose()

    assert len(actions) == 1
    assert actions[0].action_type == "dividend"


def test_backfill_market_data_full_history_persists_historical_snapshots(
    isolated_app_home: Path,
) -> None:
    config = initialize_config(isolated_app_home)
    config.universe.stock_candidates = ["AAPL", "MSFT"]
    config.universe.curated_etfs = ["SPY"]
    config.universe.min_history_days = 1
    config.universe.liquidity_lookback_days = 1
    config.universe.max_stocks = 2
    config.universe.monthly_refresh_day = 1
    config.save()
    initialize_database(config)

    provider = FakeProvider(
        "stooq",
        bars_by_symbol={
            "AAPL": (
                DailyBarRecord(
                    provider="stooq",
                    symbol="AAPL",
                    trade_date=date(2026, 1, 2),
                    open=99.0,
                    high=101.0,
                    low=98.0,
                    close=100.0,
                    volume=1_000_000,
                ),
                DailyBarRecord(
                    provider="stooq",
                    symbol="AAPL",
                    trade_date=date(2026, 2, 2),
                    open=100.0,
                    high=102.0,
                    low=99.0,
                    close=101.0,
                    volume=1_100_000,
                ),
                DailyBarRecord(
                    provider="stooq",
                    symbol="AAPL",
                    trade_date=date(2026, 3, 2),
                    open=101.0,
                    high=103.0,
                    low=100.0,
                    close=102.0,
                    volume=1_200_000,
                ),
            ),
            "MSFT": (
                DailyBarRecord(
                    provider="stooq",
                    symbol="MSFT",
                    trade_date=date(2026, 1, 2),
                    open=199.0,
                    high=201.0,
                    low=198.0,
                    close=200.0,
                    volume=900_000,
                ),
                DailyBarRecord(
                    provider="stooq",
                    symbol="MSFT",
                    trade_date=date(2026, 2, 2),
                    open=200.0,
                    high=202.0,
                    low=199.0,
                    close=201.0,
                    volume=950_000,
                ),
                DailyBarRecord(
                    provider="stooq",
                    symbol="MSFT",
                    trade_date=date(2026, 3, 2),
                    open=201.0,
                    high=203.0,
                    low=200.0,
                    close=202.0,
                    volume=975_000,
                ),
            ),
            "SPY": (
                DailyBarRecord(
                    provider="stooq",
                    symbol="SPY",
                    trade_date=date(2026, 1, 2),
                    open=499.0,
                    high=501.0,
                    low=498.0,
                    close=500.0,
                    volume=5_000_000,
                ),
                DailyBarRecord(
                    provider="stooq",
                    symbol="SPY",
                    trade_date=date(2026, 2, 2),
                    open=500.0,
                    high=503.0,
                    low=499.0,
                    close=502.0,
                    volume=5_100_000,
                ),
                DailyBarRecord(
                    provider="stooq",
                    symbol="SPY",
                    trade_date=date(2026, 3, 2),
                    open=502.0,
                    high=504.0,
                    low=501.0,
                    close=503.0,
                    volume=5_200_000,
                ),
            ),
        },
    )

    summary = backfill_market_data(
        config,
        as_of_date=date(2026, 3, 2),
        lookback_days=30,
        full_history=True,
        historical_snapshots=True,
        symbols=["AAPL", "MSFT", "SPY"],
        providers=[provider],
        primary_provider="stooq",
    )

    assert summary.full_history is True
    assert summary.historical_snapshots is True
    assert summary.historical_snapshot_count == 3

    engine = create_db_engine(config)
    try:
        with Session(engine) as session:
            snapshots = session.scalars(
                select(UniverseSnapshot).order_by(UniverseSnapshot.effective_date.asc())
            ).all()
    finally:
        engine.dispose()

    assert [snapshot.effective_date for snapshot in snapshots] == [
        date(2026, 1, 2),
        date(2026, 2, 2),
        date(2026, 3, 2),
    ]
