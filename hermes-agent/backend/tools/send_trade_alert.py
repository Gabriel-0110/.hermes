from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from backend.tools._helpers import run_tool, validate
from backend.tools.send_notification import SendNotificationInput, _dispatch_notification


class SendTradeAlertInput(BaseModel):
    symbol: str = Field(min_length=1, max_length=64)
    message: str = Field(min_length=1, max_length=4000)
    title: str | None = Field(default="Trade Alert", max_length=200)
    side: Literal["buy", "sell", "long", "short", "watch"] | None = None
    status: str | None = Field(default=None, max_length=64)
    channel: str | None = None
    channels: list[str] | None = None


def send_trade_alert(payload: dict) -> dict:
    def _run() -> dict:
        args = validate(SendTradeAlertInput, payload)
        channels = args.channels or ([args.channel] if args.channel else ["telegram", "slack"])
        return _dispatch_notification(
            SendNotificationInput(
                channels=channels,
                title=args.title,
                message=args.message,
                severity="info",
                notification_type="trade_alert",
                metadata={
                    "symbol": args.symbol.upper(),
                    "side": args.side,
                    "status": args.status,
                },
            ),
            notification_type="trade_alert",
        )

    return run_tool("send_trade_alert", _run)
