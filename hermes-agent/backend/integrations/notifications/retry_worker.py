"""Notification retry worker.

Queries the ``notifications_sent`` table for failed delivery rows that are
eligible for a retry and re-dispatches them through the appropriate channel
client.  Each attempt increments ``retry_count`` and, on failure, schedules
``next_retry_at`` with exponential back-off.  Rows that have been retried
``MAX_RETRIES`` times are marked permanently failed and left in the table as
an audit record.

Usage — run once (e.g. from a cron job or a periodic task):

    from backend.integrations.notifications.retry_worker import run_retry_pass
    run_retry_pass()

Or invoke directly:

    python -m backend.integrations.notifications.retry_worker
"""
from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from backend.db import HermesTimeSeriesRepository, ensure_time_series_schema, session_scope
from backend.db.models import NotificationSentRow
from backend.db.session import get_engine
from backend.integrations.base import IntegrationError, MissingCredentialError
from backend.integrations.notifications import SlackNotificationClient, TelegramNotificationClient

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
# Exponential back-off base in minutes: attempt 1 → 2 min, 2 → 4 min, 3 → 8 min
_BACKOFF_BASE_MINUTES = 2


def _next_retry_at(retry_count: int) -> datetime:
    delay = timedelta(minutes=_BACKOFF_BASE_MINUTES * (2 ** retry_count))
    return datetime.now(UTC) + delay


def _attempt_delivery(row: NotificationSentRow) -> tuple[bool, str | None, str | None]:
    """Attempt to (re-)deliver a notification row.

    Returns (delivered, message_id, error_detail).
    """
    payload: dict[str, Any] = row.payload or {}
    message = payload.get("message", row.detail or "")
    channel = row.channel

    if not message:
        return False, None, "Cannot retry: no message text stored in payload."

    try:
        if channel == "telegram":
            response = TelegramNotificationClient().send_message(message)
            message_id = str(response.get("message_id") or uuid.uuid4())
            return True, message_id, None
        elif channel == "slack":
            response = SlackNotificationClient().send_message(message)
            message_id = str(response.get("request_id") or uuid.uuid4())
            return True, message_id, None
        else:
            return False, None, f"No retry handler for channel: {channel}"
    except MissingCredentialError as exc:
        return False, None, f"Missing credentials: {exc}"
    except IntegrationError as exc:
        return False, None, f"Delivery error: {exc}"
    except Exception as exc:  # noqa: BLE001
        return False, None, f"Unexpected error: {exc}"


def run_retry_pass(*, max_retries: int = MAX_RETRIES, batch_size: int = 50) -> dict[str, int]:
    """Process one batch of failed notifications eligible for retry.

    Returns a summary dict with keys: attempted, delivered, failed, skipped.
    """
    engine = get_engine()
    ensure_time_series_schema(engine)

    summary = {"attempted": 0, "delivered": 0, "failed": 0, "skipped": 0}

    with session_scope() as session:
        repo = HermesTimeSeriesRepository(session)
        rows = repo.list_failed_notifications_for_retry(
            max_retries=max_retries,
            limit=batch_size,
        )

        if not rows:
            logger.debug("Notification retry pass: no eligible rows found.")
            return summary

        logger.info("Notification retry pass: found %d eligible row(s).", len(rows))

        for row in rows:
            summary["attempted"] += 1
            new_retry_count = row.retry_count + 1

            delivered, message_id, error = _attempt_delivery(row)

            if delivered:
                repo.update_notification_delivery(
                    notification_row=row,
                    delivered=True,
                    message_id=message_id,
                    detail=f"Delivered on retry #{new_retry_count}.",
                    retry_count=new_retry_count,
                    next_retry_at=None,
                    last_error=None,
                )
                summary["delivered"] += 1
                logger.info(
                    "Notification retry succeeded: id=%s channel=%s attempt=%d",
                    row.id,
                    row.channel,
                    new_retry_count,
                )
            else:
                if new_retry_count >= max_retries:
                    # Permanently failed — stop scheduling retries
                    repo.update_notification_delivery(
                        notification_row=row,
                        delivered=False,
                        detail=f"Permanently failed after {new_retry_count} attempt(s): {error}",
                        retry_count=new_retry_count,
                        next_retry_at=None,
                        last_error=error,
                    )
                    summary["failed"] += 1
                    logger.warning(
                        "Notification permanently failed: id=%s channel=%s attempts=%d error=%s",
                        row.id,
                        row.channel,
                        new_retry_count,
                        error,
                    )
                else:
                    scheduled = _next_retry_at(new_retry_count)
                    repo.update_notification_delivery(
                        notification_row=row,
                        delivered=False,
                        detail=f"Retry {new_retry_count} failed: {error}",
                        retry_count=new_retry_count,
                        next_retry_at=scheduled,
                        last_error=error,
                    )
                    summary["skipped"] += 1
                    logger.info(
                        "Notification retry %d/%d failed, next attempt at %s: id=%s channel=%s",
                        new_retry_count,
                        max_retries,
                        scheduled.isoformat(),
                        row.id,
                        row.channel,
                    )

    return summary


if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    result = run_retry_pass()
    print(
        f"Retry pass complete — "
        f"attempted={result['attempted']} "
        f"delivered={result['delivered']} "
        f"failed={result['failed']} "
        f"rescheduled={result['skipped']}"
    )
    sys.exit(0 if result["failed"] == 0 else 1)
