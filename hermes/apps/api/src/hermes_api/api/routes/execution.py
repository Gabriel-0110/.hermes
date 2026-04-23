import os
from typing import Literal

from fastapi import APIRouter, Body, Depends, HTTPException, Path, Query

from hermes_api.domain.execution import TradeProposalPayload
from hermes_api.domain.execution import (
    BridgeExecutionDispatchResponse,
    BridgeExecutionEventsResponse,
    BridgeExecutionPlaceResponse,
    BridgeExecutionPolicyResponse,
    BridgeExecutionSafety,
    BridgeExecutionSurface,
    BridgeExecutionSurfaceResponse,
    BridgePendingSignalsResponse,
)
from hermes_api.domain.portfolio import BridgePositionMonitorResponse
from hermes_api.core.config import get_settings
from hermes_api.core.security import require_api_key
from hermes_api.integrations.hermes_agent import (
    dispatch_trade_proposal,
    evaluate_trade_proposal,
    execution_safety_status,
    HermesAgentBridgeError,
    observability_service,
    place_order,
    position_monitor_snapshot,
    tradingview_store,
)

router = APIRouter()


@router.get("/")
async def get_execution_surface() -> dict[str, object]:
    try:
        store = tradingview_store()
        service = observability_service()
        pending_events = store.list_internal_events(
            limit=20,
            event_type="tradingview_signal_ready",
            delivery_status="pending",
        )
        recent_execution_events = service.get_execution_event_history(limit=20)
        bitmart_configured = bool(os.getenv("BITMART_API_KEY") and os.getenv("BITMART_SECRET"))
        settings = get_settings()
        safety = BridgeExecutionSafety.model_validate(execution_safety_status())
        return BridgeExecutionSurfaceResponse(
            status="live",
            execution=BridgeExecutionSurface(
                exchange="BITMART",
                configured=bitmart_configured,
                trading_mode=settings.hermes_trading_mode,
                safety=safety,
                live_trading_enabled=safety.live_allowed,
                live_trading_blockers=safety.blockers,
                approval_required=safety.approval_required,
                kill_switch_active=safety.kill_switch_active,
                pending_signal_events=pending_events,
                pending_signal_count=len(pending_events),
                recent_execution_events=recent_execution_events,
            ),
        ).model_dump(mode="json")
    except HermesAgentBridgeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/signals/pending")
async def get_pending_signal_events(
    limit: int = Query(default=20, ge=1, le=100),
    symbol: str | None = Query(default=None),
) -> dict[str, object]:
    try:
        store = tradingview_store()
        rows = store.list_internal_events(
            limit=limit,
            event_type="tradingview_signal_ready",
            delivery_status="pending",
            symbol=symbol,
        )
        return BridgePendingSignalsResponse(status="live", count=len(rows), events=rows).model_dump(mode="json")
    except HermesAgentBridgeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/events")
async def get_recent_execution_events(
    limit: int = Query(default=20, ge=1, le=100),
) -> dict[str, object]:
    try:
        service = observability_service()
        rows = service.get_execution_event_history(limit=limit)
        return BridgeExecutionEventsResponse(status="live", count=len(rows), events=rows).model_dump(mode="json")
    except HermesAgentBridgeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/alerts/recent")
async def get_recent_tradingview_alerts(
    limit: int = Query(default=20, ge=1, le=100),
    symbol: str | None = Query(default=None),
    processing_status: str | None = Query(default=None),
) -> dict[str, object]:
    try:
        store = tradingview_store()
        rows = store.list_alerts(
            limit=limit,
            symbol=symbol,
            processing_status=processing_status,
        )
        return {"status": "live", "count": len(rows), "alerts": rows}
    except HermesAgentBridgeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/movements")
async def get_recent_movements(
    limit: int = Query(default=20, ge=1, le=100),
    symbol: str | None = Query(default=None),
    correlation_id: str | None = Query(default=None),
) -> dict[str, object]:
    try:
        service = observability_service()
        rows = service.get_movement_history(
            limit=limit,
            symbol=symbol,
            correlation_id=correlation_id,
        )
        return {"status": "live", "count": len(rows), "movements": rows}
    except HermesAgentBridgeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/place")
