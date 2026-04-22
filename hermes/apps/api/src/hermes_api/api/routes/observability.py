from fastapi import APIRouter, HTTPException, Query

from hermes_api.integrations.hermes_agent import HermesAgentBridgeError, observability_service

router = APIRouter()


@router.get("/")
async def get_observability() -> dict[str, object]:
    try:
        service = observability_service()
        return {
            "status": "live",
            "dashboard": service.get_dashboard_snapshot(limit=20),
        }
    except HermesAgentBridgeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/workflows")
async def list_workflows(
    limit: int = Query(default=20, ge=1, le=100),
    status: str | None = Query(default=None),
) -> dict[str, object]:
    try:
        service = observability_service()
        rows = service.list_recent_workflow_runs(limit=limit, status=status)
        return {"status": "live", "count": len(rows), "workflow_runs": rows}
    except HermesAgentBridgeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/workflows/{workflow_run_id}")
async def get_workflow_run(workflow_run_id: str) -> dict[str, object]:
    try:
        service = observability_service()
        workflow_run = service.get_workflow_run(workflow_run_id)
        if workflow_run is None:
            raise HTTPException(
                status_code=404,
                detail=f"Workflow run '{workflow_run_id}' was not found.",
            )
        return {"status": "live", "workflow_run": workflow_run}
    except HermesAgentBridgeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/failures")
async def get_recent_failures(limit: int = Query(default=20, ge=1, le=100)) -> dict[str, object]:
    try:
        service = observability_service()
        rows = service.get_recent_failures(limit=limit)
        return {"status": "live", "count": len(rows), "failures": rows}
    except HermesAgentBridgeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/timeline/{correlation_id}")
async def get_event_timeline(
    correlation_id: str,
    limit_per_source: int = Query(default=50, ge=1, le=200),
) -> dict[str, object]:
    try:
        service = observability_service()
        rows = service.get_event_timeline(correlation_id, limit_per_source=limit_per_source)
        return {"status": "live", "count": len(rows), "timeline": rows}
    except HermesAgentBridgeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
