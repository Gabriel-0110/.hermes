"""Hermes Redis Streams workers — orchestration, execution, and notifications."""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time

from backend.integrations.execution.normalization import execution_order_payload
from .consumer import RedisStreamWorker
from .models import TradingEvent, TradingEventEnvelope
from backend.trading.lifecycle_notifications import (
    notify_approval_required,
    notify_kill_switch_blocked,
    notify_live_execution_failed,
    notify_live_execution_submitted,
    notify_paper_execution_completed,
)

logger = logging.getLogger(__name__)

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
                    "hermes:risk:kill_switch",
                    json.dumps({"active": True, "reason": reason}),
                )
            return True
    except Exception as exc:
        logger.warning("workers: drawdown check failed: %s", exc)
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

    if ev.event_type == "whale_flow":
        return _handle_whale_flow(event)

    if ev.event_type == "execution_requested":
        return _handle_execution_requested(event)

    # Other event types are logged and acknowledged.
    logger.debug("orchestrator_handler: no specific handler for %s — acking", ev.event_type)
    return True


def _tool_ok(response: dict | None) -> bool:
    return bool((response or {}).get("meta", {}).get("ok"))


def _tool_data(response: dict | None, default):
    if not isinstance(response, dict):
        return default
    data = response.get("data")
    return default if data is None else data


def _normalize_signal_direction(value: str | None) -> str | None:
    normalized = str(value or "").strip().lower()
    if not normalized:
        return None
    if normalized in {"buy", "bullish", "long"}:
        return "long"
    if normalized in {"sell", "bearish", "short"}:
        return "short"
    if normalized in {"close", "exit", "flat"}:
        return "flat"
    return normalized


def _strategy_market_data_symbol(symbol: str) -> str:
    normalized = str(symbol or "").strip().upper()
    if not normalized:
        return normalized
    if "/" in normalized:
        return normalized
    for quote in ("USDT", "USDC", "USD", "BTC", "ETH"):
        if normalized.endswith(quote) and len(normalized) > len(quote):
            base = normalized[: -len(quote)]
            return f"{base}/{quote}"
    return f"{normalized}/USD"


def _funding_symbol(symbol: str) -> str:
    normalized = str(symbol or "").strip().upper().replace("/", "")
    if not normalized:
        return normalized
    if normalized.endswith("USDT"):
        return normalized
    if normalized.endswith("USD"):
        return normalized[:-3] + "USDT"
    return f"{normalized}USDT"


def _fetch_market_regime() -> str:
    try:
        from backend.tools.get_market_overview import get_market_overview

        response = get_market_overview({})
        if not _tool_ok(response):
            return "unknown"
        data = _tool_data(response, {})
        if not isinstance(data, dict):
            return "unknown"
        return str(data.get("regime") or data.get("market_regime") or "unknown")
    except Exception as exc:
        logger.warning("signal_ready_worker: get_market_overview failed: %s", exc)
        return "unknown"


def _fetch_indicator_data(symbol: str, timeframe: str) -> dict:
    try:
        from backend.tools.get_indicator_snapshot import get_indicator_snapshot

        response = get_indicator_snapshot({"symbol": symbol, "interval": timeframe})
        data = _tool_data(response, {})
        return data if isinstance(data, dict) else {}
    except Exception as exc:
        logger.warning("signal_ready_worker: get_indicator_snapshot failed for %s: %s", symbol, exc)
        return {}


def _fetch_ohlcv_bars(symbol: str, timeframe: str) -> list[dict]:
    try:
        from backend.tools.get_ohlcv import get_ohlcv

        response = get_ohlcv({"symbol": symbol, "interval": timeframe, "limit": 30})
        data = _tool_data(response, [])
        return data if isinstance(data, list) else []
    except Exception as exc:
        logger.warning("signal_ready_worker: get_ohlcv failed for %s: %s", symbol, exc)
        return []


def _fetch_order_book_data(symbol: str) -> dict:
    try:
        from backend.tools.get_order_book import get_order_book

        response = get_order_book({"symbol": symbol, "limit": 20})
        data = _tool_data(response, {})
        return data if isinstance(data, dict) else {}
    except Exception as exc:
        logger.warning("signal_ready_worker: get_order_book failed for %s: %s", symbol, exc)
        return {}


def _fetch_funding_data(symbol: str) -> dict:
    try:
        from backend.tools.get_funding_rates import get_funding_rates

        response = get_funding_rates({"symbols": [_funding_symbol(symbol)], "limit": 1})
        data = _tool_data(response, {})
        return data if isinstance(data, dict) else {}
    except Exception as exc:
        logger.warning("signal_ready_worker: get_funding_rates failed for %s: %s", symbol, exc)
        return {}


def _default_size_usd_for_strategy(strategy_name: str) -> float:
    try:
        from backend.strategies.runners import BOT_RUNNER_REGISTRY

        runner_cls = BOT_RUNNER_REGISTRY.get(strategy_name)
        if runner_cls is not None:
            return float(getattr(runner_cls, "default_size_usd", 50.0))
    except Exception as exc:
        logger.debug("signal_ready_worker: runner lookup failed for %s: %s", strategy_name, exc)
    return 50.0


