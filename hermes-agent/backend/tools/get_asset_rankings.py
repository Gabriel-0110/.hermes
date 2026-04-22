from __future__ import annotations

from backend.tools._helpers import envelope, run_tool
from backend.tools.get_crypto_prices import get_crypto_prices


def get_asset_rankings(payload: dict) -> dict:
    def _run() -> dict:
        quotes = get_crypto_prices(payload)
        data = quotes.get("data")
        if not isinstance(data, list):
            # Propagate error envelope from get_crypto_prices (e.g. provider_not_configured)
            return quotes
        ranked = sorted(data, key=lambda row: row.get("market_cap") or 0, reverse=True)
        return envelope("get_asset_rankings", quotes["meta"]["providers"], ranked)

    return run_tool("get_asset_rankings", _run)

