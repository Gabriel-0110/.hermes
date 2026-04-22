"""Hermes Redis Streams workers — orchestration, execution, and notifications."""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys

from .consumer import RedisStreamWorker
from .models import TradingEventEnvelope

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Kill-switch helpers (read-only — the write path lives in get_risk_approval)
# ---------------------------------------------------------------------------

_KILL_SWITCH_KEY = "hermes:risk:kill_switch"


_LIMITS_KEY = "hermes:risk:limits"
_EQUITY_PEAK_KEY = "hermes:risk:equity_peak"


def _check_and_enforce_drawdown() -> bool:
    """Return True (and activate kill switch) if drawdown limit has been breached."""
    try:
        from backend.redis_client import get_redis_client
        from backend.tools.get_portfolio_state import get_portfolio_state

        redis = get_redis_client()

        limits_raw = redis.get(_LIMITS_KEY)
        if not limits_raw:
            return False
        limits = json.loads(limits_raw)
        drawdown_limit_pct = float(limits.get("drawdown_limit_pct", 0) or 0)
        if drawdown_limit_pct <= 0:
            return False

        peak_raw = redis.get(_EQUITY_PEAK_KEY)
        if not peak_raw:
            return False
        peak_equity = float(json.loads(peak_raw).get("equity", 0) or 0)
        if peak_equity <= 0:
            return False

        portfolio = get_portfolio_state({})
        current_equity = float(portfolio["data"].get("total_value_usd", 0) or 0)
        if current_equity <= 0:
            return False

        drawdown_pct = (peak_equity - current_equity) / peak_equity * 100.0
        if drawdown_pct >= drawdown_limit_pct:
            reason = (
                f"Drawdown limit breached: {drawdown_pct:.2f}% >= {drawdown_limit_pct:.2f}% "
                f"(peak={peak_equity:.2f}, current={current_equity:.2f})"
            )
            logger.warning("workers: auto-triggering kill switch — %s", reason)
            try:
                from backend.tools.set_kill_switch import set_kill_switch
                set_kill_switch({"active": True, "reason": reason})
            except Exception as exc:
                logger.error("workers: failed to set kill switch: %s", exc)
                # Manually write to Redis as fallback
                redis.set(
                    _KILL_SWITCH_KEY,
                    json.dumps({"active": True, "reason": reason}),
                )
            return True
    except Exception as exc:
        logger.warning("workers: drawdown check failed: %s", exc)
    return False


def _kill_switch_active() -> bool:
    """Return True if the global kill switch is set in Redis."""
    try:
        from backend.redis_client import get_redis_client

        raw = get_redis_client().get(_KILL_SWITCH_KEY)
        if raw:
            return bool(json.loads(raw).get("active"))
    except Exception as exc:
        logger.warning("workers: kill-switch read failed: %s", exc)
    return False


# ---------------------------------------------------------------------------
# Orchestrator handler — routes signal events into the trading workflow graph
# ---------------------------------------------------------------------------


def orchestrator_handler(event: TradingEventEnvelope) -> bool:
    """Dispatch incoming trading events to the appropriate downstream handler.

    Returns True (ack) on successful dispatch or graceful skip.
    Returns False (no-ack / leave pending) only on transient failures that
    should be retried.
    """
    ev = event.event
    logger.info(
        "Orchestrator received event_type=%s symbol=%s alert_id=%s correlation_id=%s",
        ev.event_type,
        ev.symbol,
        ev.alert_id,
        ev.correlation_id,
    )

    if ev.event_type == "tradingview_signal_ready":
        return _handle_signal_ready(event)

    if ev.event_type == "execution_requested":
        return _handle_execution_requested(event)

    # Other event types are logged and acknowledged.
    logger.debug("orchestrator_handler: no specific handler for %s — acking", ev.event_type)
    return True


