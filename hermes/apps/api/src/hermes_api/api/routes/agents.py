from fastapi import APIRouter, HTTPException

from hermes_api.integrations.hermes_agent import (
    HermesAgentBridgeError,
    agent_activity,
    observability_service,
    trading_desk_agent,
    trading_desk_manifest,
)

router = APIRouter()


@router.get("/")
async def get_agents() -> dict[str, object]:
    try:
        manifest = trading_desk_manifest()
        service = observability_service()
        configured_agents = manifest.get("agents", [])

        live_agents: list[dict[str, object]] = []
        for agent in configured_agents:
            canonical_id = agent.get("canonical_agent_id")
            decisions = service.get_agent_decision_history(limit=10, agent_name=canonical_id)
            latest_decision = decisions[0] if decisions else None
            live_agents.append(
                {
                    "name": agent.get("name"),
                    "canonical_agent_id": canonical_id,
                    "profile": agent.get("profile"),
                    "role": agent.get("role"),
                    "reports_to": agent.get("reports_to"),
                    "responsibilities": agent.get("responsibilities", []),
                    "allowed_toolsets": agent.get("allowed_toolsets", []),
                    "allowed_tools": agent.get("allowed_tools", []),
                    "assigned_skills": agent.get("assigned_skills", []),
                    "expected_outputs": agent.get("expected_outputs", []),
                    "recent_decision_count": len(decisions),
                    "latest_decision": latest_decision,
                }
            )

        return {
            "status": "live",
            "team_name": manifest.get("team_name"),
            "trading_mode": manifest.get("trading_mode", {}),
            "count": len(live_agents),
            "agents": live_agents,
        }
    except HermesAgentBridgeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/{agent_id}")
async def get_agent_detail(agent_id: str) -> dict[str, object]:
    try:
        manifest = trading_desk_manifest()
        agent = trading_desk_agent(agent_id)
        if agent is None:
            raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' was not found.")

        canonical_id = agent.get("canonical_agent_id", agent_id)
        activity = agent_activity(canonical_id)
        return {
            "status": "live",
            "team_name": manifest.get("team_name"),
            "trading_mode": manifest.get("trading_mode", {}),
            "agent": {
                **agent,
                "recent_decisions": activity["recent_decisions"],
                "recent_workflow_runs": activity["recent_workflow_runs"],
                "correlated_timelines": activity["correlated_timelines"],
            },
        }
    except HermesAgentBridgeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/{agent_id}/timeline")
async def get_agent_timeline(agent_id: str) -> dict[str, object]:
    try:
        agent = trading_desk_agent(agent_id)
        if agent is None:
            raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' was not found.")

        canonical_id = agent.get("canonical_agent_id", agent_id)
        activity = agent_activity(canonical_id)
        flattened = []
        for item in activity["correlated_timelines"]:
            for event in item["timeline"]:
                flattened.append(
                    {
                        "correlation_id": item["correlation_id"],
                        **event,
                    }
                )

        flattened.sort(key=lambda entry: entry.get("timestamp") or "", reverse=True)
        return {
            "status": "live",
            "agent_id": canonical_id,
            "count": len(flattened),
            "timeline": flattened,
        }
    except HermesAgentBridgeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
