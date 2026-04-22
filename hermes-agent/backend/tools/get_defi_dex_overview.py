from __future__ import annotations

import logging

from pydantic import BaseModel, Field

from backend.integrations import DefiLlamaClient
from backend.tools._helpers import envelope, provider_ok, run_tool, validate

logger = logging.getLogger(__name__)


class GetDefiDexOverviewInput(BaseModel):
    limit: int = Field(default=20, ge=1, le=100)
    chain: str | None = None


def get_defi_dex_overview(payload: dict | None = None) -> dict:
    def _run() -> dict:
        args = validate(GetDefiDexOverviewInput, payload or {})
        client = DefiLlamaClient()
        logger.info("get_defi_dex_overview limit=%s chain=%s", args.limit, args.chain)
        overview = client.get_dex_overview(limit=args.limit, chain=args.chain)
        return envelope(
            "get_defi_dex_overview",
            [provider_ok(client.provider.name)],
            overview.model_dump(mode="json"),
        )

    return run_tool("get_defi_dex_overview", _run)
