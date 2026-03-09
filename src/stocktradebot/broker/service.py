from __future__ import annotations

from dataclasses import asdict
from typing import Any

from stocktradebot.broker.ibkr_client import IBKRClientPortalClient
from stocktradebot.broker.types import (
    BrokerAccountSnapshotData,
    BrokerAdapter,
    BrokerOrderPreview,
    BrokerOrderRequest,
    BrokerOrderResult,
    BrokerPositionData,
)
from stocktradebot.config import AppConfig


class IBKRBrokerAdapter:
    name = "ibkr-client-portal"

    def __init__(
        self,
        config: AppConfig,
        *,
        mode: str,
        client: IBKRClientPortalClient | None = None,
    ) -> None:
        self.config = config
        self.mode = mode
        self.environment = "paper" if mode == "paper" else "live"
        account_id = config.broker.account_id_for_mode(mode)
        if account_id is None:
            raise RuntimeError(f"No broker account is configured for mode {mode}.")
        self.account_id = account_id
        self.client = client or IBKRClientPortalClient(
            base_url=config.broker.gateway.base_url,
            timeout_seconds=config.broker.gateway.timeout_seconds,
            verify_tls=config.broker.gateway.verify_tls,
        )

    def connectivity(self) -> tuple[bool, str]:
        try:
            status = self.client.auth_status()
            authenticated = bool(
                status.get("authenticated")
                or status.get("connected")
                or status.get("competing")
                or False
            )
            if not authenticated:
                return False, "IBKR gateway is reachable but not authenticated"
            accounts = self.available_accounts()
            if self.account_id not in accounts:
                return False, f"configured account {self.account_id} is not visible in IBKR"
            return True, f"connected to IBKR {self.environment} account {self.account_id}"
        except Exception as exc:
            return False, str(exc)

    def available_accounts(self) -> tuple[str, ...]:
        return self.client.available_accounts()

    def sync_account_state(self) -> BrokerAccountSnapshotData:
        return self.client.account_summary(self.account_id)

    def sync_positions(self) -> tuple[BrokerPositionData, ...]:
        return self.client.positions(self.account_id)

    def _resolved_order(self, order: BrokerOrderRequest) -> BrokerOrderRequest:
        if order.conid is not None:
            return order
        instrument = self.client.resolve_instrument(
            order.symbol,
            exchange=order.exchange or self.config.broker.default_exchange,
            currency=order.currency or self.config.broker.default_currency,
        )
        return BrokerOrderRequest(
            symbol=order.symbol,
            side=order.side,
            quantity=order.quantity,
            order_type=order.order_type,
            time_in_force=order.time_in_force,
            limit_price=order.limit_price,
            conid=instrument.conid,
            exchange=instrument.exchange,
            currency=instrument.currency,
        )

    def preview_order(self, order: BrokerOrderRequest) -> BrokerOrderPreview:
        resolved_order = self._resolved_order(order)
        return self.client.preview_order(self.account_id, resolved_order)

    def submit_order(self, order: BrokerOrderRequest) -> BrokerOrderResult:
        resolved_order = self._resolved_order(order)
        return self.client.submit_order(self.account_id, resolved_order)


def build_broker_adapter(
    config: AppConfig,
    *,
    mode: str,
    client: IBKRClientPortalClient | None = None,
) -> BrokerAdapter:
    if config.broker.provider != "ibkr-client-portal":
        raise RuntimeError(f"Unsupported broker provider: {config.broker.provider}")
    return IBKRBrokerAdapter(config, mode=mode, client=client)


def broker_status(
    config: AppConfig,
    *,
    adapter: BrokerAdapter | None = None,
) -> dict[str, Any]:
    if not config.broker.enabled:
        return {
            "configured": False,
            "provider": config.broker.provider,
            "message": "broker integration disabled in config",
            "paper_account_id": config.broker.paper_account_id,
            "live_account_id": config.broker.live_account_id,
            "gateway": config.broker.gateway.to_dict(),
            "connectivity": None,
            "accounts": [],
        }

    status_adapter = adapter
    if status_adapter is None:
        status_mode = "paper" if config.broker.paper_account_id else "live-manual"
        try:
            status_adapter = build_broker_adapter(config, mode=status_mode)
        except Exception as exc:
            return {
                "configured": True,
                "provider": config.broker.provider,
                "message": str(exc),
                "paper_account_id": config.broker.paper_account_id,
                "live_account_id": config.broker.live_account_id,
                "gateway": config.broker.gateway.to_dict(),
                "connectivity": {"ok": False, "detail": str(exc)},
                "accounts": [],
                "gates": {
                    "live_manual_min_paper_days": config.broker.live_manual_min_paper_days,
                    "live_autonomous_min_safe_days": config.broker.live_autonomous_min_safe_days,
                    "max_open_incidents_for_autonomous": (
                        config.broker.max_open_incidents_for_autonomous
                    ),
                    "require_live_autonomous_ack": config.broker.require_live_autonomous_ack,
                },
                "config": asdict(config.broker),
            }
    connected, detail = status_adapter.connectivity()
    accounts: tuple[str, ...] = ()
    if connected:
        accounts = status_adapter.available_accounts()
    return {
        "configured": True,
        "provider": config.broker.provider,
        "message": detail,
        "paper_account_id": config.broker.paper_account_id,
        "live_account_id": config.broker.live_account_id,
        "gateway": config.broker.gateway.to_dict(),
        "connectivity": {
            "ok": connected,
            "detail": detail,
            "environment": status_adapter.environment,
            "account_id": status_adapter.account_id,
        },
        "accounts": list(accounts),
        "gates": {
            "live_manual_min_paper_days": config.broker.live_manual_min_paper_days,
            "live_autonomous_min_safe_days": config.broker.live_autonomous_min_safe_days,
            "max_open_incidents_for_autonomous": config.broker.max_open_incidents_for_autonomous,
            "require_live_autonomous_ack": config.broker.require_live_autonomous_ack,
        },
        "config": asdict(config.broker),
    }
