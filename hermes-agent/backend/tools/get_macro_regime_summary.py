from __future__ import annotations

import logging

from pydantic import BaseModel, Field

from backend.integrations import FredClient
from backend.models import MacroRegimeIndicator, MacroRegimeSummary
from backend.tools._helpers import envelope, provider_error, provider_ok, run_tool, validate

logger = logging.getLogger(__name__)

DEFAULT_MACRO_SERIES = ["UNRATE", "SOFR180DAYAVG", "INDPRO"]


class GetMacroRegimeSummaryInput(BaseModel):
    series_ids: list[str] = Field(default_factory=lambda: DEFAULT_MACRO_SERIES.copy(), min_length=1, max_length=10)
    observation_limit: int = Field(default=2, ge=2, le=24)


def _trend(latest: float | None, previous: float | None) -> str:
    if latest is None or previous is None:
        return "unknown"
    delta = latest - previous
    if abs(delta) < 1e-9:
        return "flat"
    return "up" if delta > 0 else "down"


def _score_indicator(indicator: MacroRegimeIndicator) -> int:
    trend = indicator.trend
    if indicator.series_id == "UNRATE":
        if trend == "down":
            return 1
        if trend == "up":
            return -1
    elif indicator.series_id == "SOFR180DAYAVG":
        if trend == "down":
            return 1
        if trend == "up":
            return -1
    elif indicator.series_id == "INDPRO":
        if trend == "up":
            return 1
        if trend == "down":
            return -1
    return 0


def _build_indicator(client: FredClient, series_id: str, observation_limit: int) -> MacroRegimeIndicator:
    series = client.get_series_metadata(series_id)
    observations = client.get_series_observations(series_id, limit=observation_limit, sort_order="desc")
    latest = observations[0].value if observations else None
    previous = observations[1].value if len(observations) > 1 else None
    change = (latest - previous) if latest is not None and previous is not None else None
    trend = _trend(latest, previous)

    if series_id == "UNRATE":
        interpretation = "Lower unemployment tends to support growth sentiment; rising unemployment can signal labor-market cooling."
    elif series_id == "SOFR180DAYAVG":
        interpretation = "Lower SOFR averages imply easier front-end funding conditions; rising SOFR implies tighter conditions."
    elif series_id == "INDPRO":
        interpretation = "Industrial production rising tends to support cyclical growth; declines can point to slower real activity."
    else:
        interpretation = f"Trend in {series.title} contributes additional macro context."

    return MacroRegimeIndicator(
        series_id=series.series_id,
        title=series.title,
        units=series.units,
        latest_value=latest,
        previous_value=previous,
        change=change,
        trend=trend,
        interpretation=interpretation,
        as_of=observations[0].date if observations else series.observation_end,
    )


def build_macro_regime_summary(client: FredClient, series_ids: list[str], observation_limit: int = 2) -> MacroRegimeSummary:
    indicators = [_build_indicator(client, series_id, observation_limit) for series_id in series_ids]
    score = sum(_score_indicator(indicator) for indicator in indicators)

    if score >= 2:
        regime = "supportive_disinflationary_growth"
        risk_bias = "risk_on"
    elif score <= -2:
        regime = "restrictive_macro_slowdown"
        risk_bias = "risk_off"
    else:
        regime = "mixed_transition"
        risk_bias = "mixed"

    watch_items = [
        f"{indicator.series_id}: trend={indicator.trend}, latest={indicator.latest_value}"
        for indicator in indicators
    ]
    summary = (
        "Macro regime synthesized from unemployment, front-end rates, and industrial production trends. "
        f"Current read is {regime} with a {risk_bias} bias."
    )
    as_of = max((indicator.as_of for indicator in indicators if indicator.as_of), default=None)
    return MacroRegimeSummary(
        regime=regime,
        risk_bias=risk_bias,
        summary=summary,
        indicators=indicators,
        watch_items=watch_items,
        as_of=as_of,
    )


def get_macro_regime_summary(payload: dict | None = None) -> dict:
    def _run() -> dict:
        args = validate(GetMacroRegimeSummaryInput, payload or {})
        client = FredClient()
        if not client.configured:
            return envelope(
                "get_macro_regime_summary",
                [provider_error(client.provider.name, f"Missing {client.provider.env_var}")],
                {"error": "provider_not_configured", "detail": f"Missing {client.provider.env_var}"},
                ok=False,
            )

        logger.info("get_macro_regime_summary series_ids=%s", ",".join(args.series_ids))
        summary = build_macro_regime_summary(client, args.series_ids, observation_limit=args.observation_limit)
        return envelope("get_macro_regime_summary", [provider_ok(client.provider.name)], summary.model_dump(mode="json"))

    return run_tool("get_macro_regime_summary", _run)
