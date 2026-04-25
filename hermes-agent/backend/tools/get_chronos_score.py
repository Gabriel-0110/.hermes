"""Tool wrapper for cached Chronos direction-alignment scoring."""

from __future__ import annotations

from pydantic import BaseModel, Field

from backend.strategies.chronos_scoring import get_chronos_alignment_score
from backend.tools._helpers import envelope, provider_ok, run_tool, validate


class GetChronosScoreInput(BaseModel):
    symbol: str
    direction: str = Field(default="watch", pattern="^(long|short|watch)$")
    interval: str = "4h"
    horizon: int | None = Field(default=None, ge=1, le=60)
    max_age_minutes: int | None = Field(default=None, ge=1, le=1440)


def get_chronos_score(payload: dict) -> dict:
    def _run() -> dict:
        args = validate(GetChronosScoreInput, payload)
        details = get_chronos_alignment_score(
            args.symbol,
            args.direction,
            interval=args.interval,
            horizon=args.horizon,
            max_age_minutes=args.max_age_minutes,
        )
        return envelope(
            "get_chronos_score",
            [provider_ok("amazon_chronos_2" if details.forecast_model and "chronos" in details.forecast_model else "deterministic_research_projection")],
            details.to_dict(),
            warnings=[details.error] if details.error else None,
            ok=details.error is None,
        )

    return run_tool("get_chronos_score", _run)
