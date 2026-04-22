from __future__ import annotations

import logging

from backend.integrations.execution import get_execution_clients
from backend.tools._helpers import envelope, run_tool
from backend.tools.get_crypto_prices import get_crypto_prices
from backend.tools.get_portfolio_state import get_portfolio_state

logger = logging.getLogger(__name__)

_STABLECOINS = {"USD", "USDT", "USDC", "DAI", "FDUSD", "USDP", "TUSD"}


def _compute_avg_entry(symbol: str, venues: list[str] | None = None) -> float | None:
    """Return average entry price for *symbol* from trade history, or None."""
    try:
        trades = []
        for client in get_execution_clients(venues=venues, configured_only=True):
            trades.extend(client.get_trade_history(symbol=symbol))
        buys = [t for t in trades if (t.side or "").lower() == "buy"]
        if not buys:
            return None
        total_qty = sum(t.amount or 0.0 for t in buys)
        if total_qty == 0:
            return None
        total_cost = sum((t.price or 0.0) * (t.amount or 0.0) for t in buys)
        return total_cost / total_qty
    except Exception as exc:
        logger.debug("_compute_avg_entry(%s) skipped: %s", symbol, exc)
        return None


def get_portfolio_valuation(payload: dict | None = None) -> dict:
    def _run() -> dict:
        portfolio = get_portfolio_state(payload or {})
        positions = portfolio["data"].get("positions", [])
        if not positions:
            aggregate_balances = portfolio["data"].get("reconciliation", {}).get("aggregate_balances", [])
            positions = [
                {"symbol": row["asset"], "quantity": row.get("total") or 0.0}
                for row in aggregate_balances
                if (row.get("total") or 0.0) > 0
            ]
        symbols = [pos["symbol"] for pos in positions]
        prices = get_crypto_prices({"symbols": symbols}) if symbols else {"data": [], "meta": {"providers": []}}
        price_map = {row["symbol"]: row for row in prices["data"]}
        total = 0.0
        for pos in positions:
            mark_price = price_map.get(pos["symbol"], {}).get("price") or (1.0 if pos["symbol"] in _STABLECOINS else 0.0)
            quantity = pos.get("quantity") or 0.0
            total += quantity * mark_price
            if mark_price and quantity:
                avg_entry = _compute_avg_entry(pos["symbol"], portfolio["data"].get("venues"))
                if avg_entry is not None:
                    pos["avg_entry"] = avg_entry
                    pos["pnl_unrealized"] = (mark_price - avg_entry) * quantity
        providers = portfolio["meta"]["providers"] + prices["meta"]["providers"]
        return envelope(
            "get_portfolio_valuation",
            providers,
            {
                "total_mark_to_market_usd": total,
                "positions": positions,
                "reconciliation": portfolio["data"].get("reconciliation"),
            },
            warnings=portfolio["meta"].get("warnings") or [],
        )

    return run_tool("get_portfolio_valuation", _run)

