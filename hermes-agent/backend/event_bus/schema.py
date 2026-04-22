"""Shared schema helpers for Redis Streams trading events."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

DEFAULT_TRADING_STREAM = "events:trading"
SCHEMA_VERSION = 1


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def new_event_id() -> str:
    return str(uuid4())


def normalize_event_payload(payload: dict[str, Any] | None) -> dict[str, Any]:
    normalized = payload or {}
    return json.loads(json.dumps(normalized, default=str))

