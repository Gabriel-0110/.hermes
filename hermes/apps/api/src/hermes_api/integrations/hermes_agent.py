from __future__ import annotations

import importlib
import os
import sys
from datetime import UTC
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml


class HermesAgentBridgeError(RuntimeError):
    """Raised when the sibling Hermes Agent backend cannot be resolved."""


def _workspace_root() -> Path:
    configured_root = os.getenv("HERMES_WORKSPACE_ROOT", "").strip()
    if configured_root:
        candidate = Path(configured_root).resolve()
        if (candidate / "hermes-agent").exists() and (candidate / "hermes").exists():
            return candidate

    current = Path(__file__).resolve()
    for parent in current.parents:
        if (parent / "hermes-agent").exists() and (parent / "hermes").exists():
            return parent
    raise HermesAgentBridgeError(
        "Unable to locate workspace root containing both hermes and hermes-agent."
    )


def _hermes_agent_root() -> Path:
    return _workspace_root() / "hermes-agent"


def _trading_desk_manifest_path() -> Path:
    return _workspace_root() / "teams" / "trading-desk" / "agents.yaml"


@lru_cache(maxsize=1)
def _ensure_import_path() -> str:
    agent_root = str(_hermes_agent_root())
    if agent_root not in sys.path:
        sys.path.insert(0, agent_root)
    return agent_root


def import_from_hermes_agent(module_name: str) -> Any:
    _ensure_import_path()
    try:
        return importlib.import_module(module_name)
    except Exception as exc:  # pragma: no cover - surfaced via API responses
        raise HermesAgentBridgeError(
            f"Failed to import Hermes Agent module '{module_name}': {exc}"
        ) from exc


def observability_service() -> Any:
    module = import_from_hermes_agent("backend.observability.service")
    return module.get_observability_service()


def tradingview_store(*, db_path: Path | None = None) -> Any:
    module = import_from_hermes_agent("backend.tradingview.store")
    return module.TradingViewStore(db_path=db_path)


def _portfolio_envelope_from_snapshot(snapshot: Any | None, *, account_id: str) -> dict[str, Any]:
    meta = {
        "source": "get_portfolio_state",
        "providers": [],
        "warnings": [],
        "ok": True,
    }
    if snapshot is None:
        return {
            "meta": {
                **meta,
                "warnings": ["Portfolio adapter not yet wired to exchange/account backend."],
            },
            "data": {
                "account_id": account_id,
                "total_equity_usd": None,
                "cash_usd": None,
                "exposure_usd": None,
                "positions": [],
                "snapshot_metadata": {"source": "uninitialized", "positions_count": 0},
                "updated_at": None,
            },
        }

    return {
        "meta": meta,
        "data": {
            "account_id": snapshot.account_id,
            "total_equity_usd": snapshot.total_equity_usd,
            "cash_usd": snapshot.cash_usd,
            "exposure_usd": snapshot.exposure_usd,
            "positions": snapshot.positions or [],
            "snapshot_metadata": snapshot.payload or {},
            "updated_at": snapshot.snapshot_time.astimezone(UTC).isoformat(),
        },
    }


def portfolio_state() -> dict[str, Any]:
    db_module = import_from_hermes_agent("backend.db")
    session_module = import_from_hermes_agent("backend.db.session")

    account_id = os.getenv("TRADING_PORTFOLIO_ACCOUNT_ID", "paper")
    db_module.ensure_time_series_schema(session_module.get_engine())
    with db_module.session_scope() as session:
        snapshot = db_module.HermesTimeSeriesRepository(session).get_latest_portfolio_snapshot(
            account_id=account_id
        )

    return _portfolio_envelope_from_snapshot(snapshot, account_id=account_id)


def trading_desk_manifest() -> dict[str, Any]:
    try:
        with _trading_desk_manifest_path().open("r", encoding="utf-8") as handle:
            parsed = yaml.safe_load(handle)
    except Exception as exc:  # pragma: no cover - surfaced via API responses
        raise HermesAgentBridgeError(f"Failed to load trading desk manifest: {exc}") from exc

    if not isinstance(parsed, dict):
        raise HermesAgentBridgeError("Trading desk manifest did not parse as a mapping.")

    trading_mode = parsed.get("trading_mode")
    if not isinstance(trading_mode, dict):
        trading_mode = {}
        parsed["trading_mode"] = trading_mode

    runtime_mode = os.getenv("HERMES_TRADING_MODE", "").strip().lower()
    if runtime_mode in {"paper", "live"}:
        trading_mode["mode"] = runtime_mode
        if runtime_mode == "live":
            trading_mode["forbid_live_execution"] = False
            trading_mode["live_execution_forbidden"] = False

    return parsed


def trading_desk_agent(agent_id: str) -> dict[str, Any] | None:
    manifest = trading_desk_manifest()
    agents = manifest.get("agents", [])
    for agent in agents:
        if not isinstance(agent, dict):
            continue
        canonical_id = agent.get("canonical_agent_id")
        name = agent.get("name")
        if agent_id in {canonical_id, name}:
            return agent
    return None


def shared_resource_audit() -> dict[str, Any]:
    module = import_from_hermes_agent("backend.shared_resources")
    return module.initialize_shared_resource_catalog()


