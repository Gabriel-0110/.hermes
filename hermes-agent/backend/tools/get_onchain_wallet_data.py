from __future__ import annotations

from pydantic import BaseModel

from backend.integrations import EtherscanClient
from backend.tools._helpers import envelope, provider_error, provider_ok, run_tool, validate


class GetOnchainWalletDataInput(BaseModel):
    wallet: str
    chain: str = "ethereum"


def get_onchain_wallet_data(payload: dict) -> dict:
    def _run() -> dict:
        args = validate(GetOnchainWalletDataInput, payload)
        client = EtherscanClient()
        if not client.configured:
            return envelope("get_onchain_wallet_data", [provider_error(client.provider.name, f"Missing {client.provider.env_var}")], {}, ok=False)
        wallet = client.get_wallet_data(args.wallet)
        return envelope("get_onchain_wallet_data", [provider_ok(client.provider.name)], wallet.model_dump(mode="json"))

    return run_tool("get_onchain_wallet_data", _run)

