from __future__ import annotations

import logging
from typing import Literal

from pydantic import BaseModel, Field

from backend.integrations import FredClient
from backend.models import MacroObservationWindow
from backend.tools._helpers import envelope, provider_error, provider_ok, run_tool, validate

logger = logging.getLogger(__name__)


class GetMacroObservationsInput(BaseModel):
    series_id: str
    limit: int = Field(default=24, ge=1, le=120)
    sort_order: Literal["asc", "desc"] = "desc"
    observation_start: str | None = None
    observation_end: str | None = None


def get_macro_observations(payload: dict | None = None) -> dict:
    def _run() -> dict:
        args = validate(GetMacroObservationsInput, payload or {})
        client = FredClient()
        if not client.configured:
            return envelope(
                "get_macro_observations",
                [provider_error(client.provider.name, f"Missing {client.provider.env_var}")],
                {"error": "provider_not_configured", "detail": f"Missing {client.provider.env_var}"},
                ok=False,
            )

        logger.info("get_macro_observations series_id=%s limit=%s", args.series_id, args.limit)
        series = client.get_series_metadata(args.series_id)
        observations = client.get_series_observations(
            args.series_id,
            limit=args.limit,
            sort_order=args.sort_order,
            observation_start=args.observation_start,
            observation_end=args.observation_end,
        )
        window = MacroObservationWindow(series=series, count=len(observations), observations=observations)
        return envelope("get_macro_observations", [provider_ok(client.provider.name)], window.model_dump(mode="json"))

    return run_tool("get_macro_observations", _run)
