from __future__ import annotations

from pydantic import BaseModel, Field

from backend.tools._helpers import run_tool, validate
from backend.tools.send_notification import SendNotificationInput, _dispatch_notification


class SendExecutionUpdateInput(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    title: str | None = Field(default="Execution Update", max_length=200)
    order_id: str | None = Field(default=None, max_length=128)
    symbol: str | None = Field(default=None, max_length=64)
    status: str | None = Field(default=None, max_length=64)
    channel: str | None = None
    channels: list[str] | None = None


def send_execution_update(payload: dict) -> dict:
    def _run() -> dict:
        args = validate(SendExecutionUpdateInput, payload)
        channels = args.channels or ([args.channel] if args.channel else ["telegram", "slack"])
        return _dispatch_notification(
            SendNotificationInput(
                channels=channels,
                title=args.title,
                message=args.message,
                severity="info",
                notification_type="execution_update",
                metadata={
                    "order_id": args.order_id,
                    "symbol": args.symbol.upper() if args.symbol else None,
                    "status": args.status,
                },
            ),
            notification_type="execution_update",
        )

    return run_tool("send_execution_update", _run)
