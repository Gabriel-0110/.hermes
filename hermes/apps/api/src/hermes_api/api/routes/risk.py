from fastapi import APIRouter, Body, Depends, HTTPException, Query

from hermes_api.core.security import require_api_key
from hermes_api.domain.bridge import BridgeKillSwitchState
from hermes_api.domain.execution import BridgeExecutionSafety
from hermes_api.domain.portfolio import BridgePortfolioResponse, BridgePositionMonitorResponse
from hermes_api.integrations.hermes_agent import (
    HermesAgentBridgeError,
    evaluate_risk,
    execution_safety_status,
    get_kill_switch_state,
    list_trade_candidates,
    observability_service,
    portfolio_state,
    position_monitor_snapshot,
    set_kill_switch,
)

router = APIRouter()


@router.get("/")
async def get_risk() -> dict[str, object]:
    try:
        service = observability_service()
        dashboard = service.get_dashboard_snapshot(limit=20)
        ks = BridgeKillSwitchState.model_validate(get_kill_switch_state())
        safety = BridgeExecutionSafety.model_validate(execution_safety_status())
        monitor = position_monitor_snapshot(refresh=False)
        return {
            "status": "live",
            "risk": {
                "kill_switch": ks.model_dump(mode="json"),
                "execution_safety": safety.model_dump(mode="json"),
                "position_monitor": monitor,
                "recent_risk_rejections": dashboard["recent_risk_rejections"],
                "recent_failures": dashboard["recent_failures"],
                "recent_notifications": dashboard["recent_notifications"],
            },
        }
    except HermesAgentBridgeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/kill-switch")
async def get_kill_switch() -> dict[str, object]:
    try:
        state = BridgeKillSwitchState.model_validate(get_kill_switch_state())
        return {"status": "live", "kill_switch": state.model_dump(mode="json")}
    except HermesAgentBridgeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/kill-switch/activate")
async def activate_kill_switch(
    reason: str = Body(default="Operator-initiated kill switch", embed=True),
    operator: str = Body(default="api", embed=True),
    _: None = Depends(require_api_key),
) -> dict[str, object]:
    """Activate the global kill switch.  All new risk approvals will be denied."""
    try:
        state = BridgeKillSwitchState.model_validate(
            set_kill_switch(active=True, reason=reason, operator=operator)
        )
        return {"status": "live", "kill_switch": state.model_dump(mode="json")}
    except HermesAgentBridgeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/kill-switch/deactivate")
async def deactivate_kill_switch(
    operator: str = Body(default="api", embed=True),
    _: None = Depends(require_api_key),
) -> dict[str, object]:
    """Deactivate the global kill switch."""
    try:
        state = BridgeKillSwitchState.model_validate(set_kill_switch(active=False, operator=operator))
        return {"status": "live", "kill_switch": state.model_dump(mode="json")}
    except HermesAgentBridgeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/portfolio")
async def get_risk_portfolio_view() -> dict[str, object]:
    try:
        payload = portfolio_state()
        return BridgePortfolioResponse(status="live", portfolio=payload).model_dump(mode="json")
    except HermesAgentBridgeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/portfolio/monitor")
async def get_risk_position_monitor() -> dict[str, object]:
    try:
        payload = position_monitor_snapshot(refresh=False)
        return BridgePositionMonitorResponse(status="live", monitor=payload).model_dump(mode="json")
    except HermesAgentBridgeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/rejections")
async def get_recent_risk_rejections(
    limit: int = Query(default=20, ge=1, le=100),
) -> dict[str, object]:
    try:
        service = observability_service()
        rows = [
            row
            for row in service.get_agent_decision_history(
                limit=limit * 3,
                agent_name="risk_manager",
            )
            if row.get("decision") == "reject"
            or row.get("status") in {"reject", "rejected", "failed"}
        ][:limit]
        return {"status": "live", "count": len(rows), "rejections": rows}
    except HermesAgentBridgeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/evaluate")
async def evaluate_trade_risk(
    symbol: str = Body(embed=True),
    proposed_size_usd: float = Body(embed=True),
) -> dict[str, object]:
    """Run the risk approval gate for a proposed trade and return the decision."""
    try:
        result = evaluate_risk({"symbol": symbol, "proposed_size_usd": proposed_size_usd})
        return {"status": "live", "result": result}
    except HermesAgentBridgeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/candidates")
async def get_trade_candidates() -> dict[str, object]:
    """Return current scored trade candidates from the signal scanner."""
    try:
        result = list_trade_candidates()
        return {"status": "live", "result": result}
    except HermesAgentBridgeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
