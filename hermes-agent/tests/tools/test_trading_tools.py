import json
from pathlib import Path

import yaml

from model_tools import get_tool_definitions
from tools.registry import registry
from backend.tools.get_crypto_prices import get_crypto_prices


def test_trading_toolset_registers_expected_tools():
    defs = get_tool_definitions(enabled_toolsets=["trading-orchestrator"], quiet_mode=True)
    names = {tool["function"]["name"] for tool in defs}
    assert names == {
        "list_trade_candidates",
        "get_risk_approval",
        "get_portfolio_state",
        "get_execution_status",
        "get_recent_tradingview_alerts",
        "get_pending_signal_events",
        "get_tradingview_alert_context",
    }


def test_trading_research_toolset_includes_macro_series_tools():
    defs = get_tool_definitions(enabled_toolsets=["trading-research"], quiet_mode=True)
    names = {tool["function"]["name"] for tool in defs}
    assert "get_macro_series" in names
    assert "get_macro_observations" in names
    assert "get_macro_regime_summary" in names
    assert "get_forecast_projection" in names
    assert "get_event_risk_macro_context" not in names


def test_trading_risk_and_strategy_toolsets_expose_only_synthesized_macro_access():
    risk_defs = get_tool_definitions(enabled_toolsets=["trading-risk"], quiet_mode=True)
    strategy_defs = get_tool_definitions(enabled_toolsets=["trading-strategy"], quiet_mode=True)
    risk_names = {tool["function"]["name"] for tool in risk_defs}
    strategy_names = {tool["function"]["name"] for tool in strategy_defs}

    assert "get_macro_regime_summary" in risk_names
    assert "get_event_risk_macro_context" in risk_names
    assert "get_macro_series" not in risk_names
    assert "get_macro_observations" not in risk_names

    assert "get_macro_regime_summary" in strategy_names
    assert "get_event_risk_macro_context" not in strategy_names
    assert "get_macro_series" not in strategy_names
    assert "get_forecast_projection" not in strategy_names


def test_get_crypto_prices_fails_safely_without_credentials(monkeypatch):
    monkeypatch.delenv("COINGECKO_API_KEY", raising=False)
    monkeypatch.delenv("COINMARKETCAP_API_KEY", raising=False)
    payload = get_crypto_prices({"symbols": ["BTC"]})
    assert payload["meta"]["ok"] is False
    assert payload["data"]["error"] in {"provider_not_configured", "provider_failure"}


def test_registry_dispatch_returns_json_for_trading_tool(monkeypatch):
    monkeypatch.delenv("BITMART_API_KEY", raising=False)
    monkeypatch.delenv("BITMART_SECRET", raising=False)
    monkeypatch.delenv("BITMART_MEMO", raising=False)
    raw = registry.dispatch("get_execution_status", {})
    parsed = json.loads(raw)
    assert parsed["meta"]["source"] == "get_execution_status"
    assert parsed["meta"]["ok"] is False
    assert parsed["data"]["configured"] is False
    assert parsed["data"]["exchange"] == "BITMART"


def test_execution_tools_only_exposed_to_expected_toolsets():
    portfolio_defs = get_tool_definitions(enabled_toolsets=["trading-portfolio"], quiet_mode=True)
    risk_defs = get_tool_definitions(enabled_toolsets=["trading-risk"], quiet_mode=True)
    strategy_defs = get_tool_definitions(enabled_toolsets=["trading-strategy"], quiet_mode=True)
    research_defs = get_tool_definitions(enabled_toolsets=["trading-research"], quiet_mode=True)

    portfolio_names = {tool["function"]["name"] for tool in portfolio_defs}
    risk_names = {tool["function"]["name"] for tool in risk_defs}
    strategy_names = {tool["function"]["name"] for tool in strategy_defs}
    research_names = {tool["function"]["name"] for tool in research_defs}

    assert {"get_exchange_balances", "get_open_orders", "get_order_history", "get_trade_history"}.issubset(portfolio_names)
    assert {"get_exchange_balances", "get_open_orders", "get_execution_status", "send_risk_alert"}.issubset(risk_names)
    assert {"send_notification", "send_execution_update"}.issubset(portfolio_names)
    assert "place_order" not in portfolio_names
    assert "cancel_order" not in risk_names
    assert "place_order" not in strategy_names
    assert "cancel_order" not in strategy_names
    assert "get_execution_status" not in strategy_names
    assert "place_order" not in research_names
    assert "get_exchange_balances" not in research_names
    assert "send_daily_summary" in research_names
    assert "send_notification" not in strategy_names


