from __future__ import annotations

from fastapi.testclient import TestClient

from stocktradebot.api import create_app
from stocktradebot.config import initialize_config
from stocktradebot.storage import initialize_database


def test_api_health_and_setup_endpoints(isolated_app_home) -> None:
    config = initialize_config(isolated_app_home)
    initialize_database(config)
    client = TestClient(create_app(config))

    health = client.get("/api/v1/health")
    setup = client.get("/api/v1/setup")
    status = client.get("/api/v1/system/status")

    assert health.status_code == 200
    assert health.json()["status"] == "ok"
    assert setup.status_code == 200
    assert setup.json()["initialized"] is True
    assert status.status_code == 200
    assert status.json()["mode"] == "simulation"


def test_root_returns_placeholder_ui(isolated_app_home) -> None:
    config = initialize_config(isolated_app_home)
    initialize_database(config)
    client = TestClient(create_app(config))

    response = client.get("/")

    assert response.status_code == 200
    assert "StockTradeBot Phase 1" in response.text
