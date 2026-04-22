"""Operator authentication dependency for the Hermes API.

Usage:
    @router.post("/some-write-endpoint")
    async def my_endpoint(_: None = Depends(require_api_key)) -> ...:
        ...

Protected routes fail closed unless either:

- ``HERMES_API_KEY`` is set and callers send ``Authorization: Bearer <key>``
- ``HERMES_API_DEV_BYPASS_AUTH=true`` is set explicitly in a development/test
    environment
"""

from __future__ import annotations

import logging

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from hermes_api.core.config import Settings, get_settings

logger = logging.getLogger(__name__)

# Optional scheme — we don't want FastAPI to auto-reject missing credentials
# because we handle the "no key configured" passthrough ourselves.
_bearer_scheme = HTTPBearer(auto_error=False)


def _is_local_dev_bypass_enabled(settings: Settings) -> bool:
    app_env = settings.app_env.strip().lower()
    is_dev_env = app_env in {"development", "dev", "local", "test"}
    return bool(settings.hermes_api_dev_bypass_auth and is_dev_env)


async def require_api_key(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    settings: Settings = Depends(get_settings),
) -> None:
    """FastAPI dependency that enforces Bearer token auth on protected endpoints.

    - If ``HERMES_API_DEV_BYPASS_AUTH=true`` and ``APP_ENV`` is a development /
      local / test value, the check is bypassed explicitly.
    - Otherwise, protected routes require ``Authorization: Bearer
      <HERMES_API_KEY>``.
    - If neither a key nor an allowed bypass is configured, the endpoint fails
      closed with HTTP 503 rather than becoming silently unauthenticated.
    """
    if _is_local_dev_bypass_enabled(settings):
        logger.debug(
            "require_api_key: explicit local development auth bypass enabled"
        )
        return

    if not settings.hermes_api_key:
        raise HTTPException(
            status_code=503,
            detail=(
                "Operator authentication is not configured. Set HERMES_API_KEY "
                "or enable HERMES_API_DEV_BYPASS_AUTH=true in a development/test environment."
            ),
        )

    if credentials is None or credentials.credentials != settings.hermes_api_key:
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing API key.  Provide Authorization: Bearer <HERMES_API_KEY>.",
            headers={"WWW-Authenticate": "Bearer"},
        )
