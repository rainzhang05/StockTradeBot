from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any


@dataclass(slots=True, frozen=True)
class PositionSummary:
    symbol: str
    shares: float
    target_weight: float
    actual_weight: float
    price: float
    market_value: float
    score: float | None
    sector: str | None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True, frozen=True)
class OrderIntentSummary:
    order_id: int
    symbol: str
    side: str
    status: str
    order_type: str
    requested_shares: float
    requested_notional: float
    reference_price: float
    limit_price: float | None
    expected_slippage_bps: float
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True, frozen=True)
class FillSummary:
    fill_id: int
    order_intent_id: int
    symbol: str
    side: str
    fill_status: str
    filled_shares: float
    filled_notional: float
    fill_price: float
    commission: float
    slippage_bps: float
    expected_spread_bps: float
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True, frozen=True)
class SimulationRunSummary:
    run_id: int
    mode: str
    status: str
    as_of_date: date
    decision_date: date | None
    model_version: str | None
    dataset_snapshot_id: int | None
    regime: str | None
    start_nav: float
    end_nav: float
    cash_start: float
    cash_end: float
    gross_exposure_target: float
    gross_exposure_actual: float
    turnover_ratio: float
    target_snapshot_id: int | None
    post_trade_snapshot_id: int | None
    order_count: int
    fill_count: int
    freeze_triggered: bool
    artifact_path: str
    metadata: dict[str, Any] = field(default_factory=dict)
