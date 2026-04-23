"""Canonical audit catalog for the 13 Hermes shared trading resources."""

from __future__ import annotations

import importlib
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from tools.registry import registry


CORE_SHARED_RESOURCE_IDS = (
    "market_price_feed",
    "order_book_depth_feed",
    "trades_tape_feed",
    "technical_indicator_engine",
    "derivatives_funding_data",
    "portfolio_account_state",
    "risk_policy_engine",
    "strategy_library",
    "news_sentiment_narrative_feed",
    "onchain_ecosystem_intelligence",
    "execution_exchange_connector",
    "memory_knowledge_research_store",
    "forecasting_time_series_projection_engine",
)


@dataclass(frozen=True)
class SharedResourceSpec:
    resource_id: str
    name: str
    purpose: str
    required_tools: tuple[str, ...]
    owning_agents: tuple[str, ...]
    consumer_agents: tuple[str, ...] = ()
    required_modules: tuple[str, ...] = ()
    required_skill_ids: tuple[str, ...] = ()
    tested_by: tuple[str, ...] = ()
    backing: str = "hermes_agent_backend"


_SPECS: tuple[SharedResourceSpec, ...] = (
    SharedResourceSpec(
        "market_price_feed",
        "Market Price Feed",
        "Live and historical normalized price/OHLCV context.",
        ("get_crypto_prices", "get_market_overview", "get_ohlcv"),
        ("market_researcher",),
        ("strategy_agent", "risk_manager", "portfolio_monitor"),
        ("backend.integrations.market_data.coingecko_client", "backend.integrations.market_data.twelvedata_client"),
        tested_by=("tests/tools/test_trading_tools.py", "tests/backend/test_macro_tools.py"),
    ),
    SharedResourceSpec(
        "order_book_depth_feed",
        "Order Book / Depth Feed",
        "Bid/ask depth, spread, and liquidity-pressure snapshots.",
        ("get_order_book",),
        ("strategy_agent",),
        ("risk_manager",),
        ("backend.integrations.derivatives.bitmart_public_client",),
        tested_by=("tests/tools/test_trading_tools.py",),
    ),
    SharedResourceSpec(
        "trades_tape_feed",
        "Trades / Tape Feed",
        "Recent public trades and flow/tape acceleration context.",
        ("get_recent_trades",),
        ("strategy_agent",),
        ("market_researcher",),
        ("backend.integrations.derivatives.bitmart_public_client",),
        tested_by=("tests/tools/test_trading_tools.py",),
    ),
    SharedResourceSpec(
        "technical_indicator_engine",
        "Technical Indicator Engine",
        "Computed indicators, volatility, and multi-timeframe diagnostics.",
        ("get_indicator_snapshot", "get_volatility_metrics", "get_correlation_inputs"),
        ("strategy_agent",),
        ("risk_manager", "market_researcher"),
        ("backend.tools.get_indicator_snapshot", "backend.tools.get_volatility_metrics"),
        tested_by=("tests/tools/test_trading_tools.py", "tests/backend/test_macro_tools.py"),
    ),
    SharedResourceSpec(
        "derivatives_funding_data",
        "Derivatives & Funding Data",
        "Funding, open-interest, liquidation-zone, and leveraged sentiment context.",
        ("get_funding_rates", "get_liquidation_zones", "get_defi_open_interest"),
        ("market_researcher",),
        ("risk_manager", "strategy_agent"),
        ("backend.integrations.derivatives.bitmart_public_client", "backend.tools.get_defi_open_interest"),
        tested_by=("tests/backend/test_defillama_tools.py",),
    ),
    SharedResourceSpec(
        "portfolio_account_state",
        "Portfolio & Account State",
        "Balances, positions, exposure, PnL, and account-state snapshots.",
        ("get_portfolio_state", "get_exchange_balances", "get_portfolio_valuation"),
        ("portfolio_monitor",),
        ("orchestrator_trader", "risk_manager"),
        ("backend.tools.get_portfolio_state", "backend.services.portfolio_sync"),
        tested_by=("tests/backend/test_shared_time_series_storage.py", "tests/backend/test_position_monitoring.py"),
    ),
    SharedResourceSpec(
        "risk_policy_engine",
        "Risk Policy Engine",
        "Risk approvals, limits, drawdown controls, kill-switches, and gates.",
        ("get_risk_approval", "get_risk_state", "set_kill_switch"),
        ("risk_manager",),
        ("orchestrator_trader",),
        ("backend.trading.policy_engine", "backend.trading.safety"),
        tested_by=("tests/backend/test_trading_control_path.py",),
    ),
    SharedResourceSpec(
        "strategy_library",
        "Strategy Library",
        "Reusable strategies, templates, regime rules, and evaluation runners.",
        ("list_strategies", "evaluate_strategy", "list_trade_candidates"),
        ("strategy_agent",),
        ("orchestrator_trader", "market_researcher"),
        ("backend.strategies.registry", "backend.tools.evaluate_strategy"),
        tested_by=("tests/tools/test_trading_tools.py",),
    ),
    SharedResourceSpec(
        "news_sentiment_narrative_feed",
        "News / Sentiment / Narrative Feed",
        "Crypto news, macro news, social sentiment, and event-risk summaries.",
        ("get_crypto_news", "get_general_news", "get_social_sentiment", "get_event_risk_summary"),
        ("market_researcher",),
        ("risk_manager",),
        ("backend.integrations.news_sentiment.cryptopanic_client", "backend.integrations.news_sentiment.lunarcrush_client"),
        tested_by=("tests/tools/test_trading_tools.py",),
    ),
    SharedResourceSpec(
        "onchain_ecosystem_intelligence",
        "On-Chain / Ecosystem Intelligence",
        "Wallet flows, token activity, smart-money flow, and chain context.",
        ("get_onchain_wallet_data", "get_wallet_transactions", "get_smart_money_flows", "get_onchain_signal_summary"),
        ("market_researcher",),
        ("strategy_agent", "risk_manager", "portfolio_monitor"),
        ("backend.integrations.onchain.etherscan_client", "backend.integrations.onchain.nansen_client"),
        tested_by=("tests/tools/test_trading_tools.py",),
    ),
    SharedResourceSpec(
        "execution_exchange_connector",
        "Execution / Broker / Exchange Connector",
        "Guarded order placement, cancelation, fills, status, and venue telemetry.",
        ("place_order", "cancel_order", "get_execution_status", "get_open_orders", "get_order_history", "get_trade_history"),
        ("orchestrator_trader",),
        ("portfolio_monitor", "risk_manager"),
        ("backend.integrations.execution.ccxt_client", "backend.trading.execution_service"),
        tested_by=("tests/tools/test_execution_tools.py", "tests/backend/test_trading_control_path.py"),
    ),
    SharedResourceSpec(
        "memory_knowledge_research_store",
        "Memory / Knowledge / Research Store",
        "Durable research memos, workflow history, decisions, and post-mortems.",
        ("save_research_memo", "get_research_memos", "get_recent_tradingview_alerts"),
        ("market_researcher",),
        ("orchestrator_trader", "strategy_agent", "risk_manager", "portfolio_monitor"),
        ("backend.tools.save_research_memo", "backend.observability.service"),
        tested_by=("tests/backend/test_shared_time_series_storage.py", "tests/backend/test_tradingview_ingestion.py"),
    ),
    SharedResourceSpec(
        "forecasting_time_series_projection_engine",
        "Forecasting / Time-Series Projection Engine",
        "Research-owned low/median/high forward scenarios from normalized history.",
        ("get_forecast_projection",),
        ("market_researcher",),
        ("strategy_agent", "orchestrator_trader"),
        ("backend.tools.get_forecast_projection",),
        ("chronos2_forecasting",),
        ("tests/tools/test_trading_tools.py",),
    ),
)

