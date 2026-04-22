from __future__ import annotations

from pydantic import BaseModel

from backend.integrations import EtherscanClient
from backend.tools._helpers import envelope, provider_error, provider_ok, run_tool, validate


class GetWalletTransactionsInput(BaseModel):
    wallet: str


def get_wallet_transactions(payload: dict) -> dict:
    def _run() -> dict:
        args = validate(GetWalletTransactionsInput, payload)
        client = EtherscanClient()
        if not client.configured:
            return envelope("get_wallet_transactions", [provider_error(client.provider.name, f"Missing {client.provider.env_var}")], [], ok=False)
        txs = client.get_wallet_transactions(args.wallet)
        return envelope("get_wallet_transactions", [provider_ok(client.provider.name)], [tx.model_dump(mode="json") for tx in txs])

    return run_tool("get_wallet_transactions", _run)

