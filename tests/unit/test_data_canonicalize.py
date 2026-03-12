from __future__ import annotations

from datetime import date

from stocktradebot.config import ValidationThresholds
from stocktradebot.data.canonicalize import canonicalize_daily_bars
from stocktradebot.data.models import DailyBarRecord


def test_canonicalize_marks_verified_when_secondary_agrees() -> None:
    observations = [
        DailyBarRecord(
            provider="stooq",
            symbol="AAPL",
            trade_date=date(2026, 3, 6),
            open=100.0,
            high=101.0,
            low=99.5,
            close=100.5,
            volume=1_000_000,
        ),
        DailyBarRecord(
            provider="alpha_vantage",
            symbol="AAPL",
            trade_date=date(2026, 3, 6),
            open=100.1,
            high=101.1,
            low=99.45,
            close=100.45,
            volume=1_020_000,
        ),
    ]

    canonical_bars, incidents = canonicalize_daily_bars(
        observations,
        primary_provider="stooq",
        secondary_provider="alpha_vantage",
        thresholds=ValidationThresholds(),
    )

    assert len(canonical_bars) == 1
    assert canonical_bars[0].validation_tier == "verified"
    assert canonical_bars[0].confirming_provider == "alpha_vantage"
    assert incidents == []


def test_canonicalize_marks_provisional_without_secondary() -> None:
    observations = [
        DailyBarRecord(
            provider="stooq",
            symbol="MSFT",
            trade_date=date(2026, 3, 6),
            open=250.0,
            high=255.0,
            low=249.5,
            close=254.0,
            volume=800_000,
        )
    ]

    canonical_bars, incidents = canonicalize_daily_bars(
        observations,
        primary_provider="stooq",
        secondary_provider=None,
        thresholds=ValidationThresholds(),
    )

    assert len(canonical_bars) == 1
    assert canonical_bars[0].validation_tier == "provisional"
    assert incidents == []


def test_canonicalize_quarantines_mismatched_bars() -> None:
    observations = [
        DailyBarRecord(
            provider="stooq",
            symbol="NVDA",
            trade_date=date(2026, 3, 6),
            open=90.0,
            high=95.0,
            low=89.5,
            close=94.0,
            volume=2_000_000,
        ),
        DailyBarRecord(
            provider="alpha_vantage",
            symbol="NVDA",
            trade_date=date(2026, 3, 6),
            open=90.0,
            high=95.0,
            low=89.5,
            close=99.0,
            volume=2_000_000,
        ),
    ]

    canonical_bars, incidents = canonicalize_daily_bars(
        observations,
        primary_provider="stooq",
        secondary_provider="alpha_vantage",
        thresholds=ValidationThresholds(),
    )

    assert len(canonical_bars) == 1
    assert canonical_bars[0].validation_tier == "quarantined"
    assert len(incidents) == 1
    assert incidents[0].affected_fields == ("close",)


def test_canonicalize_keeps_yahoo_only_agreement_provisional_when_primary_is_missing() -> None:
    observations = [
        DailyBarRecord(
            provider="alpha_vantage",
            symbol="AAPL",
            trade_date=date(2026, 3, 6),
            open=100.0,
            high=101.0,
            low=99.5,
            close=100.5,
            volume=1_000_000,
        ),
        DailyBarRecord(
            provider="yahoo",
            symbol="AAPL",
            trade_date=date(2026, 3, 6),
            open=100.02,
            high=101.02,
            low=99.48,
            close=100.48,
            volume=1_010_000,
        ),
    ]

    canonical_bars, incidents = canonicalize_daily_bars(
        observations,
        primary_provider="stooq",
        secondary_provider="alpha_vantage",
        thresholds=ValidationThresholds(),
    )

    assert len(canonical_bars) == 1
    assert canonical_bars[0].primary_provider == "alpha_vantage"
    assert canonical_bars[0].validation_tier == "provisional"
    assert incidents == []
