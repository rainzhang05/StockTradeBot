from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

from stocktradebot.config import AppConfig, initialize_config, load_config
from stocktradebot.storage import (
    database_exists,
    database_is_reachable,
    initialize_database,
    read_app_state,
    record_audit_event,
)


@dataclass(slots=True)
class DoctorCheck:
    name: str
    ok: bool
    detail: str


@dataclass(slots=True)
class RuntimeBootstrap:
    config: AppConfig
    ui_url: str
    checks: list[DoctorCheck]

    @property
    def ok(self) -> bool:
        return all(check.ok for check in self.checks)


def build_ui_url(host: str, port: int) -> str:
    display_host = "127.0.0.1" if host == "0.0.0.0" else host
    return f"http://{display_host}:{port}"


def prepare_runtime(
    app_home: Path | None = None,
    *,
    host: str | None = None,
    port: int | None = None,
) -> RuntimeBootstrap:
    config = initialize_config(app_home)
    initialize_database(config)
    record_audit_event(config, "runtime", "phase 1 runtime prepared")
    checks = collect_doctor_checks(config)
    return RuntimeBootstrap(
        config=config,
        ui_url=build_ui_url(host or config.api_host, port or config.api_port),
        checks=checks,
    )


def collect_doctor_checks(config: AppConfig) -> list[DoctorCheck]:
    checks = [
        DoctorCheck("app-home", config.app_home.exists(), f"app home: {config.app_home}"),
        DoctorCheck("config", config.config_path.exists(), f"config: {config.config_path}"),
        DoctorCheck("database-file", database_exists(config), f"database: {config.database_path}"),
        DoctorCheck("database-connectivity", database_is_reachable(config), "sqlite reachable"),
    ]
    return checks


def runtime_status(app_home: Path | None = None) -> dict[str, object]:
    config = load_config(app_home)
    checks = collect_doctor_checks(config)
    return {
        "app_home": str(config.app_home),
        "config_path": str(config.config_path),
        "database_path": str(config.database_path),
        "mode": "simulation",
        "initialized": config.config_path.exists() and database_exists(config),
        "schema_version": read_app_state(config, "schema_version"),
        "checks": [asdict(check) for check in checks],
    }
