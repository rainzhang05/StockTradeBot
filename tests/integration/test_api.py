from __future__ import annotations

from datetime import date

from fastapi.testclient import TestClient

from stocktradebot.api import create_app
from stocktradebot.config import initialize_config
from stocktradebot.execution import (
    ModeTransitionSummary,
    SimulationRunSummary,
    TradingOperationSummary,
)
from stocktradebot.storage import initialize_database


def test_api_health_and_setup_endpoints(isolated_app_home) -> None:
    config = initialize_config(isolated_app_home)
    initialize_database(config)
    client = TestClient(create_app(config))

    health = client.get("/api/v1/health")
    setup = client.get("/api/v1/setup")
    status = client.get("/api/v1/system/status")
    mode = client.get("/api/v1/system/mode")
    market_data = client.get("/api/v1/market-data/status")
    incidents = client.get("/api/v1/market-data/incidents")
    universe = client.get("/api/v1/market-data/universe/latest")
    latest_dataset = client.get("/api/v1/models/datasets/latest")
    versions = client.get("/api/v1/models/versions")
    models_status = client.get("/api/v1/models/status")
    latest_model = client.get("/api/v1/models/latest")
    latest_validation = client.get("/api/v1/models/validations/latest")
    latest_backtest = client.get("/api/v1/models/backtests/latest")
    risk = client.get("/api/v1/risk/status")
    portfolio = client.get("/api/v1/portfolio/status")
    target = client.get("/api/v1/portfolio/targets/latest")
    orders = client.get("/api/v1/orders/latest")
    fills = client.get("/api/v1/fills/latest")
    broker = client.get("/api/v1/broker/status")
    paper = client.get("/api/v1/paper/status")
    live = client.get("/api/v1/live/status")

    assert health.status_code == 200
    assert health.json()["status"] == "ok"
    assert setup.status_code == 200
    assert setup.json()["initialized"] is True
    assert status.status_code == 200
    assert status.json()["mode"] == "simulation"
    assert mode.status_code == 200
    assert mode.json()["mode_state"]["current_mode"] == "simulation"
    assert health.json()["ui_url"] == "http://127.0.0.1:8000"
    assert market_data.status_code == 200
    assert market_data.json()["latest_run"] is None
    assert incidents.status_code == 200
    assert incidents.json()["items"] == []
    assert universe.status_code == 200
    assert universe.json()["snapshot"] is None
    assert latest_dataset.status_code == 200
    assert latest_dataset.json()["snapshot"] is None
    assert versions.status_code == 200
    assert versions.json()["feature_set_versions"] == []
    assert versions.json()["label_versions"] == []
    assert models_status.status_code == 200
    assert models_status.json()["latest_model"] is None
    assert latest_model.status_code == 200
    assert latest_model.json()["model"] is None
    assert latest_validation.status_code == 200
    assert latest_validation.json()["validation"] is None
    assert latest_backtest.status_code == 200
    assert latest_backtest.json()["backtest"] is None
    assert risk.status_code == 200
    assert risk.json()["active_freeze"] is None
    assert portfolio.status_code == 200
    assert portfolio.json()["latest_run"] is None
    assert target.status_code == 200
    assert target.json()["snapshot"] is None
    assert orders.status_code == 200
    assert orders.json()["items"] == []
    assert fills.status_code == 200
    assert fills.json()["items"] == []
    assert broker.status_code == 200
    assert broker.json()["paper"]["broker"]["configured"] is False
    assert paper.status_code == 200
    assert paper.json()["paper_safe_days"] == 0
    assert live.status_code == 200
    assert live.json()["safe_day_counts"]["paper"] == 0


def test_api_health_reports_runtime_override(isolated_app_home) -> None:
    config = initialize_config(isolated_app_home)
    initialize_database(config)
    client = TestClient(create_app(config, runtime_host="0.0.0.0", runtime_port=8010))

    health = client.get("/api/v1/health")

    assert health.status_code == 200
    assert health.json()["ui_url"] == "http://127.0.0.1:8010"


def test_root_returns_placeholder_ui(isolated_app_home) -> None:
    config = initialize_config(isolated_app_home)
    initialize_database(config)
    client = TestClient(create_app(config))

    response = client.get("/")

    assert response.status_code == 200
    assert "StockTradeBot" in response.text
    assert response.headers["content-type"].startswith("text/html")


def test_dataset_build_endpoint_validates_dates(isolated_app_home) -> None:
    config = initialize_config(isolated_app_home)
    initialize_database(config)
    client = TestClient(create_app(config))

    response = client.post("/api/v1/models/datasets/build", params={"as_of": "bad-date"})

    assert response.status_code == 400
    assert response.json()["detail"] == "Expected YYYY-MM-DD date format."


