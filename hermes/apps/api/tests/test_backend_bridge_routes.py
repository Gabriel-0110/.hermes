from __future__ import annotations

from datetime import UTC, datetime

from fastapi.testclient import TestClient
from hermes_api.integrations.hermes_agent import import_from_hermes_agent
from hermes_api.main import app


def _seed_observability_history() -> None:
    service_module = import_from_hermes_agent("backend.observability.service")
    context_module = import_from_hermes_agent("backend.observability.context")

    service = service_module.get_observability_service()
    context = context_module.AuditContext(
        event_id="evt_api_bridge_1",
        correlation_id="corr_api_bridge_1",
        workflow_run_id="wf_api_bridge_1",
        workflow_name="trading_workflow_graph",
        workflow_step="route_bridge_test",
        agent_name="orchestrator_trader",
    )
    with context_module.use_audit_context(context):
        service.record_workflow_run(
            workflow_run_id="wf_api_bridge_1",
            workflow_name="trading_workflow_graph",
            status="manual_review",
            summarized_input={"symbol": "BTCUSDT"},
        )
        service.record_agent_decision(
            agent_name="risk_manager",
            status="rejected",
            decision="reject",
            summarized_output={"reason": "event risk high"},
        )
        service.record_execution_event(
            status="pending",
            event_type="execution_handoff_ready",
            summarized_output={"symbol": "BTCUSDT"},
        )
        service.record_system_error(
            status="failed",
            error_message="simulated bridge error",
            error_type="RuntimeError",
            is_failure=True,
        )


def _seed_tradingview_signal() -> None:
    store_module = import_from_hermes_agent("backend.tradingview.store")

    store = store_module.TradingViewStore()
    alert = store.insert_alert(
        source="tradingview",
        symbol="BTCUSDT",
        timeframe="15m",
        alert_name="Momentum Breakout",
        signal="entry",
        direction="buy",
        strategy="momentum_v1",
        price=65000.0,
        payload={"symbol": "BTCUSDT", "signal": "entry"},
        processing_status="signal_ready",
        processing_error=None,
    )
    store.publish_event(
        event_type="tradingview_signal_ready",
        alert_event_id=alert.id,
        symbol=alert.symbol,
        payload={
            "alert_id": alert.id,
            "symbol": alert.symbol,
            "correlation_id": "corr_api_bridge_signal",
            "event_id": "evt_api_bridge_signal",
        },
        delivery_status="pending",
    )


def _seed_portfolio_snapshot() -> None:
    db_module = import_from_hermes_agent("backend.db")
    session_module = import_from_hermes_agent("backend.db.session")

    db_module.ensure_time_series_schema(session_module.get_engine())
    with db_module.session_scope() as session:
        db_module.HermesTimeSeriesRepository(session).insert_portfolio_snapshot(
            account_id="paper",
            total_equity_usd=125000.0,
            cash_usd=45000.0,
            exposure_usd=80000.0,
            positions=[{"symbol": "BTC", "quantity": 1.25}],
            snapshot_time=datetime(2026, 4, 15, 12, 0, tzinfo=UTC),
        )