_INITIALIZED_AT: datetime | None = None
_LAST_AUDIT: dict[str, Any] | None = None


def _workspace_root() -> Path:
    current = Path(__file__).resolve()
    for parent in current.parents:
        if (parent / "hermes-agent").exists() and (parent / "teams" / "trading-desk").exists():
            return parent
    return Path.cwd()


def _load_agents_manifest() -> dict[str, Any]:
    path = _workspace_root() / "teams" / "trading-desk" / "agents.yaml"
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}


def _manifest_tools_by_agent(manifest: dict[str, Any]) -> dict[str, set[str]]:
    result: dict[str, set[str]] = {}
    for agent in manifest.get("agents", []) or []:
        if not isinstance(agent, dict):
            continue
        agent_id = str(agent.get("canonical_agent_id") or agent.get("name") or "")
        result[agent_id] = set(agent.get("allowed_tools") or [])
    return result


def _manifest_skills_by_agent(manifest: dict[str, Any]) -> dict[str, set[str]]:
    result: dict[str, set[str]] = {}
    for agent in manifest.get("agents", []) or []:
        if not isinstance(agent, dict):
            continue
        agent_id = str(agent.get("canonical_agent_id") or agent.get("name") or "")
        result[agent_id] = set(agent.get("assigned_skills") or [])
    return result