def _score_tradingview_candidate(
    *,
    strategy_name: str,
    symbol: str,
    timeframe: str,
):
    from backend.strategies.registry import get_strategy_scorer

    scorer = get_strategy_scorer(strategy_name)
    regime = _fetch_market_regime()
    indicator_data = _fetch_indicator_data(_strategy_market_data_symbol(symbol), timeframe)
    funding_data = _fetch_funding_data(symbol)

    if strategy_name == "momentum":
        return scorer(symbol, indicator_data, regime=regime, funding_data=funding_data)
    if strategy_name == "mean_reversion":
        return scorer(symbol, indicator_data, regime=regime, funding_data=funding_data)
    if strategy_name == "breakout":
        return scorer(
            symbol,
            indicator_data,
            ohlcv_bars=_fetch_ohlcv_bars(_strategy_market_data_symbol(symbol), timeframe),
            order_book_data=_fetch_order_book_data(_funding_symbol(symbol)),
            regime=regime,
            funding_data=funding_data,
        )

    raise ValueError(f"Unsupported strategy for TradingView signal scoring: {strategy_name}")


def _handle_signal_ready(event: TradingEventEnvelope) -> bool:
    """Score a TradingView signal and dispatch an execution proposal when actionable."""
    ev = event.event
    payload = ev.payload or {}
    symbol = str(ev.symbol or payload.get("symbol") or "").strip().upper()
    if not symbol:
        logger.warning("signal_ready_worker: missing symbol for event_id=%s", ev.event_id)
        return True

    try:
        from backend.observability.service import get_observability_service
        from backend.strategies.registry import STRATEGY_REGISTRY, resolve_strategy_name
        from backend.trading import dispatch_trade_proposal
        from backend.trading.bot_runner import proposal_from_candidate

        observability = get_observability_service()
        strategy_name = resolve_strategy_name(
            payload.get("strategy"),
            payload.get("alert_name"),
            payload.get("signal"),
        )
        if strategy_name is None:
            logger.warning(
                "signal_ready_worker: no registered strategy matched alert_id=%s strategy=%r alert_name=%r",
                ev.alert_id,
                payload.get("strategy"),
                payload.get("alert_name"),
            )
            observability.record_execution_event(
                status="ignored",
                event_type="tradingview_signal_ignored",
                symbol=symbol,
                correlation_id=ev.correlation_id,
                workflow_run_id=ev.workflow_id,
                payload={
                    "reason": "unmatched_strategy",
                    "alert_id": ev.alert_id,
                    "strategy": payload.get("strategy"),
                    "alert_name": payload.get("alert_name"),
                },
            )
            return True

        strategy_def = STRATEGY_REGISTRY[strategy_name]
        timeframe = str(payload.get("timeframe") or strategy_def.timeframes[0] or "1h")
        candidate = _score_tradingview_candidate(
            strategy_name=strategy_name,
            symbol=symbol,
            timeframe=timeframe,
        )
        observability.record_agent_decision(
            agent_name="strategy_agent",
            status="completed",
            decision=candidate.direction,
            summarized_input={"event": ev.model_dump(mode="json")},
            summarized_output={"candidate": candidate.model_dump(mode="json")},
            metadata={"strategy_name": strategy_name, "alert_id": ev.alert_id},
        )

        requested_direction = _normalize_signal_direction(payload.get("direction") or payload.get("signal"))
        if requested_direction == "flat":
            observability.record_execution_event(
                status="ignored",
                event_type="tradingview_signal_ignored",
                symbol=symbol,
                correlation_id=ev.correlation_id,
                workflow_run_id=ev.workflow_id,
                payload={
                    "reason": "flat_signal",
                    "candidate": candidate.model_dump(mode="json"),
                    "alert_id": ev.alert_id,
                },
            )
            return True

        if requested_direction in {"long", "short"} and candidate.direction != requested_direction:
            logger.info(
                "signal_ready_worker: scorer direction mismatch for alert_id=%s expected=%s actual=%s",
                ev.alert_id,
                requested_direction,
                candidate.direction,
            )
            observability.record_execution_event(
                status="ignored",
                event_type="tradingview_signal_ignored",
                symbol=symbol,
                correlation_id=ev.correlation_id,
                workflow_run_id=ev.workflow_id,
                payload={
                    "reason": "direction_mismatch",
                    "expected_direction": requested_direction,
                    "candidate": candidate.model_dump(mode="json"),
                    "alert_id": ev.alert_id,
                },
            )
            return True

        if candidate.direction == "watch" or candidate.confidence < strategy_def.min_confidence:
            logger.info(
                "signal_ready_worker: candidate filtered for alert_id=%s direction=%s confidence=%.2f",
                ev.alert_id,
                candidate.direction,
                candidate.confidence,
            )
            observability.record_execution_event(
                status="ignored",
                event_type="tradingview_signal_filtered",
                symbol=symbol,
                correlation_id=ev.correlation_id,
                workflow_run_id=ev.workflow_id,
                payload={
                    "reason": "watch_or_low_confidence",
                    "min_confidence": strategy_def.min_confidence,
                    "candidate": candidate.model_dump(mode="json"),
                    "alert_id": ev.alert_id,
                },
            )
            return True

        proposal = proposal_from_candidate(
            candidate,
            size_usd=_default_size_usd_for_strategy(strategy_name),
            source_agent="tradingview_signal_worker",
            strategy_id=f"tradingview/{strategy_name}",
            timeframe=timeframe,
            metadata={
                "source_event_type": ev.event_type,
                "source_alert_id": ev.alert_id,
                "source_event_id": ev.event_id,
                "source_correlation_id": ev.correlation_id,
                "alert_name": payload.get("alert_name"),
                "alert_strategy": payload.get("strategy"),
                "signal": payload.get("signal"),
                "direction": payload.get("direction"),
                "price": payload.get("price"),
            },
        )
        dispatch_result = dispatch_trade_proposal(proposal)
        logger.info(
            "signal_ready_worker: dispatched proposal_id=%s strategy=%s symbol=%s status=%s",
            proposal.proposal_id,
            strategy_name,
            symbol,
            dispatch_result.status,
        )
        observability.record_execution_event(
            status=dispatch_result.status,
            event_type="tradingview_signal_dispatched",
            symbol=symbol,
            correlation_id=ev.correlation_id,
            workflow_run_id=ev.workflow_id,
            payload={
                "alert_id": ev.alert_id,
                "strategy_name": strategy_name,
                "candidate": candidate.model_dump(mode="json"),
                "proposal_id": proposal.proposal_id,
                "dispatch_status": dispatch_result.status,
            },
        )
        return True

    except ValueError as exc:
        logger.warning(
            "signal_ready_worker: invalid tradingview signal event_id=%s symbol=%s: %s",
            ev.event_id,
            symbol,
            exc,
        )
        return True

    except Exception as exc:
        logger.exception(
            "signal_ready_worker: failed for event_id=%s symbol=%s: %s",
            ev.event_id,
            symbol,
            exc,
        )
        return False