def _handle_signal_ready(event: TradingEventEnvelope) -> bool:
    """Run the trading workflow graph for a ready TradingView signal."""
    ev = event.event
    try:
        import asyncio

        from backend.workflows.graph import run_trading_workflow
        from backend.workflows.models import TradingInputEvent

        input_event = TradingInputEvent(
            event_id=ev.event_id,
            event_type=ev.event_type,
            symbol=ev.symbol or ev.payload.get("symbol") or "UNKNOWN",
            alert_id=ev.alert_id,
            correlation_id=ev.correlation_id or ev.event_id,
            signal=ev.payload.get("signal"),
            direction=ev.payload.get("direction"),
            strategy=ev.payload.get("strategy"),
            timeframe=ev.payload.get("timeframe"),
            price=float(ev.payload["price"]) if ev.payload.get("price") is not None else None,
            payload=ev.payload,
        )

        logger.info(
            "orchestrator_handler: launching trading workflow for symbol=%s signal=%s",
            input_event.symbol,
            input_event.signal,
        )

        # Run the async workflow in a new event loop (worker runs synchronously)
        result = asyncio.run(run_trading_workflow(input_event))
        logger.info(
            "orchestrator_handler: workflow completed for symbol=%s outcome=%s",
            input_event.symbol,
            result,
        )
        return True

    except Exception as exc:
        logger.exception(
            "orchestrator_handler: workflow failed for event_id=%s symbol=%s: %s",
            ev.event_id,
            ev.symbol,
            exc,
        )
        # Return True (ack) to avoid infinite retries on a broken event.
        return True


def _handle_execution_requested(event: TradingEventEnvelope) -> bool:
    """Route an approved execution request through the CCXT client (paper-mode safe)."""
    ev = event.event
    payload = ev.payload

    # Drawdown check — auto-trigger kill switch if breach detected
    if _check_and_enforce_drawdown():
        logger.warning(
            "execution_handler: drawdown limit breached — kill switch activated, "
            "rejecting execution_requested for symbol=%s",
            ev.symbol,
        )
        return True

    # Hard kill-switch check
    if _kill_switch_active():
        logger.warning(
            "execution_handler: kill switch active — rejecting execution_requested for symbol=%s",
            ev.symbol,
        )
        return True

    # Operator approval gate: if HERMES_REQUIRE_APPROVAL is enabled, hold the
    # request in the pending queue until an operator ACKs it via the API.
    # Requests that already carry an approval_id have passed the gate.
    require_approval = os.getenv("HERMES_REQUIRE_APPROVAL", "false").lower() in {"true", "1", "yes"}
    already_approved = bool(payload.get("approval_id"))
    if require_approval and not already_approved:
        try:
            from backend.approvals import create_approval_request

            approval_id = create_approval_request(
                payload=payload,
                correlation_id=ev.correlation_id or ev.event_id,
                symbol=ev.symbol,
                side=payload.get("side"),
                amount=payload.get("amount") or payload.get("size_usd"),
            )
            logger.info(
                "execution_handler: approval required — gating execution for symbol=%s "
                "approval_id=%s",
                ev.symbol,
                approval_id,
            )
        except Exception as exc:
            logger.exception(
                "execution_handler: approval gate failed for symbol=%s: %s — allowing execution",
                ev.symbol,
                exc,
            )
        return True  # ack event; worker will re-receive via republish on approval

    # Runtime trading mode is centralized so the workflow worker, API, and
    # execution adapters all agree on when live placement is actually allowed.
    from backend.integrations.execution.mode import is_paper_mode

    if is_paper_mode():
        logger.info(
            "execution_handler: PAPER MODE — simulating execution for symbol=%s side=%s amount=%s",
            ev.symbol,
            payload.get("side"),
            payload.get("amount"),
        )
        _record_simulated_execution(event)
        return True

    return _place_live_order(event)