def _registered_tool_names() -> set[str]:
    # Importing trading_tools is idempotent and triggers self-registration when
    # the dashboard starts without the full model_tools discovery path.
    importlib.import_module("tools.trading_tools")
    return set(registry.get_tool_to_toolset_map())


def _module_available(module_name: str) -> bool:
    try:
        importlib.import_module(module_name)
        return True
    except Exception:
        return False


def _build_resource_audit(spec: SharedResourceSpec, *, tools: set[str], agent_tools: dict[str, set[str]], agent_skills: dict[str, set[str]]) -> dict[str, Any]:
    missing_tools = [tool for tool in spec.required_tools if tool not in tools]
    missing_modules = [module for module in spec.required_modules if not _module_available(module)]
    owner_coverage = {
        agent_id: sorted(set(spec.required_tools).intersection(agent_tools.get(agent_id, set())))
        for agent_id in spec.owning_agents
    }
    missing_owner_tools = {
        agent_id: sorted(set(spec.required_tools).difference(agent_tools.get(agent_id, set())))
        for agent_id in spec.owning_agents
        if not set(spec.required_tools).intersection(agent_tools.get(agent_id, set()))
    }
    missing_owner_skills = {
        agent_id: sorted(set(spec.required_skill_ids).difference(agent_skills.get(agent_id, set())))
        for agent_id in spec.owning_agents
        if spec.required_skill_ids and not set(spec.required_skill_ids).issubset(agent_skills.get(agent_id, set()))
    }

    implemented = not missing_modules
    installed = not missing_tools
    applied_to_agents = not missing_owner_tools and not missing_owner_skills
    tested = bool(spec.tested_by)
    running = implemented and installed and applied_to_agents
    status = "live" if running else "needs_fix"

    return {
        "resource_id": spec.resource_id,
        "name": spec.name,
        "purpose": spec.purpose,
        "status": status,
        "implemented": implemented,
        "installed": installed,
        "tested": tested,
        "running": running,
        "applied_to_agents": applied_to_agents,
        "backing": spec.backing,
        "required_tools": list(spec.required_tools),
        "registered_tools": [tool for tool in spec.required_tools if tool in tools],
        "missing_tools": missing_tools,
        "missing_modules": missing_modules,
        "owning_agents": list(spec.owning_agents),
        "consumer_agents": list(spec.consumer_agents),
        "owner_tool_coverage": owner_coverage,
        "missing_owner_tools": missing_owner_tools,
        "missing_owner_skills": missing_owner_skills,
        "tested_by": list(spec.tested_by),
    }


def get_shared_resource_audit() -> dict[str, Any]:
    """Return a deterministic implementation/install/runtime audit."""
    tools = _registered_tool_names()
    manifest = _load_agents_manifest()
    agent_tools = _manifest_tools_by_agent(manifest)
    agent_skills = _manifest_skills_by_agent(manifest)
    resources = [
        _build_resource_audit(spec, tools=tools, agent_tools=agent_tools, agent_skills=agent_skills)
        for spec in _SPECS
    ]
    counts = {
        "total_resources": len(resources),
        "live": sum(1 for item in resources if item["status"] == "live"),
        "needs_fix": sum(1 for item in resources if item["status"] != "live"),
        "implemented": sum(1 for item in resources if item["implemented"]),
        "installed": sum(1 for item in resources if item["installed"]),
        "tested": sum(1 for item in resources if item["tested"]),
        "running": sum(1 for item in resources if item["running"]),
        "applied_to_agents": sum(1 for item in resources if item["applied_to_agents"]),
    }
    return {
        "status": "live" if counts["needs_fix"] == 0 else "needs_fix",
        "contract": "shared-resource-audit",
        "contract_version": "2026-04-23",
        "initialized_at": _INITIALIZED_AT.isoformat() if _INITIALIZED_AT else None,
        "generated_at": datetime.now(UTC).isoformat(),
        "summary": counts,
        "resources": resources,
    }


def initialize_shared_resource_catalog() -> dict[str, Any]:
    """Initialize and validate the shared resource catalog at service startup."""
    global _INITIALIZED_AT, _LAST_AUDIT
    _INITIALIZED_AT = datetime.now(UTC)
    _LAST_AUDIT = get_shared_resource_audit()
    return _LAST_AUDIT
