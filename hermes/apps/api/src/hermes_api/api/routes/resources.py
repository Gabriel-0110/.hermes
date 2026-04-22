from collections import Counter
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException

from hermes_api.integrations.hermes_agent import (
    HermesAgentBridgeError,
    observability_service,
    portfolio_state,
    tradingview_store,
)

router = APIRouter()


@router.get("/")
async def get_resources() -> dict[str, object]:
    try:
        store = tradingview_store()
        service = observability_service()
        portfolio = portfolio_state()
        recent_alerts = store.list_alerts(limit=10)
        pending_signal_events = store.list_internal_events(
            limit=10,
            event_type="tradingview_signal_ready",
            delivery_status="pending",
        )
        dashboard = service.get_dashboard_snapshot(limit=10)
        recent_workflow_runs = dashboard["recent_workflow_runs"]
        recent_risk_rejections = dashboard["recent_risk_rejections"]
        catalog = [
            {
                "name": "Market Price Feed",
                "status": "not_exposed",
                "backing": "descriptive_catalog",
                "evidence": (
                    f"{len(recent_alerts)} recent TradingView alerts are visible via the shared "
                    "store, but the product API does not expose a dedicated live price feed."
                ),
            },
            {
                "name": "Order Book / Depth Feed",
                "status": "not_exposed",
                "backing": "descriptive_catalog",
                "evidence": (
                    "No backend-backed depth feed is exposed through the "
                    "current product runtime bridge."
                ),
            },
            {
                "name": "Trades / Tape Feed",
                "status": "not_exposed",
                "backing": "descriptive_catalog",
                "evidence": (
                    "No backend-backed tape feed is exposed through the "
                    "current product runtime bridge."
                ),
            },
            {
                "name": "Technical Indicator Engine",
                "status": "backend_only",
                "backing": "hermes_agent_backend",
                "evidence": (
                    "Indicator and volatility tools exist in Hermes Agent "
                    "backend, but this product API does not expose them as a "
                    "first-class resource endpoint."
                ),
            },
            {
                "name": "Derivatives & Funding Data",
                "status": "backend_only",
                "backing": "hermes_agent_backend",
                "evidence": (
                    "Execution and DeFi surfaces exist in Hermes Agent "
                    "backend, but no dedicated product API route exposes them yet."
                ),
            },
            {
                "name": "Portfolio & Account State",
                "status": "live",
                "backing": "product_api_bridge",
                "evidence": (
                    f"Portfolio state is available through the product API bridge "
                    f"(ok={portfolio['meta']['ok']})."
                ),
            },
            {
                "name": "Risk Policy Engine",
                "status": "live",
                "backing": "product_api_bridge",
                "evidence": (
                    f"{len(recent_risk_rejections)} recent risk rejections are "
                    "visible through the product API observability bridge."
                ),
            },
            {
                "name": "Strategy Library",
                "status": "not_exposed",
                "backing": "descriptive_catalog",
                "evidence": (
                    "No backend-backed strategy registry is exposed through "
                    "this product API yet."
                ),
            },
            {
                "name": "News / Sentiment / Narrative Feed",
                "status": "backend_only",
                "backing": "hermes_agent_backend",
                "evidence": (
                    "Provider integrations exist in Hermes Agent backend, "
                    "but they are not yet exposed as a dedicated product API surface."
                ),
            },
            {
                "name": "On-Chain / Ecosystem Intelligence",
                "status": "backend_only",
                "backing": "hermes_agent_backend",
                "evidence": (
                    "On-chain tools exist in Hermes Agent backend, but the "
                    "product API does not expose them directly yet."
                ),
            },
            {
                "name": "Execution / Broker / Exchange Connector",
                "status": "live",
                "backing": "product_api_bridge",
                "evidence": (
                    f"{len(pending_signal_events)} pending signal events "
                    "and recent execution activity are visible through the execution bridge."
                ),
            },
            {
                "name": "Memory / Knowledge / Research Store",
                "status": "live",
                "backing": "product_api_bridge",
                "evidence": (
                    f"{len(recent_workflow_runs)} recent workflow runs are "
                    "stored in shared observability history and exposed "
                    "through the product API."
                ),
            },
        ]
        status_counts = Counter(item["status"] for item in catalog)
        return {
            "status": "live",
            "contract": "descriptive-capability-catalog",
            "contract_version": "2026-04-17",
            "generated_at": datetime.now(UTC).isoformat(),
            "summary": {
                "total_resources": len(catalog),
                "live_resource_count": status_counts.get("live", 0),
                "status_counts": {
                    "live": status_counts.get("live", 0),
                    "backend_only": status_counts.get("backend_only", 0),
                    "not_exposed": status_counts.get("not_exposed", 0),
                },
            },
            "resources": catalog,
        }
    except HermesAgentBridgeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
