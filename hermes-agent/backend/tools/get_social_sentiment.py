from __future__ import annotations

from pydantic import BaseModel

from backend.integrations import LunarCrushClient
from backend.tools._helpers import envelope, provider_error, provider_ok, run_tool, validate


class GetSocialSentimentInput(BaseModel):
    symbol: str


def get_social_sentiment(payload: dict) -> dict:
    def _run() -> dict:
        args = validate(GetSocialSentimentInput, payload)
        client = LunarCrushClient()
        if not client.configured:
            return envelope("get_social_sentiment", [provider_error(client.provider.name, f"Missing {client.provider.env_var}")], {}, ok=False)
        snapshot = client.get_sentiment(args.symbol)
        return envelope("get_social_sentiment", [provider_ok(client.provider.name)], snapshot.model_dump(mode="json"))

    return run_tool("get_social_sentiment", _run)

