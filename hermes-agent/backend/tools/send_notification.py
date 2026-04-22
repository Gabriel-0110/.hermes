from __future__ import annotations

import logging
import re
import uuid
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from backend.db import HermesTimeSeriesRepository, ensure_time_series_schema, session_scope
from backend.db.session import get_engine
from backend.integrations.base import IntegrationError, MissingCredentialError
from backend.integrations.notifications import SlackNotificationClient, TelegramNotificationClient
from backend.models import NotificationResult
from backend.observability.context import get_audit_context
from backend.observability.service import get_observability_service
from backend.tools._helpers import envelope, provider_error, provider_ok, run_tool, validate

logger = logging.getLogger(__name__)

NotificationChannel = Literal["log", "telegram", "slack"]
_ALLOWED_CHANNELS: set[str] = {"log", "telegram", "slack"}
_SENSITIVE_KEYWORDS = ("token", "secret", "webhook", "password", "authorization", "api_key")
_SLACK_WEBHOOK_RE = re.compile(r"https://hooks\.slack(?:-gov)?\.com/services/\S+", re.IGNORECASE)
_TELEGRAM_TOKEN_RE = re.compile(r"\b\d{6,}:[A-Za-z0-9_-]{20,}\b")


class SendNotificationInput(BaseModel):
    channel: str | None = Field(default=None)
    channels: list[str] | None = Field(default=None)
    message: str = Field(min_length=1, max_length=4000)
    title: str | None = Field(default=None, max_length=200)
    severity: str = Field(default="info", max_length=32)
    notification_type: str = Field(default="generic", max_length=64)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("message", "title", "severity", "notification_type", mode="before")
    @classmethod
    def _strip_string(cls, value: Any) -> Any:
        if isinstance(value, str):
            value = value.strip()
        return value

    @field_validator("severity")
    @classmethod
    def _normalize_severity(cls, value: str) -> str:
        normalized = value.lower()
        if normalized not in {"info", "warning", "error", "critical", "low", "medium", "high"}:
            raise ValueError("severity must be one of: info, warning, error, critical, low, medium, high")
        return normalized

    @field_validator("notification_type")
    @classmethod
    def _normalize_type(cls, value: str) -> str:
        normalized = value.lower().replace(" ", "_")
        if not normalized:
            raise ValueError("notification_type must not be empty")
        return normalized

    @field_validator("metadata")
    @classmethod
    def _validate_metadata(cls, value: dict[str, Any]) -> dict[str, Any]:
        if len(value) > 20:
            raise ValueError("metadata may contain at most 20 entries")
        return value

    @field_validator("channels", mode="before")
    @classmethod
    def _normalize_channels_field(cls, value: Any) -> Any:
        if value is None:
            return value
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        if isinstance(value, (list, tuple, set)):
            return list(value)
        raise ValueError("channels must be a list of routing targets")

    @model_validator(mode="after")
    def _validate_channels(self) -> "SendNotificationInput":
        resolved = _normalize_channels(self.channel, self.channels, default_channels=["log"])
        self.channels = resolved
        self.channel = resolved[0] if len(resolved) == 1 else "multi"
        return self


def _redact_text(value: str) -> str:
    redacted = _SLACK_WEBHOOK_RE.sub("[redacted-slack-webhook]", value)
    redacted = _TELEGRAM_TOKEN_RE.sub("[redacted-telegram-token]", redacted)
    return redacted


def _sanitize_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    sanitized: dict[str, Any] = {}
    for key, value in metadata.items():
        key_text = str(key)
        lowered = key_text.lower()
        if any(keyword in lowered for keyword in _SENSITIVE_KEYWORDS):
            sanitized[key_text] = "[redacted]"
            continue
        if isinstance(value, str):
            sanitized[key_text] = _redact_text(value)
        else:
            sanitized[key_text] = value
    return sanitized


def _normalize_channels(
    channel: str | None,
    channels: list[str] | None,
    *,
    default_channels: list[NotificationChannel],
) -> list[NotificationChannel]:
    raw_values: list[str] = []
    if channels:
        raw_values.extend(channels)
    if channel:
        raw_values.extend(part.strip() for part in channel.split(",") if part.strip())
    if not raw_values:
        raw_values = list(default_channels)

    expanded: list[str] = []
    for value in raw_values:
        lowered = value.strip().lower()
        if lowered == "all":
            expanded.extend(["telegram", "slack"])
        else:
            expanded.append(lowered)

    normalized: list[NotificationChannel] = []
    for value in expanded:
        if value not in _ALLOWED_CHANNELS:
            raise ValueError(f"unsupported notification channel: {value}")
        if value not in normalized:
            normalized.append(value)  # preserve order
    if not normalized:
        return list(default_channels)
    return normalized


def _render_notification_text(title: str | None, message: str, severity: str, metadata: dict[str, Any]) -> str:
    lines: list[str] = []
    if title:
        lines.append(f"{title} [{severity.upper()}]" if severity != "info" else title)
    elif severity != "info":
        lines.append(f"[{severity.upper()}]")
    lines.append(message)
    for key, value in metadata.items():
        if value is None:
            continue
        lines.append(f"{key}: {value}")
    return "\n".join(line for line in lines if line).strip()


