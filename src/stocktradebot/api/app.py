from __future__ import annotations

from dataclasses import asdict
from datetime import date
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, Response
from fastapi.staticfiles import StaticFiles

from stocktradebot import __version__
from stocktradebot.config import AppConfig, load_config
from stocktradebot.data import market_data_status
from stocktradebot.execution import (
    approve_live_trading_run,
    arm_live_mode,
    live_status,
    paper_status,
    paper_trade_day,
    prepare_live_trading_day,
    run_live_trading_day,
    simulate_trading_day,
    simulation_status,
)
from stocktradebot.features import build_dataset_snapshot, dataset_status
from stocktradebot.frontend import find_frontend_dist, render_placeholder_html
from stocktradebot.models import backtest_model, model_status, train_model
from stocktradebot.runtime import build_ui_url, collect_doctor_checks, runtime_status


def create_app(
    config: AppConfig | None = None,
    *,
    runtime_host: str | None = None,
    runtime_port: int | None = None,
) -> FastAPI:
    app_config = config or load_config()
    app = FastAPI(title="StockTradeBot", version=__version__)
    app.state.config = app_config
    app.state.runtime_host = runtime_host or app_config.api_host
    app.state.runtime_port = runtime_port or app_config.api_port

    frontend_dist = find_frontend_dist()
    assets_path = frontend_dist / "assets" if frontend_dist else None
    if assets_path and assets_path.exists():
        app.mount("/assets", StaticFiles(directory=assets_path), name="frontend-assets")

    @app.get("/api/v1/health")
    def health() -> dict[str, object]:
        checks = collect_doctor_checks(app_config)
        return {
            "status": "ok" if all(check.ok for check in checks) else "degraded",
            "version": __version__,
            "mode": "simulation",
            "checks": [asdict(check) for check in checks],
            "ui_url": build_ui_url(app.state.runtime_host, app.state.runtime_port),
        }

    @app.get("/api/v1/setup")
    def setup() -> dict[str, object]:
        return {
            "initialized": app_config.config_path.exists() and app_config.database_path.exists(),
            "config_path": str(app_config.config_path),
            "database_path": str(app_config.database_path),
        }

    @app.get("/api/v1/config")
    def config_snapshot() -> dict[str, object]:
        return app_config.to_dict()

    @app.get("/api/v1/system/status")
    def system_status() -> dict[str, object]:
        return runtime_status(app_config.app_home)

    @app.get("/api/v1/system/mode")
    def system_mode() -> dict[str, object]:
        return {"mode_state": simulation_status(app_config)["mode_state"]}

    @app.get("/api/v1/broker/status")
    def broker_state() -> dict[str, object]:
        return {
            "paper": paper_status(app_config),
            "live": live_status(app_config),
        }

    @app.get("/api/v1/market-data/status")
    def market_data_job_status() -> dict[str, object]:
        return market_data_status(app_config)

    @app.get("/api/v1/market-data/incidents")
    def market_data_incidents(limit: int = 20) -> dict[str, object]:
        snapshot = market_data_status(app_config, incident_limit=limit)
        return {"items": snapshot["recent_incidents"]}

    @app.get("/api/v1/market-data/universe/latest")
    def latest_universe_snapshot() -> dict[str, object]:
        snapshot = market_data_status(app_config, incident_limit=0)
        return {"snapshot": snapshot["latest_universe_snapshot"]}

    @app.get("/api/v1/models/datasets/latest")
    def latest_dataset_snapshot() -> dict[str, object]:
        snapshot = dataset_status(app_config)
        return {"snapshot": snapshot["latest_dataset_snapshot"]}

    @app.get("/api/v1/models/versions")
    def dataset_versions() -> dict[str, object]:
        snapshot = dataset_status(app_config)
        return {
            "feature_set_versions": snapshot["feature_set_versions"],
            "label_versions": snapshot["label_versions"],
        }

    @app.get("/api/v1/models/status")
    def models_status() -> dict[str, object]:
        return model_status(app_config)

    @app.get("/api/v1/models/latest")
    def latest_model() -> dict[str, object]:
        snapshot = model_status(app_config)
        return {"model": snapshot["latest_model"]}

    @app.get("/api/v1/models/validations/latest")
    def latest_validation() -> dict[str, object]:
        snapshot = model_status(app_config)
        return {"validation": snapshot["latest_validation_run"]}

    @app.get("/api/v1/models/backtests/latest")
    def latest_backtest() -> dict[str, object]:
        snapshot = model_status(app_config)
        return {"backtest": snapshot["latest_backtest_run"]}

    @app.get("/api/v1/risk/status")
    def risk_status() -> dict[str, object]:
        snapshot = simulation_status(app_config)
        return {
            "mode_state": snapshot["mode_state"],
            "active_freeze": snapshot["active_freeze"],
        }

    @app.get("/api/v1/portfolio/status")
    def portfolio_status() -> dict[str, object]:
        snapshot = simulation_status(app_config)
        return {
            "latest_run": snapshot["latest_run"],
            "latest_target_snapshot": snapshot["latest_target_snapshot"],
        }

    @app.get("/api/v1/portfolio/targets/latest")
    def latest_target_portfolio() -> dict[str, object]:
        snapshot = simulation_status(app_config)
        return {"snapshot": snapshot["latest_target_snapshot"]}

    @app.get("/api/v1/orders/latest")
    def latest_orders() -> dict[str, object]:
        snapshot = simulation_status(app_config)
        return {"items": snapshot["latest_orders"]}

    @app.get("/api/v1/fills/latest")
    def latest_fills() -> dict[str, object]:
        snapshot = simulation_status(app_config)
        return {"items": snapshot["latest_fills"]}

    @app.get("/api/v1/paper/status")
    def paper_mode_status() -> dict[str, object]:
        return paper_status(app_config)

    @app.get("/api/v1/live/status")
    def live_mode_status() -> dict[str, object]:
        return live_status(app_config)

    @app.post("/api/v1/models/datasets/build")
    def build_dataset(as_of: str | None = None) -> dict[str, object]:
        try:
            parsed_date = None if as_of is None else date.fromisoformat(as_of)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Expected YYYY-MM-DD date format.") from exc
        try:
            summary = build_dataset_snapshot(app_config, as_of_date=parsed_date)
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return {"snapshot": asdict(summary)}

    @app.post("/api/v1/models/train")
    def train_model_endpoint(as_of: str | None = None) -> dict[str, object]:
        try:
            parsed_date = None if as_of is None else date.fromisoformat(as_of)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Expected YYYY-MM-DD date format.") from exc
        try:
            summary = train_model(app_config, as_of_date=parsed_date)
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return {"training_run": asdict(summary)}

    @app.post("/api/v1/models/backtests/run")
    def backtest_model_endpoint(model_version: str | None = None) -> dict[str, object]:
        try:
            summary = backtest_model(app_config, model_version=model_version)
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return {"backtest_run": asdict(summary)}

    @app.post("/api/v1/portfolio/simulations/run")
    def run_simulation(
        as_of: str | None = None,
        model_version: str | None = None,
    ) -> dict[str, object]:
        try:
            parsed_date = None if as_of is None else date.fromisoformat(as_of)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Expected YYYY-MM-DD date format.") from exc
        try:
            summary = simulate_trading_day(
                app_config,
                as_of_date=parsed_date,
                model_version=model_version,
            )
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return {"simulation_run": asdict(summary)}

    @app.post("/api/v1/paper/run")
    def run_paper(
        as_of: str | None = None,
        model_version: str | None = None,
    ) -> dict[str, object]:
        try:
            parsed_date = None if as_of is None else date.fromisoformat(as_of)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Expected YYYY-MM-DD date format.") from exc
        try:
            summary = paper_trade_day(
                app_config,
                as_of_date=parsed_date,
                model_version=model_version,
            )
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return {"paper_run": asdict(summary)}

    @app.post("/api/v1/live/arm")
    def arm_live(
        profile: str = "manual",
        ack_disable_approvals: bool = False,
    ) -> dict[str, object]:
        try:
            summary = arm_live_mode(
                app_config,
                profile=profile,
                ack_disable_approvals=ack_disable_approvals,
                source="api",
                reason="live arm requested via API",
            )
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return {"mode_transition": asdict(summary)}

    @app.post("/api/v1/live/run")
    def run_live(
        as_of: str | None = None,
        model_version: str | None = None,
        ack_disable_approvals: bool = False,
    ) -> dict[str, object]:
        try:
            parsed_date = None if as_of is None else date.fromisoformat(as_of)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Expected YYYY-MM-DD date format.") from exc
        try:
            mode_snapshot = simulation_status(app_config)["mode_state"]
            if mode_snapshot is None:
                raise RuntimeError("Mode state is unavailable.")
            current_mode = str(mode_snapshot["current_mode"])
            if current_mode == "live-autonomous":
                run_summary = run_live_trading_day(
                    app_config,
                    as_of_date=parsed_date,
                    model_version=model_version,
                    ack_disable_approvals=ack_disable_approvals,
                )
                return {"live_run": asdict(run_summary)}
            preparation_summary = prepare_live_trading_day(
                app_config,
                as_of_date=parsed_date,
                model_version=model_version,
            )
            return {"live_preparation": asdict(preparation_summary)}
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.post("/api/v1/live/approvals")
    def approve_live(
        run_id: int | None = None,
        approve_all: bool = False,
        approve_symbol: list[str] | None = None,
        reject_symbol: list[str] | None = None,
    ) -> dict[str, object]:
        try:
            summary = approve_live_trading_run(
                app_config,
                run_id=run_id,
                approve_all=approve_all,
                approve_symbols=approve_symbol,
                reject_symbols=reject_symbol,
            )
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return {"approval_result": asdict(summary)}

    @app.get("/", response_class=HTMLResponse, response_model=None)
    def root() -> Response:
        if frontend_dist and (frontend_dist / "index.html").exists():
            return FileResponse(frontend_dist / "index.html")
        return HTMLResponse(render_placeholder_html())

    @app.get("/{path:path}", response_model=None)
    def spa_fallback(path: str) -> Response:
        if path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not found")

        if frontend_dist:
            candidate = frontend_dist / Path(path)
            if candidate.exists() and candidate.is_file():
                return FileResponse(candidate)
            index_path = frontend_dist / "index.html"
            if index_path.exists():
                return FileResponse(index_path)

        return HTMLResponse(render_placeholder_html())

    return app
