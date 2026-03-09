from __future__ import annotations

from dataclasses import asdict
from datetime import date
from pathlib import Path
from typing import Any, cast

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select
from sqlalchemy.orm import Session

from stocktradebot import __version__
from stocktradebot.config import AppConfig, apply_config_patch, load_config
from stocktradebot.data import backfill_market_data, market_data_status
from stocktradebot.execution import (
    approve_live_trading_run,
    arm_live_mode,
    enter_paper_mode,
    enter_simulation_mode,
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
from stocktradebot.observability import read_operational_events, record_operational_event
from stocktradebot.runtime import build_ui_url, collect_doctor_checks, runtime_status
from stocktradebot.storage import (
    AuditEvent,
    create_db_engine,
    database_exists,
    database_is_reachable,
    initialize_database,
    record_audit_event,
)


def _serialize_audit_events(config: AppConfig, *, limit: int = 25) -> list[dict[str, object]]:
    if not database_exists(config) or not database_is_reachable(config):
        return []

    engine = create_db_engine(config)
    try:
        with Session(engine) as session:
            items = session.scalars(
                select(AuditEvent)
                .order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc())
                .limit(limit)
            ).all()
    finally:
        engine.dispose()

    return [
        {
            "id": item.id,
            "category": item.category,
            "message": item.message,
            "created_at": item.created_at.isoformat(),
        }
        for item in items
    ]


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

    record_operational_event(
        app_config,
        category="api",
        message="api app created",
        details={
            "runtime_host": app.state.runtime_host,
            "runtime_port": app.state.runtime_port,
        },
    )

    frontend_dist = find_frontend_dist()
    assets_path = frontend_dist / "assets" if frontend_dist else None
    if assets_path and assets_path.exists():
        app.mount("/assets", StaticFiles(directory=assets_path), name="frontend-assets")

    def current_config() -> AppConfig:
        return cast(AppConfig, app.state.config)

    def health_snapshot() -> dict[str, object]:
        config = current_config()
        checks = collect_doctor_checks(config)
        mode_state = simulation_status(config)["mode_state"]
        current_mode = "simulation" if mode_state is None else str(mode_state["current_mode"])
        return {
            "status": "ok" if all(check.ok for check in checks) else "degraded",
            "version": __version__,
            "mode": current_mode,
            "checks": [asdict(check) for check in checks],
            "ui_url": build_ui_url(app.state.runtime_host, app.state.runtime_port),
        }

    def setup_snapshot() -> dict[str, object]:
        config = current_config()
        return {
            "initialized": config.config_path.exists() and config.database_path.exists(),
            "config_path": str(config.config_path),
            "database_path": str(config.database_path),
        }

    @app.get("/api/v1/health")
    def health() -> dict[str, object]:
        return health_snapshot()

    @app.get("/api/v1/setup")
    def setup() -> dict[str, object]:
        return setup_snapshot()

    @app.get("/api/v1/config")
    def config_snapshot() -> dict[str, object]:
        return current_config().to_dict()

    @app.get("/api/v1/system/status")
    def system_status() -> dict[str, object]:
        return runtime_status(current_config().app_home)

    @app.get("/api/v1/system/mode")
    def system_mode() -> dict[str, object]:
        return {"mode_state": simulation_status(current_config())["mode_state"]}

    @app.get("/api/v1/system/audit")
    def system_audit(limit: int = 25) -> dict[str, object]:
        return {"items": _serialize_audit_events(current_config(), limit=limit)}

    @app.get("/api/v1/system/logs")
    def system_logs(limit: int = 50) -> dict[str, object]:
        return {"items": read_operational_events(current_config(), limit=limit)}

    @app.put("/api/v1/config")
    def update_config(payload: dict[str, Any]) -> dict[str, object]:
        try:
            updated = apply_config_patch(current_config(), payload)
            initialize_database(updated)
            record_audit_event(updated, "config", "config updated via API")
            record_operational_event(
                updated,
                category="api:config",
                message="config updated via API",
                details={"keys": sorted(payload.keys())},
            )
        except KeyError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except (TypeError, ValueError, RuntimeError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        app.state.config = updated
        return {"config": updated.to_dict()}

    @app.post("/api/v1/system/mode")
    def update_mode(
        target_mode: str,
        ack_disable_approvals: bool = False,
    ) -> dict[str, object]:
        config = current_config()
        try:
            if target_mode == "simulation":
                summary = enter_simulation_mode(
                    config,
                    source="api",
                    reason="simulation mode requested via API",
                )
            elif target_mode == "paper":
                summary = enter_paper_mode(
                    config,
                    source="api",
                    reason="paper mode requested via API",
                )
            elif target_mode == "live-manual":
                summary = arm_live_mode(
                    config,
                    profile="manual",
                    source="api",
                    reason="live-manual arm requested via API",
                )
            elif target_mode == "live-autonomous":
                summary = arm_live_mode(
                    config,
                    profile="autonomous",
                    ack_disable_approvals=ack_disable_approvals,
                    source="api",
                    reason="live-autonomous arm requested via API",
                )
            else:
                raise HTTPException(status_code=400, detail="Unsupported target mode.")
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        record_operational_event(
            config,
            category="api:mode",
            message="mode transition requested via API",
            details={"target_mode": target_mode, "status": summary.status},
        )
        return {"mode_transition": asdict(summary)}

    @app.get("/api/v1/operator/workspace")
    def operator_workspace() -> dict[str, object]:
        config = current_config()
        return {
            "health": health_snapshot(),
            "setup": setup_snapshot(),
            "config": config.to_dict(),
            "system": {
                "status": runtime_status(config.app_home),
                "audit_events": _serialize_audit_events(config, limit=25),
                "logs": read_operational_events(config, limit=25),
            },
            "broker": broker_state(),
            "market_data": market_data_job_status(),
            "datasets": dataset_status(config),
            "models": model_status(config),
            "risk": risk_status(),
            "portfolio": {
                "status": portfolio_status(),
                "latest_target_snapshot": latest_target_portfolio()["snapshot"],
                "latest_orders": latest_orders()["items"],
                "latest_fills": latest_fills()["items"],
            },
            "paper": paper_mode_status(),
            "live": live_mode_status(),
        }

    @app.get("/api/v1/broker/status")
    def broker_state() -> dict[str, object]:
        config = current_config()
        return {
            "paper": paper_status(config),
            "live": live_status(config),
        }

    @app.get("/api/v1/market-data/status")
    def market_data_job_status() -> dict[str, object]:
        return market_data_status(current_config())

    @app.get("/api/v1/market-data/incidents")
    def market_data_incidents(limit: int = 20) -> dict[str, object]:
        snapshot = market_data_status(current_config(), incident_limit=limit)
        return {"items": snapshot["recent_incidents"]}

    @app.get("/api/v1/market-data/universe/latest")
    def latest_universe_snapshot() -> dict[str, object]:
        snapshot = market_data_status(current_config(), incident_limit=0)
        return {"snapshot": snapshot["latest_universe_snapshot"]}

    @app.post("/api/v1/market-data/backfill")
    def run_market_data_backfill(
        as_of: str | None = None,
        lookback_days: int = 180,
        symbol: list[str] | None = None,
    ) -> dict[str, object]:
        config = current_config()
        try:
            parsed_date = None if as_of is None else date.fromisoformat(as_of)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Expected YYYY-MM-DD date format.") from exc
        try:
            summary = backfill_market_data(
                config,
                as_of_date=parsed_date,
                lookback_days=lookback_days,
                symbols=symbol,
            )
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        record_operational_event(
            config,
            category="api:market-data",
            message="market-data backfill completed via API",
            details={"run_id": summary.run_id, "canonical_count": summary.canonical_count},
        )
        return {"backfill_run": asdict(summary)}

    @app.get("/api/v1/models/datasets/latest")
    def latest_dataset_snapshot() -> dict[str, object]:
        snapshot = dataset_status(current_config())
        return {"snapshot": snapshot["latest_dataset_snapshot"]}

    @app.get("/api/v1/models/versions")
    def dataset_versions() -> dict[str, object]:
        snapshot = dataset_status(current_config())
        return {
            "feature_set_versions": snapshot["feature_set_versions"],
            "label_versions": snapshot["label_versions"],
        }

    @app.get("/api/v1/models/status")
    def models_status() -> dict[str, object]:
        return model_status(current_config())

    @app.get("/api/v1/models/latest")
    def latest_model() -> dict[str, object]:
        snapshot = model_status(current_config())
        return {"model": snapshot["latest_model"]}

    @app.get("/api/v1/models/validations/latest")
    def latest_validation() -> dict[str, object]:
        snapshot = model_status(current_config())
        return {"validation": snapshot["latest_validation_run"]}

    @app.get("/api/v1/models/backtests/latest")
    def latest_backtest() -> dict[str, object]:
        snapshot = model_status(current_config())
        return {"backtest": snapshot["latest_backtest_run"]}

    @app.get("/api/v1/risk/status")
    def risk_status() -> dict[str, object]:
        snapshot = simulation_status(current_config())
        return {
            "mode_state": snapshot["mode_state"],
            "active_freeze": snapshot["active_freeze"],
        }

    @app.get("/api/v1/portfolio/status")
    def portfolio_status() -> dict[str, object]:
        snapshot = simulation_status(current_config())
        return {
            "latest_run": snapshot["latest_run"],
            "latest_target_snapshot": snapshot["latest_target_snapshot"],
        }

    @app.get("/api/v1/portfolio/targets/latest")
    def latest_target_portfolio() -> dict[str, object]:
        snapshot = simulation_status(current_config())
        return {"snapshot": snapshot["latest_target_snapshot"]}

    @app.get("/api/v1/orders/latest")
    def latest_orders() -> dict[str, object]:
        snapshot = simulation_status(current_config())
        return {"items": snapshot["latest_orders"]}

    @app.get("/api/v1/fills/latest")
    def latest_fills() -> dict[str, object]:
        snapshot = simulation_status(current_config())
        return {"items": snapshot["latest_fills"]}

    @app.get("/api/v1/paper/status")
    def paper_mode_status() -> dict[str, object]:
        return paper_status(current_config())

    @app.get("/api/v1/live/status")
    def live_mode_status() -> dict[str, object]:
        return live_status(current_config())

    @app.post("/api/v1/models/datasets/build")
    def build_dataset(as_of: str | None = None) -> dict[str, object]:
        config = current_config()
        try:
            parsed_date = None if as_of is None else date.fromisoformat(as_of)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Expected YYYY-MM-DD date format.") from exc
        try:
            summary = build_dataset_snapshot(config, as_of_date=parsed_date)
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        record_operational_event(
            config,
            category="api:dataset",
            message="dataset snapshot built via API",
            details={"snapshot_id": summary.snapshot_id, "row_count": summary.row_count},
        )
        return {"snapshot": asdict(summary)}

    @app.post("/api/v1/models/train")
    def train_model_endpoint(as_of: str | None = None) -> dict[str, object]:
        config = current_config()
        try:
            parsed_date = None if as_of is None else date.fromisoformat(as_of)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Expected YYYY-MM-DD date format.") from exc
        try:
            summary = train_model(config, as_of_date=parsed_date)
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        record_operational_event(
            config,
            category="api:train",
            message="training run completed via API",
            details={"run_id": summary.run_id, "model_version": summary.model_version},
        )
        return {"training_run": asdict(summary)}

    @app.post("/api/v1/models/backtests/run")
    def backtest_model_endpoint(model_version: str | None = None) -> dict[str, object]:
        config = current_config()
        try:
            summary = backtest_model(config, model_version=model_version)
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        record_operational_event(
            config,
            category="api:backtest",
            message="backtest run completed via API",
            details={"run_id": summary.run_id, "model_version": summary.model_version},
        )
        return {"backtest_run": asdict(summary)}

    @app.post("/api/v1/portfolio/simulations/run")
    def run_simulation(
        as_of: str | None = None,
        model_version: str | None = None,
    ) -> dict[str, object]:
        config = current_config()
        try:
            parsed_date = None if as_of is None else date.fromisoformat(as_of)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Expected YYYY-MM-DD date format.") from exc
        try:
            summary = simulate_trading_day(
                config,
                as_of_date=parsed_date,
                model_version=model_version,
            )
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        record_operational_event(
            config,
            category="api:simulation",
            message="simulation run completed via API",
            details={"run_id": summary.run_id, "mode": summary.mode},
        )
        return {"simulation_run": asdict(summary)}

    @app.post("/api/v1/paper/run")
    def run_paper(
        as_of: str | None = None,
        model_version: str | None = None,
    ) -> dict[str, object]:
        config = current_config()
        try:
            parsed_date = None if as_of is None else date.fromisoformat(as_of)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Expected YYYY-MM-DD date format.") from exc
        try:
            summary = paper_trade_day(
                config,
                as_of_date=parsed_date,
                model_version=model_version,
            )
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        record_operational_event(
            config,
            category="api:paper",
            message="paper run completed via API",
            details={"run_id": summary.run_id, "mode": summary.mode},
        )
        return {"paper_run": asdict(summary)}

    @app.post("/api/v1/live/arm")
    def arm_live(
        profile: str = "manual",
        ack_disable_approvals: bool = False,
    ) -> dict[str, object]:
        config = current_config()
        try:
            summary = arm_live_mode(
                config,
                profile=profile,
                ack_disable_approvals=ack_disable_approvals,
                source="api",
                reason="live arm requested via API",
            )
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        record_operational_event(
            config,
            category="api:live",
            message="live mode arm completed via API",
            details={"current_mode": summary.current_mode, "status": summary.status},
        )
        return {"mode_transition": asdict(summary)}

    @app.post("/api/v1/live/run")
    def run_live(
        as_of: str | None = None,
        model_version: str | None = None,
        ack_disable_approvals: bool = False,
    ) -> dict[str, object]:
        config = current_config()
        try:
            parsed_date = None if as_of is None else date.fromisoformat(as_of)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Expected YYYY-MM-DD date format.") from exc
        try:
            mode_snapshot = simulation_status(config)["mode_state"]
            if mode_snapshot is None:
                raise RuntimeError("Mode state is unavailable.")
            current_mode = str(mode_snapshot["current_mode"])
            if current_mode == "live-autonomous":
                run_summary = run_live_trading_day(
                    config,
                    as_of_date=parsed_date,
                    model_version=model_version,
                    ack_disable_approvals=ack_disable_approvals,
                )
                record_operational_event(
                    config,
                    category="api:live",
                    message="live-autonomous run completed via API",
                    details={"run_id": run_summary.run_id, "status": run_summary.status},
                )
                return {"live_run": asdict(run_summary)}
            preparation_summary = prepare_live_trading_day(
                config,
                as_of_date=parsed_date,
                model_version=model_version,
            )
            record_operational_event(
                config,
                category="api:live",
                message="live-manual preparation completed via API",
                details={
                    "run_id": preparation_summary.run_id,
                    "status": preparation_summary.status,
                },
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
        config = current_config()
        try:
            summary = approve_live_trading_run(
                config,
                run_id=run_id,
                approve_all=approve_all,
                approve_symbols=approve_symbol,
                reject_symbols=reject_symbol,
            )
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        record_operational_event(
            config,
            category="api:live",
            message="live approvals processed via API",
            details={"run_id": summary.run_id, "status": summary.status},
        )
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
