"""Storage helpers for replay and evaluation persistence."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import timezone
from typing import Any

from backend.db import HermesTimeSeriesRepository, ensure_time_series_schema, session_scope
from backend.db.session import get_engine
from backend.tradingview.models import TradingViewAlertRecord, TradingViewInternalEvent

from .models import (
    EvaluationScoreRecord,
    RegressionComparisonRecord,
    ReplayCase,
    ReplayResultRecord,
    ReplayRunRecord,
)

logger = logging.getLogger(__name__)


def _row_created_at(row: Any) -> Any:
    value = getattr(row, "created_at", None)
    return value.astimezone(timezone.utc) if value is not None else None


@dataclass(slots=True)
class ReplayStorage:
    """Persistence facade for evaluation artifacts in TimescaleDB."""

    database_url: str | None = None

    def __post_init__(self) -> None:
        ensure_time_series_schema(get_engine(database_url=self.database_url))

    def save_replay_case(self, case: ReplayCase) -> ReplayCase:
        with session_scope(database_url=self.database_url) as session:
            row = HermesTimeSeriesRepository(session).insert_replay_case(
                replay_case_id=case.id,
                source_type=case.source_type.value,
                source_event_id=case.source_event_id,
                source_correlation_id=case.source_correlation_id,
                source_alert_id=case.source_alert_id,
                label=case.label,
                input_payload=case.input_event.model_dump(mode="json"),
                expected_outcome=case.expected_outcome,
                metadata={**case.metadata, "source_payload": case.source_payload},
                created_at=case.created_at,
            )
        logger.info("replay case stored replay_case_id=%s source_event_id=%s", row.id, row.source_event_id)
        return case

    def save_replay_run(self, run: ReplayRunRecord) -> ReplayRunRecord:
        with session_scope(database_url=self.database_url) as session:
            HermesTimeSeriesRepository(session).insert_replay_run(
                replay_run_id=run.id,
                replay_case_id=run.replay_case_id,
                workflow_run_id=run.workflow_run_id,
                workflow_name=run.workflow_name,
                workflow_version=run.workflow_version,
                model_name=run.model_name,
                prompt_version=run.prompt_version,
                source_event_id=run.source_event_id,
                source_correlation_id=run.source_correlation_id,
                mode=run.mode,
                status=run.status.value,
                configuration=run.configuration,
                metadata=run.metadata,
                created_at=run.created_at,
            )
        return run

    def update_replay_run(
        self,
        replay_run_id: str,
        *,
        status: str | None = None,
        workflow_run_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        with session_scope(database_url=self.database_url) as session:
            HermesTimeSeriesRepository(session).update_replay_run(
                replay_run_id,
                status=status,
                workflow_run_id=workflow_run_id,
                metadata=metadata,
            )

    def save_replay_result(self, result: ReplayResultRecord) -> ReplayResultRecord:
        with session_scope(database_url=self.database_url) as session:
            HermesTimeSeriesRepository(session).insert_replay_result(
                replay_result_id=result.id,
                replay_run_id=result.replay_run_id,
                replay_case_id=result.replay_case_id,
                workflow_run_id=result.workflow_run_id,
                source_event_id=result.source_event_id,
                source_correlation_id=result.source_correlation_id,
                decision=result.decision,
                status=result.status,
                should_execute=result.should_execute,
                execution_intent=result.execution_intent,
                notifications=result.notifications,
                output_json=result.output,
                state_json=result.state,
                latency_ms=result.latency_ms,
                metadata=result.metadata,
                created_at=result.created_at,
            )
        return result

    def save_evaluation_scores(self, scores: list[EvaluationScoreRecord]) -> list[EvaluationScoreRecord]:
        if not scores:
            return []
        with session_scope(database_url=self.database_url) as session:
            repo = HermesTimeSeriesRepository(session)
            for score in scores:
                repo.insert_evaluation_score(
                    evaluation_score_id=score.id,
                    replay_run_id=score.replay_run_id,
                    replay_result_id=score.replay_result_id,
                    replay_case_id=score.replay_case_id,
                    rule_name=score.rule_name,
                    metric_name=score.metric_name,
                    value=score.value,
                    passed=score.passed,
                    detail=score.detail,
                    metadata=score.metadata,
                    created_at=score.created_at,
                )
        return scores

    def save_regression_comparison(self, comparison: RegressionComparisonRecord) -> RegressionComparisonRecord:
        with session_scope(database_url=self.database_url) as session:
            HermesTimeSeriesRepository(session).insert_regression_comparison(
                regression_comparison_id=comparison.id,
                baseline_replay_run_id=comparison.baseline_replay_run_id,
                candidate_replay_run_id=comparison.candidate_replay_run_id,
                comparison_type=comparison.comparison_type.value,
                baseline_label=comparison.baseline_label,
                candidate_label=comparison.candidate_label,
                status=comparison.status,
                summary=comparison.summary,
                metadata=comparison.metadata,
                created_at=comparison.created_at,
            )
        return comparison

    def load_tradingview_alert_case(self, *, alert_id: str, label: str | None = None) -> ReplayCase:
        from backend.workflows.models import TradingInputEvent

        with session_scope(database_url=self.database_url) as session:
            repo = HermesTimeSeriesRepository(session)
            alert_row = repo.get_tradingview_alert_by_id(alert_id)
            if alert_row is None:
                raise ValueError(f"TradingView alert not found: {alert_id}")
            internal_rows = repo.list_internal_events(alert_event_id=alert_id, limit=50)

        alert = TradingViewAlertRecord(
            id=alert_row.id,
            ts=alert_row.event_time.timestamp(),
            source=alert_row.source,
            symbol=alert_row.symbol,
            timeframe=alert_row.timeframe,
            alert_name=alert_row.alert_name,
            signal=alert_row.signal,
            direction=alert_row.direction,
            strategy=alert_row.strategy,
            price=alert_row.price,
            payload=alert_row.payload or {},
            processing_status=alert_row.processing_status,
            processing_error=alert_row.processing_error,
        )
        internal_events = [
            TradingViewInternalEvent(
                id=row.id,
                ts=row.event_time.timestamp(),
                event_type=row.event_type,
                alert_event_id=row.alert_event_id,
                symbol=row.symbol,
                payload=row.payload or {},
                delivery_status=row.delivery_status,
                delivery_error=row.delivery_error,
            )
            for row in internal_rows
        ]

        signal_event = next((event for event in internal_events if event.event_type == "tradingview_signal_ready"), None)
        source_payload = {
            "alert": alert.model_dump(mode="json"),
            "internal_events": [event.model_dump(mode="json") for event in internal_events],
        }
        signal_payload = signal_event.payload if signal_event is not None else {}
        alert_payload = alert.payload or {}
        event_payload = {
            **alert_payload,
            **signal_payload,
            "alert_id": alert.id,
        }
        correlation_id = signal_payload.get("correlation_id") or alert_payload.get("correlation_id") or alert.id
        event_id = signal_event.id if signal_event is not None else alert.id
        input_event = TradingInputEvent(
            event_id=event_id,
            event_type="tradingview_signal_ready" if signal_event is not None else "tradingview_alert_received",
            source="tradingview",
            received_at=alert_row.event_time.astimezone(timezone.utc),
            symbol=signal_payload.get("symbol") or alert.symbol,
            timeframe=signal_payload.get("timeframe") or alert.timeframe,
            strategy=signal_payload.get("strategy") or alert.strategy,
            signal=signal_payload.get("signal") or alert.signal,
            direction=signal_payload.get("direction") or alert.direction,
            price=alert.price,
            alert_id=alert.id,
            correlation_id=correlation_id,
            payload=event_payload,
            metadata={
                "source_event_id": event_id,
                "source_alert_id": alert.id,
                "source_correlation_id": correlation_id,
                "replay_source_type": "tradingview_alert",
            },
        )
        return ReplayCase(
            source_event_id=event_id,
            source_correlation_id=correlation_id,
            source_alert_id=alert.id,
            label=label or f"{alert.symbol or 'unknown'}:{alert.id}",
            input_event=input_event,
            source_payload=source_payload,
            metadata={"processing_status": alert.processing_status},
        )

    def list_replay_results(self, replay_run_id: str) -> list[ReplayResultRecord]:
        with session_scope(database_url=self.database_url) as session:
            rows = HermesTimeSeriesRepository(session).list_replay_results(replay_run_id=replay_run_id)
        return [
            ReplayResultRecord(
                id=row.id,
                created_at=_row_created_at(row),
                replay_run_id=row.replay_run_id,
                replay_case_id=row.replay_case_id,
                workflow_run_id=row.workflow_run_id,
                source_event_id=row.source_event_id,
                source_correlation_id=row.source_correlation_id,
                decision=row.decision,
                status=row.status,
                should_execute=row.should_execute,
                execution_intent=row.execution_intent or {},
                notifications=row.notifications or [],
                output=row.output_json or {},
                state=row.state_json or {},
                latency_ms=row.latency_ms,
                metadata=row.metadata_json or {},
            )
            for row in rows
        ]

    def list_evaluation_scores(self, replay_run_id: str) -> list[EvaluationScoreRecord]:
        with session_scope(database_url=self.database_url) as session:
            rows = HermesTimeSeriesRepository(session).list_evaluation_scores(replay_run_id=replay_run_id)
        return [
            EvaluationScoreRecord(
                id=row.id,
                created_at=_row_created_at(row),
                replay_run_id=row.replay_run_id,
                replay_result_id=row.replay_result_id,
                replay_case_id=row.replay_case_id,
                rule_name=row.rule_name,
                metric_name=row.metric_name,
                value=row.value,
                passed=row.passed,
                detail=row.detail,
                metadata=row.metadata_json or {},
            )
            for row in rows
        ]
