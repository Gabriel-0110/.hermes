from __future__ import annotations

from backend.observability import AuditContext, use_audit_context
from backend.observability.service import ObservabilityService


def test_observability_service_persists_and_queries_timeline(tmp_path, monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))

    service = ObservabilityService()
    context = AuditContext(
        event_id="evt_test_1",
        correlation_id="corr_test_1",
        workflow_run_id="wf_test_1",
        workflow_name="trading_workflow_graph",
        workflow_step="ingest_signal",
        agent_name="orchestrator_trader",
    )

    with use_audit_context(context):
        service.record_workflow_run(
            workflow_run_id="wf_test_1",
            workflow_name="trading_workflow_graph",
            status="running",
            summarized_input={"symbol": "BTCUSDT"},
        )
        service.record_workflow_step(
            step_id="wf_test_1:ingest_signal",
            workflow_run_id="wf_test_1",
            workflow_name="trading_workflow_graph",
            workflow_step="ingest_signal",
            status="completed",
            summarized_output={"symbol": "BTCUSDT", "signal": "entry"},
        )
        service.record_tool_call(
            tool_name="get_market_overview",
            status="completed",
            summarized_input={"symbol": "BTCUSDT"},
            summarized_output={"regime": "risk_on"},
        )
        service.record_agent_decision(
            agent_name="market_researcher",
            status="completed",
            decision="continue",
            summarized_output={"summary": "Context looks constructive."},
        )
        service.record_execution_event(
            status="approved",
            event_type="execution_handoff_ready",
            symbol="BTCUSDT",
            payload={"execution_request": {"symbol": "BTCUSDT", "amount": 0.1}},
            summarized_output={"size_usd": 2000},
        )
        service.record_movement(
            movement_type="order_simulated",
            status="paper_filled",
            account_id="paper",
            symbol="BTCUSDT",
            side="buy",
            quantity=0.1,
            cash_delta_usd=-2000,
            notional_delta_usd=2000,
            price=20000,
            execution_mode="paper",
            request_id="exec_req_test_1",
            idempotency_key="idem_test_1",
            source_kind="test_suite",
            payload={"note": "movement persisted"},
        )
        service.record_system_error(
            status="failed",
            error_message="transient execution adapter error",
            error_type="RuntimeError",
            is_failure=True,
        )
        service.record_workflow_run(
            workflow_run_id="wf_test_1",
            workflow_name="trading_workflow_graph",
            status="approved",
            summarized_output={"decision": "execute"},
        )

    run = service.get_workflow_run("wf_test_1")
    assert run is not None
    assert run["status"] == "approved"
    assert run["correlation_id"] == "corr_test_1"
    assert len(run["steps"]) == 1

    tool_calls = service.get_tool_call_history(correlation_id="corr_test_1")
    assert tool_calls[0]["tool_name"] == "get_market_overview"

    decisions = service.get_agent_decision_history(correlation_id="corr_test_1")
    assert decisions[0]["agent_name"] == "market_researcher"

    execution_events = service.get_execution_event_history(correlation_id="corr_test_1")
    assert execution_events[0]["event_type"] == "execution_handoff_ready"
    assert execution_events[0]["symbol"] == "BTCUSDT"
    assert execution_events[0]["payload"]["execution_request"]["symbol"] == "BTCUSDT"

    movements = service.get_movement_history(correlation_id="corr_test_1")
    assert movements[0]["movement_type"] == "order_simulated"
    assert movements[0]["account_id"] == "paper"

    failures = service.get_recent_failures()
    assert failures[0]["error_type"] == "RuntimeError"

    timeline = service.get_event_timeline("corr_test_1")
    assert any(item["kind"] == "workflow_run" for item in timeline)
    assert any(item["kind"] == "workflow_step" for item in timeline)
    assert any(item["kind"] == "tool_call" for item in timeline)
    assert any(item["kind"] == "movement" for item in timeline)
