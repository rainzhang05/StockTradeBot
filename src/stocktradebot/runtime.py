from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

from stocktradebot.config import AppConfig, initialize_config, load_config
from stocktradebot.data import market_data_status
from stocktradebot.data.providers import build_provider_registry
from stocktradebot.execution import simulation_status
from stocktradebot.features import dataset_status
from stocktradebot.models import model_status
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
    record_audit_event(config, "runtime", "runtime prepared")
    checks = collect_doctor_checks(config)
    return RuntimeBootstrap(
        config=config,
        ui_url=build_ui_url(host or config.api_host, port or config.api_port),
        checks=checks,
    )


def collect_doctor_checks(config: AppConfig) -> list[DoctorCheck]:
    provider_registry = build_provider_registry(config)
    configured_secondary = config.data_providers.secondary_provider
    fundamentals_ready = (
        not config.fundamentals_provider.enabled
    ) or config.fundamentals_provider.resolved_user_agent() is not None
    checks = [
        DoctorCheck("app-home", config.app_home.exists(), f"app home: {config.app_home}"),
        DoctorCheck("config", config.config_path.exists(), f"config: {config.config_path}"),
        DoctorCheck("database-file", database_exists(config), f"database: {config.database_path}"),
        DoctorCheck("database-connectivity", database_is_reachable(config), "sqlite reachable"),
        DoctorCheck(
            "raw-payload-dir",
            config.raw_payload_dir.exists(),
            f"raw payloads: {config.raw_payload_dir}",
        ),
        DoctorCheck(
            "primary-provider",
            config.data_providers.primary_provider in provider_registry,
            f"primary provider: {config.data_providers.primary_provider}",
        ),
        DoctorCheck(
            "secondary-provider",
            configured_secondary is None or configured_secondary in provider_registry,
            f"secondary provider: {configured_secondary or 'not configured'}",
        ),
        DoctorCheck(
            "fundamentals-provider",
            fundamentals_ready,
            (
                "fundamentals provider disabled"
                if not config.fundamentals_provider.enabled
                else (
                    "SEC fundamentals provider ready"
                    if fundamentals_ready
                    else "SEC fundamentals provider requires a configured user agent"
                )
            ),
        ),
        DoctorCheck(
            "dataset-artifacts-dir",
            config.dataset_artifacts_dir.exists(),
            f"datasets: {config.dataset_artifacts_dir}",
        ),
        DoctorCheck(
            "model-artifacts-dir",
            config.model_artifacts_dir.exists(),
            f"models: {config.model_artifacts_dir}",
        ),
        DoctorCheck(
            "report-artifacts-dir",
            config.report_artifacts_dir.exists(),
            f"reports: {config.report_artifacts_dir}",
        ),
    ]
    return checks


def runtime_status(app_home: Path | None = None) -> dict[str, object]:
    config = load_config(app_home)
    checks = collect_doctor_checks(config)
    has_database = database_exists(config) and database_is_reachable(config)
    trading = simulation_status(config) if has_database else None
    current_mode = config.execution.default_mode
    if trading is not None and trading["mode_state"] is not None:
        current_mode = str(trading["mode_state"]["current_mode"])
    return {
        "app_home": str(config.app_home),
        "config_path": str(config.config_path),
        "database_path": str(config.database_path),
        "mode": current_mode,
        "initialized": config.config_path.exists() and database_exists(config),
        "schema_version": read_app_state(config, "schema_version"),
        "checks": [asdict(check) for check in checks],
        "market_data": market_data_status(config) if has_database else None,
        "datasets": dataset_status(config) if has_database else None,
        "models": model_status(config) if has_database else None,
        "simulation": trading,
    }
