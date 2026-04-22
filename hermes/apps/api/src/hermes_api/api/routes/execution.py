import os
from typing import Literal

from fastapi import APIRouter, Body, Depends, HTTPException, Path, Query

from hermes_api.core.config import get_settings
from hermes_api.core.security import require_api_key
from hermes_api.integrations.hermes_agent import (
    HermesAgentBridgeError,
    observability_service,
    place_order,
    tradingview_store,
)

router = APIRouter()


_LIVE_TRADING_ACK_PHRASE = "I_ACKNOWLEDGE_LIVE_TRADING_RISK"


def _live_execution_blockers() -> list[str]:
    settings = get_settings()
    blockers: list[str] = []
    if settings.hermes_trading_mode.lower() != "live":
        blockers.append("HERMES_TRADING_MODE must be set to 'live'.")
    if not settings.hermes_enable_live_trading:
        blockers.append("HERMES_ENABLE_LIVE_TRADING=true is required.")
    if settings.hermes_live_trading_ack.strip() != _LIVE_TRADING_ACK_PHRASE:
        blockers.append(
            "HERMES_LIVE_TRADING_ACK must equal "
            f"{_LIVE_TRADING_ACK_PHRASE!r}."
        )
    return blockers


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
        live_blockers = _live_execution_blockers()
        return {
            "status": "live",
            "execution": {
                "exchange": "BITMART",
                "configured": bitmart_configured,
                "trading_mode": settings.hermes_trading_mode,
                "live_trading_enabled": not live_blockers,
                "live_trading_blockers": live_blockers,
                "pending_signal_events": pending_events,
                "pending_signal_count": len(pending_events),
                "recent_execution_events": recent_execution_events,
            },
        }
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
        return {"status": "live", "count": len(rows), "events": rows}
    except HermesAgentBridgeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/events")
async def get_recent_execution_events(
    limit: int = Query(default=20, ge=1, le=100),
) -> dict[str, object]:
    try:
        service = observability_service()
        rows = service.get_execution_event_history(limit=limit)
        return {"status": "live", "count": len(rows), "events": rows}
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
    _: None = Depends(require_api_key),
) -> dict[str, object]:
    """Place a trade order directly through the configured exchange connector.

    Requires BitMart credentials in the backend environment and will be
    rejected if the global kill switch is active or trading mode is "paper".
    """
    live_blockers = _live_execution_blockers()
    if live_blockers:
        raise HTTPException(
            status_code=403,
            detail={"message": "Live execution is blocked.", "blockers": live_blockers},
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
            }
        )
        if not result.get("ok", True):
            raise HTTPException(status_code=400, detail=result)
        return {"status": "live", "order": result}
    except HTTPException:
        raise
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