def test_dataset_build_endpoint_requires_backfill_first(isolated_app_home) -> None:
    config = initialize_config(isolated_app_home)
    initialize_database(config)
    client = TestClient(create_app(config))

    response = client.post("/api/v1/models/datasets/build", params={"as_of": "2026-03-09"})

    assert response.status_code == 409
    assert response.json()["detail"] == "No universe snapshots are available. Run backfill first."


def test_model_train_and_backtest_endpoints_require_research_prerequisites(
    isolated_app_home,
) -> None:
    config = initialize_config(isolated_app_home)
    initialize_database(config)
    client = TestClient(create_app(config))

    train_response = client.post("/api/v1/models/train", params={"as_of": "2026-03-09"})
    backtest_response = client.post("/api/v1/models/backtests/run")
    simulate_response = client.post("/api/v1/portfolio/simulations/run")

    assert train_response.status_code == 409
    assert (
        train_response.json()["detail"]
        == "No universe snapshots are available. Run backfill first."
    )
    assert backtest_response.status_code == 409
    assert backtest_response.json()["detail"] == "No trained model is available. Run train first."
    assert simulate_response.status_code == 409
    assert (
        simulate_response.json()["detail"]
        == "No universe snapshots are available. Run backfill first."
    )


def test_phase6_endpoints_expose_live_and_paper_controls(
    isolated_app_home,
    monkeypatch,
) -> None:
    config = initialize_config(isolated_app_home)
    initialize_database(config)
    client = TestClient(create_app(config))

    monkeypatch.setattr(
        "stocktradebot.api.app.paper_trade_day",
        lambda *_args, **_kwargs: SimulationRunSummary(
            run_id=21,
            mode="paper",
            status="completed",
            as_of_date=date(2026, 4, 15),
            decision_date=date(2026, 4, 15),
            model_version="linear-correlation-v1-test",
            dataset_snapshot_id=9,
            regime="neutral",
            start_nav=100_000.0,
            end_nav=100_200.0,
            cash_start=100_000.0,
            cash_end=79_000.0,
            gross_exposure_target=0.2,
            gross_exposure_actual=0.2,
            turnover_ratio=0.1,
            target_snapshot_id=11,
            post_trade_snapshot_id=12,
            order_count=2,
            fill_count=2,
            freeze_triggered=False,
            artifact_path="artifacts/reports/paper.json",
            metadata={},
        ),
    )
    monkeypatch.setattr(
        "stocktradebot.api.app.arm_live_mode",
        lambda *_args, **_kwargs: ModeTransitionSummary(
            previous_mode="paper",
            current_mode="live-manual",
            requested_mode="live-manual",
            live_profile="manual",
            status="armed",
            armed=True,
            reason="api",
            metadata={"checks": []},
        ),
    )
    monkeypatch.setattr(
        "stocktradebot.api.app.simulation_status",
        lambda *_args, **_kwargs: {"mode_state": {"current_mode": "live-manual"}},
    )
    monkeypatch.setattr(
        "stocktradebot.api.app.prepare_live_trading_day",
        lambda *_args, **_kwargs: TradingOperationSummary(
            action="prepare-live-run",
            mode="live-manual",
            status="pending-approval",
            message="ready",
            run_id=44,
            approvals=(),
            metadata={},
        ),
    )
    monkeypatch.setattr(
        "stocktradebot.api.app.approve_live_trading_run",
        lambda *_args, **_kwargs: TradingOperationSummary(
            action="approve-live-run",
            mode="live-manual",
            status="completed",
            message="approved",
            run_id=44,
            approvals=(),
            metadata={},
        ),
    )

    paper_run = client.post("/api/v1/paper/run", params={"as_of": "2026-04-15"})
    live_arm = client.post("/api/v1/live/arm", params={"profile": "manual"})
    live_run = client.post("/api/v1/live/run", params={"as_of": "2026-04-15"})
    approvals = client.post("/api/v1/live/approvals", params={"approve_all": "true"})

    assert paper_run.status_code == 200
    assert paper_run.json()["paper_run"]["run_id"] == 21
    assert live_arm.status_code == 200
    assert live_arm.json()["mode_transition"]["status"] == "armed"
    assert live_run.status_code == 200
    assert live_run.json()["live_preparation"]["status"] == "pending-approval"
    assert approvals.status_code == 200
    assert approvals.json()["approval_result"]["status"] == "completed"
