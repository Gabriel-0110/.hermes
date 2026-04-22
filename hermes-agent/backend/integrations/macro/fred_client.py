"""FRED client for backend-only macro data access."""

from __future__ import annotations

import logging

from backend.integrations.base import BaseIntegrationClient, IntegrationError
from backend.integrations.provider_profiles import PROVIDER_PROFILES
from backend.models import MacroObservation, MacroSeries

logger = logging.getLogger(__name__)


def _parse_optional_float(value: str | None) -> float | None:
    if value is None:
        return None
    normalized = value.strip()
    if not normalized or normalized == ".":
        return None
    try:
        return float(normalized)
    except ValueError as exc:
        raise IntegrationError(f"FRED returned a non-numeric observation value: {value!r}") from exc


class FredClient(BaseIntegrationClient):
    provider = PROVIDER_PROFILES["fred"]
    base_url = "https://api.stlouisfed.org/fred"

    def auth_params(self) -> dict[str, str]:
        return {"api_key": self._api_key, "file_type": "json"}

    def search_series(self, query: str, limit: int = 10) -> list[MacroSeries]:
        logger.info("FRED series search query=%s limit=%s", query, limit)
        payload = self.request(
            "GET",
            "/series/search",
            params={"search_text": query, "limit": limit, "order_by": "popularity", "sort_order": "desc"},
        )
        rows = payload.get("seriess")
        if not isinstance(rows, list):
            raise IntegrationError("FRED search response was missing 'seriess'.")
        return [self._normalize_series(row) for row in rows[:limit]]

    def get_series_metadata(self, series_id: str) -> MacroSeries:
        logger.info("FRED series metadata requested for %s", series_id)
        payload = self.request("GET", "/series", params={"series_id": series_id})
        rows = payload.get("seriess")
        if not isinstance(rows, list) or not rows:
            raise IntegrationError(f"FRED did not return metadata for series {series_id}.")
        return self._normalize_series(rows[0])

    def get_series_observations(
        self,
        series_id: str,
        *,
        limit: int = 24,
        sort_order: str = "desc",
        observation_start: str | None = None,
        observation_end: str | None = None,
    ) -> list[MacroObservation]:
        logger.info(
            "FRED observations requested for %s limit=%s sort_order=%s observation_start=%s observation_end=%s",
            series_id,
            limit,
            sort_order,
            observation_start,
            observation_end,
        )
        params: dict[str, str | int] = {
            "series_id": series_id,
            "limit": limit,
            "sort_order": sort_order,
        }
        if observation_start:
            params["observation_start"] = observation_start
        if observation_end:
            params["observation_end"] = observation_end
        payload = self.request("GET", "/series/observations", params=params)
        rows = payload.get("observations")
        if not isinstance(rows, list):
            raise IntegrationError("FRED observations response was missing 'observations'.")
        observations: list[MacroObservation] = []
        for row in rows[:limit]:
            observations.append(
                MacroObservation(
                    series_id=series_id,
                    date=row["date"],
                    value=_parse_optional_float(row.get("value")),
                    raw_value=row.get("value"),
                    realtime_start=row.get("realtime_start"),
                    realtime_end=row.get("realtime_end"),
                )
            )
        return observations

    def _normalize_series(self, row: dict) -> MacroSeries:
        series_id = row.get("id")
        title = row.get("title")
        if not series_id or not title:
            raise IntegrationError("FRED series payload was missing id or title.")
        popularity = row.get("popularity")
        return MacroSeries(
            series_id=series_id,
            title=title,
            frequency=row.get("frequency"),
            units=row.get("units"),
            seasonal_adjustment=row.get("seasonal_adjustment"),
            popularity=int(popularity) if popularity not in (None, "") else None,
            observation_start=row.get("observation_start"),
            observation_end=row.get("observation_end"),
            last_updated=row.get("last_updated"),
            notes=row.get("notes"),
        )
