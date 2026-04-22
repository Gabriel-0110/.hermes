from __future__ import annotations

from pydantic import BaseModel, Field

from backend.integrations import NewsApiClient
from backend.tools._helpers import envelope, provider_error, provider_ok, run_tool, validate


class GetGeneralNewsInput(BaseModel):
    query: str = "crypto macro"
    limit: int = Field(default=10, ge=1, le=50)


def get_general_news(payload: dict | None = None) -> dict:
    def _run() -> dict:
        args = validate(GetGeneralNewsInput, payload or {})
        client = NewsApiClient()
        if not client.configured:
            return envelope("get_general_news", [provider_error(client.provider.name, f"Missing {client.provider.env_var}")], [], ok=False)
        items = client.get_news(args.query, args.limit)
        return envelope("get_general_news", [provider_ok(client.provider.name)], [item.model_dump(mode="json") for item in items])

    return run_tool("get_general_news", _run)

