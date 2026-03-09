from __future__ import annotations

import hashlib
from pathlib import Path

from stocktradebot.config import AppConfig
from stocktradebot.data.models import FundamentalPayload, ProviderHistoryPayload, StoredPayloadRef


def _safe_symbol(symbol: str) -> str:
    return symbol.replace("/", "-").replace(".", "-")


def _build_payload_path(
    base_dir: Path,
    *,
    timestamp: str,
    checksum_prefix: str,
    payload_format: str,
) -> Path:
    base_name = f"{timestamp}-{checksum_prefix}"
    candidate = base_dir / f"{base_name}.{payload_format}"
    collision_index = 1
    while candidate.exists():
        candidate = base_dir / f"{base_name}-{collision_index:02d}.{payload_format}"
        collision_index += 1
    return candidate


def persist_raw_payload(
    config: AppConfig,
    payload: ProviderHistoryPayload | FundamentalPayload,
) -> StoredPayloadRef:
    timestamp = payload.requested_at.strftime("%Y%m%dT%H%M%S%fZ")
    encoded_payload = payload.raw_payload.encode("utf-8")
    checksum_sha256 = hashlib.sha256(encoded_payload).hexdigest()
    provider_dir = (
        config.raw_payload_dir / payload.provider / payload.domain / _safe_symbol(payload.symbol)
    )
    provider_dir.mkdir(parents=True, exist_ok=True)
    file_path = _build_payload_path(
        provider_dir,
        timestamp=timestamp,
        checksum_prefix=checksum_sha256[:12],
        payload_format=payload.payload_format,
    )
    file_path.write_text(payload.raw_payload, encoding="utf-8")

    relative_path = file_path.relative_to(config.app_home)
    return StoredPayloadRef(
        relative_path=str(relative_path),
        absolute_path=file_path,
        checksum_sha256=checksum_sha256,
        byte_count=len(encoded_payload),
    )


def payload_absolute_path(config: AppConfig, relative_path: str | Path) -> Path:
    return config.app_home / Path(relative_path)
