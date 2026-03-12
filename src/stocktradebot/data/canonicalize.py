from __future__ import annotations

from collections import defaultdict
from datetime import date

from stocktradebot.config import ValidationThresholds
from stocktradebot.data.models import (
    CanonicalBarRecord,
    DailyBarRecord,
    DataQualityIncidentRecord,
)

PRICE_FIELDS = ("open", "high", "low", "close")


def _relative_difference(left: float | int, right: float | int) -> float:
    if left == right:
        return 0.0
    scale = max(abs(float(left)), abs(float(right)), 1.0)
    return abs(float(left) - float(right)) / scale


def _has_valid_ohlc(bar: DailyBarRecord) -> bool:
    return (
        bar.low <= min(bar.open, bar.close)
        and bar.high >= max(bar.open, bar.close)
        and bar.high >= bar.low
        and bar.volume >= 0
    )


def _compare_bars(
    primary: DailyBarRecord,
    candidate: DailyBarRecord,
    thresholds: ValidationThresholds,
) -> tuple[bool, tuple[str, ...]]:
    if primary.trade_date != candidate.trade_date:
        return False, ("trade_date",)

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


def canonicalize_daily_bars(
    observations: list[DailyBarRecord],
    *,
    primary_provider: str,
    secondary_provider: str | None,
    thresholds: ValidationThresholds,
) -> tuple[list[CanonicalBarRecord], list[DataQualityIncidentRecord]]:
    grouped: dict[tuple[str, date], dict[str, DailyBarRecord]] = defaultdict(dict)
    for observation in observations:
        grouped[(observation.symbol, observation.trade_date)][observation.provider] = observation

    canonical_bars: list[CanonicalBarRecord] = []
    incidents: list[DataQualityIncidentRecord] = []

    for (symbol, trade_date), provider_bars in sorted(grouped.items()):
        ordered_provider_names = [primary_provider]
        if secondary_provider and secondary_provider != primary_provider:
            ordered_provider_names.append(secondary_provider)
        ordered_provider_names.extend(
            sorted(
                provider_name
                for provider_name in provider_bars
                if provider_name not in ordered_provider_names
            )
        )

        primary_bar = next(
            (provider_bars[name] for name in ordered_provider_names if name in provider_bars),
            None,
        )
        if primary_bar is None:
            continue
        primary_provider_observation = provider_bars.get(primary_provider)

        field_provenance = {
            field_name: primary_bar.provider for field_name in (*PRICE_FIELDS, "volume")
        }
        if not _has_valid_ohlc(primary_bar):
            canonical_bars.append(
                CanonicalBarRecord(
                    symbol=symbol,
                    trade_date=trade_date,
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
            )
            incidents.append(
                DataQualityIncidentRecord(
                    symbol=symbol,
                    trade_date=trade_date,
                    domain="daily_prices",
                    affected_fields=("ohlc",),
                    involved_providers=(primary_bar.provider,),
                    observed_values={primary_bar.provider: primary_bar.field_values()},
                )
            )
            continue

        comparison_candidates = [
            provider_bars[name]
            for name in ordered_provider_names
            if name in provider_bars and name != primary_bar.provider
        ]
        confirming_bar: DailyBarRecord | None = None
        mismatch_fields: tuple[str, ...] = ()
        for candidate in comparison_candidates:
            matches, mismatch_fields = _compare_bars(primary_bar, candidate, thresholds)
            if matches:
                confirming_bar = candidate
                break

        if confirming_bar is not None and primary_provider_observation is not None:
            canonical_bars.append(
                CanonicalBarRecord(
                    symbol=symbol,
                    trade_date=trade_date,
                    open=primary_bar.open,
                    high=primary_bar.high,
                    low=primary_bar.low,
                    close=primary_bar.close,
                    volume=primary_bar.volume,
                    validation_tier="verified",
                    primary_provider=primary_bar.provider,
                    confirming_provider=confirming_bar.provider,
                    field_provenance=field_provenance,
                )
            )
            continue

        validation_tier = "provisional"
        if comparison_candidates and confirming_bar is None:
            validation_tier = "quarantined"
        canonical_bars.append(
            CanonicalBarRecord(
                symbol=symbol,
                trade_date=trade_date,
                open=primary_bar.open,
                high=primary_bar.high,
                low=primary_bar.low,
                close=primary_bar.close,
                volume=primary_bar.volume,
                validation_tier=validation_tier,
                primary_provider=primary_bar.provider,
                confirming_provider=None,
                field_provenance=field_provenance,
            )
        )

        if comparison_candidates and confirming_bar is None:
            incidents.append(
                DataQualityIncidentRecord(
                    symbol=symbol,
                    trade_date=trade_date,
                    domain="daily_prices",
                    affected_fields=mismatch_fields or ("provider_agreement",),
                    involved_providers=tuple(sorted(provider_bars)),
                    observed_values={
                        provider_name: bar.field_values()
                        for provider_name, bar in sorted(provider_bars.items())
                    },
                )
            )

    return canonical_bars, incidents
