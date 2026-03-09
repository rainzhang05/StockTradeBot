from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from stocktradebot.config import initialize_config
from stocktradebot.data.models import ProviderHistoryPayload
from stocktradebot.data.raw import persist_raw_payload


def test_persist_raw_payload_avoids_filename_collisions(isolated_app_home: Path) -> None:
    config = initialize_config(isolated_app_home)
    payload = ProviderHistoryPayload(
        provider="stooq",
        symbol="AAPL",
        domain="daily_prices",
        requested_at=datetime(2026, 3, 9, 12, 0, tzinfo=UTC),
        request_url="https://example.test/stooq/AAPL",
        payload_format="json",
        raw_payload='{"symbol":"AAPL"}',
    )

    first = persist_raw_payload(config, payload)
    second = persist_raw_payload(config, payload)

    assert first.relative_path != second.relative_path
    assert first.absolute_path.exists()
    assert second.absolute_path.exists()
    assert first.checksum_sha256 == second.checksum_sha256
