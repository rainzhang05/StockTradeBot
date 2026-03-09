from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta


@dataclass(slots=True, frozen=True)
class IntradayFrequencySpec:
    name: str
    provider_interval: str
    minutes: int
    expected_bars_per_session: int
    feature_set_version: str
    label_version: str
    target_label_name: str
    primary_horizon_bars: int
    secondary_horizon_bars: int
    minimum_history_bars: int
    dataset_lookback_sessions: int
    training_window_bars: int
    validation_window_bars: int
    walk_forward_step_bars: int


FREQUENCY_SPECS: dict[str, IntradayFrequencySpec] = {
    "15min": IntradayFrequencySpec(
        name="15min",
        provider_interval="15min",
        minutes=15,
        expected_bars_per_session=26,
        feature_set_version="intraday-15min-core-v1",
        label_version="intraday-15min-forward-return-v1",
        target_label_name="ranking_label_primary",
        primary_horizon_bars=8,
        secondary_horizon_bars=16,
        minimum_history_bars=52,
        dataset_lookback_sessions=30,
        training_window_bars=260,
        validation_window_bars=65,
        walk_forward_step_bars=65,
    ),
    "1h": IntradayFrequencySpec(
        name="1h",
        provider_interval="60min",
        minutes=60,
        expected_bars_per_session=7,
        feature_set_version="intraday-1h-core-v1",
        label_version="intraday-1h-forward-return-v1",
        target_label_name="ranking_label_primary",
        primary_horizon_bars=3,
        secondary_horizon_bars=5,
        minimum_history_bars=35,
        dataset_lookback_sessions=45,
        training_window_bars=140,
        validation_window_bars=35,
        walk_forward_step_bars=35,
    ),
}


SESSION_OPEN = time(9, 30, tzinfo=UTC)
SESSION_CLOSE = time(16, 0, tzinfo=UTC)


def get_frequency_spec(frequency: str) -> IntradayFrequencySpec:
    normalized = frequency.strip().lower()
    if normalized not in FREQUENCY_SPECS:
        supported = ", ".join(sorted(FREQUENCY_SPECS))
        raise ValueError(
            f"Unsupported intraday frequency '{frequency}'. Expected one of: {supported}."
        )
    return FREQUENCY_SPECS[normalized]


def decision_timestamp(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def expected_bar_starts(session_date: date, *, frequency: str) -> tuple[datetime, ...]:
    spec = get_frequency_spec(frequency)
    first_bar = datetime.combine(session_date, SESSION_OPEN)
    return tuple(
        first_bar + timedelta(minutes=spec.minutes * index)
        for index in range(spec.expected_bars_per_session)
    )