def _resolve_order_amount(payload: dict) -> float:
    """Resolve a base-unit order amount from the event payload.

    Workflow-sourced events carry ``size_usd`` (notional USD) rather than a
    base-unit quantity.  When that is the case we attempt a best-effort price
    lookup and divide.  A direct ``amount`` field in the payload always wins.
    """
    # Direct amount takes priority (from manual /execution/place API calls).
    if payload.get("amount") is not None:
        raw = payload["amount"]
        return float(raw)

    size_usd = payload.get("size_usd")
    if size_usd is None:
        raise ValueError("execution payload has neither 'amount' nor 'size_usd'")

    size_usd_f = float(size_usd)
    symbol = (payload.get("symbol") or "").upper()

    # Try to get a current price to convert notional → quantity.
    try:
        from backend.tools.get_crypto_prices import get_crypto_prices

        # Strip quote currency suffix (e.g. BTC/USDT → BTC, BTCUSDT → BTC)
        base = symbol.replace("USDT", "").replace("USD", "").replace("/", "").strip()
        result = get_crypto_prices({"symbols": [base]})
        prices = result.get("data", [])
        if isinstance(prices, list) and prices:
            price = prices[0].get("price")
            if price and float(price) > 0:
                qty = size_usd_f / float(price)
                logger.info(
                    "_resolve_order_amount: %s size_usd=%.2f price=%.4f → qty=%.8f",
                    base,
                    size_usd_f,
                    float(price),
                    qty,
                )
                return qty
    except Exception as exc:
        logger.warning("_resolve_order_amount: price lookup failed for %s: %s", symbol, exc)

    # Cannot resolve; return size_usd as-is and let the exchange reject if wrong.
    logger.warning(
        "_resolve_order_amount: falling back to size_usd=%.2f as amount for %s",
        size_usd_f,
        symbol,
    )
    return size_usd_f


def _clamp_order_amount(amount: float, symbol: str) -> float:
    """Clamp order amount to respect max_position_usd risk limit."""
    try:
        from backend.redis_client import get_redis_client

        redis = get_redis_client()
        limits_raw = redis.get(_LIMITS_KEY)
        if not limits_raw:
            return amount
        limits = json.loads(limits_raw)
        max_position_usd = limits.get("max_position_usd")
        if not max_position_usd or float(max_position_usd) <= 0:
            return amount

        # Get current price to convert USD limit → quantity
        try:
            from backend.tools.get_crypto_prices import get_crypto_prices

            base = symbol.upper().replace("USDT", "").replace("USD", "").replace("/", "").strip()
            result = get_crypto_prices({"symbols": [base]})
            prices = result.get("data", [])
            if isinstance(prices, list) and prices:
                price = float(prices[0].get("price") or 0)
                if price > 0:
                    max_qty = float(max_position_usd) / price
                    if amount > max_qty:
                        logger.warning(
                            "_clamp_order_amount: clamping %s from %.8f to %.8f "
                            "(max_position_usd=%.2f price=%.4f)",
                            symbol, amount, max_qty, float(max_position_usd), price,
                        )
                        return max_qty
        except Exception as exc:
            logger.warning("_clamp_order_amount: price lookup failed for %s: %s", symbol, exc)
    except Exception as exc:
        logger.warning("_clamp_order_amount: limits read failed: %s", exc)
    return amount


