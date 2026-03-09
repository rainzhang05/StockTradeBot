from __future__ import annotations

import json
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path

from sqlalchemy.orm import Session

from stocktradebot.config import initialize_config
from stocktradebot.data import backfill_intraday_data, backfill_market_data
from stocktradebot.data.models import (
    DailyBarRecord,
    FundamentalObservationRecord,
    FundamentalPayload,
    IntradayBarRecord,
    ProviderHistoryPayload,
)
from stocktradebot.features import build_intraday_dataset_snapshot
from stocktradebot.models import validate_intraday_research
from stocktradebot.storage import (
    UniverseSnapshot,
    UniverseSnapshotMember,
    create_db_engine,
    initialize_database,
)


class FakeDailyProvider:
    def __init__(self, name: str, *, bars_by_symbol: dict[str, tuple[DailyBarRecord, ...]]) -> None:
        self.name = name
        self.bars_by_symbol = bars_by_symbol

    def fetch_daily_history(
        self, symbol: str, start_date: date, end_date: date
    ) -> ProviderHistoryPayload:
        bars = tuple(
            bar
            for bar in self.bars_by_symbol.get(symbol, ())
            if start_date <= bar.trade_date <= end_date
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
        )


class FakeIntradayProvider:
    name = "alpha_vantage"

    def __init__(self, *, bars_by_symbol: dict[str, tuple[IntradayBarRecord, ...]]) -> None:
        self.bars_by_symbol = bars_by_symbol

    def fetch_intraday_history(
        self,
        symbol: str,
        *,
        frequency: str,
        start_at: datetime,
        end_at: datetime,
    ) -> ProviderHistoryPayload:
        bars = tuple(
            bar
            for bar in self.bars_by_symbol.get(symbol, ())
            if bar.frequency == frequency and start_at <= bar.bar_start <= end_at
        )
        return ProviderHistoryPayload(
            provider=self.name,
            symbol=symbol,
            domain=f"intraday_prices:{frequency}",
            requested_at=datetime(2026, 3, 9, 12, 0, tzinfo=UTC),
            request_url=f"https://example.test/{self.name}/{symbol}/{frequency}",
            payload_format="json",
            raw_payload=json.dumps(
                {"provider": self.name, "symbol": symbol, "frequency": frequency}
            ),
            intraday_bars=bars,
        )


class FakeFundamentalsProvider:
    name = "sec_companyfacts"

    def __init__(
        self, observations_by_symbol: dict[str, tuple[FundamentalObservationRecord, ...]]
    ) -> None:
        self.observations_by_symbol = observations_by_symbol

    def fetch_fundamentals(self, symbol: str) -> FundamentalPayload:
        return FundamentalPayload(
            provider=self.name,
            symbol=symbol,
            domain="fundamentals",
            requested_at=datetime(2026, 3, 9, 12, 0, tzinfo=UTC),
            request_url=f"https://example.test/sec/{symbol}",
            payload_format="json",
            raw_payload=json.dumps({"provider": self.name, "symbol": symbol}),
            observations=self.observations_by_symbol.get(symbol, ()),
        )


def _daily_series(
    symbol: str, *, start_date: date, days: int, start_close: float, daily_step: float
) -> tuple[DailyBarRecord, ...]:
    rows: list[DailyBarRecord] = []
    for offset in range(days):
        trade_date = start_date + timedelta(days=offset)
        close = start_close + daily_step * offset
        rows.append(
            DailyBarRecord(
                provider="stooq",
                symbol=symbol,
                trade_date=trade_date,
                open=close - 0.8,
                high=close + 1.0,
                low=close - 1.2,
                close=close,
                volume=1_000_000 + offset * 1000,
            )
        )
    return tuple(rows)


def _fundamentals(symbol: str) -> tuple[FundamentalObservationRecord, ...]:
    values = {
        "revenue": (100.0, 180.0),
        "net_income": (10.0, 22.0),
        "operating_income": (12.0, 26.0),
        "total_assets": (200.0, 260.0),
        "total_liabilities": (80.0, 90.0),
        "shareholders_equity": (120.0, 170.0),
        "shares_outstanding": (10.0, 10.0),
        "operating_cash_flow": (20.0, 35.0),
        "capital_expenditures": (5.0, 8.0),
    }
    rows: list[FundamentalObservationRecord] = []
    for metric_name, (value_2024, value_2025) in values.items():
        rows.append(
            FundamentalObservationRecord(
                provider="sec_companyfacts",
                symbol=symbol,
                metric_name=metric_name,
                source_concept=metric_name,
                fiscal_period_end=date(2024, 12, 31),
                fiscal_period_type="FY",
                filed_at=datetime(2025, 2, 15, 23, 59, tzinfo=UTC),
                available_at=datetime(2025, 2, 15, 23, 59, tzinfo=UTC),
                unit="USD",
                value=value_2024,
            )
        )
        rows.append(
            FundamentalObservationRecord(
                provider="sec_companyfacts",
                symbol=symbol,
                metric_name=metric_name,
                source_concept=metric_name,
                fiscal_period_end=date(2025, 12, 31),
                fiscal_period_type="FY",
                filed_at=datetime(2026, 2, 15, 23, 59, tzinfo=UTC),
                available_at=datetime(2026, 2, 15, 23, 59, tzinfo=UTC),
                unit="USD",
                value=value_2025,
            )
        )
    return tuple(rows)


