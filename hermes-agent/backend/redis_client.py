"""Shared Redis client helpers for Hermes backend services."""

from __future__ import annotations

import logging
import os
from threading import Lock

from redis import Redis
from redis.exceptions import RedisError

logger = logging.getLogger(__name__)

DEFAULT_REDIS_URL = "redis://localhost:6379/0"

_CLIENT_CACHE: dict[str, Redis] = {}
_CLIENT_CACHE_LOCK = Lock()


def get_redis_url() -> str:
    return os.getenv("REDIS_URL", DEFAULT_REDIS_URL).strip() or DEFAULT_REDIS_URL


def get_redis_client(*, redis_url: str | None = None) -> Redis:
    resolved_url = redis_url or get_redis_url()
    with _CLIENT_CACHE_LOCK:
        client = _CLIENT_CACHE.get(resolved_url)
        if client is None:
            client = Redis.from_url(
                resolved_url,
                decode_responses=True,
                health_check_interval=30,
            )
            _CLIENT_CACHE[resolved_url] = client
            logger.info("Initialized shared Redis client for %s", resolved_url)
        return client


def ping_redis(*, redis_url: str | None = None) -> bool:
    try:
        resolved_url = redis_url or get_redis_url()
        ok = bool(get_redis_client(redis_url=resolved_url).ping())
        if ok:
            logger.info("Redis ping succeeded for %s", resolved_url)
        return ok
    except RedisError as exc:
        logger.warning("Redis ping failed for %s: %s", redis_url or get_redis_url(), exc)
        return False


# Backward-compatible module globals for older imports.
REDIS_URL = get_redis_url()
redis_client = get_redis_client(redis_url=REDIS_URL)
