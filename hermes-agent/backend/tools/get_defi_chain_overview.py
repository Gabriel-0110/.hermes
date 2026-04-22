from __future__ import annotations

import logging

from pydantic import BaseModel, Field

from backend.integrations import DefiLlamaClient
from backend.tools._helpers import envelope, provider_ok, run_tool, validate

logger = logging.getLogger(__name__)


class GetDefiChainOverviewInput(BaseModel):
    limit: int = Field(default=25, ge=1, le=200)
    search: str | None = None


def get_defi_chain_overview(payload: dict | None = None) -> dict:
    def _run() -> dict:
        args = validate(GetDefiChainOverviewInput, payload or {})
        client = DefiLlamaClient()
        logger.info("get_defi_chain_overview limit=%s search=%s", args.limit, args.search)
        chains = client.get_chains_overview(limit=args.limit, search=args.search)
        return envelope(
            "get_defi_chain_overview",
            [provider_ok(client.provider.name)],
            [item.model_dump(mode="json") for item in chains],
        )

    return run_tool("get_defi_chain_overview", _run)
