from __future__ import annotations

import logging

from pydantic import BaseModel, Field

from backend.integrations import DefiLlamaClient, DefiLlamaEndpointUnavailableError
from backend.tools._helpers import envelope, provider_error, provider_ok, run_tool, validate

logger = logging.getLogger(__name__)


class GetDefiYieldsInput(BaseModel):
    limit: int = Field(default=25, ge=1, le=200)
    chain: str | None = None
    project: str | None = None
    stablecoin: bool | None = None
    min_tvl: float | None = Field(default=None, ge=0)
    min_apy: float | None = None


def get_defi_yields(payload: dict | None = None) -> dict:
    def _run() -> dict:
        args = validate(GetDefiYieldsInput, payload or {})
        client = DefiLlamaClient()
        logger.info(
            "get_defi_yields limit=%s chain=%s project=%s stablecoin=%s min_tvl=%s min_apy=%s",
            args.limit,
            args.chain,
            args.project,
            args.stablecoin,
            args.min_tvl,
            args.min_apy,
        )
        try:
            pools = client.get_yields(
                limit=args.limit,
                chain=args.chain,
                project=args.project,
                stablecoin=args.stablecoin,
                min_tvl=args.min_tvl,
                min_apy=args.min_apy,
            )
        except DefiLlamaEndpointUnavailableError as exc:
            return envelope(
                "get_defi_yields",
                [provider_error(client.provider.name, str(exc))],
                {"error": "endpoint_not_available", "detail": str(exc)},
                ok=False,
            )
        return envelope(
            "get_defi_yields",
            [provider_ok(client.provider.name)],
            [item.model_dump(mode="json") for item in pools],
        )

    return run_tool("get_defi_yields", _run)
