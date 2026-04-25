"""get_funding_rates — Current perpetual funding rates across public derivatives venues."""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

from backend.integrations.derivatives.public_data import (
    aggregate_funding_rate_snapshots,
    fetch_funding_rate_snapshots,
    resolve_requested_venues,
)
from backend.tools._helpers import envelope, provider_error, provider_ok, run_tool, validate


class GetFundingRatesInput(BaseModel):
    symbols: list[str] | None = Field(default=None, description="Specific symbols e.g. ['BTCUSDT','ETHUSDT']. Omit for top 20 by absolute funding rate.")
    limit: int = Field(default=20, ge=1, le=100)
    venue: str | list[str] | None = Field(
        default=None,
        description="Venue id, comma-separated venue list, list of venues, or 'all'. Defaults to bitmart.",
    )

    @field_validator("venue")
    @classmethod
    def _validate_venue(cls, value: str | list[str] | None) -> str | list[str] | None:
        if value is not None:
            resolve_requested_venues(value)
        return value


def get_funding_rates(payload: dict) -> dict:
    def _run() -> dict:
        args = validate(GetFundingRatesInput, payload)
        venues = resolve_requested_venues(args.venue)
        snapshots, errors = fetch_funding_rate_snapshots(
            symbols=args.symbols,
            venues=venues,
            limit=args.limit,
        )

        providers = [
            provider_ok(client.provider.name, detail=f"venue={venue}")
            for venue, client, _snapshot in snapshots
        ]
        providers.extend(
            provider_error(provider_name, f"venue={venue}: {exc}")
            for venue, provider_name, exc in errors
        )
        warnings = [f"{venue}: {exc}" for venue, _provider_name, exc in errors]

        if not snapshots:
            return envelope(
                "get_funding_rates",
                providers,
                {
                    "error": "provider_failure",
                    "detail": "No funding-rate venues returned data.",
                    "requested_venues": venues,
                },
                warnings=warnings,
                ok=False,
            )

        if len(venues) == 1:
            data = snapshots[0][2].model_dump(mode="json")
            data["venue"] = snapshots[0][0]
        else:
            data = aggregate_funding_rate_snapshots(snapshots)

        return envelope(
            "get_funding_rates",
            providers,
            data,
            warnings=warnings,
            ok=True,
        )

    return run_tool("get_funding_rates", _run)
