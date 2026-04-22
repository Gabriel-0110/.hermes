from __future__ import annotations

import logging

from pydantic import BaseModel, Field, model_validator

from backend.integrations import FredClient
from backend.models import MacroSeriesLookup
from backend.tools._helpers import envelope, provider_error, provider_ok, run_tool, validate

logger = logging.getLogger(__name__)


class GetMacroSeriesInput(BaseModel):
    query: str | None = None
    series_id: str | None = None
    limit: int = Field(default=10, ge=1, le=25)

    @model_validator(mode="after")
    def check_lookup_mode(self) -> "GetMacroSeriesInput":
        if bool(self.query) == bool(self.series_id):
            raise ValueError("Provide exactly one of query or series_id.")
        return self


def get_macro_series(payload: dict | None = None) -> dict:
    def _run() -> dict:
        args = validate(GetMacroSeriesInput, payload or {})
        client = FredClient()
        if not client.configured:
            return envelope(
                "get_macro_series",
                [provider_error(client.provider.name, f"Missing {client.provider.env_var}")],
                {"error": "provider_not_configured", "detail": f"Missing {client.provider.env_var}"},
                ok=False,
            )

        if args.series_id:
            logger.info("get_macro_series exact lookup series_id=%s", args.series_id)
            results = [client.get_series_metadata(args.series_id)]
        else:
            logger.info("get_macro_series search query=%s limit=%s", args.query, args.limit)
            results = client.search_series(args.query or "", limit=args.limit)

        lookup = MacroSeriesLookup(
            query=args.query,
            requested_series_id=args.series_id,
            count=len(results),
            results=results,
        )
        return envelope("get_macro_series", [provider_ok(client.provider.name)], lookup.model_dump(mode="json"))

    return run_tool("get_macro_series", _run)
