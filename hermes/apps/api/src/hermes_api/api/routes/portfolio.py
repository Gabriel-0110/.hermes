"""Portfolio management API routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from hermes_api.core.security import require_api_key
from hermes_api.domain.portfolio import BridgePortfolioResponse, BridgePortfolioSyncResponse
from hermes_api.integrations.hermes_agent import (
    HermesAgentBridgeError,
    portfolio_state,
    sync_portfolio,
)

router = APIRouter()


@router.get("/")
async def get_portfolio() -> dict[str, object]:
    """Return the latest known portfolio state (from DB snapshot)."""
    try:
        payload = portfolio_state()
        return BridgePortfolioResponse(status="live", portfolio=payload).model_dump(mode="json")
    except HermesAgentBridgeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/sync")
async def trigger_portfolio_sync(_: None = Depends(require_api_key)) -> dict[str, object]:
    """Fetch live balances from the exchange and persist a fresh snapshot.

    Requires ``BITMART_API_KEY``, ``BITMART_SECRET``, and ``BITMART_MEMO``
    to be set in the backend environment.
    """
    try:
        result = sync_portfolio()
        return BridgePortfolioSyncResponse(status="live", sync=result).model_dump(mode="json")
    except HermesAgentBridgeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        # Surface credential / exchange errors as 503 with context
        raise HTTPException(status_code=503, detail=str(exc)) from exc
