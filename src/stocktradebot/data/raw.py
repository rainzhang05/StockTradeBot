from __future__ import annotations

import hashlib
from pathlib import Path

from stocktradebot.config import AppConfig
from stocktradebot.data.models import ProviderHistoryPayload, StoredPayloadRef


def _safe_symbol(symbol: str) -> str:
    return symbol.replace("/", "-").replace(".", "-")


def persist_raw_payload(config: AppConfig, payload: ProviderHistoryPayload) -> StoredPayloadRef:
    timestamp = payload.requested_at.strftime("%Y%m%dT%H%M%S%fZ")
    provider_dir = (
        config.raw_payload_dir / payload.provider / payload.domain / _safe_symbol(payload.symbol)
    )
    provider_dir.mkdir(parents=True, exist_ok=True)
    file_path = provider_dir / f"{timestamp}.{payload.payload_format}"
    file_path.write_text(payload.raw_payload, encoding="utf-8")

    encoded_payload = payload.raw_payload.encode("utf-8")
    relative_path = file_path.relative_to(config.app_home)
    return StoredPayloadRef(
        relative_path=str(relative_path),
        absolute_path=file_path,
        checksum_sha256=hashlib.sha256(encoded_payload).hexdigest(),
        byte_count=len(encoded_payload),
    )


def payload_absolute_path(config: AppConfig, relative_path: str | Path) -> Path:
    return config.app_home / Path(relative_path)
