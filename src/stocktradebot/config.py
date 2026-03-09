from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8000
CONFIG_FILENAME = "config.json"


def resolve_app_home(app_home: Path | None = None) -> Path:
    if app_home is not None:
        return app_home.expanduser().resolve()

    env_home = os.getenv("STOCKTRADEBOT_HOME")
    if env_home:
        return Path(env_home).expanduser().resolve()

    return (Path.home() / ".stocktradebot").resolve()


@dataclass(slots=True)
class AppConfig:
    app_home: Path
    config_path: Path
    database_path: Path
    artifacts_dir: Path
    logs_dir: Path
    api_host: str = DEFAULT_HOST
    api_port: int = DEFAULT_PORT
    open_browser_on_launch: bool = True
    timezone: str = "local"

    @classmethod
    def default(cls, app_home: Path | None = None) -> AppConfig:
        resolved_home = resolve_app_home(app_home)
        return cls(
            app_home=resolved_home,
            config_path=resolved_home / CONFIG_FILENAME,
            database_path=resolved_home / "runtime" / "stocktradebot.sqlite3",
            artifacts_dir=resolved_home / "artifacts",
            logs_dir=resolved_home / "logs",
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any], app_home: Path | None = None) -> AppConfig:
        defaults = cls.default(app_home)
        return cls(
            app_home=defaults.app_home,
            config_path=defaults.config_path,
            database_path=Path(data.get("database_path", defaults.database_path)).expanduser(),
            artifacts_dir=Path(data.get("artifacts_dir", defaults.artifacts_dir)).expanduser(),
            logs_dir=Path(data.get("logs_dir", defaults.logs_dir)).expanduser(),
            api_host=str(data.get("api_host", defaults.api_host)),
            api_port=int(data.get("api_port", defaults.api_port)),
            open_browser_on_launch=bool(
                data.get("open_browser_on_launch", defaults.open_browser_on_launch)
            ),
            timezone=str(data.get("timezone", defaults.timezone)),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "database_path": str(self.database_path),
            "artifacts_dir": str(self.artifacts_dir),
            "logs_dir": str(self.logs_dir),
            "api_host": self.api_host,
            "api_port": self.api_port,
            "open_browser_on_launch": self.open_browser_on_launch,
            "timezone": self.timezone,
        }

    def database_url(self) -> str:
        return f"sqlite+pysqlite:///{self.database_path}"

    def ensure_runtime_dirs(self) -> None:
        self.app_home.mkdir(parents=True, exist_ok=True)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)

    def save(self) -> None:
        self.ensure_runtime_dirs()
        self.config_path.write_text(json.dumps(self.to_dict(), indent=2) + "\n", encoding="utf-8")


def load_config(app_home: Path | None = None) -> AppConfig:
    defaults = AppConfig.default(app_home)
    if not defaults.config_path.exists():
        return defaults

    data = json.loads(defaults.config_path.read_text(encoding="utf-8"))
    return AppConfig.from_dict(data, app_home=defaults.app_home)


def initialize_config(app_home: Path | None = None, *, overwrite: bool = False) -> AppConfig:
    config = AppConfig.default(app_home)
    if config.config_path.exists() and not overwrite:
        return load_config(app_home)

    config.save()
    return config
