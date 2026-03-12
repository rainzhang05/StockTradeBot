from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

from stocktradebot.config import initialize_config
from stocktradebot.data.models import (
    DailyBarRecord,
    FundamentalObservationRecord,
    FundamentalPayload,
    ProviderHistoryPayload,
)
from stocktradebot.data.service import backfill_market_data, market_data_status
from stocktradebot.features import build_dataset_snapshot, dataset_status
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


def _price_series(
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


def _fundamentals(symbol: str) -> tuple[FundamentalObservationRecord, ...]:
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


def test_build_dataset_snapshot_is_reproducible_and_availability_aware(
    isolated_app_home: Path,
) -> None:
    config = initialize_config(isolated_app_home)
    config.universe.stock_candidates = ["AAPL", "MSFT"]
    config.universe.curated_etfs = ["SPY"]
    config.universe.min_history_days = 20
    config.universe.liquidity_lookback_days = 20
    config.universe.max_stocks = 2
    config.model_training.min_feature_history_days = 60
    config.model_training.dataset_lookback_days = 100
    config.save()
    initialize_database(config)

    start_date = date(2025, 12, 1)
    primary = FakePriceProvider(
        "stooq",
        bars_by_symbol={
            "AAPL": _price_series(
                "stooq",
                "AAPL",
                start_date=start_date,
                days=120,
                starting_close=100.0,
                daily_step=0.6,
            ),
            "MSFT": _price_series(
                "stooq",
                "MSFT",
                start_date=start_date,
                days=120,
                starting_close=200.0,
                daily_step=0.4,
            ),
            "SPY": _price_series(
                "stooq",
                "SPY",
                start_date=start_date,
                days=120,
                starting_close=500.0,
                daily_step=0.3,
            ),
        },
    )
    secondary = FakePriceProvider(
        "alpha_vantage",
        bars_by_symbol={
            "AAPL": _price_series(
                "alpha_vantage",
                "AAPL",
                start_date=start_date,
                days=120,
                starting_close=100.0,
                daily_step=0.6,
                multiplier=1.0005,
            ),
            "MSFT": _price_series(
                "alpha_vantage",
                "MSFT",
                start_date=start_date,
                days=120,
                starting_close=200.0,
                daily_step=0.4,
                multiplier=1.0004,
            ),
            "SPY": _price_series(
                "alpha_vantage",
                "SPY",
                start_date=start_date,
                days=120,
                starting_close=500.0,
                daily_step=0.3,
                multiplier=1.0002,
            ),
        },
    )
    fundamentals_provider = FakeFundamentalsProvider(
        {"AAPL": _fundamentals("AAPL"), "MSFT": _fundamentals("MSFT")}
    )

    backfill_market_data(
        config,
        as_of_date=date(2026, 2, 1),
        lookback_days=80,
        symbols=["AAPL", "MSFT", "SPY"],
        providers=[primary, secondary],
        fundamentals_provider=fundamentals_provider,
        primary_provider="stooq",
        secondary_provider="alpha_vantage",
    )
    summary = backfill_market_data(
        config,
        as_of_date=date(2026, 3, 20),
        lookback_days=110,
        symbols=["AAPL", "MSFT", "SPY"],
        providers=[primary, secondary],
        fundamentals_provider=fundamentals_provider,
        primary_provider="stooq",
        secondary_provider="alpha_vantage",
    )

    assert summary.fundamentals_payload_count == 2
    assert summary.fundamentals_observation_count == 36

    dataset = build_dataset_snapshot(config, as_of_date=date(2026, 3, 20))

    assert dataset.row_count > 0
    assert dataset.feature_set_version == "daily-core-v1"
    assert dataset.label_version == "forward-return-v1"
    artifact_path = config.app_home / dataset.artifact_path
    assert artifact_path.exists()

    rows = [
        json.loads(line)
        for line in artifact_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(rows) == dataset.row_count
    first_row = rows[0]
    assert "features" in first_row
    assert "labels" in first_row
    assert "ranking_label_5d" in first_row["labels"]

    pre_filing = next(
        row for row in rows if row["symbol"] == "AAPL" and row["trade_date"] == "2026-02-14"
    )
    post_filing = next(
        row for row in rows if row["symbol"] == "AAPL" and row["trade_date"] == "2026-02-16"
    )
    assert pre_filing["features"]["earnings_yield"] < post_filing["features"]["earnings_yield"]

    status = dataset_status(config)
    assert status["latest_dataset_snapshot"]["id"] == dataset.snapshot_id
    assert status["feature_set_versions"][0]["version"] == "daily-core-v1"
    assert status["label_versions"][0]["version"] == "forward-return-v1"
    assert status["fundamentals_observation_count"] == 36
    assert any(
        row["symbol"] in {"AAPL", "MSFT"} and row["features"]["sector_relative_20d"] is not None
        for row in rows
    )


def test_provisional_only_daily_data_supports_research_scope_but_blocks_promotion_scope(
    isolated_app_home: Path,
) -> None:
    config = initialize_config(isolated_app_home)
    config.universe.stock_candidates = ["AAPL", "MSFT"]
    config.universe.curated_etfs = ["SPY"]
    config.universe.min_history_days = 20
    config.universe.liquidity_lookback_days = 20
    config.universe.max_stocks = 2
    config.model_training.min_feature_history_days = 60
    config.model_training.dataset_lookback_days = 100
    config.save()
    initialize_database(config)

    primary = FakePriceProvider(
        "stooq",
        bars_by_symbol={
            "AAPL": _price_series(
                "stooq",
                "AAPL",
                start_date=date(2025, 12, 1),
                days=120,
                starting_close=100.0,
                daily_step=0.6,
            ),
            "MSFT": _price_series(
                "stooq",
                "MSFT",
                start_date=date(2025, 12, 1),
                days=120,
                starting_close=200.0,
                daily_step=0.4,
            ),
            "SPY": _price_series(
                "stooq",
                "SPY",
                start_date=date(2025, 12, 1),
                days=120,
                starting_close=500.0,
                daily_step=0.3,
            ),
        },
    )

    backfill_market_data(
        config,
        as_of_date=date(2026, 3, 20),
        lookback_days=110,
        symbols=["AAPL", "MSFT", "SPY"],
        providers=[primary],
        primary_provider="stooq",
        secondary_provider=None,
    )

    status = market_data_status(config)
    assert status["daily_readiness"]["research_state"] == "research-capable"
    assert status["daily_readiness"]["promotion_state"] == "promotion-blocked"

    research_dataset = build_dataset_snapshot(
        config,
        as_of_date=date(2026, 3, 20),
        quality_scope="research",
    )
    assert research_dataset.quality_scope == "research"
    artifact_path = config.app_home / research_dataset.artifact_path
    rows = [
        json.loads(line)
        for line in artifact_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert rows
    assert any(
        row["symbol"] in {"AAPL", "MSFT"} and row["features"]["sector_relative_20d"] is not None
        for row in rows
    )

    with pytest.raises(RuntimeError, match="requested quality scope"):
        build_dataset_snapshot(
            config,
            as_of_date=date(2026, 3, 20),
            quality_scope="promotion",
        )
