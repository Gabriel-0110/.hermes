from __future__ import annotations

import logging

from pydantic import BaseModel, Field

from backend.integrations import DefiLlamaClient
from backend.tools._helpers import envelope, provider_ok, run_tool, validate

logger = logging.getLogger(__name__)


class GetDefiRegimeSummaryInput(BaseModel):
    chain_limit: int = Field(default=5, ge=1, le=20)
    protocol_limit: int = Field(default=5, ge=1, le=20)
    yield_limit: int = Field(default=5, ge=1, le=20)


def get_defi_regime_summary(payload: dict | None = None) -> dict:
    def _run() -> dict:
        args = validate(GetDefiRegimeSummaryInput, payload or {})
        client = DefiLlamaClient()
        logger.info(
            "get_defi_regime_summary chain_limit=%s protocol_limit=%s yield_limit=%s",
            args.chain_limit,
            args.protocol_limit,
            args.yield_limit,
        )
        summary = client.get_regime_summary(
            chain_limit=args.chain_limit,
            protocol_limit=args.protocol_limit,
            yield_limit=args.yield_limit,
        )
        warnings = summary.open_interest.warnings if summary.open_interest and summary.open_interest.warnings else None
        return envelope(
            "get_defi_regime_summary",
            [provider_ok(client.provider.name, detail=f"open_interest_access={summary.open_interest.access_level if summary.open_interest else 'unknown'}")],
            summary.model_dump(mode="json"),
            warnings=warnings,
        )

    return run_tool("get_defi_regime_summary", _run)