def _intraday_series(
    symbol: str,
    *,
    start_date: date,
    sessions: int,
    base_close: float,
    session_step: float,
    bar_step: float,
) -> tuple[IntradayBarRecord, ...]:
    rows: list[IntradayBarRecord] = []
    session_start = time(9, 30)
    for day_offset in range(sessions):
        session_date = start_date + timedelta(days=day_offset)
        base = datetime.combine(session_date, session_start, tzinfo=UTC)
        for bar_index in range(26):
            close = base_close + session_step * day_offset + bar_step * bar_index
            rows.append(
                IntradayBarRecord(
                    provider="alpha_vantage",
                    symbol=symbol,
                    frequency="15min",
                    bar_start=base + timedelta(minutes=15 * bar_index),
                    open=close - 0.05,
                    high=close + 0.10,
                    low=close - 0.15,
                    close=close,
                    volume=10_000 + day_offset * 50 + bar_index,
                )
            )
    return tuple(rows)


def test_intraday_research_flow_builds_datasets_and_validation_reports(
    isolated_app_home: Path,
) -> None:
    config = initialize_config(isolated_app_home)
    config.universe.stock_candidates = ["AAPL", "MSFT"]
    config.universe.curated_etfs = ["SPY"]
    config.universe.min_history_days = 20
    config.universe.max_stocks = 2
    config.save()
    initialize_database(config)

    daily_primary = FakeDailyProvider(
        "stooq",
        bars_by_symbol={
            "AAPL": _daily_series(
                "AAPL", start_date=date(2025, 10, 1), days=160, start_close=100.0, daily_step=0.6
            ),
            "MSFT": _daily_series(
                "MSFT", start_date=date(2025, 10, 1), days=160, start_close=200.0, daily_step=0.2
            ),
            "SPY": _daily_series(
                "SPY", start_date=date(2025, 10, 1), days=160, start_close=500.0, daily_step=0.3
            ),
        },
    )
    daily_secondary = FakeDailyProvider(
        "alpha_vantage",
        bars_by_symbol={
            "AAPL": _daily_series(
                "AAPL", start_date=date(2025, 10, 1), days=160, start_close=100.05, daily_step=0.6
            ),
            "MSFT": _daily_series(
                "MSFT", start_date=date(2025, 10, 1), days=160, start_close=200.04, daily_step=0.2
            ),
            "SPY": _daily_series(
                "SPY", start_date=date(2025, 10, 1), days=160, start_close=500.03, daily_step=0.3
            ),
        },
    )
    fundamentals_provider = FakeFundamentalsProvider(
        {"AAPL": _fundamentals("AAPL"), "MSFT": _fundamentals("MSFT")}
    )
    backfill_market_data(
        config,
        as_of_date=date(2026, 3, 20),
        lookback_days=120,
        symbols=["AAPL", "MSFT", "SPY"],
        providers=[daily_primary, daily_secondary],
        fundamentals_provider=fundamentals_provider,
        primary_provider="stooq",
        secondary_provider="alpha_vantage",
    )
    engine = create_db_engine(config)
    try:
        with Session(engine) as session:
            snapshot = UniverseSnapshot(
                effective_date=date(2026, 3, 11),
                stock_count=2,
                etf_count=1,
                selection_version="intraday-test-v1",
                summary_json=json.dumps({"seeded": True}),
            )
            session.add(snapshot)
            session.flush()
            for symbol, asset_type in (("AAPL", "stock"), ("MSFT", "stock"), ("SPY", "etf")):
                session.add(
                    UniverseSnapshotMember(
                        snapshot_id=snapshot.id,
                        symbol=symbol,
                        asset_type=asset_type,
                        rank=1,
                        liquidity_score=1.0,
                        inclusion_reason="test-seed",
                        latest_validation_tier="verified",
                    )
                )
            session.commit()
    finally:
        engine.dispose()

    intraday_provider = FakeIntradayProvider(
        bars_by_symbol={
            "AAPL": _intraday_series(
                "AAPL",
                start_date=date(2026, 2, 1),
                sessions=40,
                base_close=100.0,
                session_step=0.8,
                bar_step=0.05,
            ),
            "MSFT": _intraday_series(
                "MSFT",
                start_date=date(2026, 2, 1),
                sessions=40,
                base_close=200.0,
                session_step=0.15,
                bar_step=0.02,
            ),
            "SPY": _intraday_series(
                "SPY",
                start_date=date(2026, 2, 1),
                sessions=40,
                base_close=500.0,
                session_step=0.3,
                bar_step=0.01,
            ),
        }
    )
    backfill_summary = backfill_intraday_data(
        config,
        frequency="15min",
        as_of_date=date(2026, 3, 11),
        lookback_days=40,
        symbols=["AAPL", "MSFT", "SPY"],
        providers=[intraday_provider],
        primary_provider="alpha_vantage",
    )
    assert backfill_summary.frequency == "15min"
    assert backfill_summary.quality_report_path is not None
    assert (config.app_home / backfill_summary.quality_report_path).exists()

    dataset = build_intraday_dataset_snapshot(
        config, frequency="15min", as_of_date=date(2026, 3, 11)
    )
    assert dataset.frequency == "15min"
    assert dataset.row_count > 0
    assert dataset.as_of_timestamp is not None
    assert (config.app_home / dataset.artifact_path).exists()

    validation = validate_intraday_research(config, frequency="15min", as_of_date=date(2026, 3, 11))
    assert validation.frequency == "15min"
    assert validation.fold_count >= 2
    assert (config.app_home / validation.artifact_path).exists()
    assert "average_excess_return" in validation.metrics
