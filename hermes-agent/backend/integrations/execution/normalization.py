"""Helpers for normalizing exchange responses into Hermes execution models."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from backend.integrations.base import IntegrationError
from backend.models import ExecutionOrder, ExecutionTrade


def isoformat_exchange_timestamp(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat()
    try:
        return datetime.fromtimestamp(float(value) / 1000, tz=timezone.utc).isoformat()
    except Exception:
        return None


def float_or_none(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def normalize_ccxt_order(*, provider_name: str, order: dict[str, Any]) -> ExecutionOrder:
    info = order.get("info") or {}
    order_id = order.get("id") or info.get("order_id") or info.get("orderId")
    if not order_id:
        raise IntegrationError(f"{provider_name} returned an order without an id.")
    return ExecutionOrder(
        order_id=str(order_id),
        exchange=provider_name,
        symbol=str(order.get("symbol") or info.get("symbol") or "unknown"),
        side=order.get("side"),
        order_type=order.get("type") or info.get("type"),
        status=order.get("status") or info.get("state"),
        client_order_id=order.get("clientOrderId") or info.get("clientOrderId"),
        price=float_or_none(order.get("price")),
        average_price=float_or_none(order.get("average")),
        amount=float_or_none(order.get("amount")),
        filled=float_or_none(order.get("filled")),
        remaining=float_or_none(order.get("remaining")),
        cost=float_or_none(order.get("cost")),
        time_in_force=order.get("timeInForce") or info.get("timeInForce"),
        post_only=order.get("postOnly"),
        reduce_only=order.get("reduceOnly"),
        created_at=isoformat_exchange_timestamp(order.get("timestamp")),
        updated_at=isoformat_exchange_timestamp(order.get("lastUpdateTimestamp") or order.get("timestamp")),
    )


def normalize_ccxt_trade(*, provider_name: str, trade: dict[str, Any]) -> ExecutionTrade:
    info = trade.get("info") or {}
    trade_id = trade.get("id") or info.get("trade_id") or info.get("tradeId")
    if not trade_id:
        raise IntegrationError(f"{provider_name} returned a trade without an id.")
    fee = trade.get("fee") or {}
    return ExecutionTrade(
        trade_id=str(trade_id),
        order_id=trade.get("order") or info.get("order_id") or info.get("orderId"),
        exchange=provider_name,
        symbol=str(trade.get("symbol") or info.get("symbol") or "unknown"),
        side=trade.get("side"),
        price=float_or_none(trade.get("price")),
        amount=float_or_none(trade.get("amount")),
        cost=float_or_none(trade.get("cost")),
        fee_cost=float_or_none(fee.get("cost")),
        fee_currency=fee.get("currency"),
        liquidity=trade.get("takerOrMaker"),
        timestamp=isoformat_exchange_timestamp(trade.get("timestamp")),
    )


def execution_order_payload(
    order: ExecutionOrder,
    *,
    request_id: str | None = None,
    idempotency_key: str | None = None,
    routing: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = order.model_dump(mode="json")
    if request_id:
        payload["request_id"] = request_id
    if idempotency_key:
        payload["idempotency_key"] = idempotency_key
    if routing is not None:
        payload["routing"] = routing
    return payload
