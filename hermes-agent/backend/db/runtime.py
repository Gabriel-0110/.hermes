"""Runtime bootstrap hooks for Hermes shared database storage."""

from __future__ import annotations

import logging
import time

from sqlalchemy.exc import OperationalError

from .bootstrap import ensure_time_series_schema, list_hypertables, list_managed_tables
from .session import get_database_backend, get_database_url, get_engine

logger = logging.getLogger(__name__)

_RUNTIME_BOOTSTRAP_COMPLETE = False


def _emit(message: str) -> None:
    print(message, flush=True)


def bootstrap_shared_storage_on_startup() -> None:
    """Initialize shared storage for live Hermes runtimes."""

    global _RUNTIME_BOOTSTRAP_COMPLETE

    if _RUNTIME_BOOTSTRAP_COMPLETE:
        _emit("Shared DB bootstrap skipped: already completed in this process.")
        return

    database_url = get_database_url()
    backend = get_database_backend(database_url)

    if not database_url:
        _emit("Shared DB bootstrap skipped: DATABASE_URL is not set.")
        _RUNTIME_BOOTSTRAP_COMPLETE = True
        return

    _emit(f"Shared DB bootstrap started: backend={backend}")

    last_error: Exception | None = None
    managed_tables: list[str] = []
    hypertables: list[str] = []
    for attempt in range(1, 11):
        try:
            engine = get_engine(database_url=database_url)
            ensure_time_series_schema(engine)
            managed_tables = list_managed_tables(engine)
            hypertables = list_hypertables(engine)
            last_error = None
            break
        except OperationalError as exc:
            last_error = exc
            _emit(f"Shared DB bootstrap retry {attempt}/10 after OperationalError: {exc}")
            time.sleep(1.0)
        except Exception as exc:
            last_error = exc
            break

    if last_error is not None:
        _emit(f"Shared DB bootstrap failed: backend={backend}")
        logger.exception("Shared DB bootstrap failed: backend=%s", backend, exc_info=last_error)
        raise last_error

    _emit(
        "Shared DB bootstrap succeeded: "
        f"backend={backend} "
        f"tables={','.join(managed_tables) if managed_tables else 'none'} "
        f"hypertables={','.join(hypertables) if hypertables else 'none'}"
    )
    _RUNTIME_BOOTSTRAP_COMPLETE = True
