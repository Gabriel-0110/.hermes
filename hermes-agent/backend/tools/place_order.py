from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

from backend.integrations.execution import VenueExecutionClient, select_order_venue
from backend.integrations.execution.normalization import execution_order_payload
from backend.trading.models import ExecutionOutcome, ExecutionRequest, ExecutionResult, RiskRejectionReason
from backend.trading.safety import evaluate_execution_safety
from backend.tools._helpers import envelope, provider_error, provider_ok, run_tool, validate


class PlaceOrderInput(BaseModel):
    symbol: str = Field(min_length=3, max_length=32)
    side: Literal["buy", "sell"]
    order_type: Literal["market", "limit", "stop", "stop_limit"] = "market"
    amount: float = Field(gt=0)
    price: float | None = Field(default=None, gt=0)
    stop_loss_price: float | None = Field(default=None, gt=0)
    take_profit_price: float | None = Field(default=None, gt=0)
    leverage: float | None = Field(default=None, gt=0)
    margin_mode: Literal["cross", "isolated"] | None = None
    client_order_id: str | None = Field(default=None, min_length=1, max_length=64)
    time_in_force: Literal["GTC", "IOC", "FOK"] | None = None
    post_only: bool = False
    reduce_only: bool = False
    close_only: bool = False
    position_side: Literal["long", "short"] | None = None
    venue: str | None = Field(default=None, min_length=2, max_length=32)
    venues: list[str] | None = None
    approval_id: str | None = Field(default=None, min_length=1, max_length=64)

    @model_validator(mode="after")
    def _validate_price_requirements(self) -> "PlaceOrderInput":
        if self.order_type in {"limit", "stop", "stop_limit"} and self.price is None:
            raise ValueError("price is required for limit and stop-style orders")
        if self.order_type == "market" and self.post_only:
            raise ValueError("post_only is not supported for market orders")
        if self.close_only:
            self.reduce_only = True
        if self.reduce_only and self.position_side is None:
            raise ValueError("position_side is required for reduce-only BitMart futures close orders")
        return self


def _is_bitmart_direct_futures_client(client: object) -> bool:
    return (
        getattr(client, "exchange_id", None) == "bitmart"
        and getattr(client, "account_type", None) in {"contract", "futures", "swap"}
    )


def _bitmart_bracket_warning_messages(order) -> list[str]:
    metadata = getattr(order, "metadata", {}) or {}
    bracket_orders = metadata.get("bitmart_bracket_orders")
    if not isinstance(bracket_orders, dict):
        return []

    warnings: list[str] = []
    for label, details in bracket_orders.items():
        if not isinstance(details, dict) or details.get("status") != "failed":
            continue
        warning = f"BitMart {label.replace('_', ' ')} bracket follow-up failed"
        if details.get("trigger_price"):
            warning += f" @ {details['trigger_price']}"
        if details.get("failure_category"):
            warning += f" [{details['failure_category']}]"
        if details.get("error"):
            warning += f": {details['error']}"
        warnings.append(warning)
    return warnings