def _handle_whale_flow(event: TradingEventEnvelope) -> bool:
    """Convert a whale-flow event into a standard trade proposal when actionable."""
    ev = event.event
    payload = ev.payload or {}
    symbol = str(ev.symbol or payload.get("symbol") or "").strip().upper()
    if not symbol:
        logger.warning("whale_flow_worker: missing symbol for event_id=%s", ev.event_id)
        return True

    try:
        from backend.observability.service import get_observability_service
        from backend.strategies.registry import STRATEGY_REGISTRY
        from backend.strategies.whale_follower import build_whale_follow_proposal, score_whale_follower
        from backend.trading import dispatch_trade_proposal

        observability = get_observability_service()
        candidate = score_whale_follower(symbol, payload, regime=_fetch_market_regime())
        observability.record_agent_decision(
            agent_name="strategy_agent",
            status="completed",
            decision=candidate.direction,
            summarized_input={"event": ev.model_dump(mode="json")},
            summarized_output={"candidate": candidate.model_dump(mode="json")},
            metadata={"strategy_name": "whale_follower", "event_id": ev.event_id},
        )

        strategy_def = STRATEGY_REGISTRY["whale_follower"]
        if candidate.direction == "watch" or candidate.confidence < strategy_def.min_confidence:
            observability.record_execution_event(
                status="ignored",
                event_type="whale_flow_filtered",
                symbol=symbol,
                correlation_id=ev.correlation_id,
                workflow_run_id=ev.workflow_id,
                payload={
                    "reason": "watch_or_low_confidence",
                    "min_confidence": strategy_def.min_confidence,
                    "candidate": candidate.model_dump(mode="json"),
                    "source_event_id": ev.event_id,
                },
            )
            return True

        proposal = build_whale_follow_proposal(candidate, payload, source_agent="whale_flow_worker")
        dispatch_result = dispatch_trade_proposal(proposal)
        logger.info(
            "whale_flow_worker: dispatched proposal_id=%s symbol=%s status=%s",
            proposal.proposal_id,
            symbol,
            dispatch_result.status,
        )
        observability.record_execution_event(
            status=dispatch_result.status,
            event_type="whale_flow_dispatched",
            symbol=symbol,
            correlation_id=ev.correlation_id,
            workflow_run_id=ev.workflow_id,
            payload={
                "candidate": candidate.model_dump(mode="json"),
                "proposal_id": proposal.proposal_id,
                "dispatch_status": dispatch_result.status,
                "source_event_id": ev.event_id,
            },
        )
        return True

    except ValueError as exc:
        logger.warning(
            "whale_flow_worker: invalid whale_flow event_id=%s symbol=%s: %s",
            ev.event_id,
            symbol,
            exc,
        )
        return True

    except Exception as exc:
        logger.exception(
            "whale_flow_worker: failed for event_id=%s symbol=%s: %s",
            ev.event_id,
            symbol,
            exc,
        )
        return False


