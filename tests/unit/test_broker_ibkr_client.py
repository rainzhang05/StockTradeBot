from __future__ import annotations

from stocktradebot.broker.ibkr_client import IBKRClientPortalClient
from stocktradebot.broker.types import BrokerOrderRequest


def test_ibkr_client_parses_accounts_summary_and_positions(monkeypatch) -> None:
    client = IBKRClientPortalClient(
        base_url="https://example.test/v1/api",
        timeout_seconds=5.0,
        verify_tls=False,
    )

    def fake_request_json(method: str, path: str, **_kwargs):
        if path == "/portfolio/accounts":
            return [{"accountId": "DU1234567"}]
        if path == "/portfolio/DU1234567/summary":
            return [
                {"tag": "NetLiquidation", "value": "100000"},
                {"tag": "TotalCashValue", "value": "50000"},
                {"tag": "BuyingPower", "value": "200000"},
                {"tag": "AvailableFunds", "value": "150000"},
                {"tag": "Currency", "value": "USD"},
            ]
        if path == "/portfolio/DU1234567/positions/0":
            return [
                {
                    "ticker": "AAPL",
                    "position": 10,
                    "mktPrice": 200.0,
                    "mktValue": 2000.0,
                    "avgCost": 190.0,
                    "unrealizedPnl": 100.0,
                    "realizedPnl": 0.0,
                    "currency": "USD",
                }
            ]
        raise AssertionError(f"Unexpected request {method} {path}")

    monkeypatch.setattr(client, "_request_json", fake_request_json)

    assert client.available_accounts() == ("DU1234567",)
    account = client.account_summary("DU1234567")
    positions = client.positions("DU1234567")

    assert account.net_liquidation == 100000.0
    assert account.cash_balance == 50000.0
    assert account.buying_power == 200000.0
    assert positions[0].symbol == "AAPL"
    assert positions[0].market_value == 2000.0


def test_ibkr_client_confirms_reply_when_submitting_order(monkeypatch) -> None:
    client = IBKRClientPortalClient(
        base_url="https://example.test/v1/api",
        timeout_seconds=5.0,
        verify_tls=False,
    )
    order = BrokerOrderRequest(
        symbol="AAPL",
        side="buy",
        quantity=5,
        order_type="limit",
        time_in_force="DAY",
        limit_price=200.0,
        conid="265598",
    )

    def fake_request_json(method: str, path: str, payload=None, **_kwargs):
        if path == "/iserver/account/DU1234567/orders":
            assert payload is not None
            return [{"id": "reply-1", "message": ["Confirm order"]}]
        if path == "/iserver/reply/reply-1":
            return {
                "order_id": "OID-1001",
                "status": "filled",
                "filledQuantity": 5,
                "avgPrice": 199.5,
                "commission": 1.25,
            }
        raise AssertionError(f"Unexpected request {method} {path}")

    monkeypatch.setattr(client, "_request_json", fake_request_json)

    result = client.submit_order("DU1234567", order)

    assert result.broker_order_id == "OID-1001"
    assert result.status == "filled"
    assert result.filled_quantity == 5
    assert result.average_fill_price == 199.5
