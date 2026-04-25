"""Pydantic models for shared Redis Streams trading events."""

from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import BaseModel, Field

from .schema import DEFAULT_TRADING_STREAM, SCHEMA_VERSION, new_event_id, normalize_event_payload, utc_now_iso

TradingEventType = Literal[
    "tradingview_alert_received",
    "tradingview_signal_ready",
    "funding_spread_detected",
    "whale_flow",
    "strategy_candidate_created",
    "risk_review_requested",
    "risk_review_completed",
    "execution_requested",
    "execution_status_updated",
    "portfolio_snapshot_updated",
    "notification_requested",
]


class TradingEvent(BaseModel):
    event_id: str = Field(default_factory=new_event_id)
    event_type: TradingEventType
    source: str = "hermes"
    created_at: str = Field(default_factory=utc_now_iso)
    schema_version: int = SCHEMA_VERSION
    symbol: str | None = None
    alert_id: str | None = None
    correlation_id: str | None = None
    causation_id: str | None = None
    producer: str | None = None
    workflow_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)

    def model_post_init(self, __context: Any) -> None:
        self.payload = normalize_event_payload(self.payload)
        self.metadata = normalize_event_payload(self.metadata)


class TradingEventEnvelope(BaseModel):
    stream: str = DEFAULT_TRADING_STREAM
    redis_id: str | None = None
    event: TradingEvent

    def to_stream_fields(self) -> dict[str, str]:
        event = self.event
        return {
            "event_id": event.event_id,
            "event_type": event.event_type,
            "source": event.source,
            "created_at": event.created_at,
            "schema_version": str(event.schema_version),
            "symbol": event.symbol or "",
            "alert_id": event.alert_id or "",
            "correlation_id": event.correlation_id or "",
            "causation_id": event.causation_id or "",
            "producer": event.producer or "",
            "workflow_id": event.workflow_id or "",
            "payload": json.dumps(event.payload, separators=(",", ":"), sort_keys=True),
            "metadata": json.dumps(event.metadata, separators=(",", ":"), sort_keys=True),
        }

    @classmethod
    def from_stream_message(cls, *, stream: str, redis_id: str, fields: dict[str, str]) -> "TradingEventEnvelope":
        return cls(
            stream=stream,
            redis_id=redis_id,
            event=TradingEvent(
                event_id=fields["event_id"],
                event_type=fields["event_type"],
                source=fields.get("source") or "hermes",
                created_at=fields.get("created_at") or utc_now_iso(),
                schema_version=int(fields.get("schema_version") or SCHEMA_VERSION),
                symbol=fields.get("symbol") or None,
                alert_id=fields.get("alert_id") or None,
                correlation_id=fields.get("correlation_id") or None,
                causation_id=fields.get("causation_id") or None,
                producer=fields.get("producer") or None,
                workflow_id=fields.get("workflow_id") or None,
                payload=json.loads(fields.get("payload") or "{}"),
                metadata=json.loads(fields.get("metadata") or "{}"),
            ),
        )

