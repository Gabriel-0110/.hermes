"""Shared execution mode helpers.

Centralizes the decision for whether exchange execution should remain in paper
mode or is explicitly unlocked for live trading.
"""

from __future__ import annotations

import os
import threading
from datetime import UTC, datetime, timedelta
from typing import Any

from backend.db import HermesTimeSeriesRepository, ensure_time_series_schema, session_scope
from backend.db.session import get_engine

LIVE_TRADING_ACK_PHRASE = "I_ACKNOWLEDGE_LIVE_TRADING_RISK"
PAPER_SHADOW_ACCOUNT_ID = "paper_shadow"


def _is_truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def current_trading_mode() -> str:
    mode = os.getenv("HERMES_TRADING_MODE", "paper").strip().lower()
    return mode if mode in {"disabled", "paper", "live"} else "paper"


def is_disabled_mode() -> bool:
    return current_trading_mode() == "disabled"


def is_paper_mode() -> bool:
    explicit = os.getenv("HERMES_PAPER_MODE")
    if explicit is not None and explicit.strip() != "":
        return _is_truthy(explicit)
    return current_trading_mode() not in {"live", "disabled"}


def live_trading_blockers() -> list[str]:
    blockers: list[str] = []
    if current_trading_mode() != "live":
        blockers.append("HERMES_TRADING_MODE must be set to 'live'.")
    if not _is_truthy(os.getenv("HERMES_ENABLE_LIVE_TRADING")):
        blockers.append("HERMES_ENABLE_LIVE_TRADING=true is required.")
    if os.getenv("HERMES_LIVE_TRADING_ACK", "").strip() != LIVE_TRADING_ACK_PHRASE:
        blockers.append(
            "HERMES_LIVE_TRADING_ACK must equal "
            f"{LIVE_TRADING_ACK_PHRASE!r}."
        )
    return blockers


def live_trading_enabled() -> bool:
    return not live_trading_blockers()


