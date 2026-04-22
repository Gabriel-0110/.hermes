"""Normalized TradingView ingestion models."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class ParsedTradingViewPayload(BaseModel):
    content_type: str
    mode: Literal["json", "text_json", "raw_text", "raw_bytes", "invalid_json"]
    parsed_payload: Any = None
    raw_payload: Any = None
    parse_error: str | None = None


class NormalizedTradingViewAlert(BaseModel):
    source: str = "tradingview"
    received_at: str
    symbol: str | None = None
    timeframe: str | None = None
    alert_name: str | None = None
    strategy: str | None = None
    signal: str | None = None
    direction: str | None = None
    price: float | None = None
    raw_payload: Any = None


class TradingViewAlertRecord(BaseModel):
    id: str
    ts: float
    source: str
    symbol: str | None = None
    timeframe: str | None = None
    alert_name: str | None = None
    signal: str | None = None
    direction: str | None = None
    strategy: str | None = None
    price: float | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    processing_status: str
    processing_error: str | None = None


class TradingViewInternalEvent(BaseModel):
    id: str
    ts: float
    event_type: Literal[
        "tradingview_alert_received",
        "tradingview_signal_ready",
        "tradingview_alert_failed",
    ]
    alert_event_id: str
    symbol: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    delivery_status: str = "pending"
    delivery_error: str | None = None


class TradingViewIngestionResult(BaseModel):
    alert: TradingViewAlertRecord
    internal_events: list[TradingViewInternalEvent] = Field(default_factory=list)
    redacted_fields: list[str] = Field(default_factory=list)
