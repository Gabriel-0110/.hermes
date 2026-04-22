from __future__ import annotations

import logging

from pydantic import BaseModel

from backend.integrations import FredClient
from backend.models import EventRiskMacroContext
from backend.tools._helpers import envelope, provider_error, provider_ok, run_tool, validate
from backend.tools.get_macro_regime_summary import DEFAULT_MACRO_SERIES, build_macro_regime_summary

logger = logging.getLogger(__name__)


class GetEventRiskMacroContextInput(BaseModel):
    event: str = "upcoming macro event"


def get_event_risk_macro_context(payload: dict | None = None) -> dict:
    def _run() -> dict:
        args = validate(GetEventRiskMacroContextInput, payload or {})
        client = FredClient()
        if not client.configured:
            return envelope(
                "get_event_risk_macro_context",
                [provider_error(client.provider.name, f"Missing {client.provider.env_var}")],
                {"error": "provider_not_configured", "detail": f"Missing {client.provider.env_var}"},
                ok=False,
            )

        logger.info("get_event_risk_macro_context event=%s", args.event)
        regime = build_macro_regime_summary(client, DEFAULT_MACRO_SERIES, observation_limit=2)
        context = EventRiskMacroContext(
            event=args.event,
            regime=regime.regime,
            risk_bias=regime.risk_bias,
            summary=(
                f"{args.event}: use the current macro regime as context rather than as a deterministic signal. "
                f"Current bias is {regime.risk_bias} with watch items focused on labor, front-end rates, and production."
            ),
            indicators=regime.indicators,
            watch_items=regime.watch_items,
            as_of=regime.as_of,
        )
        return envelope("get_event_risk_macro_context", [provider_ok(client.provider.name)], context.model_dump(mode="json"))

    return run_tool("get_event_risk_macro_context", _run)