def test_observability_route_returns_live_dashboard(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    monkeypatch.delenv("DATABASE_URL", raising=False)

    _seed_observability_history()
    client = TestClient(app)
    response = client.get("/api/v1/observability")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "live"
    assert (
        payload["dashboard"]["recent_workflow_runs"][0]["workflow_name"]
        == "trading_workflow_graph"
    )


def test_agents_route_returns_manifest_and_live_decision_counts(
    monkeypatch,
    tmp_path,
) -> None:
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    monkeypatch.delenv("DATABASE_URL", raising=False)

    _seed_observability_history()
    client = TestClient(app)
    response = client.get("/api/v1/agents")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "live"
    assert payload["team_name"] == "hermes-trading-desk"
    assert payload["count"] == 5
    risk_agent = next(
        agent for agent in payload["agents"] if agent["canonical_agent_id"] == "risk_manager"
    )
    assert risk_agent["recent_decision_count"] >= 1
    assert risk_agent["latest_decision"]["agent_name"] == "risk_manager"


def test_agent_detail_and_timeline_routes_return_live_activity(
    monkeypatch,
    tmp_path,
) -> None:
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    monkeypatch.delenv("DATABASE_URL", raising=False)

    _seed_observability_history()
    client = TestClient(app)

    detail_response = client.get("/api/v1/agents/risk_manager")
    assert detail_response.status_code == 200
    detail_payload = detail_response.json()
    assert detail_payload["status"] == "live"
    assert detail_payload["agent"]["canonical_agent_id"] == "risk_manager"
    assert detail_payload["agent"]["recent_decisions"][0]["agent_name"] == "risk_manager"
    assert (
        detail_payload["agent"]["correlated_timelines"][0]["correlation_id"]
        == "corr_api_bridge_1"
    )

    timeline_response = client.get("/api/v1/agents/risk_manager/timeline")
    assert timeline_response.status_code == 200
    timeline_payload = timeline_response.json()
    assert timeline_payload["status"] == "live"
    assert timeline_payload["agent_id"] == "risk_manager"
    assert timeline_payload["count"] >= 1
    assert timeline_payload["timeline"][0]["correlation_id"] == "corr_api_bridge_1"


def test_execution_route_returns_pending_signal_events(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    monkeypatch.delenv("DATABASE_URL", raising=False)

    _seed_tradingview_signal()
    client = TestClient(app)
    response = client.get("/api/v1/execution")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "live"
    assert payload["execution"]["pending_signal_count"] == 1
    assert (
        payload["execution"]["pending_signal_events"][0]["event_type"]
        == "tradingview_signal_ready"
    )
    assert payload["execution"]["safety"]["execution_mode"] == "paper"
    assert payload["execution"]["live_trading_enabled"] is False
    assert payload["execution"]["live_trading_blockers"] == []


def test_execution_route_surfaces_live_approval_requirement(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("HERMES_TRADING_MODE", "live")
    monkeypatch.setenv("HERMES_ENABLE_LIVE_TRADING", "true")
    monkeypatch.setenv("HERMES_LIVE_TRADING_ACK", "I_ACKNOWLEDGE_LIVE_TRADING_RISK")
    monkeypatch.setenv("HERMES_REQUIRE_APPROVAL", "true")

    _seed_tradingview_signal()
    client = TestClient(app)
    response = client.get("/api/v1/execution")

    assert response.status_code == 200
    payload = response.json()
    assert payload["execution"]["approval_required"] is True
    assert payload["execution"]["live_trading_enabled"] is False
    assert payload["execution"]["safety"]["approval_required"] is True


def test_execution_route_surfaces_live_blockers_in_typed_safety(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("HERMES_TRADING_MODE", "live")
    monkeypatch.delenv("HERMES_ENABLE_LIVE_TRADING", raising=False)
    monkeypatch.delenv("HERMES_LIVE_TRADING_ACK", raising=False)

    _seed_tradingview_signal()
    client = TestClient(app)
    response = client.get("/api/v1/execution")

    assert response.status_code == 200
    payload = response.json()
    assert payload["execution"]["live_trading_enabled"] is False
    assert payload["execution"]["safety"]["execution_mode"] == "live"
    assert payload["execution"]["safety"]["blockers"]


def test_agents_route_overlays_runtime_trading_mode(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("HERMES_TRADING_MODE", "live")

    _seed_observability_history()
    client = TestClient(app)
    response = client.get("/api/v1/agents")

    assert response.status_code == 200
    payload = response.json()
    assert payload["trading_mode"]["mode"] == "live"
    assert payload["trading_mode"]["forbid_live_execution"] is False


def test_risk_and_resources_routes_return_live_backend_data(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("TRADING_PORTFOLIO_ACCOUNT_ID", "paper")

    _seed_observability_history()
    _seed_tradingview_signal()
    _seed_portfolio_snapshot()

    client = TestClient(app)

    risk_response = client.get("/api/v1/risk")
    assert risk_response.status_code == 200
    risk_payload = risk_response.json()
    assert risk_payload["status"] == "live"
    assert risk_payload["risk"]["recent_risk_rejections"][0]["agent_name"] == "risk_manager"

    portfolio_response = client.get("/api/v1/risk/portfolio")
    assert portfolio_response.status_code == 200
    portfolio_payload = portfolio_response.json()
    assert portfolio_payload["portfolio"]["data"]["account_id"] == "paper"
    assert portfolio_payload["portfolio"]["data"]["positions"][0]["symbol"] == "BTC"


def test_execution_proposal_endpoints_expose_controlled_pipeline(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("HERMES_API_DEV_BYPASS_AUTH", "true")
    from hermes_api.core.config import get_settings

    get_settings.cache_clear()

    _seed_portfolio_snapshot()
    client = TestClient(app)
    proposal = {
        "source_agent": "strategy_agent",
        "symbol": "BTCUSDT",
        "side": "buy",
        "order_type": "market",
        "requested_size_usd": 1500.0,
        "rationale": "Breakout continuation with bounded size and monitored invalidation.",
        "strategy_id": "breakout_v1",
        "strategy_template_id": "momentum_breakout",
        "timeframe": "15m",
    }

    evaluate_response = client.post("/api/v1/execution/proposals/evaluate", json=proposal)
    assert evaluate_response.status_code == 200
    evaluate_payload = evaluate_response.json()
    assert evaluate_payload["status"] == "live"
    assert evaluate_payload["policy_decision"]["proposal_id"]
    assert evaluate_payload["policy_decision"]["execution_mode"] == "paper"

    submit_response = client.post("/api/v1/execution/proposals/submit", json=proposal)
    assert submit_response.status_code == 200
    submit_payload = submit_response.json()
    assert submit_payload["status"] == "live"
    assert submit_payload["dispatch"]["status"] in {"queued", "manual_review"}
    assert submit_payload["dispatch"]["dispatch_payload"]["symbol"] == "BTCUSDT"


def test_position_monitor_endpoint_returns_portfolio_risk_summary(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    monkeypatch.delenv("DATABASE_URL", raising=False)

    _seed_portfolio_snapshot()
    client = TestClient(app)
    response = client.get("/api/v1/execution/positions/monitor")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "live"
    assert payload["monitor"]["portfolio"]["account_id"] == "paper"
    assert payload["monitor"]["risk_summary"]["total_positions"] >= 1
    assert payload["monitor"]["state_mode"] in {"live", "paper", "unknown"}


def test_risk_route_surfaces_execution_safety_and_position_monitor(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    monkeypatch.delenv("DATABASE_URL", raising=False)

    _seed_observability_history()
    _seed_portfolio_snapshot()

    client = TestClient(app)
    response = client.get("/api/v1/risk")

    assert response.status_code == 200
    payload = response.json()
    assert payload["risk"]["execution_safety"]["execution_mode"] == "paper"
    assert payload["risk"]["position_monitor"]["portfolio"]["account_id"] == "paper"

    resources_response = client.get("/api/v1/resources")
    assert resources_response.status_code == 200
    resources_payload = resources_response.json()
    assert resources_payload["status"] == "live"
    assert resources_payload["contract"] == "shared-resource-audit"
    assert resources_payload["summary"]["total_resources"] == len(resources_payload["resources"])
    assert resources_payload["summary"]["total_resources"] == 13
    assert resources_payload["summary"]["running"] == 13

    resources_by_id = {
        item["resource_id"]: item
        for item in resources_payload["resources"]
    }
    assert resources_by_id["execution_exchange_connector"]["status"] == "live"
    assert resources_by_id["portfolio_account_state"]["status"] == "live"
    assert resources_by_id["strategy_library"]["status"] == "live"
    assert resources_by_id["forecasting_time_series_projection_engine"]["status"] == "live"
