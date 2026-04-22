"""Shared CCXT-backed execution client for backend-only exchange access."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any

from backend.integrations.base import IntegrationError, MissingCredentialError
from backend.integrations.execution.mode import (
    current_trading_mode,
    is_paper_mode,
    live_trading_blockers,
)
from backend.integrations.provider_profiles import PROVIDER_PROFILES
from backend.models import ExchangeBalances, ExecutionBalance, ExecutionOrder, ExecutionStatus, ExecutionTrade

logger = logging.getLogger(__name__)


class CCXTExecutionClient:
    """Backend-only execution adapter with BitMart as the first supported exchange."""

    provider = PROVIDER_PROFILES["bitmart"]
    exchange_id = "bitmart"
    account_type = "spot"

    def __init__(self) -> None:
        self._api_key = os.getenv("BITMART_API_KEY", "").strip()
        self._secret = os.getenv("BITMART_SECRET", "").strip()
        self._memo = os.getenv("BITMART_MEMO", "").strip()
        self._exchange: Any | None = None
        self._markets_loaded = False

    @property
    def configured(self) -> bool:
        return bool(self._api_key and self._secret and self._memo)

    @property
    def rate_limit_enabled(self) -> bool:
        return True

    def require_credentials(self) -> None:
        if self.configured:
            return
        missing = [
            name
            for name, value in (
                ("BITMART_API_KEY", self._api_key),
                ("BITMART_SECRET", self._secret),
                ("BITMART_MEMO", self._memo),
            )
            if not value
        ]
        raise MissingCredentialError(
            "BITMART is not configured. Set the following backend env vars: " + ", ".join(missing)
        )

    def _import_ccxt(self) -> Any:
        try:
            import ccxt  # type: ignore
        except ImportError as exc:
            raise IntegrationError("CCXT is not installed. Add the 'ccxt' dependency to enable exchange execution.") from exc
        return ccxt

    _LIVE_URLS = (
        "https://api-cloud-v2.bitmart.com",
        "https://api-cloud.bitmart.com",
    )

    def _check_paper_mode_url(self) -> None:
        """Raise if paper mode is active but a live exchange URL would be used."""
        if not is_paper_mode():
            blockers = live_trading_blockers()
            if blockers:
                raise IntegrationError(
                    "Live trading unlock is incomplete: " + " ".join(blockers)
                )
            return
        # If an explicit override URL is set, check whether it's a live URL
        override_url = os.getenv("BITMART_BASE_URL", "").strip().rstrip("/")
        if override_url:
            for live_url in self._LIVE_URLS:
                if override_url.startswith(live_url):
                    raise IntegrationError(
                        f"HERMES_PAPER_MODE is active but BITMART_BASE_URL points to a live endpoint: {override_url}. "
                        "Unset HERMES_PAPER_MODE or switch to a sandbox URL to proceed."
                    )
        # No override — default BitMart URLs are live; block unconditionally in paper mode
        else:
            raise IntegrationError(
                "Paper trading mode is active. Real order placement is disabled. "
                f"Current mode is {current_trading_mode()!r}. "
                "Set HERMES_TRADING_MODE=live and complete the live trading unlock env vars to enable live trading."
            )

    def _get_exchange(self) -> Any:
        self.require_credentials()
        self._check_paper_mode_url()
        if self._exchange is not None:
            return self._exchange
        ccxt = self._import_ccxt()
        try:
            self._exchange = ccxt.bitmart(
                {
                    "apiKey": self._api_key,
                    "secret": self._secret,
                    "memo": self._memo,
                    "password": self._memo,
                    "enableRateLimit": True,
                    "options": {"defaultType": self.account_type},
                }
            )
        except Exception as exc:  # pragma: no cover - defensive against library-level init issues
            raise IntegrationError("Failed to initialize the BitMart execution client.") from exc
        return self._exchange

    def _ensure_markets_loaded(self) -> None:
        if self._markets_loaded:
            return
        exchange = self._get_exchange()
        self._call_exchange("load_markets", exchange.load_markets)
        self._markets_loaded = True

    def _call_exchange(self, operation: str, fn: Any, *args: Any, **kwargs: Any) -> Any:
        try:
            return fn(*args, **kwargs)
        except MissingCredentialError:
            raise
        except Exception as exc:
            logger.warning("BitMart %s failed: %s", operation, exc.__class__.__name__)
            raise IntegrationError(f"BitMart {operation} failed.") from exc

    def _isoformat(self, value: Any) -> str | None:
        if value is None:
            return None
        if isinstance(value, datetime):
            return value.astimezone(timezone.utc).isoformat()
        try:
            return datetime.fromtimestamp(float(value) / 1000, tz=timezone.utc).isoformat()
        except Exception:
            return None

    def _float_or_none(self, value: Any) -> float | None:
        if value is None or value == "":
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _normalize_order(self, order: dict[str, Any]) -> ExecutionOrder:
        info = order.get("info") or {}
        order_id = order.get("id") or info.get("order_id") or info.get("orderId")
        if not order_id:
            raise IntegrationError("BitMart returned an order without an id.")
        return ExecutionOrder(
            order_id=str(order_id),
            exchange=self.provider.name,
            symbol=str(order.get("symbol") or info.get("symbol") or "unknown"),
            side=order.get("side"),
            order_type=order.get("type") or info.get("type"),
            status=order.get("status") or info.get("state"),
            client_order_id=order.get("clientOrderId") or info.get("clientOrderId"),
            price=self._float_or_none(order.get("price")),
            average_price=self._float_or_none(order.get("average")),
            amount=self._float_or_none(order.get("amount")),
            filled=self._float_or_none(order.get("filled")),
            remaining=self._float_or_none(order.get("remaining")),
            cost=self._float_or_none(order.get("cost")),
            time_in_force=order.get("timeInForce") or info.get("timeInForce"),
            post_only=order.get("postOnly"),
            reduce_only=order.get("reduceOnly"),
            created_at=self._isoformat(order.get("timestamp")),
            updated_at=self._isoformat(order.get("lastUpdateTimestamp") or order.get("timestamp")),
        )

    def _normalize_trade(self, trade: dict[str, Any]) -> ExecutionTrade:
        info = trade.get("info") or {}
        trade_id = trade.get("id") or info.get("trade_id") or info.get("tradeId")
        if not trade_id:
            raise IntegrationError("BitMart returned a trade without an id.")
        fee = trade.get("fee") or {}
        return ExecutionTrade(
            trade_id=str(trade_id),
            order_id=trade.get("order") or info.get("order_id") or info.get("orderId"),
            exchange=self.provider.name,
            symbol=str(trade.get("symbol") or info.get("symbol") or "unknown"),
            side=trade.get("side"),
            price=self._float_or_none(trade.get("price")),
            amount=self._float_or_none(trade.get("amount")),
            cost=self._float_or_none(trade.get("cost")),
            fee_cost=self._float_or_none(fee.get("cost")),
            fee_currency=fee.get("currency"),
            liquidity=trade.get("takerOrMaker"),
            timestamp=self._isoformat(trade.get("timestamp")),
        )

    def get_exchange_balances(self) -> ExchangeBalances:
        exchange = self._get_exchange()
        balance = self._call_exchange("fetch_balance", exchange.fetch_balance)
        balances: list[ExecutionBalance] = []
        for asset, totals in (balance.get("total") or {}).items():
            free_map = balance.get("free") or {}
            used_map = balance.get("used") or {}
            balances.append(
                ExecutionBalance(
                    asset=str(asset),
                    free=self._float_or_none(free_map.get(asset)),
                    used=self._float_or_none(used_map.get(asset)),
                    total=self._float_or_none(totals),
                )
            )
        balances.sort(key=lambda item: item.asset)
        return ExchangeBalances(
            exchange=self.provider.name,
            account_type=self.account_type,
            balances=balances,
            as_of=datetime.now(timezone.utc).isoformat(),
        )

    def get_open_orders(self, *, symbol: str | None = None, limit: int | None = None) -> list[ExecutionOrder]:
        self._ensure_markets_loaded()
        exchange = self._get_exchange()
        params = {"limit": limit} if limit else {}
        orders = self._call_exchange("fetch_open_orders", exchange.fetch_open_orders, symbol, None, limit, params)
        return [self._normalize_order(order) for order in orders]

    def place_order(
        self,
        *,
        symbol: str,
        side: str,
        order_type: str,
        amount: float,
        price: float | None = None,
        client_order_id: str | None = None,
        time_in_force: str | None = None,
        post_only: bool = False,
    ) -> ExecutionOrder:
        self._ensure_markets_loaded()
        exchange = self._get_exchange()
        params: dict[str, Any] = {}
        if client_order_id:
            params["clientOrderId"] = client_order_id
        if time_in_force:
            params["timeInForce"] = time_in_force
        if post_only:
            params["postOnly"] = True
        # TODO(openclaw): confirm any BitMart-specific spot/futures flags that should be normalized here before widening exchange support.
        logger.info("Submitting BitMart order for %s %s %s", symbol, side, order_type)
        order = self._call_exchange(
            "create_order",
            exchange.create_order,
            symbol,
            order_type,
            side,
            amount,
            price,
            params,
        )
        normalized = self._normalize_order(order)
        logger.info("BitMart order submitted successfully for %s as %s", normalized.symbol, normalized.order_id)
        return normalized

    def cancel_order(self, *, order_id: str, symbol: str | None = None) -> ExecutionOrder:
        exchange = self._get_exchange()
        logger.info("Cancelling BitMart order %s", order_id)
        order = self._call_exchange("cancel_order", exchange.cancel_order, order_id, symbol)
        normalized = self._normalize_order(order)
        logger.info("BitMart order %s cancellation acknowledged", normalized.order_id)
        return normalized

    def get_order_history(
        self,
        *,
        symbol: str | None = None,
        since: int | None = None,
        limit: int | None = None,
    ) -> list[ExecutionOrder]:
        exchange = self._get_exchange()
        orders = self._call_exchange("fetch_orders", exchange.fetch_orders, symbol, since, limit)
        return [self._normalize_order(order) for order in orders]

    def get_trade_history(
        self,
        *,
        symbol: str | None = None,
        since: int | None = None,
        limit: int | None = None,
    ) -> list[ExecutionTrade]:
        exchange = self._get_exchange()
        trades = self._call_exchange("fetch_my_trades", exchange.fetch_my_trades, symbol, since, limit)
        # TODO(openclaw): review BitMart trade fee / maker-taker field mapping against live responses before adding PnL logic.
        return [self._normalize_trade(trade) for trade in trades]

    def get_execution_status(self, *, order_id: str | None = None, symbol: str | None = None) -> ExecutionStatus:
        if not self.configured:
            return ExecutionStatus(
                exchange=self.provider.name,
                configured=False,
                connected=False,
                rate_limit_enabled=self.rate_limit_enabled,
                account_type=self.account_type,
                detail="BitMart credentials are not configured.",
                checked_at=datetime.now(timezone.utc).isoformat(),
            )
        exchange = self._get_exchange()
        order: ExecutionOrder | None = None
        detail = "BitMart execution client configured."
        if order_id:
            raw_order = self._call_exchange("fetch_order", exchange.fetch_order, order_id, symbol)
            order = self._normalize_order(raw_order)
            detail = f"Fetched BitMart status for order {order.order_id}."
        else:
            self._ensure_markets_loaded()
        return ExecutionStatus(
            exchange=self.provider.name,
            configured=True,
            connected=True,
            rate_limit_enabled=self.rate_limit_enabled,
            account_type=self.account_type,
            detail=detail,
            order=order,
            checked_at=datetime.now(timezone.utc).isoformat(),
        )
