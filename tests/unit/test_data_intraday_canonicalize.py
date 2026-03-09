from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from stocktradebot.config import initialize_config
from stocktradebot.data.canonicalize_intraday import canonicalize_intraday_bars
from stocktradebot.data.models import IntradayBarRecord


def _session_bars(symbol: str, *, session_date: date, count: int = 26) -> list[IntradayBarRecord]:
    base = datetime(session_date.year, session_date.month, session_date.day, 9, 30, tzinfo=UTC)
    rows: list[IntradayBarRecord] = []
    for index in range(count):
        close = 100.0 + index * 0.2
        rows.append(
            IntradayBarRecord(
                provider="alpha_vantage",
                symbol=symbol,
                frequency="15min",
                bar_start=base + timedelta(minutes=15 * index),
                open=close - 0.1,
                high=close + 0.2,
                low=close - 0.3,
                close=close,
                volume=1000 + index,
            )
        )
    return rows


def test_intraday_canonicalization_promotes_complete_sessions_to_verified(
    isolated_app_home,
) -> None:
    config = initialize_config(isolated_app_home)
    bars = _session_bars("AAPL", session_date=date(2026, 3, 9))

    canonical_bars, incidents = canonicalize_intraday_bars(
        bars,
        config=config,
        frequency="15min",
        primary_provider="alpha_vantage",
        secondary_provider=None,
        thresholds=config.data_providers.validation,
    )

    assert canonical_bars
    assert all(bar.validation_tier == "verified" for bar in canonical_bars)
    assert incidents == []


def test_intraday_canonicalization_records_missing_session_coverage(isolated_app_home) -> None:
    config = initialize_config(isolated_app_home)
    bars = _session_bars("AAPL", session_date=date(2026, 3, 9), count=20)

    canonical_bars, incidents = canonicalize_intraday_bars(
        bars,
        config=config,
        frequency="15min",
        primary_provider="alpha_vantage",
        secondary_provider=None,
        thresholds=config.data_providers.validation,
    )

    assert canonical_bars
    assert any(bar.validation_tier == "provisional" for bar in canonical_bars)
    assert any(incident.affected_fields == ("session_coverage",) for incident in incidents)