def _handle_execution_requested(event: TradingEventEnvelope) -> bool:
    """Route an approved execution request through the CCXT client (paper-mode safe)."""
    ev = event.event
    try:
        from backend.trading.models import ExecutionRequest

        request = ExecutionRequest.model_validate(ev.payload)
    except Exception as exc:
        logger.error(
            "execution_handler: malformed execution_requested payload for event_id=%s: %s",
            ev.event_id,
            exc,
        )
        return True
    payload = request.model_dump(mode="json")
    logger.info(
        "execution_handler: received execution_requested request_id=%s proposal_id=%s idempotency_key=%s symbol=%s",
        request.request_id,
        request.proposal_id,
        request.idempotency_key,
        request.symbol,
    )

    # Drawdown check — auto-trigger kill switch if breach detected
    if _check_and_enforce_drawdown():
        logger.warning(
            "execution_handler: drawdown limit breached — kill switch activated, "
            "rejecting execution_requested for symbol=%s",
            ev.symbol,
        )
        from backend.trading.models import ExecutionOutcome, ExecutionResult, RiskRejectionReason

        _record_execution_event(
            event,
            outcome=ExecutionOutcome.from_result(
                request,
                ExecutionResult.blocked(
                    symbol=request.symbol,
                    execution_mode="paper" if os.getenv("HERMES_TRADING_MODE", "paper").lower() != "live" else "live",
                    reason=RiskRejectionReason.DRAWDOWN_LIMIT_BREACHED,
                    correlation_id=ev.correlation_id,
                    workflow_id=ev.workflow_id,
                    payload={**payload, "blocking_stage": "drawdown_guard"},
                ),
            ),
        )
        notify_kill_switch_blocked(
            symbol=ev.symbol or request.symbol or "unknown",
            reason="Drawdown limit breached — kill switch auto-activated.",
            trigger="drawdown",
        )
        return True

    from backend.trading.safety import evaluate_execution_safety

    safety = evaluate_execution_safety(approval_id=payload.get("approval_id"))

    # Hard kill-switch check
    if safety.kill_switch_active:
        logger.warning(
            "execution_handler: kill switch active — rejecting execution_requested for symbol=%s",
            ev.symbol,
        )
        from backend.trading.models import ExecutionOutcome, ExecutionResult, RiskRejectionReason

        _record_execution_event(
            event,
            outcome=ExecutionOutcome.from_result(
                request,
                ExecutionResult.blocked(
                    symbol=request.symbol,
                    execution_mode=safety.execution_mode,
                    reason=RiskRejectionReason.KILL_SWITCH_ACTIVE,
                    correlation_id=ev.correlation_id,
                    workflow_id=ev.workflow_id,
                    payload={**payload, "blocking_stage": "kill_switch_guard"},
                ),
            ),
        )
        notify_kill_switch_blocked(
            symbol=ev.symbol or request.symbol or "unknown",
            reason=safety.kill_switch_reason,
            trigger="kill_switch",
        )
        return True

    if safety.blockers:
        logger.warning(
            "execution_handler: live trading blocked for request_id=%s symbol=%s blockers=%s",
            request.request_id,
            ev.symbol,
            safety.blockers,
        )
        from backend.trading.models import ExecutionOutcome, ExecutionResult, RiskRejectionReason

        _record_execution_event(
            event,
            outcome=ExecutionOutcome.from_result(
                request,
                ExecutionResult.blocked(
                    symbol=request.symbol,
                    execution_mode=safety.execution_mode,
                    reason=RiskRejectionReason.LIVE_TRADING_DISABLED,
                    correlation_id=ev.correlation_id,
                    workflow_id=ev.workflow_id,
                    error_message=" ".join(safety.blockers),
                    payload={**payload, "blocking_stage": "live_trading_guard", "blockers": list(safety.blockers)},
                ),
            ),
        )
        return True

    # Operator approval gate: if HERMES_REQUIRE_APPROVAL is enabled, hold the
    # request in the pending queue until an operator ACKs it via the API.
    # Requests that already carry an approval_id have passed the gate.
    if safety.approval_required:
        try:
            from backend.approvals import create_approval_request

            approval_id = create_approval_request(
                payload=payload,
                correlation_id=ev.correlation_id or ev.event_id,
                symbol=ev.symbol,
                side=request.side,
                amount=request.amount or request.size_usd,
                proposal_id=request.proposal_id,
                execution_mode=safety.execution_mode,
            )
            logger.info(
                "execution_handler: approval required — gating execution for symbol=%s "
                "approval_id=%s",
                ev.symbol,
                approval_id,
            )
            notify_approval_required(
                proposal_id=request.proposal_id or "",
                symbol=ev.symbol or request.symbol or "unknown",
                side=request.side,
                size_usd=float(request.amount or request.size_usd or 0),
                execution_mode=safety.execution_mode,
                approval_id=approval_id,
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
    if safety.execution_mode != "live":
        logger.info(
            "execution_handler: PAPER MODE — simulating execution for symbol=%s side=%s amount=%s paired=%s",
            ev.symbol,
            request.side,
            request.amount,
            bool(request.legs),
        )
        _record_simulated_execution(event)
        notify_paper_execution_completed(
            symbol=ev.symbol or request.symbol or "unknown",
            side="paired" if request.legs else request.side,
            size_usd=float(request.size_usd or request.amount or 0),
            proposal_id=request.proposal_id,
            correlation_id=ev.correlation_id,
        )
        return True

    return _place_live_order(event, request=request)


def _resolve_order_amount(payload: dict, *, prefer_size_usd: bool = False) -> float:
    """Resolve a base-unit order amount from the event payload.

    Workflow-sourced events carry ``size_usd`` (notional USD) rather than a
    base-unit quantity.  When that is the case we attempt a best-effort price
    lookup and divide.  A direct ``amount`` field in the payload always wins.
    """
    # Direct amount takes priority for manual /execution/place calls. Workflow
    # proposals usually carry USD notional, so live workers should prefer
    # size_usd conversion when both fields are present.
    if payload.get("amount") is not None and not prefer_size_usd:
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


def _place_paired_live_order(event: TradingEventEnvelope, *, request) -> bool:
    """Place a paired multi-leg order with best-effort rollback on failure."""
    ev = event.event
    from backend.integrations.execution import VenueExecutionClient
    from backend.trading.models import ExecutionOutcome, ExecutionResult

    payload = request.model_dump(mode="json")
    placed_legs: list[tuple[object, object, float]] = []

    try:
        for leg in request.legs:
            client = VenueExecutionClient(leg.venue, account_type=leg.account_type)
            if not client.configured:
                raise ValueError(f"{leg.venue}:{leg.account_type} execution client is not configured")

            amount = _clamp_order_amount(
                _resolve_order_amount(
                    {
                        "symbol": leg.symbol,
                        "amount": leg.amount,
                        "size_usd": leg.size_usd,
                    },
                    prefer_size_usd=leg.amount is None and leg.size_usd is not None,
                ),
                leg.symbol,
            )
            order = client.place_order(
                symbol=leg.symbol,
                side=leg.side,
                order_type=leg.order_type,
                amount=amount,
                price=float(leg.price) if leg.price is not None else None,
                client_order_id=leg.client_order_id,
                reduce_only=leg.reduce_only,
                position_side=leg.position_side,
            )
            placed_legs.append((leg, order, amount))

        result = ExecutionResult.success_result(
            symbol=request.symbol,
            order_id=",".join(str(getattr(order, "order_id", "") or "") for _, order, _ in placed_legs),
            execution_mode="live",
            correlation_id=ev.correlation_id,
            workflow_id=ev.workflow_id,
            payload={
                **payload,
                "paired_execution": True,
                "execution_legs": [
                    {
                        "leg_id": leg.leg_id,
                        "venue": leg.venue,
                        "account_type": leg.account_type,
                        "requested_amount": amount,
                        "exchange_order": execution_order_payload(
                            order,
                            request_id=request.request_id,
                            idempotency_key=request.idempotency_key,
                        ),
                    }
                    for leg, order, amount in placed_legs
                ],
            },
        )
        _record_execution_event(event, outcome=ExecutionOutcome.from_result(request, result))
        notify_live_execution_submitted(
            symbol=request.symbol,
            side="paired",
            order_id=result.order_id or "",
            amount=float(request.size_usd or 0),
            proposal_id=request.proposal_id,
            correlation_id=ev.correlation_id,
        )
        return True

    except Exception as exc:
        rollback_results: list[dict[str, object]] = []
        rollback_failed = False

        for leg, _order, amount in reversed(placed_legs):
            try:
                client = VenueExecutionClient(leg.venue, account_type=leg.account_type)
                unwind_order = client.place_order(
                    symbol=leg.symbol,
                    side="sell" if leg.side == "buy" else "buy",
                    order_type="market",
                    amount=amount,
                    client_order_id=f"{leg.client_order_id or leg.leg_id}-rollback",
                    reduce_only=leg.account_type in {"swap", "futures", "contract"},
                    position_side=leg.position_side,
                )
                rollback_results.append(
                    {
                        "leg_id": leg.leg_id,
                        "rolled_back": True,
                        "rollback_order": execution_order_payload(
                            unwind_order,
                            request_id=request.request_id,
                            idempotency_key=request.idempotency_key,
                        ),
                    }
                )
            except Exception as rollback_exc:
                rollback_failed = True
                rollback_results.append(
                    {
                        "leg_id": leg.leg_id,
                        "rolled_back": False,
                        "error": str(rollback_exc),
                    }
                )

        result = ExecutionResult.failed(
            symbol=request.symbol,
            execution_mode="live",
            correlation_id=ev.correlation_id,
            workflow_id=ev.workflow_id,
            error_message=str(exc),
            payload={
                **payload,
                "paired_execution": True,
                "failure_stage": "paired_exchange_submission",
                "placed_legs": [
                    {
                        "leg_id": leg.leg_id,
                        "venue": leg.venue,
                        "account_type": leg.account_type,
                        "requested_amount": amount,
                        "exchange_order": execution_order_payload(
                            order,
                            request_id=request.request_id,
                            idempotency_key=request.idempotency_key,
                        ),
                    }
                    for leg, order, amount in placed_legs
                ],
                "rollback": rollback_results,
            },
        )
        _record_execution_event(event, outcome=ExecutionOutcome.from_result(request, result))
        notify_live_execution_failed(
            symbol=ev.symbol or request.symbol or "unknown",
            side="paired",
            error=str(exc),
            proposal_id=request.proposal_id,
            correlation_id=ev.correlation_id,
        )
        return bool(placed_legs) and not rollback_failed


def _place_live_order(event: TradingEventEnvelope, *, request=None) -> bool:
    """Place a real order via CCXTExecutionClient."""
    ev = event.event
    from backend.trading.models import ExecutionOutcome, ExecutionRequest, ExecutionResult, RiskRejectionReason

    request = request or ExecutionRequest.model_validate(ev.payload)
    if request.legs:
        return _place_paired_live_order(event, request=request)

    payload = request.model_dump(mode="json")

    try:
        from backend.integrations.execution import VenueExecutionClient
        from backend.integrations.base import IntegrationError, MissingCredentialError

        client = VenueExecutionClient("bitmart")
        if not client.configured:
            logger.error(
                "execution_handler: BitMart not configured — cannot place order for symbol=%s",
                ev.symbol,
            )
            result = ExecutionResult.blocked(
                symbol=request.symbol,
                execution_mode="live",
                reason=RiskRejectionReason.EXCHANGE_NOT_CONFIGURED,
                correlation_id=ev.correlation_id,
                workflow_id=ev.workflow_id,
                payload={**payload, "failure_stage": "exchange_configuration"},
            )
            _record_execution_event(event, outcome=ExecutionOutcome.from_result(request, result))
            return True  # ack to avoid poison-pill loop

        status = client.get_execution_status(symbol=request.symbol or ev.symbol)
        if getattr(status, "readiness_status", None) != "api_execution_ready":
            detail = (
                "BitMart direct futures execution requires readiness_status='api_execution_ready'. "
                f"Current readiness_status={getattr(status, 'readiness_status', None)!r}."
            )
            result = ExecutionResult.blocked(
                symbol=request.symbol,
                execution_mode="live",
                reason=RiskRejectionReason.EXECUTION_FAILED,
                correlation_id=ev.correlation_id,
                workflow_id=ev.workflow_id,
                error_message=detail,
                payload={
                    **payload,
                    "failure_stage": "execution_readiness",
                    "readiness_status": getattr(status, "readiness_status", None),
                    "readiness": getattr(status, "readiness", None),
                    "support_matrix": getattr(status, "support_matrix", None),
                },
            )
            _record_execution_event(event, outcome=ExecutionOutcome.from_result(request, result))
            return True

        order = client.place_order(
            symbol=request.symbol or ev.symbol or "",
            side=request.side,
            order_type=request.order_type,
            amount=_clamp_order_amount(
                _resolve_order_amount(payload, prefer_size_usd=payload.get("size_usd") is not None),
                request.symbol or ev.symbol or "",
            ),
            price=float(request.price) if request.price is not None else None,
            client_order_id=request.client_order_id,
        )
        logger.info(
            "execution_handler: live order placed request_id=%s order_id=%s symbol=%s",
            request.request_id,
            order.order_id,
            order.symbol,
        )
        result = ExecutionResult.success_result(
            symbol=order.symbol,
            order_id=order.order_id,
            execution_mode="live",
            correlation_id=ev.correlation_id,
            workflow_id=ev.workflow_id,
            payload={
                **payload,
                "request_id": request.request_id,
                "idempotency_key": request.idempotency_key,
                "exchange_order": execution_order_payload(
                    order,
                    request_id=request.request_id,
                    idempotency_key=request.idempotency_key,
                ),
            },
        )
        _record_execution_event(event, outcome=ExecutionOutcome.from_result(request, result))
        notify_live_execution_submitted(
            symbol=order.symbol,
            side=request.side,
            order_id=order.order_id or "",
            amount=float(request.amount or request.size_usd or 0),
            proposal_id=request.proposal_id,
            correlation_id=ev.correlation_id,
        )
        return True

    except (KeyError, TypeError, ValueError) as exc:
        logger.error(
            "execution_handler: malformed execution_requested payload for event_id=%s: %s",
            ev.event_id,
            exc,
        )
        return True  # malformed events should be acked to unblock the stream

    except Exception as exc:
        result = ExecutionResult.failed(
            symbol=request.symbol,
            execution_mode="live",
            correlation_id=ev.correlation_id,
            workflow_id=ev.workflow_id,
            error_message=str(exc),
            payload={**payload, "failure_stage": "exchange_submission"},
        )
        _record_execution_event(event, outcome=ExecutionOutcome.from_result(request, result))
        logger.exception(
            "execution_handler: unexpected error placing order request_id=%s symbol=%s: %s",
            request.request_id,
            ev.symbol,
            exc,
        )
        notify_live_execution_failed(
            symbol=ev.symbol or request.symbol or "unknown",
            side=request.side,
            error=str(exc),
            proposal_id=request.proposal_id,
            correlation_id=ev.correlation_id,
        )
        return False  # transient — leave unacked for retry


def _record_simulated_execution(event: TradingEventEnvelope) -> None:
    """Persist a paper-mode execution event in the observability store."""
    ev = event.event
    try:
        from backend.observability.service import get_observability_service
        from backend.trading.models import ExecutionOutcome, ExecutionRequest, ExecutionResult

        request = ExecutionRequest.model_validate(ev.payload)
        result = ExecutionResult.success_result(
            symbol=request.symbol,
            order_id=None,
            execution_mode="paper",
            correlation_id=ev.correlation_id,
            workflow_id=ev.workflow_id,
            payload={
                **request.model_dump(mode="json"),
                "request_id": request.request_id,
                "idempotency_key": request.idempotency_key,
                "paper_mode": True,
                "paired_execution": bool(request.legs),
            },
        )
        outcome = ExecutionOutcome.from_result(request, result)

        get_observability_service().record_execution_event(
            event_type="order_simulated",
            status="paper_filled",
            symbol=ev.symbol,
            correlation_id=ev.correlation_id,
            workflow_run_id=ev.workflow_id,
            payload={"execution_outcome": outcome.model_dump(mode="json")},
        )
        get_observability_service().record_movement(
            movement_type="order_simulated",
            status="paper_filled",
            symbol=request.symbol,
            side=request.side,
            quantity=request.amount,
            notional_delta_usd=request.size_usd,
            price=request.price,
            execution_mode=result.execution_mode,
            order_id=result.order_id,
            request_id=request.request_id,
            idempotency_key=request.idempotency_key,
            source_kind="execution_worker.paper",
            correlation_id=ev.correlation_id,
            workflow_run_id=ev.workflow_id,
            event_id=ev.event_id,
            payload={"execution_outcome": outcome.model_dump(mode="json")},
            metadata={"proposal_id": request.proposal_id},
        )
        if not request.legs:
            try:
                from backend.trading.position_manager import apply_execution_outcome_to_portfolio

                apply_execution_outcome_to_portfolio(outcome)
            except Exception as exc:
                logger.warning("execution_handler: failed to project paper execution into portfolio snapshot: %s", exc)
    except Exception as exc:
        logger.warning("execution_handler: failed to record simulated execution: %s", exc)


def _record_execution_event(
    event: TradingEventEnvelope,
    *,
    outcome,
) -> None:
    ev = event.event
    try:
        from backend.observability.service import get_observability_service

        result = outcome.result
        event_type = "order_placed"
        if result.status == "blocked":
            event_type = "order_blocked"
        elif result.status == "failed":
            event_type = "order_failed"

        get_observability_service().record_execution_event(
            event_type=event_type,
            status=result.status,
            symbol=ev.symbol,
            correlation_id=ev.correlation_id,
            workflow_run_id=ev.workflow_id,
            summarized_input={"execution_request": outcome.request.model_dump(mode="json")},
            summarized_output={"execution_result": result.model_dump(mode="json")},
            metadata={
                "execution_request_id": outcome.request.request_id,
                "idempotency_key": outcome.request.idempotency_key,
                "proposal_id": outcome.request.proposal_id,
            },
        )
        get_observability_service().record_movement(
            movement_type=event_type,
            status=result.status,
            symbol=outcome.request.symbol,
            side=outcome.request.side,
            quantity=outcome.request.amount,
            notional_delta_usd=outcome.request.size_usd,
            price=outcome.request.price,
            execution_mode=result.execution_mode,
            order_id=result.order_id,
            request_id=outcome.request.request_id,
            idempotency_key=outcome.request.idempotency_key,
            source_kind="execution_worker.live",
            correlation_id=ev.correlation_id,
            workflow_run_id=ev.workflow_id,
            event_id=ev.event_id,
            payload={
                "execution_request": outcome.request.model_dump(mode="json"),
                "execution_result": result.model_dump(mode="json"),
            },
            metadata={"proposal_id": outcome.request.proposal_id},
        )
        if result.success and not outcome.request.legs:
            try:
                from backend.trading.position_manager import apply_execution_outcome_to_portfolio

                apply_execution_outcome_to_portfolio(outcome)
            except Exception as exc:
                logger.warning("execution_handler: failed to refresh portfolio after execution outcome: %s", exc)
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


def _coerce_symbol_list(value: str | list[str] | None) -> list[str] | None:
    if value is None:
        return None
    if isinstance(value, str):
        tokens = [token.strip().upper() for token in value.split(",") if token.strip()]
        return tokens or None

    tokens = [str(token or "").strip().upper() for token in value if str(token or "").strip()]
    return tokens or None


def run_funding_spread_watcher_once(
    *,
    symbols: str | list[str] | None = None,
    venues: str | list[str] | None = None,
    limit: int = 20,
    threshold: float = 0.0002,
) -> list[TradingEventEnvelope]:
    """Scan aggregate funding rates and publish cross-venue spread events."""
    from backend.event_bus.publisher import publish_trading_event
    from backend.tools.get_funding_rates import get_funding_rates

    requested_symbols = _coerce_symbol_list(symbols)
    response = get_funding_rates(
        {
            "symbols": requested_symbols,
            "limit": limit,
            "venue": venues if venues is not None else "all",
        }
    )
    if not _tool_ok(response):
        logger.warning("funding_spread_watcher: get_funding_rates returned non-ok response")
        return []

    data = _tool_data(response, {})
    if not isinstance(data, dict):
        return []

    spread_rows = data.get("symbols") if data.get("aggregated") else []
    if not isinstance(spread_rows, list):
        return []

    published: list[TradingEventEnvelope] = []
    for row in spread_rows:
        if not isinstance(row, dict):
            continue

        symbol = str(row.get("symbol") or "").upper()
        funding_spread = float(row.get("funding_spread_8h") or 0.0)
        if not symbol or abs(funding_spread) < threshold:
            continue

        max_venue = row.get("max_funding_venue")
        min_venue = row.get("min_funding_venue")
        event = TradingEvent(
            event_type="funding_spread_detected",
            symbol=symbol,
            correlation_id=f"funding-spread::{symbol}",
            producer="funding_spread_watcher",
            workflow_id=f"watcher::funding_spread::{symbol}",
            payload={
                "symbol": symbol,
                "funding_spread_8h": funding_spread,
                "funding_spread_bps": row.get("funding_spread_bps"),
                "spread_threshold_8h": threshold,
                "highest_funding_leg": {
                    "venue": max_venue,
                    "exchange": row.get("max_funding_exchange"),
                    "funding_rate": row.get("max_funding_rate"),
                },
                "lowest_funding_leg": {
                    "venue": min_venue,
                    "exchange": row.get("min_funding_exchange"),
                    "funding_rate": row.get("min_funding_rate"),
                },
                "trade_hint": {
                    "short_perp_venue": max_venue,
                    "long_perp_venue": min_venue,
                    "thesis": "Funding spread exceeds the cross-venue carry watch threshold.",
                },
                "venue_details": row.get("venues") or [],
                "requested_venues": data.get("requested_venues") or [],
            },
            metadata={
                "watcher": "funding_spread",
                "threshold": threshold,
                "limit": limit,
            },
        )
        published.append(publish_trading_event(event))

    return published


def run_funding_spread_watcher_forever(
    *,
    symbols: str | list[str] | None = None,
    venues: str | list[str] | None = None,
    limit: int = 20,
    threshold: float = 0.0002,
    interval_seconds: int = 300,
) -> None:
    """Continuously poll funding spreads and publish events when thresholds trip."""
    while True:
        published = run_funding_spread_watcher_once(
            symbols=symbols,
            venues=venues,
            limit=limit,
            threshold=threshold,
        )
        logger.info(
            "funding_spread_watcher: published %s funding spread signal(s)",
            len(published),
        )
        time.sleep(max(interval_seconds, 1))


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
    parser.add_argument("worker", choices=("orchestrator", "notifications", "execution", "funding_spread_watcher"))
    parser.add_argument("--symbols", default=None, help="Comma-separated symbols for the funding spread watcher.")
    parser.add_argument("--venues", default="all", help="Venue, comma-separated venue list, or 'all' for the funding spread watcher.")
    parser.add_argument("--limit", type=int, default=20, help="Maximum symbols to scan per funding spread pass.")
    parser.add_argument("--threshold", type=float, default=0.0002, help="Minimum absolute funding spread per 8h required to publish an event.")
    parser.add_argument("--interval-seconds", type=int, default=300, help="Polling interval for the funding spread watcher.")
    parser.add_argument("--once", action="store_true", help="Run the funding spread watcher once and exit.")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    if args.worker == "orchestrator":
        build_orchestrator_worker().run_forever(orchestrator_handler)
        return 0

    if args.worker == "execution":
        build_execution_worker().run_forever(_handle_execution_requested)
        return 0

    if args.worker == "funding_spread_watcher":
        if args.once:
            run_funding_spread_watcher_once(
                symbols=args.symbols,
                venues=args.venues,
                limit=args.limit,
                threshold=args.threshold,
            )
            return 0

        run_funding_spread_watcher_forever(
            symbols=args.symbols,
            venues=args.venues,
            limit=args.limit,
            threshold=args.threshold,
            interval_seconds=args.interval_seconds,
        )
        return 0

    build_notification_worker().run_forever(notification_handler)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
