from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from stocktradebot.config import AppConfig
from stocktradebot.data.models import FundamentalObservationRecord, FundamentalPayload
from stocktradebot.data.providers.base import FundamentalsProvider, ProviderError
from stocktradebot.data.raw import persist_raw_payload
from stocktradebot.storage import FundamentalObservation, ProviderPayload


def store_fundamental_payload(
    session: Session,
    config: AppConfig,
    payload: FundamentalPayload,
) -> tuple[int, int]:
    stored_payload = persist_raw_payload(config, payload)
    payload_row = ProviderPayload(
        provider=payload.provider,
        domain=payload.domain,
        symbol=payload.symbol,
        request_url=payload.request_url,
        payload_format=payload.payload_format,
        payload_path=stored_payload.relative_path,
        checksum_sha256=stored_payload.checksum_sha256,
        byte_count=stored_payload.byte_count,
        row_count=len(payload.observations),
        requested_at=payload.requested_at,
    )
    session.add(payload_row)
    session.flush()

    session.execute(
        delete(FundamentalObservation).where(
            FundamentalObservation.provider == payload.provider,
            FundamentalObservation.symbol == payload.symbol,
        )
    )
    for observation in payload.observations:
        session.add(
            FundamentalObservation(
                provider=observation.provider,
                symbol=observation.symbol,
                metric_name=observation.metric_name,
                source_concept=observation.source_concept,
                fiscal_period_end=observation.fiscal_period_end,
                fiscal_period_type=observation.fiscal_period_type,
                filed_at=observation.filed_at,
                available_at=observation.available_at,
                unit=observation.unit,
                value=observation.value,
                form_type=observation.form_type,
                accession=observation.accession,
                payload_id=payload_row.id,
                observed_at=payload.requested_at,
            )
        )

    return payload_row.id, len(payload.observations)


def backfill_fundamentals(
    session: Session,
    config: AppConfig,
    *,
    symbols: Sequence[str],
    provider: FundamentalsProvider | None,
) -> tuple[int, int, list[str]]:
    if provider is None:
        return 0, 0, []

    payload_count = 0
    observation_count = 0
    fetch_errors: list[str] = []
    for symbol in symbols:
        try:
            payload = provider.fetch_fundamentals(symbol)
        except ProviderError as exc:
            fetch_errors.append(f"{provider.name}:{symbol}:{exc}")
            continue

        payload_count += 1
        observation_count += store_fundamental_payload(session, config, payload)[1]
        session.commit()

    return payload_count, observation_count, fetch_errors


def load_fundamental_observations(
    session: Session,
    *,
    symbols: Sequence[str],
) -> list[FundamentalObservationRecord]:
    rows = session.scalars(
        select(FundamentalObservation).where(FundamentalObservation.symbol.in_(symbols))
    ).all()
    return [
        FundamentalObservationRecord(
            provider=row.provider,
            symbol=row.symbol,
            metric_name=row.metric_name,
            source_concept=row.source_concept,
            fiscal_period_end=row.fiscal_period_end,
            fiscal_period_type=row.fiscal_period_type,
            filed_at=row.filed_at,
            available_at=row.available_at,
            unit=row.unit,
            value=row.value,
            form_type=row.form_type,
            accession=row.accession,
        )
        for row in rows
    ]
