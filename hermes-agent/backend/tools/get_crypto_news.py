from __future__ import annotations

from pydantic import BaseModel, Field

from backend.integrations import CryptoPanicClient
from backend.tools._helpers import envelope, provider_error, provider_ok, run_tool, validate


class GetCryptoNewsInput(BaseModel):
    assets: list[str] = Field(default_factory=list, max_length=10)
    limit: int = Field(default=10, ge=1, le=50)


def get_crypto_news(payload: dict | None = None) -> dict:
    def _run() -> dict:
        args = validate(GetCryptoNewsInput, payload or {})
        client = CryptoPanicClient()
        if not client.configured:
            return envelope("get_crypto_news", [provider_error(client.provider.name, f"Missing {client.provider.env_var}")], [], ok=False)
        items = client.get_news(args.assets, args.limit)
        return envelope("get_crypto_news", [provider_ok(client.provider.name)], [item.model_dump(mode="json") for item in items])

    return run_tool("get_crypto_news", _run)

