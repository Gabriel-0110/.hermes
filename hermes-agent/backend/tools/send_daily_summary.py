from __future__ import annotations

from pydantic import BaseModel, Field

from backend.tools._helpers import run_tool, validate
from backend.tools.send_notification import SendNotificationInput, _dispatch_notification


class SendDailySummaryInput(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    title: str | None = Field(default="Daily Summary", max_length=200)
    summary_date: str | None = Field(default=None, max_length=64)
    channel: str | None = None
    channels: list[str] | None = None


def send_daily_summary(payload: dict) -> dict:
    def _run() -> dict:
        args = validate(SendDailySummaryInput, payload)
        channels = args.channels or ([args.channel] if args.channel else ["telegram", "slack"])
        return _dispatch_notification(
            SendNotificationInput(
                channels=channels,
                title=args.title,
                message=args.message,
                severity="info",
                notification_type="daily_summary",
                metadata={"summary_date": args.summary_date},
            ),
            notification_type="daily_summary",
        )

    return run_tool("send_daily_summary", _run)
