"""Etherscan client normalizing wallet and transfer activity."""

from __future__ import annotations

from backend.integrations.base import BaseIntegrationClient
from backend.integrations.provider_profiles import PROVIDER_PROFILES
from backend.models import WalletData, WalletTransaction


class EtherscanClient(BaseIntegrationClient):
    provider = PROVIDER_PROFILES["etherscan"]
    base_url = "https://api.etherscan.io/api"

    def auth_params(self) -> dict[str, str]:
        return {"apikey": self._api_key}

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
            },
        )
        txs: list[WalletTransaction] = []
        for row in payload.get("result", [])[:20]:
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

