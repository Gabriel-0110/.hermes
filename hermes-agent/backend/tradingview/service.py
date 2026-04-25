"""Shared TradingView ingestion service."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any
from uuid import uuid4

from redis.exceptions import RedisError

from backend.event_bus.models import TradingEvent
from backend.event_bus.publisher import TradingEventPublisher
from backend.observability import AuditContext, use_audit_context
from backend.observability.service import get_observability_service

from .models import TradingViewAlertRecord, TradingViewIngestionResult
from .normalize import normalize_alert, parse_payload, sanitize_payload
from .store import TradingViewStore

logger = logging.getLogger(__name__)


class TradingViewIngestionService:
    """Validate, normalize, persist, and republish TradingView alerts."""

    def __init__(self, db_path: Path | None = None, event_publisher: TradingEventPublisher | None = None):
        self.store = TradingViewStore(db_path=db_path)
        self.event_publisher = event_publisher or TradingEventPublisher()
        logger.info("TradingView ingestion service initialized with Redis stream publisher.")

    def ingest(self, *, body: bytes, content_type: str | None, source: str = "tradingview") -> TradingViewIngestionResult:
        observability = get_observability_service()
        parsed = parse_payload(body, content_type)
        sanitized_raw, redacted_fields = sanitize_payload(parsed.raw_payload)
        parsed = parsed.model_copy(update={"raw_payload": sanitized_raw})
        normalized = normalize_alert(parsed).model_copy(update={"source": source, "raw_payload": sanitized_raw})

        processing_status = "signal_ready" if normalized.signal or normalized.direction else "received"
        processing_error = parsed.parse_error
        if parsed.mode == "invalid_json":
            processing_status = "failed"

        correlation_id = f"corr_{uuid4().hex[:16]}"
        event_id = f"evt_{uuid4().hex[:16]}"
        audit = AuditContext(
            event_id=event_id,
            correlation_id=correlation_id,
            workflow_name="tradingview_ingestion",
            workflow_step="ingest_webhook",
            agent_name="tradingview_ingestion_service",
            metadata={"source": source},
        )
        context_manager = use_audit_context(audit)

        with context_manager:
            payload: dict[str, Any] = {
                "content_type": parsed.content_type,
                "parse_mode": parsed.mode,
                "normalized": normalized.model_dump(mode="json"),
                "raw_payload": sanitized_raw,
                "redacted_fields": redacted_fields,
                "correlation_id": correlation_id,
                "event_id": event_id,
            }
            if parsed.parse_error:
                payload["parse_error"] = parsed.parse_error

            observability.record_execution_event(
                status="received",
                event_type="tradingview_event_ingested",
                summarized_input={"content_type": content_type, "raw_payload": sanitized_raw},
                metadata={"source": source, "redacted_fields": redacted_fields},
            )

            alert = self.store.insert_alert(
                source=source,
                symbol=normalized.symbol,
                timeframe=normalized.timeframe,
                alert_name=normalized.alert_name,
                signal=normalized.signal,
                direction=normalized.direction,
                strategy=normalized.strategy,
                price=normalized.price,
                payload=payload,
                processing_status=processing_status,
                processing_error=processing_error,
            )

            internal_events = [
                self.store.publish_event(
                    event_type="tradingview_alert_received",
                    alert_event_id=alert.id,
                    symbol=alert.symbol,
                    payload={
                        "alert_id": alert.id,
                        "processing_status": alert.processing_status,
                        "correlation_id": correlation_id,
                        "event_id": event_id,
                    },
                )
            ]
            if processing_status == "signal_ready":
                internal_events.append(
                    self.store.publish_event(
                        event_type="tradingview_signal_ready",
                        alert_event_id=alert.id,
                        symbol=alert.symbol,
                        payload={
                            "alert_id": alert.id,
                            "symbol": alert.symbol,
                            "signal": alert.signal,
                            "direction": alert.direction,
                            "alert_name": alert.alert_name,
                            "strategy": alert.strategy,
                            "timeframe": alert.timeframe,
                            "price": alert.price,
                            "correlation_id": correlation_id,
                            "event_id": event_id,
                        },
                    )
                )
            if processing_status == "failed":
                internal_events.append(
                    self.store.publish_event(
                        event_type="tradingview_alert_failed",
                        alert_event_id=alert.id,
                        symbol=alert.symbol,
                        payload={
                            "alert_id": alert.id,
                            "error": alert.processing_error,
                            "correlation_id": correlation_id,
                            "event_id": event_id,
                        },
                    )
                )

            self._publish_stream_events(alert=alert, processing_status=processing_status, correlation_id=correlation_id)
            observability.record_execution_event(
                status=processing_status,
                event_type="tradingview_ingestion_persisted",
                summarized_output={"alert_id": alert.id, "status": processing_status},
                error_message=processing_error,
                metadata={"internal_events": [item.event_type for item in internal_events]},
            )

            if processing_status == "failed":
                observability.record_system_error(
                    status="failed",
                    error_message=processing_error,
                    summarized_input={"content_type": content_type},
                    summarized_output={"alert_id": alert.id},
                    error_type="TradingViewParseError",
                    metadata={"source": source},
                )

            return TradingViewIngestionResult(
                alert=alert,
                internal_events=internal_events,
                redacted_fields=redacted_fields,
            )

    def _publish_stream_events(self, *, alert: TradingViewAlertRecord, processing_status: str, correlation_id: str) -> None:
        observability = get_observability_service()
        stream_events = [
            TradingEvent(
                event_type="tradingview_alert_received",
                source="tradingview",
                producer="backend.tradingview.service",
                symbol=alert.symbol,
                alert_id=alert.id,
                correlation_id=correlation_id,
                payload={
                    "alert_id": alert.id,
                    "symbol": alert.symbol,
                    "processing_status": alert.processing_status,
                    "signal": alert.signal,
                    "direction": alert.direction,
                },
            )
        ]
        if processing_status == "signal_ready":
            stream_events.append(
                TradingEvent(
                    event_type="tradingview_signal_ready",
                    source="tradingview",
                    producer="backend.tradingview.service",
                    symbol=alert.symbol,
                    alert_id=alert.id,
                    correlation_id=correlation_id,
                    causation_id=alert.id,
                    payload={
                        "alert_id": alert.id,
                        "symbol": alert.symbol,
                        "signal": alert.signal,
                        "direction": alert.direction,
                        "alert_name": alert.alert_name,
                        "strategy": alert.strategy,
                        "timeframe": alert.timeframe,
                        "price": alert.price,
                    },
                )
            )

        for event in stream_events:
            try:
                envelope = self.event_publisher.publish(event)
                logger.info(
                    "TradingView Redis publish succeeded: event_type=%s alert_id=%s redis_id=%s",
                    event.event_type,
                    alert.id,
                    envelope.redis_id,
                )
                observability.record_execution_event(
                    status="published",
                    event_type=event.event_type,
                    summarized_output={"alert_id": alert.id, "redis_id": envelope.redis_id},
                    metadata={"stream": envelope.stream, "producer": event.producer},
                )
            except RedisError:
                logger.exception(
                    "Failed to publish %s for TradingView alert %s to Redis Streams",
                    event.event_type,
                    alert.id,
                )
                observability.record_system_error(
                    status="redis_publish_failed",
                    error_message=f"Failed to publish {event.event_type} for alert {alert.id}",
                    error_type="RedisError",
                    summarized_output={"alert_id": alert.id, "event_type": event.event_type},
                    metadata={"producer": event.producer},
                )
