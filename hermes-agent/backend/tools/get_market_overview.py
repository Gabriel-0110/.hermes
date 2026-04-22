from __future__ import annotations

from backend.integrations import CoinGeckoClient, CoinMarketCapClient
from backend.tools._helpers import envelope, provider_error, provider_ok, run_tool


def get_market_overview(_: dict | None = None) -> dict:
    def _run() -> dict:
        providers = []
        for client in (CoinGeckoClient(), CoinMarketCapClient()):
            if not client.configured:
                providers.append(provider_error(client.provider.name, f"Missing {client.provider.env_var}"))
                continue
            overview = client.get_market_overview()
            providers.append(provider_ok(client.provider.name))
            return envelope("get_market_overview", providers, overview.model_dump(mode="json"))
        return envelope("get_market_overview", providers, {"error": "provider_not_configured"}, ok=False)

    return run_tool("get_market_overview", _run)

