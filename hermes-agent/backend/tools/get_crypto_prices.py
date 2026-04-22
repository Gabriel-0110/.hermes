from __future__ import annotations

from pydantic import BaseModel, Field

from backend.integrations import CoinGeckoClient, CoinMarketCapClient
from backend.tools._helpers import envelope, provider_error, provider_ok, run_tool, validate


class GetCryptoPricesInput(BaseModel):
    symbols: list[str] = Field(min_length=1, max_length=20)
    currency: str = "USD"


def get_crypto_prices(payload: dict) -> dict:
    def _run() -> dict:
        args = validate(GetCryptoPricesInput, payload)
        providers = []
        warnings: list[str] = []
        client_chain = [CoinGeckoClient(), CoinMarketCapClient()]
        for client in client_chain:
            if not client.configured:
                providers.append(provider_error(client.provider.name, f"Missing {client.provider.env_var}"))
                continue
            quotes = client.get_prices(args.symbols, args.currency)
            providers.append(provider_ok(client.provider.name))
            return envelope("get_crypto_prices", providers, [quote.model_dump(mode="json") for quote in quotes], warnings=warnings)
        return envelope(
            "get_crypto_prices",
            providers,
            {"error": "provider_not_configured", "detail": "No configured market data provider."},
            warnings=["No configured market data provider."],
            ok=False,
        )

    return run_tool("get_crypto_prices", _run)
