from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime

from stocktradebot.config import AppConfig, ValidationThresholds
from stocktradebot.data.canonicalize import PRICE_FIELDS, _relative_difference
from stocktradebot.data.models import (
    DataQualityIncidentRecord,
    IntradayBarRecord,
    IntradayCanonicalBarRecord,
)
from stocktradebot.intraday import expected_bar_starts, get_frequency_spec


def _has_valid_ohlc(bar: IntradayBarRecord) -> bool:
    return (
        bar.low <= min(bar.open, bar.close)
        and bar.high >= max(bar.open, bar.close)
        and bar.high >= bar.low
        and bar.volume >= 0
    )


def _compare_bars(
    primary: IntradayBarRecord,
    candidate: IntradayBarRecord,
    thresholds: ValidationThresholds,
) -> tuple[bool, tuple[str, ...]]:
    if primary.bar_start != candidate.bar_start or primary.frequency != candidate.frequency:
        return False, ("bar_start",)

    mismatches: list[str] = []
    for field_name in PRICE_FIELDS:
        if _relative_difference(getattr(primary, field_name), getattr(candidate, field_name)) > (
            thresholds.ohlc_relative_tolerance
        ):
            mismatches.append(field_name)
    if (
        _relative_difference(primary.volume, candidate.volume)
        > thresholds.volume_relative_tolerance
    ):
        mismatches.append("volume")
    return not mismatches, tuple(mismatches)


def canonicalize_intraday_bars(
    observations: list[IntradayBarRecord],
    *,
    config: AppConfig,
    frequency: str,
    primary_provider: str,
    secondary_provider: str | None,
    thresholds: ValidationThresholds,
) -> tuple[list[IntradayCanonicalBarRecord], list[DataQualityIncidentRecord]]:
    spec = get_frequency_spec(frequency)
    grouped: dict[tuple[str, str, datetime], dict[str, IntradayBarRecord]] = defaultdict(dict)
    for observation in observations:
        grouped[(observation.symbol, observation.frequency, observation.bar_start)][
            observation.provider
        ] = observation

    canonical_bars: list[IntradayCanonicalBarRecord] = []
    incidents: list[DataQualityIncidentRecord] = []
    session_rows: dict[tuple[str, date], list[IntradayCanonicalBarRecord]] = defaultdict(list)

    for (symbol, row_frequency, bar_start), provider_bars in sorted(grouped.items()):
        ordered_provider_names = [primary_provider]
        if secondary_provider and secondary_provider != primary_provider:
            ordered_provider_names.append(secondary_provider)
        ordered_provider_names.extend(
            sorted(name for name in provider_bars if name not in ordered_provider_names)
        )
        primary_bar = next(
            (provider_bars[name] for name in ordered_provider_names if name in provider_bars), None
        )
        if primary_bar is None:
            continue

        field_provenance = {
            field_name: primary_bar.provider for field_name in (*PRICE_FIELDS, "volume")
        }
        if not _has_valid_ohlc(primary_bar):
            incidents.append(
                DataQualityIncidentRecord(
                    symbol=symbol,
                    trade_date=primary_bar.trade_date,
                    domain=f"intraday_prices:{row_frequency}",
                    affected_fields=("ohlc",),
                    involved_providers=(primary_bar.provider,),
                    observed_values={primary_bar.provider: primary_bar.field_values()},
                )
            )
            canonical_bar = IntradayCanonicalBarRecord(
                symbol=symbol,
                frequency=row_frequency,
                bar_start=bar_start,
                open=primary_bar.open,
                high=primary_bar.high,
                low=primary_bar.low,
                close=primary_bar.close,
                volume=primary_bar.volume,
                validation_tier="quarantined",
                primary_provider=primary_bar.provider,
                confirming_provider=None,
                field_provenance=field_provenance,
            )
            canonical_bars.append(canonical_bar)
            session_rows[(symbol, primary_bar.trade_date)].append(canonical_bar)
            continue

        comparison_candidates = [
            provider_bars[name]
            for name in ordered_provider_names
            if name in provider_bars and name != primary_bar.provider
        ]
        confirming_bar: IntradayBarRecord | None = None
        mismatch_fields: tuple[str, ...] = ()
        for candidate in comparison_candidates:
            matches, mismatch_fields = _compare_bars(primary_bar, candidate, thresholds)
            if matches:
                confirming_bar = candidate
                break

        validation_tier = "verified" if confirming_bar is not None else "provisional"
        if comparison_candidates and confirming_bar is None:
            validation_tier = "quarantined"
            incidents.append(
                DataQualityIncidentRecord(
                    symbol=symbol,
                    trade_date=primary_bar.trade_date,
                    domain=f"intraday_prices:{row_frequency}",
                    affected_fields=mismatch_fields or ("provider_agreement",),
                    involved_providers=tuple(sorted(provider_bars)),
                    observed_values={
                        provider_name: bar.field_values()
                        for provider_name, bar in sorted(provider_bars.items())
                    },
                )
            )

        canonical_bar = IntradayCanonicalBarRecord(
            symbol=symbol,
            frequency=row_frequency,
            bar_start=bar_start,
            open=primary_bar.open,
            high=primary_bar.high,
            low=primary_bar.low,
            close=primary_bar.close,
            volume=primary_bar.volume,
            validation_tier=validation_tier,
            primary_provider=primary_bar.provider,
            confirming_provider=None if confirming_bar is None else confirming_bar.provider,
            field_provenance=field_provenance,
        )
        canonical_bars.append(canonical_bar)
        session_rows[(symbol, primary_bar.trade_date)].append(canonical_bar)

    upgraded_bars: list[IntradayCanonicalBarRecord] = []
    promotable_sessions: set[tuple[str, date]] = set()
    for (symbol, session_date), rows in sorted(session_rows.items()):
        expected_times = set(expected_bar_starts(session_date, frequency=frequency))
        observed_times = {row.bar_start for row in rows if row.validation_tier != "quarantined"}
        coverage_ratio = len(observed_times) / spec.expected_bars_per_session
        missing_times = sorted(expected_times - observed_times)
        if coverage_ratio >= config.intraday_research.minimum_session_coverage:
            promotable_sessions.add((symbol, session_date))
        else:
            incidents.append(
                DataQualityIncidentRecord(
                    symbol=symbol,
                    trade_date=session_date,
                    domain=f"intraday_prices:{frequency}",
                    affected_fields=("session_coverage",),
                    involved_providers=(primary_provider,),
                    observed_values={
                        "session": {
                            "coverage_ratio": round(coverage_ratio, 6),
                            "missing_bar_count": len(missing_times),
                        }
                    },
                )
            )

    for row in canonical_bars:
        session_key = (row.symbol, row.trade_date)
        if row.validation_tier == "provisional" and session_key in promotable_sessions:
            upgraded_bars.append(
                IntradayCanonicalBarRecord(
                    symbol=row.symbol,
                    frequency=row.frequency,
                    bar_start=row.bar_start,
                    open=row.open,
                    high=row.high,
                    low=row.low,
                    close=row.close,
                    volume=row.volume,
                    validation_tier="verified",
                    primary_provider=row.primary_provider,
                    confirming_provider=row.confirming_provider,
                    field_provenance=row.field_provenance,
                )
            )
        else:
            upgraded_bars.append(row)
    return upgraded_bars, incidents
