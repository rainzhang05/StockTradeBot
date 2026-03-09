from __future__ import annotations

import json
import ssl
from dataclasses import asdict
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from stocktradebot.broker.types import (
    BrokerAccountSnapshotData,
    BrokerInstrument,
    BrokerOrderPreview,
    BrokerOrderRequest,
    BrokerOrderResult,
    BrokerPositionData,
)


def _coerce_float(value: Any, *, default: float = 0.0) -> float:
    if value in {None, ""}:
        return default
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        return float(value)
    return float(str(value).replace(",", ""))


def _coerce_str(value: Any, *, default: str = "") -> str:
    if value is None:
        return default
    return str(value)


def _normalize_summary_payload(payload: Any) -> dict[str, Any]:
    if isinstance(payload, dict):
        return {_coerce_str(key).lower(): value for key, value in payload.items()}
    if isinstance(payload, list):
        normalized: dict[str, Any] = {}
        for item in payload:
            if not isinstance(item, dict):
                continue
            key = (
                item.get("tag")
                or item.get("key")
                or item.get("name")
                or item.get("field")
                or item.get("id")
            )
            if key is None:
                continue
            normalized[_coerce_str(key).lower()] = item.get("amount", item.get("value"))
        return normalized
    raise RuntimeError("Unexpected IBKR account summary payload.")


def _warning_messages(payload: Any) -> tuple[str, ...]:
    messages: list[str] = []
    if isinstance(payload, dict):
        for key in ("message", "warning", "warn", "alerts"):
            value = payload.get(key)
            if value is None:
                continue
            if isinstance(value, list):
                messages.extend(_coerce_str(item) for item in value if item is not None)
            else:
                messages.append(_coerce_str(value))
    elif isinstance(payload, list):
        for item in payload:
            messages.extend(_warning_messages(item))
    return tuple(message for message in messages if message)


def _first_mapping(payload: Any) -> dict[str, Any]:
    if isinstance(payload, dict):
        return payload
    if isinstance(payload, list):
        for item in payload:
            if isinstance(item, dict):
                return item
    raise RuntimeError("Unexpected IBKR payload shape.")


