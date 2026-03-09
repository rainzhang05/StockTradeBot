from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, Response
from fastapi.staticfiles import StaticFiles

from stocktradebot import __version__
from stocktradebot.config import AppConfig, load_config
from stocktradebot.data import market_data_status
from stocktradebot.frontend import find_frontend_dist, render_placeholder_html
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
