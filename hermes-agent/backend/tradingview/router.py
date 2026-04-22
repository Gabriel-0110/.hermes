"""FastAPI router for TradingView webhook ingestion."""

from __future__ import annotations

import os

from fastapi import APIRouter, HTTPException, Request

from .service import TradingViewIngestionService

tradingview_router = APIRouter()


def _expected_secret_header() -> str:
    return os.getenv("TRADINGVIEW_WEBHOOK_SECRET_HEADER", "X-TV-Secret")


def _expected_secret() -> str:
    return os.getenv("TRADINGVIEW_WEBHOOK_SECRET", "").strip()


@tradingview_router.post("/webhooks/tradingview")
async def ingest_tradingview_webhook(
    request: Request,
):
    expected_secret = _expected_secret()
    header_name = _expected_secret_header()
    provided_secret = request.headers.get(header_name)
    if not expected_secret:
        raise HTTPException(status_code=503, detail="TradingView webhook secret is not configured.")
    if provided_secret != expected_secret:
        raise HTTPException(
            status_code=401,
            detail=f"Unauthorized TradingView webhook request. Use the {header_name} header.",
        )

    body = await request.body()
    service = TradingViewIngestionService()
    result = service.ingest(
        body=body,
        content_type=request.headers.get("content-type"),
        source="tradingview",
    )
    return {
        "ok": result.alert.processing_status != "failed",
        "alert_id": result.alert.id,
        "processing_status": result.alert.processing_status,
        "processing_error": result.alert.processing_error,
        "correlation_id": result.alert.payload.get("correlation_id"),
        "event_id": result.alert.payload.get("event_id"),
        "published_events": [event.event_type for event in result.internal_events],
        "redacted_fields": result.redacted_fields,
    }