def test_shared_resource_catalog_reports_all_core_resources_live():
    from backend.shared_resources import get_shared_resource_audit, initialize_shared_resource_catalog

    initialize_shared_resource_catalog()
    audit = get_shared_resource_audit()
    resources = {item["resource_id"]: item for item in audit["resources"]}

    assert audit["summary"]["total_resources"] == 13
    assert audit["summary"]["running"] == 13
    assert resources["forecasting_time_series_projection_engine"]["applied_to_agents"] is True
    assert "get_forecast_projection" in resources["forecasting_time_series_projection_engine"]["registered_tools"]


def test_forecast_projection_fails_safely_without_history(monkeypatch):
    from backend.tools import get_forecast_projection as module

    monkeypatch.setattr(
        module,
        "get_ohlcv",
        lambda _: {
            "meta": {"ok": True, "providers": []},
            "data": [{"close": 100.0 + idx} for idx in range(10)],
        },
    )

    payload = module.get_forecast_projection({"symbol": "BTC/USD", "horizon": 3, "history_limit": 20})
    assert payload["meta"]["ok"] is False
    assert payload["data"]["error"] == "insufficient_history"


def test_forecast_projection_returns_research_package(monkeypatch):
    from backend.tools import get_forecast_projection as module

    monkeypatch.setattr(
        module,
        "get_ohlcv",
        lambda _: {
            "meta": {"ok": True, "providers": []},
            "data": [{"close": 100.0 + idx} for idx in range(30)],
        },
    )

    payload = module.get_forecast_projection({"symbol": "BTC/USD", "horizon": 3, "history_limit": 30})
    assert payload["meta"]["ok"] is True
    assert payload["data"]["forecast_is_trade_signal"] is False
    assert payload["data"]["horizon"] == 3
    assert len(payload["data"]["scenarios"]) == 3


def test_orchestrator_toolset_covers_assigned_skill_requirements():
    defs = get_tool_definitions(enabled_toolsets=["trading-orchestrator"], quiet_mode=True)
    available = {tool["function"]["name"] for tool in defs}

    root = Path(__file__).resolve().parents[3]
    skill_paths = [
        root / "teams/trading-desk/skills/workflow_routing.yaml",
        root / "teams/trading-desk/skills/execution_requesting.yaml",
    ]

    required_tools = set()
    for path in skill_paths:
        data = yaml.safe_load(path.read_text()) or {}
        required_tools.update(data.get("tools_required", []))

    assert required_tools.issubset(available)


def test_registry_dispatch_returns_recent_tradingview_alerts_envelope(monkeypatch, tmp_path):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    monkeypatch.delenv("DATABASE_URL", raising=False)
    from backend.tradingview.service import TradingViewIngestionService

    TradingViewIngestionService(db_path=tmp_path / "state.db").ingest(
        body=b'{"symbol":"BTCUSDT","signal":"entry","direction":"buy"}',
        content_type="application/json",
    )

    raw = registry.dispatch("get_recent_tradingview_alerts", {"limit": 5})
    parsed = json.loads(raw)
    assert parsed["meta"]["source"] == "get_recent_tradingview_alerts"
    assert parsed["data"]["count"] == 1
    assert parsed["data"]["alerts"][0]["symbol"] == "BTCUSDT"
