from fastapi import APIRouter, HTTPException

from hermes_api.integrations.hermes_agent import (
    HermesAgentBridgeError,
    shared_resource_audit,
)

router = APIRouter()


@router.get("/")
async def get_resources() -> dict[str, object]:
    try:
        return shared_resource_audit()
    except HermesAgentBridgeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