def agent_activity(agent_id: str, *, decision_limit: int = 10) -> dict[str, Any]:
    service = observability_service()
    recent_decisions = service.get_agent_decision_history(
        limit=decision_limit,
        agent_name=agent_id,
    )
    correlation_ids: list[str] = []
    for decision in recent_decisions:
        correlation_id = decision.get("correlation_id")
        if correlation_id and correlation_id not in correlation_ids:
            correlation_ids.append(correlation_id)

    correlated_timelines = []
    for correlation_id in correlation_ids[:5]:
        timeline = service.get_event_timeline(correlation_id, limit_per_source=50)
        correlated_timelines.append(
            {
                "correlation_id": correlation_id,
                "timeline": timeline,
                "timeline_count": len(timeline),
            }
        )

    recent_workflow_runs = [
        row
        for row in service.list_recent_workflow_runs(limit=100)
        if row.get("agent_name") == agent_id
    ][:20]

    return {
        "recent_decisions": recent_decisions,
        "recent_workflow_runs": recent_workflow_runs,
        "correlated_timelines": correlated_timelines,
    }


# ---------------------------------------------------------------------------
# Kill-switch helpers
# ---------------------------------------------------------------------------

_KILL_SWITCH_KEY = "hermes:risk:kill_switch"


def get_kill_switch_state() -> dict[str, Any]:
    """Return the current kill-switch state from Redis."""
    try:
        import json

        redis_module = import_from_hermes_agent("backend.redis_client")
        rc = redis_module.get_redis_client()
        raw = rc.get(_KILL_SWITCH_KEY)
        if raw:
            return json.loads(raw)
    except Exception:
        pass
    return {"active": False, "reason": None}


def set_kill_switch(
    *,
    active: bool,
    reason: str | None = None,
    operator: str | None = None,
) -> dict[str, Any]:
    """Activate or deactivate the global kill switch in Redis.

    Returns the written state dict.
    """
    import json
    from datetime import UTC, datetime

    redis_module = import_from_hermes_agent("backend.redis_client")
    rc = redis_module.get_redis_client()

    state: dict[str, Any] = {
        "active": active,
        "reason": reason or ("Operator kill switch" if active else "Operator cleared"),
        "operator": operator or "api",
        "updated_at": datetime.now(UTC).isoformat(),
    }
    rc.set(_KILL_SWITCH_KEY, json.dumps(state))
    return state


# ---------------------------------------------------------------------------
# Portfolio sync helper
# ---------------------------------------------------------------------------


def sync_portfolio(*, account_id: str | None = None) -> dict[str, Any]:
    """Trigger a live portfolio sync from the exchange and return the result."""
    module = import_from_hermes_agent("backend.services.portfolio_sync")
    state = module.sync_portfolio_from_exchange(account_id=account_id)
    return {
        "meta": {
            "source": "portfolio_sync",
            "providers": ["bitmart"],
            "warnings": [],
            "ok": True,
        },
        "data": state.model_dump(mode="json"),
    }


# ---------------------------------------------------------------------------
# Direct execution helper
# ---------------------------------------------------------------------------


def place_order(payload: dict[str, Any]) -> dict[str, Any]:
    """Place an order directly via the CCXT execution client."""
    module = import_from_hermes_agent("backend.tools.place_order")
    return module.place_order(payload)


def execution_safety_status(*, approval_id: str | None = None) -> dict[str, Any]:
    """Return the centralized execution safety decision from hermes-agent."""
    module = import_from_hermes_agent("backend.trading.safety")
    decision = module.evaluate_execution_safety(approval_id=approval_id)
    return {
        "execution_mode": decision.execution_mode,
        "blockers": list(decision.blockers),
        "approval_required": decision.approval_required,
        "kill_switch_active": decision.kill_switch_active,
        "kill_switch_reason": decision.kill_switch_reason,
        "live_allowed": decision.live_allowed,
    }


# ---------------------------------------------------------------------------
# Risk approval helper
# ---------------------------------------------------------------------------


def evaluate_risk(payload: dict[str, Any]) -> dict[str, Any]:
    """Run the risk approval gate for a proposed trade."""
    module = import_from_hermes_agent("backend.tools.get_risk_approval")
    return module.get_risk_approval(payload)


# ---------------------------------------------------------------------------
# Trade candidates helper
# ---------------------------------------------------------------------------


def list_trade_candidates() -> dict[str, Any]:
    """Return the current list of scored trade candidates."""
    module = import_from_hermes_agent("backend.tools.list_trade_candidates")
    return module.list_trade_candidates()


# ---------------------------------------------------------------------------
# Controlled trading pipeline helpers
# ---------------------------------------------------------------------------


def evaluate_trade_proposal(payload: dict[str, Any]) -> dict[str, Any]:
    module = import_from_hermes_agent("backend.trading")
    proposal = module.TradeProposal.model_validate(payload)
    result = module.evaluate_trade_proposal(proposal)
    return result.model_dump(mode="json")


def dispatch_trade_proposal(payload: dict[str, Any]) -> dict[str, Any]:
    module = import_from_hermes_agent("backend.trading")
    proposal = module.TradeProposal.model_validate(payload)
    result = module.dispatch_trade_proposal(proposal)
    return result.model_dump(mode="json")


def position_monitor_snapshot(
    *,
    account_id: str | None = None,
    refresh: bool = False,
) -> dict[str, Any]:
    module = import_from_hermes_agent("backend.trading")
    result = module.get_position_monitor_snapshot(account_id=account_id, refresh=refresh)
    return result.model_dump(mode="json")
