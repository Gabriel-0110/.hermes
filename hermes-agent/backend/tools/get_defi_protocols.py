from __future__ import annotations

import logging

from pydantic import BaseModel, Field

from backend.integrations import DefiLlamaClient
from backend.tools._helpers import envelope, provider_ok, run_tool, validate

logger = logging.getLogger(__name__)


class GetDefiProtocolsInput(BaseModel):
    limit: int = Field(default=25, ge=1, le=200)
    category: str | None = None
    chain: str | None = None
    search: str | None = None


def get_defi_protocols(payload: dict | None = None) -> dict:
    def _run() -> dict:
        args = validate(GetDefiProtocolsInput, payload or {})
        client = DefiLlamaClient()
        logger.info(
            "get_defi_protocols limit=%s category=%s chain=%s search=%s",
            args.limit,
            args.category,
            args.chain,
            args.search,
        )
        protocols = client.get_protocols(
            limit=args.limit,
            category=args.category,
            chain=args.chain,
            search=args.search,
        )
        return envelope(
            "get_defi_protocols",
            [provider_ok(client.provider.name)],
            [item.model_dump(mode="json") for item in protocols],
        )

    return run_tool("get_defi_protocols", _run)
