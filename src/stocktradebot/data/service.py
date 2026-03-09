from __future__ import annotations

import json
from collections import Counter
from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from stocktradebot.config import AppConfig
from stocktradebot.data.canonicalize import canonicalize_daily_bars
from stocktradebot.data.models import (
    BackfillSummary,
    CanonicalBarRecord,
    DailyBarRecord,
    DataQualityIncidentRecord,
    ProviderHistoryPayload,
    UniverseSnapshotRecord,
)
from stocktradebot.data.providers import build_provider_registry
from stocktradebot.data.providers.base import DailyHistoryProvider, ProviderError
from stocktradebot.data.raw import persist_raw_payload
from stocktradebot.data.universe import (
    build_universe_snapshot,
    resolve_curated_etfs,
    resolve_stock_candidates,
)
from stocktradebot.storage import (
    BackfillRun,
    CanonicalDailyBar,
    CorporateActionObservation,
    DailyBarObservation,
    DataQualityIncident,
    ProviderPayload,
    UniverseSnapshot,
    UniverseSnapshotMember,
    create_db_engine,
    database_exists,
    database_is_reachable,
    record_audit_event,
)


def _normalize_symbols(symbols: Sequence[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    normalized: list[str] = []
    for symbol in symbols:
        stripped = symbol.strip().upper()
        if stripped and stripped not in seen:
            seen.add(stripped)
            normalized.append(stripped)
    return tuple(normalized)


def _default_symbol_set(config: AppConfig) -> tuple[str, ...]:
    return _normalize_symbols((*resolve_stock_candidates(config), *resolve_curated_etfs(config)))


def _resolve_provider_list(
    config: AppConfig,
    *,
    providers: Sequence[DailyHistoryProvider] | None,
    primary_provider: str | None,
    secondary_provider: str | None,
) -> tuple[tuple[DailyHistoryProvider, ...], str, str | None]:
    if providers is not None:
        provider_map = {provider.name: provider for provider in providers}
    else:
        provider_map = build_provider_registry(config)

    primary_name = primary_provider or config.data_providers.primary_provider
    secondary_name = secondary_provider or config.data_providers.secondary_provider
    if primary_name not in provider_map:
        raise RuntimeError(f"Primary provider '{primary_name}' is not available.")

    selected_providers = [provider_map[primary_name]]
    resolved_secondary_name: str | None = None
    if secondary_name and secondary_name != primary_name and secondary_name in provider_map:
        selected_providers.append(provider_map[secondary_name])
        resolved_secondary_name = secondary_name

    return tuple(selected_providers), primary_name, resolved_secondary_name


def _store_payload(
    session: Session,
    config: AppConfig,
    payload: ProviderHistoryPayload,
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
        row_count=len(payload.bars) + len(payload.corporate_actions),
        requested_at=payload.requested_at,
    )
    session.add(payload_row)
    session.flush()

    for bar in payload.bars:
        session.merge(
            DailyBarObservation(
                provider=bar.provider,
                symbol=bar.symbol,
                trade_date=bar.trade_date,
                open=bar.open,
                high=bar.high,
                low=bar.low,
                close=bar.close,
                volume=bar.volume,
                currency=bar.currency,
                split_adjusted=bar.split_adjusted,
                payload_id=payload_row.id,
                observed_at=payload.requested_at,
            )
        )

    if payload.corporate_actions:
        min_ex_date = min(action.ex_date for action in payload.corporate_actions)
        max_ex_date = max(action.ex_date for action in payload.corporate_actions)
        session.execute(
            delete(CorporateActionObservation).where(
                CorporateActionObservation.provider == payload.provider,
                CorporateActionObservation.symbol == payload.symbol,
                CorporateActionObservation.ex_date >= min_ex_date,
                CorporateActionObservation.ex_date <= max_ex_date,
            )
        )
        for action in payload.corporate_actions:
            session.add(
                CorporateActionObservation(
                    provider=action.provider,
                    symbol=action.symbol,
                    ex_date=action.ex_date,
                    action_type=action.action_type,
                    value=action.value,
                    currency=action.currency,
                    payload_id=payload_row.id,
                )
            )

    return payload_row.id, len(payload.bars)


def _load_observations(
    session: Session,
    *,
    symbols: tuple[str, ...],
    provider_names: tuple[str, ...],
    start_date: date,
    end_date: date,
) -> list[DailyBarRecord]:
    rows = session.scalars(
        select(DailyBarObservation).where(
            DailyBarObservation.symbol.in_(symbols),
            DailyBarObservation.provider.in_(provider_names),
            DailyBarObservation.trade_date >= start_date,
            DailyBarObservation.trade_date <= end_date,
        )
    ).all()
    return [
        DailyBarRecord(
            provider=row.provider,
            symbol=row.symbol,
            trade_date=row.trade_date,
            open=row.open,
            high=row.high,
            low=row.low,
            close=row.close,
            volume=row.volume,
            currency=row.currency,
            split_adjusted=row.split_adjusted,
        )
        for row in rows
    ]


def _replace_canonical_rows(
    session: Session,
    *,
    symbols: tuple[str, ...],
    start_date: date,
    end_date: date,
    canonical_bars: Sequence[CanonicalBarRecord],
    incidents: Sequence[DataQualityIncidentRecord],
) -> None:
    session.execute(
        delete(CanonicalDailyBar).where(
            CanonicalDailyBar.symbol.in_(symbols),
            CanonicalDailyBar.trade_date >= start_date,
            CanonicalDailyBar.trade_date <= end_date,
        )
    )
    session.execute(
        delete(DataQualityIncident).where(
            DataQualityIncident.symbol.in_(symbols),
            DataQualityIncident.trade_date >= start_date,
            DataQualityIncident.trade_date <= end_date,
            DataQualityIncident.domain == "daily_prices",
        )
    )

    for bar in canonical_bars:
        session.add(
            CanonicalDailyBar(
                symbol=bar.symbol,
                trade_date=bar.trade_date,
                open=bar.open,
                high=bar.high,
                low=bar.low,
                close=bar.close,
                volume=bar.volume,
                validation_tier=bar.validation_tier,
                primary_provider=bar.primary_provider,
                confirming_provider=bar.confirming_provider,
                field_provenance=json.dumps(bar.field_provenance, sort_keys=True),
            )
        )

    for incident in incidents:
        session.add(
            DataQualityIncident(
                symbol=incident.symbol,
                trade_date=incident.trade_date,
                domain=incident.domain,
                affected_fields=json.dumps(incident.affected_fields),
                involved_providers=json.dumps(incident.involved_providers),
                observed_values=json.dumps(incident.observed_values, sort_keys=True),
                resolution_status=incident.resolution_status,
                operator_notes=incident.operator_notes,
            )
        )


def _store_universe_snapshot(
    session: Session,
    *,
    snapshot_record: UniverseSnapshotRecord,
) -> int:
    snapshot_row = UniverseSnapshot(
        effective_date=snapshot_record.effective_date,
        stock_count=snapshot_record.stock_count,
        etf_count=snapshot_record.etf_count,
        selection_version=snapshot_record.selection_version,
        summary_json=json.dumps(snapshot_record.summary, sort_keys=True),
    )
    session.add(snapshot_row)
    session.flush()
    for member in snapshot_record.members:
        session.add(
            UniverseSnapshotMember(
                snapshot_id=snapshot_row.id,
                symbol=member.symbol,
                asset_type=member.asset_type,
                rank=member.rank,
                liquidity_score=member.liquidity_score,
                inclusion_reason=member.inclusion_reason,
                latest_validation_tier=member.latest_validation_tier,
            )
        )
    return snapshot_row.id


def backfill_market_data(
    config: AppConfig,
    *,
    as_of_date: date | None = None,
    lookback_days: int = 120,
    symbols: Sequence[str] | None = None,
    providers: Sequence[DailyHistoryProvider] | None = None,
    primary_provider: str | None = None,
    secondary_provider: str | None = None,
) -> BackfillSummary:
    selected_symbols = (
        _normalize_symbols(symbols)
        if symbols is not None and len(symbols) > 0
        else _default_symbol_set(config)
    )
    effective_as_of_date = as_of_date or datetime.now(UTC).date()
    start_date = effective_as_of_date - timedelta(days=max(lookback_days * 2, 45))
    selected_providers, primary_name, secondary_name = _resolve_provider_list(
        config,
        providers=providers,
        primary_provider=primary_provider,
        secondary_provider=secondary_provider,
    )
    provider_names = tuple(provider.name for provider in selected_providers)

    engine = create_db_engine(config)
    try:
        with Session(engine) as session:
            run_row = BackfillRun(
                status="running",
                requested_symbols=json.dumps(selected_symbols),
                primary_provider=primary_name,
                secondary_provider=secondary_name,
                as_of_date=effective_as_of_date,
                lookback_days=lookback_days,
                summary_json="{}",
            )
            session.add(run_row)
            session.commit()
            run_id = run_row.id

            payload_count = 0
            observation_count = 0
            fetch_errors: list[str] = []
            for symbol in selected_symbols:
                for provider in selected_providers:
                    try:
                        payload = provider.fetch_daily_history(
                            symbol,
                            start_date,
                            effective_as_of_date,
                        )
                    except ProviderError as exc:
                        fetch_errors.append(f"{provider.name}:{symbol}:{exc}")
                        record_audit_event(
                            config,
                            "market-data",
                            f"provider fetch failed for {provider.name} {symbol}: {exc}",
                        )
                        continue

                    payload_count += 1
                    observation_count += _store_payload(session, config, payload)[1]
                    session.commit()

            observations = _load_observations(
                session,
                symbols=selected_symbols,
                provider_names=provider_names,
                start_date=start_date,
                end_date=effective_as_of_date,
            )
            canonical_bars, incidents = canonicalize_daily_bars(
                observations,
                primary_provider=primary_name,
                secondary_provider=secondary_name,
                thresholds=config.data_providers.validation,
            )
            _replace_canonical_rows(
                session,
                symbols=selected_symbols,
                start_date=start_date,
                end_date=effective_as_of_date,
                canonical_bars=canonical_bars,
                incidents=incidents,
            )

            snapshot_record = build_universe_snapshot(
                canonical_bars,
                config=config,
                as_of_date=effective_as_of_date,
            )
            snapshot_id = _store_universe_snapshot(session, snapshot_record=snapshot_record)

            validation_counts = dict(
                sorted(Counter(bar.validation_tier for bar in canonical_bars).items())
            )
            summary_payload = {
                "payload_count": payload_count,
                "observation_count": observation_count,
                "canonical_count": len(canonical_bars),
                "incident_count": len(incidents),
                "providers_used": provider_names,
                "validation_counts": validation_counts,
                "fetch_errors": fetch_errors,
                "universe_snapshot_id": snapshot_id,
            }
            run_row.status = "completed_with_errors" if fetch_errors else "completed"
            run_row.summary_json = json.dumps(summary_payload, sort_keys=True)
            run_row.completed_at = datetime.now(UTC)
            session.commit()

            record_audit_event(
                config,
                "market-data",
                f"backfill run {run_id} completed with {len(canonical_bars)} canonical bars",
            )
            return BackfillSummary(
                run_id=run_id,
                as_of_date=effective_as_of_date,
                requested_symbols=selected_symbols,
                primary_provider=primary_name,
                secondary_provider=secondary_name,
                payload_count=payload_count,
                observation_count=observation_count,
                canonical_count=len(canonical_bars),
                incident_count=len(incidents),
                universe_snapshot_id=snapshot_id,
                validation_counts=validation_counts,
                providers_used=provider_names,
            )
    except Exception:
        with Session(engine) as session:
            failed_run = session.get(BackfillRun, run_id) if "run_id" in locals() else None
            if failed_run is not None:
                failed_run.status = "failed"
                failed_run.error_message = "backfill aborted unexpectedly"
                failed_run.completed_at = datetime.now(UTC)
                session.commit()
        raise
    finally:
        engine.dispose()


def market_data_status(config: AppConfig, *, incident_limit: int = 20) -> dict[str, object]:
    if not database_exists(config) or not database_is_reachable(config):
        return {
            "latest_run": None,
            "latest_universe_snapshot": None,
            "validation_counts": {},
            "recent_incidents": [],
        }

    engine = create_db_engine(config)
    try:
        with Session(engine) as session:
            latest_run = session.scalar(select(BackfillRun).order_by(BackfillRun.id.desc()))
            latest_snapshot = session.scalar(
                select(UniverseSnapshot).order_by(
                    UniverseSnapshot.effective_date.desc(),
                    UniverseSnapshot.id.desc(),
                )
            )
            validation_rows = session.execute(
                select(
                    CanonicalDailyBar.validation_tier,
                    func.count(),
                ).group_by(CanonicalDailyBar.validation_tier)
            ).all()
            recent_incidents = session.scalars(
                select(DataQualityIncident)
                .order_by(DataQualityIncident.created_at.desc(), DataQualityIncident.id.desc())
                .limit(incident_limit)
            ).all()
    finally:
        engine.dispose()

    latest_run_summary = json.loads(latest_run.summary_json) if latest_run is not None else None
    return {
        "latest_run": (
            {
                "id": latest_run.id,
                "status": latest_run.status,
                "as_of_date": latest_run.as_of_date.isoformat(),
                "primary_provider": latest_run.primary_provider,
                "secondary_provider": latest_run.secondary_provider,
                "summary": latest_run_summary,
                "completed_at": (
                    latest_run.completed_at.isoformat()
                    if latest_run.completed_at is not None
                    else None
                ),
            }
            if latest_run is not None
            else None
        ),
        "latest_universe_snapshot": (
            {
                "id": latest_snapshot.id,
                "effective_date": latest_snapshot.effective_date.isoformat(),
                "stock_count": latest_snapshot.stock_count,
                "etf_count": latest_snapshot.etf_count,
                "selection_version": latest_snapshot.selection_version,
                "summary": json.loads(latest_snapshot.summary_json),
            }
            if latest_snapshot is not None
            else None
        ),
        "validation_counts": {tier: count for tier, count in validation_rows},
        "recent_incidents": [
            {
                "id": incident.id,
                "symbol": incident.symbol,
                "trade_date": incident.trade_date.isoformat(),
                "domain": incident.domain,
                "resolution_status": incident.resolution_status,
                "affected_fields": json.loads(incident.affected_fields),
                "involved_providers": json.loads(incident.involved_providers),
            }
            for incident in recent_incidents
        ],
    }
