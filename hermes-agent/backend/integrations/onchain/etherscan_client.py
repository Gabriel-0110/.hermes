"""Etherscan client normalizing wallet and transfer activity."""

from __future__ import annotations

from backend.integrations.base import BaseIntegrationClient
from backend.integrations.provider_profiles import PROVIDER_PROFILES
from backend.models import WalletData, WalletTransaction


class EtherscanClient(BaseIntegrationClient):
    provider = PROVIDER_PROFILES["etherscan"]
    # Updated to Etherscan API V2 — V1 (api.etherscan.io/api) is deprecated
    base_url = "https://api.etherscan.io/v2/api"

    def auth_params(self) -> dict[str, str]:
        # V2 requires chainid param; default to Ethereum mainnet (chainid=1)
        return {"apikey": self._api_key, "chainid": "1"}

    def get_wallet_transactions(self, wallet: str, startblock: int = 0, endblock: int = 99999999) -> list[WalletTransaction]:
        payload = self.request(
            "GET",
            "",
            params={
                "module": "account",
                "action": "txlist",
                "address": wallet,
                "startblock": startblock,
                "endblock": endblock,
                "sort": "desc",
                "offset": "20",
            },
        )
        txs: list[WalletTransaction] = []
        for row in (payload.get("result") or [])[:20]:
            if not isinstance(row, dict):
                continue
            txs.append(
                WalletTransaction(
                    tx_hash=row.get("hash", ""),
                    timestamp=row.get("timeStamp"),
                    direction="out" if row.get("from", "").lower() == wallet.lower() else "in",
                    asset="ETH",
                    amount=float(row["value"]) / 1e18 if row.get("value") else None,
                    counterparty=row.get("to") if row.get("from", "").lower() == wallet.lower() else row.get("from"),
                )
            )
        return txs

    def get_wallet_data(self, wallet: str) -> WalletData:
        txs = self.get_wallet_transactions(wallet)
        return WalletData(wallet=wallet, tx_count=len(txs), recent_transactions=txs)

