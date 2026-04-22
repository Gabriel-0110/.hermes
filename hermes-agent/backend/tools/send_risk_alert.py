from __future__ import annotations

from pydantic import BaseModel, Field

from backend.tools._helpers import run_tool, validate
from backend.tools.send_notification import SendNotificationInput, _dispatch_notification


class SendRiskAlertInput(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    title: str | None = Field(default="Risk Alert", max_length=200)
    severity: str = Field(default="high", max_length=32)
    symbol: str | None = Field(default=None, max_length=64)
    channel: str | None = None
    channels: list[str] | None = None


def send_risk_alert(payload: dict) -> dict:
    def _run() -> dict:
        args = validate(SendRiskAlertInput, payload)
        channels = args.channels or ([args.channel] if args.channel else ["telegram", "slack"])
        return _dispatch_notification(
            SendNotificationInput(
                channels=channels,
                title=args.title,
                message=args.message,
                severity=args.severity,
                notification_type="risk_alert",
                metadata={"symbol": args.symbol.upper() if args.symbol else None},
            ),
            notification_type="risk_alert",
        )

    return run_tool("send_risk_alert", _run)
