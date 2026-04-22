"""TradingView payload parsing, redaction, and normalization."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from .models import NormalizedTradingViewAlert, ParsedTradingViewPayload

_REDACTED = "[REDACTED]"
_MAX_RAW_TEXT = 64_000
_SENSITIVE_KEY_FRAGMENTS = (
    "secret",
    "token",
    "password",
    "passphrase",
    "api_key",
    "apikey",
    "access_key",
    "accesskey",
    "private_key",
    "privatekey",
    "exchange_key",
    "exchange_secret",
    "broker_key",
    "broker_secret",
    "client_secret",
)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_payload(body: bytes, content_type: str | None) -> ParsedTradingViewPayload:
    normalized_content_type = (content_type or "").split(";", 1)[0].strip().lower()
    if normalized_content_type == "application/json":
        try:
            parsed = json.loads(body.decode("utf-8"))
            return ParsedTradingViewPayload(
                content_type=normalized_content_type,
                mode="json",
                parsed_payload=parsed,
                raw_payload=parsed,
            )
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            return ParsedTradingViewPayload(
                content_type=normalized_content_type,
                mode="invalid_json",
                raw_payload=_safe_text(body),
                parse_error=f"invalid_json:{exc}",
            )

    if normalized_content_type == "text/plain":
        raw_text = _safe_text(body)
        try:
            parsed = json.loads(raw_text)
            return ParsedTradingViewPayload(
                content_type=normalized_content_type,
                mode="text_json",
                parsed_payload=parsed,
                raw_payload=parsed,
            )
        except json.JSONDecodeError:
            return ParsedTradingViewPayload(
                content_type=normalized_content_type,
                mode="raw_text",
                raw_payload=raw_text,
            )

    return ParsedTradingViewPayload(
        content_type=normalized_content_type or "application/octet-stream",
        mode="raw_bytes",
        raw_payload={"raw_text": _safe_text(body)},
    )


def sanitize_payload(payload: Any) -> tuple[Any, list[str]]:
    redacted_fields: list[str] = []

    def _sanitize(value: Any, path: str) -> Any:
        if isinstance(value, dict):
            sanitized: dict[str, Any] = {}
            for key, nested in value.items():
                next_path = f"{path}.{key}" if path else str(key)
                if _is_sensitive_key(str(key)):
                    redacted_fields.append(next_path)
                    sanitized[key] = _REDACTED
                else:
                    sanitized[key] = _sanitize(nested, next_path)
            return sanitized
        if isinstance(value, list):
            return [_sanitize(item, f"{path}[{idx}]") for idx, item in enumerate(value)]
        if isinstance(value, str) and len(value) > _MAX_RAW_TEXT:
            return value[:_MAX_RAW_TEXT]
        return value

    return _sanitize(payload, ""), redacted_fields


def normalize_alert(parsed: ParsedTradingViewPayload) -> NormalizedTradingViewAlert:
    payload = parsed.parsed_payload if isinstance(parsed.parsed_payload, dict) else {}
    sanitized_raw = parsed.raw_payload
    return NormalizedTradingViewAlert(
        received_at=utc_now_iso(),
        symbol=_upper(_pick(payload, "symbol", "ticker", "tv_symbol", "instrument.symbol")),
        timeframe=_string(_pick(payload, "timeframe", "interval", "resolution", "bar_interval")),
        alert_name=_string(_pick(payload, "alert_name", "alert", "name", "title")),
        strategy=_string(_pick(payload, "strategy", "strategy.name", "strategy_id")),
        signal=_signal(_pick(payload, "signal", "action", "order_action", "order.action")),
        direction=_direction(_pick(payload, "direction", "side", "position", "market_position", "bias")),
        price=_floatish(_pick(payload, "price", "close", "last", "market_price", "order_price")),
        raw_payload=sanitized_raw,
    )


def _pick(payload: dict[str, Any], *paths: str) -> Any:
    for path in paths:
        current: Any = payload
        found = True
        for part in path.split("."):
            if isinstance(current, dict) and part in current:
                current = current[part]
            else:
                found = False
                break
        if found and current not in (None, ""):
            return current
    return None


def _string(value: Any) -> str | None:
    if value is None:
        return None
    rendered = str(value).strip()
    return rendered or None


def _upper(value: Any) -> str | None:
    rendered = _string(value)
    return rendered.upper() if rendered else None


def _signal(value: Any) -> str | None:
    rendered = _string(value)
    return rendered.lower() if rendered else None


def _direction(value: Any) -> str | None:
    rendered = _signal(value)
    if rendered in {"buy", "bullish"}:
        return "long"
    if rendered in {"sell", "bearish"}:
        return "short"
    if rendered in {"close", "flat", "exit"}:
        return "flat"
    return rendered


def _floatish(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _is_sensitive_key(key: str) -> bool:
    lowered = key.strip().lower()
    return any(fragment in lowered for fragment in _SENSITIVE_KEY_FRAGMENTS)


def _safe_text(body: bytes) -> str:
    return body.decode("utf-8", errors="replace")[:_MAX_RAW_TEXT]
