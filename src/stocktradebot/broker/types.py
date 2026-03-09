from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(slots=True, frozen=True)
class BrokerInstrument:
    symbol: str
    conid: str
    exchange: str
    currency: str = "USD"


@dataclass(slots=True, frozen=True)
class BrokerAccountSnapshotData:
    account_id: str
    currency: str
    net_liquidation: float
    cash_balance: float
    buying_power: float
    available_funds: float
    cushion: float | None
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True, frozen=True)
class BrokerPositionData:
    symbol: str
    quantity: float
    market_price: float
    market_value: float
    average_cost: float | None
    unrealized_pnl: float | None
    realized_pnl: float | None
    currency: str = "USD"
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True, frozen=True)
class BrokerOrderRequest:
    symbol: str
    side: str
    quantity: float
    order_type: str
    time_in_force: str = "DAY"
    limit_price: float | None = None
    conid: str | None = None
    exchange: str = "SMART"
    currency: str = "USD"


@dataclass(slots=True, frozen=True)
class BrokerOrderPreview:
    symbol: str
    side: str
    order_type: str
    quantity: float
    time_in_force: str
    limit_price: float | None
    estimated_commission: float | None
    warnings: tuple[str, ...] = ()
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True, frozen=True)
class BrokerOrderResult:
    broker_order_id: str | None
    status: str
    filled_quantity: float
    average_fill_price: float | None
    commission: float | None
    warnings: tuple[str, ...] = ()
    raw: dict[str, Any] = field(default_factory=dict)


class BrokerAdapter(Protocol):
    name: str
    environment: str
    account_id: str

    def connectivity(self) -> tuple[bool, str]: ...

    def available_accounts(self) -> tuple[str, ...]: ...

    def sync_account_state(self) -> BrokerAccountSnapshotData: ...

    def sync_positions(self) -> tuple[BrokerPositionData, ...]: ...

    def preview_order(self, order: BrokerOrderRequest) -> BrokerOrderPreview: ...

    def submit_order(self, order: BrokerOrderRequest) -> BrokerOrderResult: ...
