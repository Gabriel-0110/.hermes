from __future__ import annotations

from backend.db import HermesTimeSeriesRepository, ensure_time_series_schema, session_scope
from backend.db.session import get_engine
from backend.tools.send_daily_summary import send_daily_summary
from backend.tools.send_notification import send_notification
from backend.tools.send_trade_alert import send_trade_alert


def test_send_notification_defaults_to_log_and_records_audit(tmp_path, monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))

    payload = send_notification({"message": "risk limit breached"})

    assert payload["meta"]["ok"] is True
    assert payload["data"]["delivered"] is True
    assert payload["data"]["channel"] == "log"
    assert payload["data"]["channels"] == ["log"]

    ensure_time_series_schema(get_engine())
    with session_scope() as session:
        rows = HermesTimeSeriesRepository(session).list_notifications_sent(limit=5, channel="log")

    assert len(rows) == 1
    assert rows[0].payload["message"] == "risk limit breached"
    assert rows[0].payload["channels"] == ["log"]


def test_send_notification_routes_to_telegram_and_slack(tmp_path, monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))

    def _telegram_send(self, text: str):
        assert "Execution Update" in text
        return {"message_id": 42}

    def _slack_send(self, text: str, *, blocks=None):
        assert "Execution Update" in text
        return {"ok": True, "request_id": "slack-123"}

    monkeypatch.setattr(
        "backend.tools.send_notification.TelegramNotificationClient.send_message",
        _telegram_send,
    )
    monkeypatch.setattr(
        "backend.tools.send_notification.SlackNotificationClient.send_message",
        _slack_send,
    )

    payload = send_notification(
        {
            "channels": ["telegram", "slack"],
            "title": "Execution Update",
            "message": "Order filled",
            "notification_type": "execution_update",
        }
    )

    assert payload["meta"]["ok"] is True
    assert payload["data"]["delivered"] is True
    assert payload["data"]["channel"] == "multi"
    assert payload["data"]["channels"] == ["telegram", "slack"]
    assert {result["channel"] for result in payload["data"]["results"]} == {"telegram", "slack"}


def test_send_notification_sanitizes_webhooks_before_persisting(tmp_path, monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))

    payload = send_notification(
        {
            "message": "rotate https://hooks.slack.com/services/T000/B000/SECRET immediately",
            "metadata": {"bot_token": "123456:ABCDEF_secret_token_value"},
        }
    )

    assert payload["data"]["delivered"] is True

    ensure_time_series_schema(get_engine())
    with session_scope() as session:
        rows = HermesTimeSeriesRepository(session).list_notifications_sent(limit=5, channel="log")

    assert rows[0].payload["message"] == "rotate [redacted-slack-webhook] immediately"
    assert rows[0].payload["metadata"]["bot_token"] == "[redacted]"


def test_send_trade_alert_defaults_to_external_channels(tmp_path, monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))

    calls: list[str] = []

    def _telegram_send(self, text: str):
        calls.append("telegram")
        assert "BTCUSDT" in text
        return {"message_id": 7}

    def _slack_send(self, text: str, *, blocks=None):
        calls.append("slack")
        assert "BTCUSDT" in text
        return {"ok": True, "request_id": "req-1"}

    monkeypatch.setattr(
        "backend.tools.send_notification.TelegramNotificationClient.send_message",
        _telegram_send,
    )
    monkeypatch.setattr(
        "backend.tools.send_notification.SlackNotificationClient.send_message",
        _slack_send,
    )

    payload = send_trade_alert({"symbol": "BTCUSDT", "message": "Breakout confirmed", "side": "buy"})

    assert payload["data"]["channels"] == ["telegram", "slack"]
    assert calls == ["telegram", "slack"]


def test_send_daily_summary_warns_when_external_channels_are_unconfigured(tmp_path, monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    monkeypatch.delenv("SLACK_WEBHOOK_URL", raising=False)

    payload = send_daily_summary({"message": "Calm session, no major catalyst changes."})

    assert payload["meta"]["ok"] is True
    assert payload["data"]["delivered"] is False
    assert sorted(payload["meta"]["warnings"]) == ["slack not configured", "telegram not configured"]
