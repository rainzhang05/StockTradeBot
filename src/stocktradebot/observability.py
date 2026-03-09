from __future__ import annotations

import json
from collections import deque
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from stocktradebot.config import AppConfig


def utc_now() -> datetime:
    return datetime.now(UTC)


def operational_log_path(config: AppConfig) -> Path:
    config.ensure_runtime_dirs()
    return config.logs_dir / "events.jsonl"


def record_operational_event(
    config: AppConfig,
    *,
    category: str,
    message: str,
    level: str = "info",
    details: dict[str, Any] | None = None,
) -> None:
    payload = {
        "timestamp": utc_now().isoformat(),
        "level": level,
        "category": category,
        "message": message,
        "details": details or {},
    }
    log_path = operational_log_path(config)
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True))
        handle.write("\n")


def read_operational_events(config: AppConfig, *, limit: int = 50) -> list[dict[str, Any]]:
    log_path = operational_log_path(config)
    if not log_path.exists():
        return []

    items: deque[dict[str, Any]] = deque(maxlen=max(limit, 0) or None)
    with log_path.open("r", encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line:
                continue
            try:
                parsed = json.loads(line)
            except json.JSONDecodeError:
                items.append(
                    {
                        "timestamp": None,
                        "level": "error",
                        "category": "logging",
                        "message": "Unreadable log line encountered.",
                        "details": {"raw": line},
                    }
                )
                continue
            if isinstance(parsed, dict):
                items.append(parsed)

    return list(reversed(list(items)))
