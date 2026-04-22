"""Shared backend-only notification clients."""

from backend.integrations.notifications.slack_client import SlackNotificationClient
from backend.integrations.notifications.telegram_client import TelegramNotificationClient

__all__ = ["SlackNotificationClient", "TelegramNotificationClient"]