def _place_live_order(event: TradingEventEnvelope) -> bool:
    """Place a real order via CCXTExecutionClient."""
    ev = event.event
    payload = ev.payload

    try:
        from backend.integrations.execution.ccxt_client import CCXTExecutionClient
        from backend.integrations.base import IntegrationError, MissingCredentialError

        client = CCXTExecutionClient()
        if not client.configured:
            logger.error(
                "execution_handler: BitMart not configured — cannot place order for symbol=%s",
                ev.symbol,
            )
            return True  # ack to avoid poison-pill loop

        order = client.place_order(
            symbol=payload.get("symbol") or ev.symbol or "",
            side=payload["side"],
            order_type=payload.get("order_type", "market"),
            amount=_clamp_order_amount(
                _resolve_order_amount(payload),
                payload.get("symbol") or ev.symbol or "",
            ),
            price=float(payload["price"]) if payload.get("price") else None,
            client_order_id=payload.get("client_order_id"),
        )
        logger.info(
            "execution_handler: live order placed order_id=%s symbol=%s",
            order.order_id,
            order.symbol,
        )
        _record_execution_event(event, order_id=order.order_id, status="filled")
        return True

    except (KeyError, TypeError, ValueError) as exc:
        logger.error(
            "execution_handler: malformed execution_requested payload for event_id=%s: %s",
            ev.event_id,
            exc,
        )
        return True  # malformed events should be acked to unblock the stream

    except Exception as exc:
        logger.exception(
            "execution_handler: unexpected error placing order for symbol=%s: %s",
            ev.symbol,
            exc,
        )
        return False  # transient — leave unacked for retry


def _record_simulated_execution(event: TradingEventEnvelope) -> None:
    """Persist a paper-mode execution event in the observability store."""
    ev = event.event
    try:
        from backend.observability.service import get_observability_service

        get_observability_service().record_execution_event(
            event_type="order_simulated",
            status="paper_filled",
            symbol=ev.symbol,
            correlation_id=ev.correlation_id,
            workflow_run_id=ev.workflow_id,
            payload={**ev.payload, "paper_mode": True},
        )
    except Exception as exc:
        logger.warning("execution_handler: failed to record simulated execution: %s", exc)


def _record_execution_event(
    event: TradingEventEnvelope,
    *,
    order_id: str,
    status: str,
) -> None:
    ev = event.event
    try:
        from backend.observability.service import get_observability_service

        get_observability_service().record_execution_event(
            event_type="order_placed",
            status=status,
            symbol=ev.symbol,
            correlation_id=ev.correlation_id,
            workflow_run_id=ev.workflow_id,
            payload={**ev.payload, "order_id": order_id},
        )
    except Exception as exc:
        logger.warning("execution_handler: failed to record live execution event: %s", exc)


# ---------------------------------------------------------------------------
# Notification handler
# ---------------------------------------------------------------------------


def notification_handler(event: TradingEventEnvelope) -> bool:
    """Deliver notification_requested events through the configured channels."""
    ev = event.event
    logger.info(
        "notification_handler: received %s correlation_id=%s",
        ev.event_type,
        ev.correlation_id,
    )

    if ev.event_type != "notification_requested":
        return True

    payload = ev.payload
    message = payload.get("message") or payload.get("text") or str(payload)
    title = payload.get("title") or f"Hermes alert: {ev.symbol or 'system'}"

    try:
        from backend.tools.send_notification import send_notification

        send_notification({"title": title, "message": message, "severity": payload.get("severity", "info")})
        logger.info("notification_handler: delivered notification for correlation_id=%s", ev.correlation_id)
    except Exception as exc:
        logger.warning("notification_handler: delivery failed: %s", exc)
        # Still ack — notification failures should not block the stream
    return True


# ---------------------------------------------------------------------------
# Worker builders
# ---------------------------------------------------------------------------


def build_orchestrator_worker() -> RedisStreamWorker:
    return RedisStreamWorker(group_name="orchestrator_group")


def build_notification_worker() -> RedisStreamWorker:
    return RedisStreamWorker(group_name="notifications_group")


def build_execution_worker() -> RedisStreamWorker:
    return RedisStreamWorker(group_name="execution_group")


# ---------------------------------------------------------------------------
# CLI entry-point
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run a Hermes Redis Streams worker")
    parser.add_argument("worker", choices=("orchestrator", "notifications", "execution"))
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    if args.worker == "orchestrator":
        build_orchestrator_worker().run_forever(orchestrator_handler)
        return 0

    if args.worker == "execution":
        build_execution_worker().run_forever(_handle_execution_requested)
        return 0

    build_notification_worker().run_forever(notification_handler)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
