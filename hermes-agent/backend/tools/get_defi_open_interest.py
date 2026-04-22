from __future__ import annotations

import logging

from pydantic import BaseModel, Field

from backend.integrations import DefiLlamaClient
from backend.tools._helpers import envelope, provider_ok, run_tool, validate

logger = logging.getLogger(__name__)


class GetDefiOpenInterestInput(BaseModel):
    limit: int = Field(default=20, ge=1, le=100)
    chain: str | None = None


def get_defi_open_interest(payload: dict | None = None) -> dict:
    def _run() -> dict:
        args = validate(GetDefiOpenInterestInput, payload or {})
        client = DefiLlamaClient()
        logger.info("get_defi_open_interest limit=%s chain=%s", args.limit, args.chain)
        overview = client.get_open_interest_overview(limit=args.limit, chain=args.chain)
        warnings = overview.warnings if overview.warnings else None
        return envelope(
            "get_defi_open_interest",
            [provider_ok(client.provider.name, detail=f"access_level={overview.access_level}")],
            overview.model_dump(mode="json"),
            warnings=warnings,
        )

    return run_tool("get_defi_open_interest", _run)