async def place_trade_order(
    symbol: str = Body(embed=True),
    side: Literal["buy", "sell"] = Body(embed=True),
    order_type: Literal["market", "limit"] = Body(default="market", embed=True),
    amount: float = Body(embed=True, gt=0),
    price: float | None = Body(default=None, embed=True),
    client_order_id: str | None = Body(default=None, embed=True),
    reduce_only: bool = Body(default=False, embed=True),
    close_only: bool = Body(default=False, embed=True),
    position_side: Literal["long", "short"] | None = Body(default=None, embed=True),
    approval_id: str | None = Body(default=None, embed=True),
    _: None = Depends(require_api_key),
) -> dict[str, object]:
    """Place a trade order directly through the configured exchange connector.

    Requires BitMart credentials in the backend environment and will be
    rejected if the global kill switch is active or trading mode is "paper".
    """
    safety = BridgeExecutionSafety.model_validate(execution_safety_status())
    if not safety.live_allowed:
        raise HTTPException(
            status_code=403,
            detail={
                "message": "Live execution is blocked.",
                "blockers": safety.blockers,
                "approval_required": safety.approval_required,
                "kill_switch_active": safety.kill_switch_active,
            },
        )
    try:
        result = place_order(
            {
                "symbol": symbol,
                "side": side,
                "order_type": order_type,
                "amount": amount,
                "price": price,
                "client_order_id": client_order_id,
                "reduce_only": reduce_only,
                "close_only": close_only,
                "position_side": position_side,
                "approval_id": approval_id,
            }
        )
        if not result.get("ok", True):
            raise HTTPException(status_code=400, detail=result)
        return BridgeExecutionPlaceResponse(status="live", order=result).model_dump(mode="json")
    except HTTPException:
        raise
    except HermesAgentBridgeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/proposals/evaluate")
async def evaluate_execution_proposal(
    proposal: TradeProposalPayload,
) -> dict[str, object]:
    """Evaluate a trade proposal through the policy/risk engine without dispatching it."""
    try:
        result = evaluate_trade_proposal(proposal.model_dump(mode="json"))
        return BridgeExecutionPolicyResponse(status="live", policy_decision=result).model_dump(mode="json")
    except HermesAgentBridgeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/proposals/submit")
async def submit_execution_proposal(
    proposal: TradeProposalPayload,
    _: None = Depends(require_api_key),
) -> dict[str, object]:
    """Validate and dispatch a trade proposal into the controlled execution path."""
    try:
        result = dispatch_trade_proposal(proposal.model_dump(mode="json"))
        return BridgeExecutionDispatchResponse(status="live", dispatch=result).model_dump(mode="json")
    except HermesAgentBridgeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/positions/monitor")
async def get_position_monitor(
    refresh: bool = Query(default=False),
    account_id: str | None = Query(default=None),
) -> dict[str, object]:
    """Return a compact position-monitoring snapshot for the active portfolio."""
    try:
        result = position_monitor_snapshot(account_id=account_id, refresh=refresh)
        return BridgePositionMonitorResponse(status="live", monitor=result).model_dump(mode="json")
    except HermesAgentBridgeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


# ---------------------------------------------------------------------------
# Operator approval queue endpoints
# ---------------------------------------------------------------------------


def _get_approval_store():
    """Lazy import to avoid hard dependency when approvals module is unavailable."""
    try:
        from backend.approvals import (  # type: ignore[import]
            approve_request,
            list_pending_approvals,
            reject_request,
        )
        return list_pending_approvals, approve_request, reject_request
    except ImportError as exc:
        raise HermesAgentBridgeError(
            "Approval store unavailable — hermes-agent backend not importable"
        ) from exc


@router.get("/approvals/pending")
async def get_pending_approvals(
    limit: int = Query(default=20, ge=1, le=100),
) -> dict[str, object]:
    """List execution requests awaiting operator approval."""
    try:
        list_pending, _, _ = _get_approval_store()
        approvals = list_pending(limit=limit)
        return {"status": "live", "count": len(approvals), "approvals": approvals}
    except HermesAgentBridgeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/approvals/{approval_id}/approve")
async def approve_execution(
    approval_id: str = Path(min_length=1),
    operator: str = Body(default="api", embed=True),
    _: None = Depends(require_api_key),
) -> dict[str, object]:
    """Approve a pending execution request, allowing it to proceed."""
    try:
        _, approve, _ = _get_approval_store()
        result = approve(approval_id=approval_id, operator=operator)
        if result is None:
            raise HTTPException(status_code=404, detail=f"Approval {approval_id!r} not found.")
        return {"status": "live", "approval": result}
    except HTTPException:
        raise
    except HermesAgentBridgeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/approvals/{approval_id}/reject")
async def reject_execution(
    approval_id: str = Path(min_length=1),
    reason: str = Body(default="Operator rejected.", embed=True),
    operator: str = Body(default="api", embed=True),
    _: None = Depends(require_api_key),
) -> dict[str, object]:
    """Reject a pending execution request."""
    try:
        _, _, reject = _get_approval_store()
        result = reject(approval_id=approval_id, reason=reason, operator=operator)
        if result is None:
            raise HTTPException(status_code=404, detail=f"Approval {approval_id!r} not found.")
        return {"status": "live", "approval": result}
    except HTTPException:
        raise
    except HermesAgentBridgeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
