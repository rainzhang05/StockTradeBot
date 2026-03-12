from __future__ import annotations

import json
from contextlib import contextmanager
from datetime import UTC, date, datetime

from stocktradebot.data.providers.yahoo import YahooDailyHistoryProvider, resolve_yahoo_symbol


@contextmanager
def _fake_urlopen(_request, timeout: float):
    first_timestamp = int(datetime(2026, 3, 4, tzinfo=UTC).timestamp())
    second_timestamp = int(datetime(2026, 3, 5, tzinfo=UTC).timestamp())

    class _Response:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def read(self) -> bytes:
            payload = {
                "chart": {
                    "result": [
                        {
                            "timestamp": [first_timestamp, second_timestamp],
                            "indicators": {
                                "quote": [
                                    {
                                        "open": [100.0, 101.0],
                                        "high": [102.0, 103.0],
                                        "low": [99.0, 100.0],
                                        "close": [101.0, 102.0],
                                        "volume": [1_000_000, 1_100_000],
                                    }
                                ]
                            },
                            "events": {
                                "dividends": {
                                    str(second_timestamp): {
                                        "date": second_timestamp,
                                        "amount": 0.24,
                                    }
                                },
                                "splits": {
                                    str(second_timestamp): {
                                        "date": second_timestamp,
                                        "numerator": 2,
                                        "denominator": 1,
                                    }
                                },
                            },
                        }
                    ],
                    "error": None,
                }
            }
            return json.dumps(payload).encode("utf-8")

    yield _Response()


def test_resolve_yahoo_symbol_replaces_dot_share_classes() -> None:
    assert resolve_yahoo_symbol("BRK.B") == "BRK-B"


def test_yahoo_daily_history_provider_parses_bars_and_actions(monkeypatch) -> None:
    monkeypatch.setattr("stocktradebot.data.providers.yahoo.urlopen", _fake_urlopen)
    provider = YahooDailyHistoryProvider(
        base_url="https://query1.finance.yahoo.com",
        timeout_seconds=20.0,
    )

    payload = provider.fetch_daily_history(
        "AAPL",
        start_date=date(2026, 3, 4),
        end_date=date(2026, 3, 5),
    )

    assert payload.provider == "yahoo"
    assert len(payload.bars) == 2
    assert payload.bars[0].trade_date == date(2026, 3, 4)
    assert payload.bars[1].close == 102.0
    assert len(payload.corporate_actions) == 2
    assert payload.corporate_actions[0].action_type == "dividend"
    assert payload.corporate_actions[1].action_type == "split"
    assert payload.corporate_actions[1].value == 2.0