def _float_or_none(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _normalize_shadow_symbols(symbol: str | None) -> tuple[str, str]:
    normalized = str(symbol or "").upper().replace("/", "").replace("-", "").strip()
    if normalized.endswith("USDT"):
        base = normalized[:-4]
        market_symbol = normalized
    elif normalized.endswith("USD"):
        base = normalized[:-3]
        market_symbol = f"{base}USDT"
    else:
        base = normalized
        market_symbol = f"{base}USDT"
    return base, market_symbol


def next_paper_shadow_fill_at(now: datetime | None = None) -> datetime:
    reference = (now or datetime.now(UTC)).astimezone(UTC)
    return reference.replace(second=0, microsecond=0) + timedelta(minutes=1)


def _fetch_shadow_mid_price(symbol: str) -> float | None:
    base_symbol, market_symbol = _normalize_shadow_symbols(symbol)

    try:
        from backend.integrations.derivatives.bitmart_public_client import BitMartPublicClient

        order_book = BitMartPublicClient().get_order_book(market_symbol, limit=5)
        if order_book.best_bid is not None and order_book.best_ask is not None:
            return round((order_book.best_bid + order_book.best_ask) / 2.0, 8)
        if order_book.best_bid is not None:
            return order_book.best_bid
        if order_book.best_ask is not None:
            return order_book.best_ask
    except Exception:
        pass

    try:
        from backend.tools.get_crypto_prices import get_crypto_prices

        response = get_crypto_prices({"symbols": [base_symbol]})
        data = response.get("data") or []
        if isinstance(data, list) and data:
            return _float_or_none(data[0].get("price"))
    except Exception:
        pass

    return None


def _live_reference_price(exchange_order: dict[str, Any] | None, fallback_price: float | None = None) -> float | None:
    if isinstance(exchange_order, dict):
        for key in ("average_price", "average", "price"):
            value = _float_or_none(exchange_order.get(key))
            if value is not None:
                return value
    return fallback_price


def _approval_reference_price(symbol: str, fallback_price: float | None = None) -> float | None:
    if fallback_price is not None:
        return fallback_price
    return _fetch_shadow_mid_price(symbol)


def _notional_for_fill(price: float | None, amount: float | None, fallback: float | None) -> float | None:
    if price is not None and amount is not None:
        return abs(price * amount)
    return fallback


def _pnl_divergence(side: str, live_reference_price: float | None, shadow_price: float | None, amount: float | None) -> float | None:
    if live_reference_price is None or shadow_price is None or amount is None:
        return None
    sign = 1.0 if str(side).lower() == "buy" else -1.0
    return sign * (shadow_price - live_reference_price) * amount


def record_paper_shadow_fill(spec: dict[str, Any], *, fill_time: datetime | None = None) -> None:
    resolved_fill_time = (fill_time or next_paper_shadow_fill_at()).astimezone(UTC)
    shadow_price = _fetch_shadow_mid_price(str(spec.get("symbol") or ""))
    live_reference_price = _float_or_none(spec.get("live_reference_price"))
    amount = _float_or_none(spec.get("amount"))
    live_notional_usd = _float_or_none(spec.get("live_notional_usd"))
    shadow_notional_usd = _notional_for_fill(shadow_price, amount, _float_or_none(spec.get("shadow_notional_usd")))

    ensure_time_series_schema(get_engine())
    with session_scope() as session:
        HermesTimeSeriesRepository(session).insert_paper_shadow_fill(
            fill_time=resolved_fill_time,
            proposal_id=spec.get("proposal_id"),
            request_id=spec.get("request_id"),
            leg_id=spec.get("leg_id"),
            correlation_id=spec.get("correlation_id"),
            workflow_run_id=spec.get("workflow_run_id"),
            strategy_id=spec.get("strategy_id"),
            strategy_template_id=spec.get("strategy_template_id"),
            source_agent=spec.get("source_agent"),
            symbol=str(spec.get("symbol") or "").upper(),
            side=str(spec.get("side") or "buy").lower(),
            execution_style=str(spec.get("execution_style") or "single"),
            live_order_id=spec.get("live_order_id"),
            live_reference_price=live_reference_price,
            shadow_price=shadow_price,
            amount=amount,
            live_notional_usd=live_notional_usd,
            shadow_notional_usd=shadow_notional_usd,
            pnl_divergence_usd=_pnl_divergence(
                str(spec.get("side") or "buy"),
                live_reference_price,
                shadow_price,
                amount,
            ),
            payload={
                "shadow_fill_at": resolved_fill_time.isoformat(),
                "paper_shadow_account_id": PAPER_SHADOW_ACCOUNT_ID,
                **(spec.get("payload") or {}),
            },
            metadata={
                **(spec.get("metadata") or {}),
                "paper_shadow": True,
            },
        )


def schedule_paper_shadow_fill(spec: dict[str, Any]) -> datetime:
    fill_at = next_paper_shadow_fill_at()
    delay = max((fill_at - datetime.now(UTC)).total_seconds(), 0.05)

    def _runner() -> None:
        try:
            record_paper_shadow_fill(spec, fill_time=fill_at)
        except Exception:
            # Best-effort only — never break live execution because the shadow book failed.
            pass

    timer = threading.Timer(delay, _runner)
    timer.daemon = True
    timer.start()
    return fill_at


def schedule_paper_shadow_for_request(request, result) -> list[str]:
    if current_trading_mode() != "live":
        return []

    payload = result.payload if isinstance(result.payload, dict) else {}
    scheduled: list[str] = []

    if request.legs and isinstance(payload.get("execution_legs"), list):
        request_legs = {leg.leg_id: leg for leg in request.legs}
        for leg_payload in payload.get("execution_legs") or []:
            if not isinstance(leg_payload, dict):
                continue
            leg = request_legs.get(str(leg_payload.get("leg_id") or ""))
            if leg is None:
                continue
            exchange_order = leg_payload.get("exchange_order") if isinstance(leg_payload.get("exchange_order"), dict) else {}
            fill_at = schedule_paper_shadow_fill(
                {
                    "proposal_id": request.proposal_id,
                    "request_id": request.request_id,
                    "leg_id": leg.leg_id,
                    "correlation_id": result.correlation_id,
                    "workflow_run_id": result.workflow_id,
                    "strategy_id": request.strategy_id,
                    "strategy_template_id": request.strategy_template_id,
                    "source_agent": request.source_agent,
                    "symbol": leg.symbol,
                    "side": leg.side,
                    "execution_style": request.execution_style,
                    "live_order_id": exchange_order.get("order_id"),
                    "live_reference_price": _live_reference_price(exchange_order, leg.price),
                    "amount": _float_or_none(leg.amount) or _float_or_none(leg_payload.get("requested_amount")),
                    "live_notional_usd": _notional_for_fill(
                        _live_reference_price(exchange_order, leg.price),
                        _float_or_none(leg.amount) or _float_or_none(leg_payload.get("requested_amount")),
                        leg.size_usd,
                    ),
                    "payload": {
                        "exchange_order": exchange_order,
                        "execution_leg": leg_payload,
                    },
                    "metadata": {"paired_execution": True, "shadow_stage": "execution"},
                }
            )
            scheduled.append(fill_at.isoformat())
        return scheduled

    exchange_order = payload.get("exchange_order") if isinstance(payload.get("exchange_order"), dict) else {}
    fill_at = schedule_paper_shadow_fill(
        {
            "proposal_id": request.proposal_id,
            "request_id": request.request_id,
            "correlation_id": result.correlation_id,
            "workflow_run_id": result.workflow_id,
            "strategy_id": request.strategy_id,
            "strategy_template_id": request.strategy_template_id,
            "source_agent": request.source_agent,
            "symbol": request.symbol,
            "side": request.side,
            "execution_style": request.execution_style,
            "live_order_id": result.order_id,
            "live_reference_price": _live_reference_price(exchange_order, request.price),
            "amount": _float_or_none(request.amount),
            "live_notional_usd": _notional_for_fill(
                _live_reference_price(exchange_order, request.price),
                _float_or_none(request.amount),
                request.size_usd,
            ),
            "payload": {"exchange_order": exchange_order},
            "metadata": {"paired_execution": False, "shadow_stage": "execution"},
        }
    )
    return [fill_at.isoformat()]


def schedule_paper_shadow_for_approved_request(
    request,
    *,
    correlation_id: str | None = None,
    workflow_run_id: str | None = None,
) -> list[str]:
    if current_trading_mode() != "live":
        return []

    scheduled: list[str] = []

    if request.legs:
        for leg in request.legs:
            reference_price = _approval_reference_price(str(leg.symbol or ""), _float_or_none(leg.price))
            fill_at = schedule_paper_shadow_fill(
                {
                    "proposal_id": request.proposal_id,
                    "request_id": request.request_id,
                    "leg_id": leg.leg_id,
                    "correlation_id": correlation_id,
                    "workflow_run_id": workflow_run_id,
                    "strategy_id": request.strategy_id,
                    "strategy_template_id": request.strategy_template_id,
                    "source_agent": request.source_agent,
                    "symbol": leg.symbol,
                    "side": leg.side,
                    "execution_style": request.execution_style,
                    "live_reference_price": reference_price,
                    "amount": _float_or_none(leg.amount),
                    "live_notional_usd": _notional_for_fill(reference_price, _float_or_none(leg.amount), leg.size_usd),
                    "payload": {"execution_leg": leg.model_dump(mode="json")},
                    "metadata": {"paired_execution": True, "shadow_stage": "approval"},
                }
            )
            scheduled.append(fill_at.isoformat())
        return scheduled

    reference_price = _approval_reference_price(str(request.symbol or ""), _float_or_none(request.price))
    fill_at = schedule_paper_shadow_fill(
        {
            "proposal_id": request.proposal_id,
            "request_id": request.request_id,
            "correlation_id": correlation_id,
            "workflow_run_id": workflow_run_id,
            "strategy_id": request.strategy_id,
            "strategy_template_id": request.strategy_template_id,
            "source_agent": request.source_agent,
            "symbol": request.symbol,
            "side": request.side,
            "execution_style": request.execution_style,
            "live_reference_price": reference_price,
            "amount": _float_or_none(request.amount),
            "live_notional_usd": _notional_for_fill(reference_price, _float_or_none(request.amount), request.size_usd),
            "payload": {"execution_request": request.model_dump(mode="json")},
            "metadata": {"paired_execution": False, "shadow_stage": "approval"},
        }
    )
    return [fill_at.isoformat()]
