from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta

from stocktradebot.config import AppConfig
from stocktradebot.data.models import (
    DailyBarRecord,
    FundamentalObservationRecord,
    FundamentalPayload,
    ProviderHistoryPayload,
)
from stocktradebot.data.service import backfill_market_data
from stocktradebot.storage import initialize_database


class FakePriceProvider:
    def __init__(self, name: str, *, bars_by_symbol: dict[str, tuple[DailyBarRecord, ...]]) -> None:
        self.name = name
        self.bars_by_symbol = bars_by_symbol

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


class FakeFundamentalsProvider:
    name = "sec_companyfacts"

    def __init__(
        self,
        observations_by_symbol: dict[str, tuple[FundamentalObservationRecord, ...]],
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


def price_series(
    provider: str,
    symbol: str,
    *,
    start_date: date,
    days: int,
    starting_close: float,
    daily_step: float,
    multiplier: float = 1.0,
) -> tuple[DailyBarRecord, ...]:
    rows: list[DailyBarRecord] = []
    for offset in range(days):
        trade_date = start_date + timedelta(days=offset)
        close = (starting_close + daily_step * offset) * multiplier
        rows.append(
            DailyBarRecord(
                provider=provider,
                symbol=symbol,
                trade_date=trade_date,
                open=close - 0.8,
                high=close + 1.2,
                low=close - 1.5,
                close=close,
                volume=1_000_000 + 1000 * offset,
            )
        )
    return tuple(rows)


def fundamentals(symbol: str) -> tuple[FundamentalObservationRecord, ...]:
    def observation(
        metric_name: str,
        value_2024: float,
        value_2025: float,
    ) -> tuple[FundamentalObservationRecord, FundamentalObservationRecord]:
        return (
            FundamentalObservationRecord(
                provider="sec_companyfacts",
                symbol=symbol,
                metric_name=metric_name,
                source_concept=metric_name,
                fiscal_period_end=date(2024, 12, 31),
                fiscal_period_type="FY",
                filed_at=datetime(2025, 2, 15, 23, 59, 59, tzinfo=UTC),
                available_at=datetime(2025, 2, 15, 23, 59, 59, tzinfo=UTC),
                unit="USD" if metric_name != "shares_outstanding" else "shares",
                value=value_2024,
                form_type="10-K",
                accession="00000000002024",
            ),
            FundamentalObservationRecord(
                provider="sec_companyfacts",
                symbol=symbol,
                metric_name=metric_name,
                source_concept=metric_name,
                fiscal_period_end=date(2025, 12, 31),
                fiscal_period_type="FY",
                filed_at=datetime(2026, 2, 15, 23, 59, 59, tzinfo=UTC),
                available_at=datetime(2026, 2, 15, 23, 59, 59, tzinfo=UTC),
                unit="USD" if metric_name != "shares_outstanding" else "shares",
                value=value_2025,
                form_type="10-K",
                accession="00000000002025",
            ),
        )

    rows: list[FundamentalObservationRecord] = []
    rows.extend(observation("revenue", 100.0, 180.0))
    rows.extend(observation("net_income", 10.0, 25.0))
    rows.extend(observation("operating_income", 12.0, 30.0))
    rows.extend(observation("total_assets", 200.0, 260.0))
    rows.extend(observation("total_liabilities", 80.0, 90.0))
    rows.extend(observation("shareholders_equity", 120.0, 170.0))
    rows.extend(observation("shares_outstanding", 10.0, 10.0))
    rows.extend(observation("operating_cash_flow", 20.0, 35.0))
    rows.extend(observation("capital_expenditures", 5.0, 8.0))
    return tuple(rows)


def seed_phase3_research_data(config: AppConfig) -> None:
    config.universe.stock_candidates = ["AAPL", "MSFT"]
    config.universe.curated_etfs = ["SPY"]
    config.universe.min_history_days = 20
    config.universe.liquidity_lookback_days = 20
    config.universe.max_stocks = 2
    config.model_training.min_feature_history_days = 40
    config.model_training.dataset_lookback_days = 140
    config.model_training.training_window_days = 20
    config.model_training.validation_window_days = 10
    config.model_training.walk_forward_step_days = 10
    config.model_training.min_training_rows = 20
    config.model_training.min_validation_folds = 2
    config.model_training.target_portfolio_size = 2
    config.save()
    initialize_database(config)

    start_date = date(2025, 11, 1)
    primary = FakePriceProvider(
        "stooq",
        bars_by_symbol={
            "AAPL": price_series(
                "stooq",
                "AAPL",
                start_date=start_date,
                days=180,
                starting_close=100.0,
                daily_step=0.6,
            ),
            "MSFT": price_series(
                "stooq",
                "MSFT",
                start_date=start_date,
                days=180,
                starting_close=200.0,
                daily_step=0.35,
            ),
            "SPY": price_series(
                "stooq",
                "SPY",
                start_date=start_date,
                days=180,
                starting_close=500.0,
                daily_step=0.25,
            ),
        },
    )
    secondary = FakePriceProvider(
        "alpha_vantage",
        bars_by_symbol={
            "AAPL": price_series(
                "alpha_vantage",
                "AAPL",
                start_date=start_date,
                days=180,
                starting_close=100.0,
                daily_step=0.6,
                multiplier=1.0005,
            ),
            "MSFT": price_series(
                "alpha_vantage",
                "MSFT",
                start_date=start_date,
                days=180,
                starting_close=200.0,
                daily_step=0.35,
                multiplier=1.0004,
            ),
            "SPY": price_series(
                "alpha_vantage",
                "SPY",
                start_date=start_date,
                days=180,
                starting_close=500.0,
                daily_step=0.25,
                multiplier=1.0002,
            ),
        },
    )
    fundamentals_provider = FakeFundamentalsProvider(
        {"AAPL": fundamentals("AAPL"), "MSFT": fundamentals("MSFT")}
    )

    backfill_market_data(
        config,
        as_of_date=date(2026, 2, 1),
        lookback_days=90,
        symbols=["AAPL", "MSFT", "SPY"],
        providers=[primary, secondary],
        fundamentals_provider=fundamentals_provider,
        primary_provider="stooq",
        secondary_provider="alpha_vantage",
    )
    backfill_market_data(
        config,
        as_of_date=date(2026, 4, 15),
        lookback_days=140,
        symbols=["AAPL", "MSFT", "SPY"],
        providers=[primary, secondary],
        fundamentals_provider=fundamentals_provider,
        primary_provider="stooq",
        secondary_provider="alpha_vantage",
    )