def place_order(payload: dict | None = None) -> dict:
    def _run() -> dict:
        args = validate(PlaceOrderInput, payload or {})
        request = ExecutionRequest(
            symbol=args.symbol,
            side=args.side,
            order_type=args.order_type,
            amount=args.amount,
            price=args.price,
            leverage=args.leverage,
            margin_mode=args.margin_mode,
            stop_loss_price=args.stop_loss_price,
            take_profit_price=args.take_profit_price,
            client_order_id=args.client_order_id,
            reduce_only=args.reduce_only,
            position_side=args.position_side,
            approval_id=args.approval_id,
            metadata={"source": "backend.tools.place_order"},
        )

        def _blocked_payload(
            *,
            error: str,
            detail: str,
            reason: RiskRejectionReason,
            execution_mode: Literal["paper", "live"],
            warnings: list[str],
            payload: dict | None = None,
        ) -> dict:
            outcome = ExecutionOutcome.from_result(
                request,
                ExecutionResult.blocked(
                    symbol=request.symbol,
                    execution_mode=execution_mode,
                    reason=reason,
                    error_message=detail if error == "live_trading_disabled" else None,
                    payload=payload,
                ),
            )
            return envelope(
                "place_order",
                [],
                {
                    "error": error,
                    "detail": detail,
                    "execution_mode": execution_mode,
                    "execution_request": outcome.request.model_dump(mode="json"),
                    "execution_result": outcome.result.model_dump(mode="json"),
                },
                warnings=warnings,
                ok=False,
            )

        safety = evaluate_execution_safety(approval_id=args.approval_id)
        if safety.execution_mode != "live":
            return _blocked_payload(
                error="paper_mode_active",
                detail="Paper trading mode is active. Real order placement is disabled.",
                reason=RiskRejectionReason.LIVE_TRADING_DISABLED,
                execution_mode=safety.execution_mode,
                warnings=["Live order placement is disabled outside explicit live mode."],
                payload={"blocking_stage": "paper_mode_guard"},
            )
        if safety.kill_switch_active:
            return _blocked_payload(
                error="kill_switch_active",
                detail=safety.kill_switch_reason or "Kill switch is active.",
                reason=RiskRejectionReason.KILL_SWITCH_ACTIVE,
                execution_mode=safety.execution_mode,
                warnings=["Kill switch is active."],
                payload={"blocking_stage": "kill_switch_guard"},
            )
        if safety.blockers:
            return _blocked_payload(
                error="live_trading_disabled",
                detail=" ".join(safety.blockers),
                reason=RiskRejectionReason.LIVE_TRADING_DISABLED,
                execution_mode=safety.execution_mode,
                warnings=list(safety.blockers),
                payload={"blocking_stage": "live_trading_guard", "blockers": list(safety.blockers)},
            )
        if safety.approval_required:
            return _blocked_payload(
                error="approval_required",
                detail="Live order placement requires an approval_id while approvals are enabled.",
                reason=RiskRejectionReason.APPROVAL_REQUIRED,
                execution_mode=safety.execution_mode,
                warnings=["Operator approval is required before live order placement."],
                payload={"blocking_stage": "approval_guard"},
            )
        routing = select_order_venue(
            symbol=args.symbol,
            side=args.side,
            amount=args.amount,
            order_type=args.order_type,
            price=args.price,
            venue=args.venue,
            venues=args.venues,
        )
        client = VenueExecutionClient(routing["selected_venue"])
        if not client.configured:
            missing = ", ".join(client.credential_env_names)
            outcome = ExecutionOutcome.from_result(
                request,
                ExecutionResult.blocked(
                    symbol=request.symbol,
                    execution_mode="live",
                    reason=RiskRejectionReason.EXCHANGE_NOT_CONFIGURED,
                    payload={"failure_stage": "provider_configuration"},
                ),
            )
            return envelope(
                "place_order",
                [provider_error(client.provider.name, f"Missing {missing}")],
                {
                    "error": "provider_not_configured",
                    "detail": f"{client.provider.name} credentials are not configured in the backend environment.",
                    "execution_request": outcome.request.model_dump(mode="json"),
                    "execution_result": outcome.result.model_dump(mode="json"),
                },
                warnings=[f"{client.provider.name} credentials are not configured in the backend environment."],
                ok=False,
            )
        if _is_bitmart_direct_futures_client(client):
            status = client.get_execution_status(symbol=args.symbol)
            if getattr(status, "readiness_status", None) != "api_execution_ready":
                support_matrix = getattr(status, "support_matrix", None)
                readiness = getattr(status, "readiness", None)
                blockers = []
                if isinstance(support_matrix, dict):
                    blockers = list(support_matrix.get("blockers") or [])
                if not blockers and isinstance(readiness, dict):
                    blockers = list(readiness.get("blockers") or [])
                detail = (
                    "BitMart direct futures execution requires readiness_status='api_execution_ready'. "
                    f"Current readiness_status={getattr(status, 'readiness_status', None)!r}."
                )
                outcome = ExecutionOutcome.from_result(
                    request,
                    ExecutionResult.blocked(
                        symbol=request.symbol,
                        execution_mode="live",
                        reason=RiskRejectionReason.EXECUTION_FAILED,
                        error_message=detail,
                        payload={
                            "failure_stage": "execution_readiness",
                            "readiness_status": getattr(status, "readiness_status", None),
                            "readiness": readiness,
                            "support_matrix": support_matrix,
                        },
                    ),
                )
                return envelope(
                    "place_order",
                    [provider_error(client.provider.name, detail)],
                    {
                        "error": "execution_readiness_blocked",
                        "detail": detail,
                        "execution_request": outcome.request.model_dump(mode="json"),
                        "execution_result": outcome.result.model_dump(mode="json"),
                    },
                    warnings=blockers or [detail],
                    ok=False,
                )
        order = client.place_order(
            symbol=args.symbol,
            side=args.side,
            order_type=args.order_type,
            amount=args.amount,
            price=args.price,
            stop_loss_price=args.stop_loss_price,
            take_profit_price=args.take_profit_price,
            leverage=args.leverage,
            margin_mode=args.margin_mode,
            client_order_id=args.client_order_id,
            time_in_force=args.time_in_force,
            post_only=args.post_only,
            reduce_only=args.reduce_only,
            position_side=args.position_side,
        )
        data = order.model_dump(mode="json")
        outcome = ExecutionOutcome.from_result(
            request,
            ExecutionResult.success_result(
                symbol=order.symbol,
                order_id=order.order_id,
                execution_mode="live",
                payload={"exchange_order": execution_order_payload(order, request_id=request.request_id, idempotency_key=request.idempotency_key, routing=routing)},
            ),
        )
        bracket_warnings = _bitmart_bracket_warning_messages(order)
        data["routing"] = routing
        data["execution_request"] = outcome.request.model_dump(mode="json")
        data["execution_result"] = outcome.result.model_dump(mode="json")
        if bracket_warnings:
            data["bracket_status"] = (order.metadata or {}).get("bitmart_bracket_status") or "partial_failure"
            data["bracket_warnings"] = bracket_warnings
        warnings = list(routing.get("warnings") or []) + bracket_warnings
        return envelope("place_order", [provider_ok(client.provider.name)], data, warnings=warnings)

    return run_tool("place_order", _run)
