"""Replay runner for Hermes trading workflow evaluation."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from time import perf_counter
from typing import Any

from backend.db import HermesTimeSeriesRepository, session_scope
from backend.models import PortfolioState
from backend.observability import AuditContext, use_audit_context
from backend.observability.service import get_observability_service
from backend.workflows.deps import TradingWorkflowDeps
from backend.workflows.graph import IngestSignalNode, trading_workflow_graph
from backend.workflows.models import TradingInputEvent, TradingWorkflowState, WorkflowStage
from backend.workflows.tools import HermesWorkflowTools, TradingWorkflowToolset, WorkflowToolResult

from .models import (
    EvaluationRuleConfig,
    ReplayCase,
    ReplayExecutionArtifacts,
    ReplayResultRecord,
    ReplayRunConfig,
    ReplayRunRecord,
    ReplayRunStatus,
    ReplayWorkflowExecution,
)
from .scoring import score_replay_result
from .storage import ReplayStorage

logger = logging.getLogger(__name__)


def _tool_result(name: str, data: Any, *, warnings: list[str] | None = None) -> WorkflowToolResult:
    return WorkflowToolResult(name=name, ok=True, data=data, warnings=warnings or [])


@dataclass(slots=True)
class ReplayWorkflowTools:
    """Replay-safe wrapper around the normal workflow tool surface."""

    base_tools: TradingWorkflowToolset = field(default_factory=HermesWorkflowTools)
    replay_case: ReplayCase | None = None
    database_url: str | None = None
    allow_live_execution: bool = False
    allow_live_notifications: bool = False
    notification_test_sink: str | None = "log"

    def get_tradingview_alert_context(self, payload: dict[str, Any]) -> WorkflowToolResult:
        if self.replay_case and payload.get("alert_id") == self.replay_case.source_alert_id:
            data = self.replay_case.source_payload
            return _tool_result(
                "get_tradingview_alert_context",
                data,
                warnings=["Replay mode served TradingView alert context from stored historical payload."],
            )
        return self.base_tools.get_tradingview_alert_context(payload)

    def get_market_overview(self, payload: dict[str, Any] | None = None) -> WorkflowToolResult:
        return self.base_tools.get_market_overview(payload)

    def get_macro_regime_summary(self, payload: dict[str, Any] | None = None) -> WorkflowToolResult:
        return self.base_tools.get_macro_regime_summary(payload)

    def get_event_risk_summary(self, payload: dict[str, Any] | None = None) -> WorkflowToolResult:
        return self.base_tools.get_event_risk_summary(payload)

    def get_onchain_signal_summary(self, payload: dict[str, Any]) -> WorkflowToolResult:
        return self.base_tools.get_onchain_signal_summary(payload)

    def get_volatility_metrics(self, payload: dict[str, Any]) -> WorkflowToolResult:
        return self.base_tools.get_volatility_metrics(payload)

    def get_portfolio_state(self, payload: dict[str, Any] | None = None) -> WorkflowToolResult:
        if self.replay_case is None:
            return self.base_tools.get_portfolio_state(payload)

        account_id = os.getenv("TRADING_PORTFOLIO_ACCOUNT_ID", "paper")
        with session_scope(database_url=self.database_url) as session:
            snapshot = HermesTimeSeriesRepository(session).get_portfolio_snapshot_at_or_before(
                account_id=account_id,
                as_of=self.replay_case.input_event.received_at,
            )

        if snapshot is None:
            return self.base_tools.get_portfolio_state(payload)

        state = PortfolioState(
            account_id=snapshot.account_id,
            total_equity_usd=snapshot.total_equity_usd,
            cash_usd=snapshot.cash_usd,
            exposure_usd=snapshot.exposure_usd,
            positions=snapshot.positions or [],
            updated_at=snapshot.snapshot_time.isoformat(),
        )
        return _tool_result(
            "get_portfolio_state",
            state.model_dump(mode="json"),
            warnings=["Replay mode used historical portfolio snapshot at-or-before the source event timestamp."],
        )

    def get_risk_approval(self, payload: dict[str, Any]) -> WorkflowToolResult:
        return self.base_tools.get_risk_approval(payload)

    def place_order(self, payload: dict[str, Any]) -> WorkflowToolResult:
        if self.allow_live_execution:
            raise RuntimeError("Replay tool wrapper does not support live order placement.")
        return WorkflowToolResult(
            name="place_order",
            ok=False,
            data={"error": "replay_execution_blocked", "detail": "Replay mode blocks live order placement."},
            warnings=["Replay mode blocked a live order placement attempt."],
            error="replay_execution_blocked",
            detail="Replay mode blocks live order placement.",
        )

    def send_notification(self, payload: dict[str, Any]) -> WorkflowToolResult:
        if self.allow_live_notifications:
            raise RuntimeError("Replay tool wrapper does not support live notification delivery.")
        sink = self.notification_test_sink or "disabled"
        return WorkflowToolResult(
            name="send_notification",
            ok=True,
            data={"sink": sink, "payload": payload},
            warnings=[f"Replay mode diverted notification to test sink '{sink}'."],
        )


@dataclass(slots=True)
class ReplayRunner:
    """Run historical TradingView workflow cases in replay mode."""

    storage: ReplayStorage = field(default_factory=ReplayStorage)
    base_tools: TradingWorkflowToolset = field(default_factory=HermesWorkflowTools)

    def load_tradingview_cases(self, *, alert_ids: list[str]) -> list[ReplayCase]:
        return [self.storage.load_tradingview_alert_case(alert_id=alert_id) for alert_id in alert_ids]

    async def run_case(
        self,
        replay_case: ReplayCase,
        *,
        rules: EvaluationRuleConfig | None = None,
        run_config: ReplayRunConfig | None = None,
        deps: TradingWorkflowDeps | None = None,
    ) -> ReplayExecutionArtifacts:
        run_config = run_config or ReplayRunConfig()
        rules = rules or EvaluationRuleConfig()
        self.storage.save_replay_case(replay_case)

        run_record = ReplayRunRecord(
            replay_case_id=replay_case.id,
            workflow_name=run_config.workflow_name,
            workflow_version=run_config.workflow_version,
            model_name=run_config.model_name,
            prompt_version=run_config.prompt_version,
            source_event_id=replay_case.source_event_id,
            source_correlation_id=replay_case.source_correlation_id,
            mode=run_config.mode,
            status=ReplayRunStatus.RUNNING,
            configuration=run_config.model_dump(mode="json"),
            metadata={
                **run_config.metadata,
                "replay_case_id": replay_case.id,
                "source_alert_id": replay_case.source_alert_id,
            },
        )
        self.storage.save_replay_run(run_record)

        try:
            execution = await self._execute_workflow(replay_case, run_record, run_config, deps=deps)
            result_record = ReplayResultRecord(
                replay_run_id=run_record.id,
                replay_case_id=replay_case.id,
                workflow_run_id=execution.workflow_run_id,
                source_event_id=replay_case.source_event_id,
                source_correlation_id=replay_case.source_correlation_id,
                decision=execution.output.get("decision"),
                status=execution.output.get("status"),
                should_execute=bool(execution.output.get("should_execute")),
                execution_intent=execution.output.get("execution_intent") or {},
                notifications=execution.output.get("notifications") or [],
                output=execution.output,
                state=execution.state.model_dump(mode="json"),
                latency_ms=execution.latency_ms,
                metadata={
                    "replay_mode": True,
                    "live_execution_blocked": not run_config.allow_live_execution,
                    "live_notifications_blocked": not run_config.allow_live_notifications,
                },
            )
            self.storage.save_replay_result(result_record)
            scores = score_replay_result(
                replay_run_id=run_record.id,
                replay_case=replay_case,
                replay_result=result_record,
                rules=rules,
            )
            self.storage.save_evaluation_scores(scores)
            self.storage.update_replay_run(
                run_record.id,
                status=ReplayRunStatus.COMPLETED.value,
                workflow_run_id=execution.workflow_run_id,
                metadata={**run_record.metadata, "latency_ms": execution.latency_ms},
            )
            run_record.status = ReplayRunStatus.COMPLETED
            run_record.workflow_run_id = execution.workflow_run_id
            run_record.metadata = {**run_record.metadata, "latency_ms": execution.latency_ms}
            logger.info(
                "Replay completed replay_run_id=%s replay_case_id=%s workflow_run_id=%s",
                run_record.id,
                replay_case.id,
                execution.workflow_run_id,
            )
            return ReplayExecutionArtifacts(
                replay_run=run_record,
                replay_result=result_record,
                evaluation_scores=scores,
            )
        except Exception as exc:
            self.storage.update_replay_run(
                run_record.id,
                status=ReplayRunStatus.FAILED.value,
                metadata={**run_record.metadata, "error": str(exc)},
            )
            logger.exception("Replay failed replay_run_id=%s replay_case_id=%s", run_record.id, replay_case.id)
            raise

    async def _execute_workflow(
        self,
        replay_case: ReplayCase,
        run_record: ReplayRunRecord,
        run_config: ReplayRunConfig,
        *,
        deps: TradingWorkflowDeps | None = None,
    ) -> ReplayWorkflowExecution:
        event = TradingInputEvent.model_validate(
            replay_case.input_event.model_copy(
                update={
                    "workflow_id": run_record.id.replace("replay_run_", "wf_replay_"),
                    "metadata": {
                        **replay_case.input_event.metadata,
                        **run_config.metadata,
                        "run_mode": "replay",
                        "replay_case_id": replay_case.id,
                        "replay_run_id": run_record.id,
                        "source_event_id": replay_case.source_event_id,
                        "source_correlation_id": replay_case.source_correlation_id,
                    },
                }
            ).model_dump(mode="json")
        )
        replay_tools = ReplayWorkflowTools(
            base_tools=self.base_tools,
            replay_case=replay_case,
            database_url=self.storage.database_url,
            allow_live_execution=run_config.allow_live_execution,
            allow_live_notifications=run_config.allow_live_notifications,
            notification_test_sink=run_config.notification_test_sink,
        )
        workflow_deps = deps or TradingWorkflowDeps()
        workflow_deps.tools = replay_tools
        if run_config.model_name and workflow_deps.agent_model is None:
            logger.info("Replay config requested model label=%s but supplied deps.agent_model takes precedence only when present.", run_config.model_name)

        state = TradingWorkflowState.from_event(event)
        correlation_id = event.correlation_id or event.alert_id or state.workflow_id
        observability = get_observability_service()
        audit = AuditContext(
            event_id=event.event_id,
            correlation_id=correlation_id,
            workflow_run_id=state.workflow_id,
            workflow_name=run_config.workflow_name,
            workflow_step=WorkflowStage.INGEST_SIGNAL.value,
            agent_name="orchestrator_trader",
            metadata=event.metadata,
        )
        started = perf_counter()
        with use_audit_context(audit):
            observability.record_workflow_run(
                workflow_run_id=state.workflow_id,
                workflow_name=run_config.workflow_name,
                status="running",
                summarized_input=event.model_dump(mode="json"),
                metadata=event.metadata,
            )
            logger.info(
                "Replay workflow start replay_run_id=%s workflow_run_id=%s source_event_id=%s",
                run_record.id,
                state.workflow_id,
                replay_case.source_event_id,
            )
            try:
                async with trading_workflow_graph.iter(IngestSignalNode(), state=state, deps=workflow_deps) as graph_run:
                    async for node in graph_run:
                        logger.info(
                            "Replay workflow node complete replay_run_id=%s workflow_run_id=%s node=%s",
                            run_record.id,
                            state.workflow_id,
                            type(node).__name__,
                        )
                result = graph_run.result
                assert result is not None, "Replay graph run did not produce a result"
                observability.record_workflow_run(
                    workflow_run_id=state.workflow_id,
                    workflow_name=run_config.workflow_name,
                    status=result.output.status,
                    summarized_output=result.output.model_dump(mode="json"),
                    metadata={
                        **event.metadata,
                        "branch_history": [item.value for item in state.branch_history],
                    },
                )
                latency_ms = round((perf_counter() - started) * 1000.0, 3)
                return ReplayWorkflowExecution(
                    state=state,
                    output=result.output.model_dump(mode="json"),
                    workflow_run_id=state.workflow_id,
                    correlation_id=correlation_id,
                    latency_ms=latency_ms,
                )
            except Exception as exc:
                observability.record_workflow_run(
                    workflow_run_id=state.workflow_id,
                    workflow_name=run_config.workflow_name,
                    status="failed",
                    error_message=str(exc),
                    metadata=event.metadata,
                )
                observability.record_system_error(
                    status="replay_failed",
                    error_message=str(exc),
                    error_type=exc.__class__.__name__,
                    summarized_input=event.model_dump(mode="json"),
                    metadata={
                        **event.metadata,
                        "workflow_run_id": state.workflow_id,
                    },
                )
                raise