class IBKRClientPortalClient:
    def __init__(
        self,
        *,
        base_url: str,
        timeout_seconds: float,
        verify_tls: bool,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.verify_tls = verify_tls

    def _ssl_context(self) -> ssl.SSLContext | None:
        if self.verify_tls:
            return None
        return ssl._create_unverified_context()

    def _request_json(
        self,
        method: str,
        path: str,
        *,
        query: dict[str, str] | None = None,
        payload: dict[str, Any] | None = None,
    ) -> Any:
        url = f"{self.base_url}{path}"
        if query:
            url = f"{url}?{urlencode(query)}"
        request = Request(url, method=method.upper())
        request.add_header("Accept", "application/json")
        if payload is not None:
            encoded = json.dumps(payload).encode("utf-8")
            request.data = encoded
            request.add_header("Content-Type", "application/json")
        with urlopen(  # noqa: S310
            request,
            timeout=self.timeout_seconds,
            context=self._ssl_context(),
        ) as response:
            raw_body = response.read()
        if not raw_body:
            return {}
        return json.loads(raw_body.decode("utf-8"))

    def auth_status(self) -> dict[str, Any]:
        payload = self._request_json("GET", "/iserver/auth/status")
        if not isinstance(payload, dict):
            raise RuntimeError("Unexpected IBKR auth payload.")
        return payload

    def available_accounts(self) -> tuple[str, ...]:
        payload = self._request_json("GET", "/portfolio/accounts")
        accounts: list[str] = []
        if isinstance(payload, list):
            for item in payload:
                if isinstance(item, str):
                    accounts.append(item)
                    continue
                if not isinstance(item, dict):
                    continue
                account_id = item.get("accountId") or item.get("id") or item.get("acctId")
                if account_id is not None:
                    accounts.append(_coerce_str(account_id))
        elif isinstance(payload, dict):
            values = payload.get("accounts")
            if isinstance(values, list):
                for item in values:
                    accounts.append(_coerce_str(item))
        return tuple(account for account in accounts if account)

    def resolve_instrument(
        self,
        symbol: str,
        *,
        exchange: str,
        currency: str,
    ) -> BrokerInstrument:
        payload = self._request_json(
            "GET",
            "/iserver/secdef/search",
            query={"symbol": symbol, "name": "true"},
        )
        if not isinstance(payload, list) or not payload:
            raise RuntimeError(f"IBKR could not resolve instrument for {symbol}.")
        best_match = None
        for item in payload:
            if not isinstance(item, dict):
                continue
            if _coerce_str(item.get("symbol")).upper() == symbol.upper():
                best_match = item
                break
        if best_match is None:
            best_match = _first_mapping(payload)
        conid = best_match.get("conid") or best_match.get("conidex") or best_match.get("id")
        if conid is None:
            raise RuntimeError(f"IBKR did not return a conid for {symbol}.")
        return BrokerInstrument(
            symbol=symbol.upper(),
            conid=_coerce_str(conid),
            exchange=_coerce_str(best_match.get("description"), default=exchange) or exchange,
            currency=_coerce_str(best_match.get("currency"), default=currency) or currency,
        )

    def account_summary(self, account_id: str) -> BrokerAccountSnapshotData:
        payload = self._request_json("GET", f"/portfolio/{account_id}/summary")
        normalized = _normalize_summary_payload(payload)
        net_liquidation = _coerce_float(
            normalized.get("netliquidation")
            or normalized.get("net liquidation")
            or normalized.get("net_liquidation")
        )
        cash_balance = _coerce_float(
            normalized.get("totalcashvalue")
            or normalized.get("cashbalance")
            or normalized.get("cash balance")
            or normalized.get("cash")
        )
        buying_power = _coerce_float(
            normalized.get("buyingpower") or normalized.get("buying_power") or cash_balance
        )
        available_funds = _coerce_float(
            normalized.get("availablefunds") or normalized.get("available_funds") or buying_power
        )
        cushion_value = normalized.get("cushion")
        return BrokerAccountSnapshotData(
            account_id=account_id,
            currency=_coerce_str(normalized.get("currency"), default="USD") or "USD",
            net_liquidation=net_liquidation,
            cash_balance=cash_balance,
            buying_power=buying_power,
            available_funds=available_funds,
            cushion=None if cushion_value in {None, ""} else _coerce_float(cushion_value),
            payload=normalized,
        )

    def positions(self, account_id: str) -> tuple[BrokerPositionData, ...]:
        payload = self._request_json("GET", f"/portfolio/{account_id}/positions/0")
        if not isinstance(payload, list):
            raise RuntimeError("Unexpected IBKR positions payload.")
        positions: list[BrokerPositionData] = []
        for item in payload:
            if not isinstance(item, dict):
                continue
            symbol = _coerce_str(item.get("ticker") or item.get("symbol")).upper()
            if not symbol:
                continue
            quantity = _coerce_float(item.get("position") or item.get("qty"))
            market_price = _coerce_float(item.get("mktPrice") or item.get("marketPrice"))
            market_value = _coerce_float(
                item.get("mktValue") or item.get("marketValue") or quantity * market_price
            )
            positions.append(
                BrokerPositionData(
                    symbol=symbol,
                    quantity=quantity,
                    market_price=market_price,
                    market_value=market_value,
                    average_cost=(
                        None if item.get("avgCost") is None else _coerce_float(item.get("avgCost"))
                    ),
                    unrealized_pnl=(
                        None
                        if item.get("unrealizedPnl") is None
                        else _coerce_float(item.get("unrealizedPnl"))
                    ),
                    realized_pnl=(
                        None
                        if item.get("realizedPnl") is None
                        else _coerce_float(item.get("realizedPnl"))
                    ),
                    currency=_coerce_str(item.get("currency"), default="USD") or "USD",
                    payload=item,
                )
            )
        return tuple(positions)

    def _order_payload(self, order: BrokerOrderRequest) -> dict[str, Any]:
        if order.conid is None:
            raise RuntimeError(f"Order for {order.symbol} is missing IBKR conid resolution.")
        payload = {
            "acctId": None,
            "conid": order.conid,
            "secType": f"{order.conid}:STK",
            "ticker": order.symbol,
            "cOID": f"stocktradebot-{order.symbol.lower()}",
            "orderType": order.order_type.upper(),
            "side": order.side.upper(),
            "tif": order.time_in_force.upper(),
            "quantity": order.quantity,
            "outsideRTH": False,
            "listingExchange": order.exchange,
        }
        if order.limit_price is not None:
            payload["price"] = order.limit_price
        return payload

    def preview_order(self, account_id: str, order: BrokerOrderRequest) -> BrokerOrderPreview:
        payload = self._request_json(
            "POST",
            f"/iserver/account/{account_id}/orders/whatif",
            payload={"orders": [self._order_payload(order)]},
        )
        order_preview = _first_mapping(payload)
        commission_value = (
            order_preview.get("commission")
            or order_preview.get("commission_amount")
            or order_preview.get("amount")
        )
        return BrokerOrderPreview(
            symbol=order.symbol,
            side=order.side,
            order_type=order.order_type,
            quantity=order.quantity,
            time_in_force=order.time_in_force,
            limit_price=order.limit_price,
            estimated_commission=(
                None if commission_value in {None, ""} else _coerce_float(commission_value)
            ),
            warnings=_warning_messages(payload),
            raw=order_preview,
        )

    def _confirm_reply(self, reply_id: str) -> Any:
        return self._request_json("POST", f"/iserver/reply/{reply_id}", payload={"confirmed": True})

    def submit_order(self, account_id: str, order: BrokerOrderRequest) -> BrokerOrderResult:
        payload = self._request_json(
            "POST",
            f"/iserver/account/{account_id}/orders",
            payload={"orders": [self._order_payload(order)]},
        )
        response_payload = payload
        response_mapping = _first_mapping(payload)
        reply_id = response_mapping.get("id") or response_mapping.get("replyid")
        if reply_id is not None and response_mapping.get("order_id") is None:
            response_payload = self._confirm_reply(_coerce_str(reply_id))
            response_mapping = _first_mapping(response_payload)
        order_id = (
            response_mapping.get("order_id")
            or response_mapping.get("orderId")
            or response_mapping.get("id")
        )
        filled_quantity = _coerce_float(
            response_mapping.get("filledQuantity")
            or response_mapping.get("filled_qty")
            or response_mapping.get("size")
        )
        average_fill_price_value = (
            response_mapping.get("avgPrice")
            or response_mapping.get("avg_price")
            or response_mapping.get("price")
        )
        commission_value = (
            response_mapping.get("commission")
            or response_mapping.get("commission_amount")
            or response_mapping.get("estimatedCommission")
        )
        return BrokerOrderResult(
            broker_order_id=None if order_id is None else _coerce_str(order_id),
            status=_coerce_str(
                response_mapping.get("order_status")
                or response_mapping.get("status")
                or "submitted"
            ),
            filled_quantity=filled_quantity,
            average_fill_price=(
                None
                if average_fill_price_value in {None, ""}
                else _coerce_float(average_fill_price_value)
            ),
            commission=None if commission_value in {None, ""} else _coerce_float(commission_value),
            warnings=_warning_messages(response_payload),
            raw=(
                response_payload
                if isinstance(response_payload, dict)
                else {"items": response_payload, "order": asdict(order)}
            ),
        )
