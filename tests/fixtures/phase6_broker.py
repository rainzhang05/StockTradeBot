from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from stocktradebot.broker.types import (
    BrokerAccountSnapshotData,
    BrokerOrderPreview,
    BrokerOrderRequest,
    BrokerOrderResult,
    BrokerPositionData,
)
from stocktradebot.config import AppConfig
from stocktradebot.storage import ModelRegistryEntry, SimulationRun, create_db_engine


@dataclass(slots=True)
class FakeBrokerPosition:
    symbol: str
    quantity: float
    price: float
    average_cost: float

    @property
    def market_value(self) -> float:
        return self.quantity * self.price


class FakeBrokerAdapter:
    name = "fake-ibkr"

    def __init__(
        self,
        *,
        environment: str,
        account_id: str,
        starting_cash: float,
        prices: dict[str, float],
        positions: Iterable[FakeBrokerPosition] = (),
    ) -> None:
        self.environment = environment
        self.account_id = account_id
        self._cash_balance = starting_cash
        self._prices = {symbol.upper(): float(price) for symbol, price in prices.items()}
        self._positions = {position.symbol: position for position in positions}
        self._order_sequence = 1000

    def connectivity(self) -> tuple[bool, str]:
        return True, f"connected to fake {self.environment} account {self.account_id}"

    def available_accounts(self) -> tuple[str, ...]:
        return (self.account_id,)

    def sync_account_state(self) -> BrokerAccountSnapshotData:
        market_value = sum(position.market_value for position in self._positions.values())
        net_liquidation = self._cash_balance + market_value
        return BrokerAccountSnapshotData(
            account_id=self.account_id,
            currency="USD",
            net_liquidation=net_liquidation,
            cash_balance=self._cash_balance,
            buying_power=max(net_liquidation * 2.0, 0.0),
            available_funds=max(self._cash_balance, 0.0),
            cushion=None if net_liquidation <= 0 else self._cash_balance / net_liquidation,
            payload={"environment": self.environment},
        )

    def sync_positions(self) -> tuple[BrokerPositionData, ...]:
        return tuple(
            BrokerPositionData(
                symbol=position.symbol,
                quantity=position.quantity,
                market_price=position.price,
                market_value=position.market_value,
                average_cost=position.average_cost,
                unrealized_pnl=(position.price - position.average_cost) * position.quantity,
                realized_pnl=0.0,
                currency="USD",
                payload={"environment": self.environment},
            )
            for position in sorted(self._positions.values(), key=lambda item: item.symbol)
            if abs(position.quantity) > 1e-9
        )

    def preview_order(self, order: BrokerOrderRequest) -> BrokerOrderPreview:
        preview_price = order.limit_price or self._price_for(order.symbol)
        commission = abs(order.quantity * preview_price) * 0.0005
        return BrokerOrderPreview(
            symbol=order.symbol,
            side=order.side,
            order_type=order.order_type,
            quantity=order.quantity,
            time_in_force=order.time_in_force,
            limit_price=order.limit_price,
            estimated_commission=commission,
            warnings=(),
            raw={"environment": self.environment},
        )

    def submit_order(self, order: BrokerOrderRequest) -> BrokerOrderResult:
        self._order_sequence += 1
        fill_price = order.limit_price or self._price_for(order.symbol)
        commission = abs(order.quantity * fill_price) * 0.0005
        signed_quantity = order.quantity if order.side == "buy" else -order.quantity
        if order.side == "buy":
            self._cash_balance -= order.quantity * fill_price + commission
        else:
            self._cash_balance += order.quantity * fill_price - commission
        existing = self._positions.get(order.symbol)
        if existing is None:
            self._positions[order.symbol] = FakeBrokerPosition(
                symbol=order.symbol,
                quantity=signed_quantity,
                price=fill_price,
                average_cost=fill_price,
            )
        else:
            new_quantity = existing.quantity + signed_quantity
            if abs(new_quantity) <= 1e-9:
                self._positions.pop(order.symbol, None)
            else:
                average_cost = existing.average_cost
                if order.side == "buy" and existing.quantity >= 0:
                    average_cost = (
                        existing.average_cost * existing.quantity + fill_price * order.quantity
                    ) / new_quantity
                self._positions[order.symbol] = FakeBrokerPosition(
                    symbol=order.symbol,
                    quantity=new_quantity,
                    price=fill_price,
                    average_cost=average_cost,
                )
        return BrokerOrderResult(
            broker_order_id=str(self._order_sequence),
            status="filled",
            filled_quantity=order.quantity,
            average_fill_price=fill_price,
            commission=commission,
            warnings=(),
            raw={"environment": self.environment, "order_id": self._order_sequence},
        )

    def _price_for(self, symbol: str) -> float:
        price = self._prices.get(symbol.upper())
        if price is None:
            raise RuntimeError(f"Missing fake broker price for {symbol}.")
        return price


def mark_latest_model_candidate(config: AppConfig) -> None:
    engine = create_db_engine(config)
    try:
        with Session(engine) as session:
            model = session.scalar(
                select(ModelRegistryEntry).order_by(
                    ModelRegistryEntry.created_at.desc(),
                    ModelRegistryEntry.id.desc(),
                )
            )
            if model is None:
                raise RuntimeError("No model is available to promote for testing.")
            model.promotion_status = "candidate"
            model.promotion_reasons_json = "[]"
            session.commit()
    finally:
        engine.dispose()


def seed_safe_paper_days(config: AppConfig, *, day_count: int) -> None:
    engine = create_db_engine(config)
    try:
        with Session(engine) as session:
            for offset in range(day_count):
                session.add(
                    SimulationRun(
                        status="completed",
                        mode="paper",
                        as_of_date=datetime(2026, 3, 1 + offset, tzinfo=UTC).date(),
                        decision_date=datetime(2026, 3, 1 + offset, tzinfo=UTC).date(),
                        model_entry_id=None,
                        dataset_snapshot_id=None,
                        regime="neutral",
                        gross_exposure_target=0.2,
                        gross_exposure_actual=0.2,
                        start_nav=100_000.0,
                        end_nav=100_100.0,
                        cash_start=100_000.0,
                        cash_end=80_000.0,
                        artifact_path=None,
                        summary_json='{"freeze_triggered": false}',
                        error_message=None,
                        completed_at=datetime(2026, 3, 1 + offset, 16, 0, tzinfo=UTC),
                    )
                )
            session.commit()
    finally:
        engine.dispose()
