from __future__ import annotations

import logging

from pydantic import BaseModel

from backend.integrations import DefiLlamaClient
from backend.tools._helpers import envelope, provider_ok, run_tool, validate

logger = logging.getLogger(__name__)


class GetDefiProtocolDetailsInput(BaseModel):
    slug: str


def get_defi_protocol_details(payload: dict | None = None) -> dict:
    def _run() -> dict:
        args = validate(GetDefiProtocolDetailsInput, payload or {})
        client = DefiLlamaClient()
        logger.info("get_defi_protocol_details slug=%s", args.slug)
        details = client.get_protocol_details(args.slug)
        return envelope(
            "get_defi_protocol_details",
            [provider_ok(client.provider.name)],
            details.model_dump(mode="json"),
        )

    return run_tool("get_defi_protocol_details", _run)
