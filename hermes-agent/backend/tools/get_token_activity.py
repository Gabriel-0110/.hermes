from __future__ import annotations

from backend.tools._helpers import envelope, run_tool
from backend.tools.get_wallet_transactions import get_wallet_transactions


def get_token_activity(payload: dict) -> dict:
    def _run() -> dict:
        txs = get_wallet_transactions(payload)
        data = txs["data"]
        assets = sorted({row.get("asset") for row in data if row.get("asset")})
        return envelope("get_token_activity", txs["meta"]["providers"], {"wallet": payload.get("wallet"), "assets": assets, "transactions": data})

    return run_tool("get_token_activity", _run)

