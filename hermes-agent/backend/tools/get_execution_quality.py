"""get_execution_quality — analyse fill quality for recent trades vs current mid-price."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from pydantic import BaseModel, Field

from backend.integrations.derivatives.bitmart_public_client import BitMartPublicClient
from backend.integrations.execution.ccxt_client import CCXTExecutionClient
from backend.integrations.base import MissingCredentialError
from backend.tools._helpers import envelope, provider_ok, provider_error, run_tool, validate

logger = logging.getLogger(__name__)


class GetExecutionQualityInput(BaseModel):
    symbol: str = Field(..., description="Symbol to analyse (e.g. 'BTC/USDT' or 'BTCUSDT').")
    limit: int = Field(default=20, ge=1, le=100, description="Number of recent fills to analyse.")


def get_execution_quality(payload: dict) -> dict:
    def _run() -> dict:
        args = validate(GetExecutionQualityInput, payload)

        exec_client = CCXTExecutionClient()
        if not exec_client.configured:
            return envelope(
                "get_execution_quality",
                [provider_error(exec_client.provider.name, "Exchange credentials not configured")],
                {"error": "Exchange not configured — set BITMART_API_KEY, BITMART_SECRET, BITMART_MEMO."},
                ok=False,
            )

        # Normalise symbols
        ccxt_symbol = args.symbol.replace("USDT", "/USDT").replace("USD", "/USD") if "/" not in args.symbol else args.symbol
        futures_symbol = args.symbol.replace("/", "").upper()
        if not futures_symbol.endswith("USDT"):
            futures_symbol = futures_symbol + "USDT"

        # Fetch filled trades
        trades: list = []
        try:
            trades = exec_client.get_trade_history(symbol=ccxt_symbol, limit=args.limit)
        except (MissingCredentialError, Exception) as exc:
            logger.warning("get_execution_quality: trade history fetch failed: %s", exc)
            return envelope(
                "get_execution_quality",
                [provider_error(exec_client.provider.name, str(exc))],
                {"error": f"Could not fetch trade history: {exc}"},
                ok=False,
            )

        if not trades:
            return envelope(
                "get_execution_quality",
                [provider_ok(exec_client.provider.name)],
                {
                    "symbol": args.symbol,
                    "fills_analysed": 0,
                    "note": "No fills found for the requested symbol and window.",
                },
            )

        # Get current mid-price from order book as reference
        mid_price: float | None = None
        ob_provider = "bitmart_futures_public"
        try:
            pub_client = BitMartPublicClient()
            ob = pub_client.get_order_book(futures_symbol, limit=5)
            if ob.best_bid and ob.best_ask:
                mid_price = (ob.best_bid + ob.best_ask) / 2
        except Exception as exc:
            logger.debug("get_execution_quality: order book fetch for mid-price failed: %s", exc)

        # Compute execution quality metrics
        fill_prices: list[float] = []
        fill_sizes: list[float] = []
        costs: list[float] = []
        sides: list[str] = []

        for t in trades:
            # t is an ExecutionTrade Pydantic model
            price = getattr(t, "price", None)
            amount = getattr(t, "amount", None)
            cost = getattr(t, "cost", None)
            side = getattr(t, "side", "unknown")

            if price is not None and amount is not None:
                try:
                    fill_prices.append(float(price))
                    fill_sizes.append(float(amount))
                    costs.append(float(cost) if cost is not None else float(price) * float(amount))
                    sides.append(str(side or "unknown"))
                except (TypeError, ValueError):
                    continue

        if not fill_prices:
            return envelope(
                "get_execution_quality",
                [provider_ok(exec_client.provider.name)],
                {
                    "symbol": args.symbol,
                    "fills_analysed": 0,
                    "note": "Fills found but no price data available.",
                },
            )

        # VWAP
        total_cost = sum(costs)
        total_size = sum(fill_sizes)
        vwap = total_cost / total_size if total_size > 0 else None

        # Slippage vs current mid (in basis points)
        avg_fill_price = sum(fill_prices) / len(fill_prices)
        slippage_bps: float | None = None
        slippage_note = "No current mid-price available — cannot compute slippage."
        if mid_price is not None and mid_price > 0:
            slippage_bps = abs(avg_fill_price - mid_price) / mid_price * 10000
            slippage_note = f"Avg fill {avg_fill_price:.6f} vs current mid {mid_price:.6f}"

        buy_count = sides.count("buy")
        sell_count = sides.count("sell")

        providers = [provider_ok(exec_client.provider.name)]
        if mid_price is not None:
            providers.append(provider_ok(ob_provider))

        return envelope(
            "get_execution_quality",
            providers,
            {
                "symbol": args.symbol,
                "fills_analysed": len(fill_prices),
                "avg_fill_price": round(avg_fill_price, 6),
                "vwap": round(vwap, 6) if vwap is not None else None,
                "total_notional_usd": round(total_cost, 2),
                "current_mid_price": round(mid_price, 6) if mid_price is not None else None,
                "avg_slippage_bps": round(slippage_bps, 2) if slippage_bps is not None else None,
                "slippage_note": slippage_note,
                "buy_fills": buy_count,
                "sell_fills": sell_count,
                "analysed_at": datetime.now(UTC).isoformat(),
            },
        )

    return run_tool("get_execution_quality", _run)