def _dispatch_notification(
    args: SendNotificationInput,
    *,
    default_channels: list[NotificationChannel] | None = None,
    notification_type: str | None = None,
) -> dict[str, Any]:
    if default_channels is not None:
        args.channels = _normalize_channels(args.channel, args.channels, default_channels=default_channels)
        args.channel = args.channels[0] if len(args.channels) == 1 else "multi"
    if notification_type:
        args.notification_type = notification_type

    sanitized_message = _redact_text(args.message)
    sanitized_metadata = _sanitize_metadata(args.metadata)
    audit = get_audit_context()
    if audit is not None:
        sanitized_metadata = {
            **sanitized_metadata,
            "event_id": audit.event_id,
            "correlation_id": audit.correlation_id,
            "workflow_run_id": audit.workflow_run_id,
            "workflow_name": audit.workflow_name,
            "workflow_step": audit.workflow_step,
            "agent_name": audit.agent_name,
        }
    rendered = _render_notification_text(args.title, sanitized_message, args.severity, sanitized_metadata)

    providers = []
    results: list[dict[str, Any]] = []
    warnings: list[str] = []
    delivered = False

    for channel in args.channels or ["log"]:
        if channel == "log":
            message_id = f"log-{uuid.uuid4()}"
            results.append(
                {
                    "channel": "log",
                    "delivered": True,
                    "message_id": message_id,
                    "detail": "Notification captured by Hermes audit log backend.",
                }
            )
            providers.append(provider_ok("log", "Audit trail stored locally."))
            delivered = True
            logger.info("Notification captured in audit log type=%s severity=%s", args.notification_type, args.severity)
            continue

        try:
            if channel == "telegram":
                response = TelegramNotificationClient().send_message(rendered)
                message_id = str(response.get("message_id") or uuid.uuid4())
                detail = "Delivered through Telegram Bot API."
                providers.append(provider_ok("telegram", detail))
            elif channel == "slack":
                response = SlackNotificationClient().send_message(rendered)
                message_id = str(response.get("request_id") or uuid.uuid4())
                detail = "Delivered through Slack incoming webhook."
                providers.append(provider_ok("slack", detail))
            else:  # pragma: no cover - protected by validation
                raise ValueError(f"unsupported notification channel: {channel}")
            results.append(
                {
                    "channel": channel,
                    "delivered": True,
                    "message_id": message_id,
                    "detail": detail,
                }
            )
            delivered = True
            logger.info(
                "Notification delivered type=%s severity=%s channel=%s",
                args.notification_type,
                args.severity,
                channel,
            )
        except MissingCredentialError as exc:
            providers.append(provider_error(channel, str(exc)))
            results.append({"channel": channel, "delivered": False, "message_id": None, "detail": str(exc)})
            warnings.append(f"{channel} not configured")
            logger.info(
                "Notification skipped due to missing %s configuration type=%s",
                channel,
                args.notification_type,
            )
        except IntegrationError as exc:
            providers.append(provider_error(channel, str(exc)))
            results.append({"channel": channel, "delivered": False, "message_id": None, "detail": str(exc)})
            warnings.append(f"{channel} delivery failed")
            logger.warning(
                "Notification delivery failed type=%s channel=%s detail=%s",
                args.notification_type,
                channel,
                str(exc),
            )

    result = NotificationResult(
        delivered=delivered,
        channel=args.channel or "log",
        channels=list(args.channels or ["log"]),
        message_id=next((item["message_id"] for item in results if item.get("delivered")), None),
        detail="Delivered to at least one channel." if delivered else "No requested notification channels accepted the message.",
        notification_type=args.notification_type,
        severity=args.severity,
        title=args.title,
        results=results,
    )

    ensure_time_series_schema(get_engine())
    with session_scope() as session:
        HermesTimeSeriesRepository(session).insert_notification_sent(
            channel=result.channel,
            message_id=result.message_id,
            delivered=result.delivered,
            detail=result.detail,
            payload={
                "message": sanitized_message,
                "title": args.title,
                "severity": args.severity,
                "notification_type": args.notification_type,
                "channels": result.channels,
                "results": result.results,
                "metadata": sanitized_metadata,
            },
        )
    get_observability_service().record_execution_event(
        status="delivered" if result.delivered else "skipped",
        event_type="notification_sent",
        summarized_input={"channels": result.channels, "notification_type": args.notification_type},
        summarized_output=result.model_dump(mode="json"),
        metadata={"notification_type": args.notification_type, "severity": args.severity},
    )

    return envelope("send_notification", providers, result.model_dump(mode="json"), warnings=warnings)


def send_notification(payload: dict) -> dict:
    def _run() -> dict:
        args = validate(SendNotificationInput, payload)
        return _dispatch_notification(args)

    return run_tool("send_notification", _run)
