from __future__ import annotations

import json
from datetime import UTC, datetime

from stocktradebot.data.providers.sec import SecCompanyFactsProvider


def test_sec_companyfacts_provider_parses_observations_conservatively(monkeypatch) -> None:
    provider = SecCompanyFactsProvider(
        base_url="https://data.sec.gov/api/xbrl/companyfacts",
        ticker_mapping_url="https://www.sec.gov/files/company_tickers.json",
        timeout_seconds=5.0,
        user_agent="StockTradeBot test <test@example.com>",
        symbol_to_cik={"AAPL": "0000320193"},
    )

    payload_json = {
        "facts": {
            "us-gaap": {
                "Revenues": {
                    "units": {
                        "USD": [
                            {
                                "end": "2025-12-31",
                                "filed": "2026-02-15",
                                "form": "10-K",
                                "fp": "FY",
                                "val": 400000000000,
                                "accn": "0000320193-26-000001",
                            }
                        ]
                    }
                },
                "NetIncomeLoss": {
                    "units": {
                        "USD": [
                            {
                                "end": "2025-12-31",
                                "filed": "2026-02-15",
                                "form": "10-K",
                                "fp": "FY",
                                "val": 95000000000,
                                "accn": "0000320193-26-000001",
                            }
                        ]
                    }
                },
                "Assets": {
                    "units": {
                        "USD": [
                            {
                                "end": "2025-12-31",
                                "filed": "2026-02-15",
                                "form": "10-K",
                                "fp": "FY",
                                "val": 350000000000,
                                "accn": "0000320193-26-000001",
                            }
                        ]
                    }
                },
            },
            "dei": {
                "EntityCommonStockSharesOutstanding": {
                    "units": {
                        "shares": [
                            {
                                "end": "2025-12-31",
                                "filed": "2026-02-15",
                                "form": "10-K",
                                "fp": "FY",
                                "val": 15000000000,
                                "accn": "0000320193-26-000001",
                            }
                        ]
                    }
                }
            },
        }
    }

    def fake_read_url(url: str) -> tuple[str, datetime]:
        return json.dumps(payload_json), datetime(2026, 3, 9, 12, 0, tzinfo=UTC)

    monkeypatch.setattr(provider, "_read_url", fake_read_url)

    payload = provider.fetch_fundamentals("AAPL")

    assert payload.provider == "sec_companyfacts"
    assert payload.metadata["cik"] == "0000320193"
    assert len(payload.observations) == 4
    revenue = next(
        observation for observation in payload.observations if observation.metric_name == "revenue"
    )
    assert revenue.source_concept == "Revenues"
    assert revenue.available_at == datetime(2026, 2, 15, 23, 59, 59, tzinfo=UTC)
    assert revenue.accession == "000032019326000001"
