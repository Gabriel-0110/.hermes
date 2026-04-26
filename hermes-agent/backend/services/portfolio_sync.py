"""Portfolio synchronisation service.

Fetches live balances from the configured exchange via CCXT, resolves USD
values for non-stablecoin holdings and persists a PortfolioSnapshotRow.

Usage (one-shot sync):
    from backend.services.portfolio_sync import sync_portfolio_from_exchange
    result = sync_portfolio_from_exchange()
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

from backend.db import HermesTimeSeriesRepository, ensure_time_series_schema, session_scope
from backend.db.session import get_engine
from backend.integrations.execution.ccxt_client import CCXTExecutionClient
from backend.integrations.base import MissingCredentialError
from backend.models import ExchangeBalances, PortfolioAsset, PortfolioState

logger = logging.getLogger(__name__)

# Stablecoins whose total balance is treated as cash (1 USD each)
_STABLECOINS: frozenset[str] = frozenset(
    {"USDT", "USDC", "BUSD", "TUSD", "DAI", "FDUSD", "USDP", "USDD", "GUSD"}
)

# Minimum balance (in native units) to bother pricing
_DUST_THRESHOLD = 1e-6


def _resolve_prices(symbols: list[str]) -> dict[str, float]:
    """Return a best-effort symbol→USD price map for the given assets.

    Tries CoinGecko first, then CoinMarketCap.  Falls back gracefully;
    assets whose price cannot be resolved will not appear in the result.
    """
    if not symbols:
        return {}

    prices: dict[str, float] = {}

    try:
        from backend.integrations import CoinGeckoClient, CoinMarketCapClient

        for client in (CoinGeckoClient(), CoinMarketCapClient()):
            if not client.configured:
                continue
            try:
                quotes = client.get_prices(symbols, "USD")
                for quote in quotes:
                    if quote.price is not None and quote.symbol:
                        prices[quote.symbol.upper()] = quote.price
                if prices:
                    break  # got at least some prices; stop
            except Exception as exc:
                logger.warning("portfolio_sync: price fetch failed via %s: %s", client.provider.name, exc)
    except Exception as exc:
        logger.warning("portfolio_sync: provider import error: %s", exc)

    return prices


def sync_portfolio_from_exchange(
    *,
    account_id: str | None = None,
) -> PortfolioState:
    """Fetch live balances from the exchange, compute USD metrics, and persist.

    Returns the resulting :class:`backend.models.PortfolioState` regardless of
    whether persistence succeeded so callers always get a valid model.

    Raises :class:`backend.integrations.base.MissingCredentialError` if the
    exchange client is not configured (no credentials in env).
    """
    effective_account_id = account_id or os.getenv("TRADING_PORTFOLIO_ACCOUNT_ID", "paper")
    client = CCXTExecutionClient()

    if not client.configured:
        err = (
            "Cannot sync portfolio: BitMart credentials (BITMART_API_KEY, "
            "BITMART_SECRET, BITMART_MEMO) are not configured."
        )
        try:
            from backend.trading.lifecycle_notifications import notify_portfolio_sync_failed
            notify_portfolio_sync_failed(account_id=effective_account_id, error=err)
        except Exception:
            pass
        raise MissingCredentialError(err)

    logger.info("portfolio_sync: fetching live balances for account_id=%s", effective_account_id)

    try:
        balances: ExchangeBalances = client.get_exchange_balances()
    except Exception as exc:
        try:
            from backend.trading.lifecycle_notifications import notify_portfolio_sync_failed
            notify_portfolio_sync_failed(account_id=effective_account_id, error=str(exc))
        except Exception:
            pass
        raise

    # Separate stablecoins (cash) from non-trivial positions
    cash_usd: float = 0.0
    position_assets: list[str] = []
    position_totals: dict[str, float] = {}

    for balance in balances.balances:
        symbol_upper = balance.asset.upper()
        total = balance.total or 0.0
        if total <= _DUST_THRESHOLD:
            continue

        if symbol_upper in _STABLECOINS:
            cash_usd += total
        else:
            position_assets.append(symbol_upper)
            position_totals[symbol_upper] = total

    # Resolve prices for non-stable holdings
    prices = _resolve_prices(position_assets)

    positions: list[PortfolioAsset] = []
    exposure_usd: float = 0.0

    for symbol_upper in position_assets:
        qty = position_totals[symbol_upper]
        price = prices.get(symbol_upper)
        notional = qty * price if price is not None else None
        if notional is not None:
            exposure_usd += notional
        positions.append(
            PortfolioAsset(
                symbol=symbol_upper,
                quantity=qty,
                mark_price=price,
                notional_usd=notional,
            )
        )

    total_equity_usd = cash_usd + exposure_usd
    now_iso = datetime.now(timezone.utc).isoformat()

    state = PortfolioState(
        account_id=effective_account_id,
        total_equity_usd=total_equity_usd if total_equity_usd > 0 else None,
        cash_usd=cash_usd if cash_usd > 0 else None,
        exposure_usd=exposure_usd if exposure_usd > 0 else None,
        positions=positions,
        updated_at=now_iso,
    )

    # Persist the snapshot
    _persist_snapshot(state, balances)
    try:
        from backend.trading.lifecycle_notifications import notify_portfolio_sync_completed
        notify_portfolio_sync_completed(
            account_id=state.account_id,
            total_equity_usd=state.total_equity_usd,
            positions_count=len(state.positions),
        )
    except Exception:
        pass
    return state


def _persist_snapshot(state: PortfolioState, raw_balances: ExchangeBalances) -> None:
    """Store the portfolio state as a PortfolioSnapshotRow."""
    try:
        engine = get_engine()
        ensure_time_series_schema(engine)
        with session_scope() as session:
            HermesTimeSeriesRepository(session).insert_portfolio_snapshot(
                account_id=state.account_id,
                total_equity_usd=state.total_equity_usd,
                cash_usd=state.cash_usd,
                exposure_usd=state.exposure_usd,
                positions=[p.model_dump(mode="json") for p in state.positions],
                payload={
                    "source": "exchange_sync",
                    "execution_mode": "live",
                    "exchange": raw_balances.exchange,
                    "account_type": raw_balances.account_type,
                    "as_of": raw_balances.as_of,
                    "positions_count": len(state.positions),
                },
            )
        logger.info(
            "portfolio_sync: snapshot persisted for account_id=%s total_equity=%.2f",
            state.account_id,
            state.total_equity_usd or 0.0,
        )
    except Exception as exc:
        logger.error("portfolio_sync: snapshot persistence failed: %s", exc)
