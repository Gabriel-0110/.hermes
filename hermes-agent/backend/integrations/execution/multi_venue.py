"""Venue-aware CCXT execution client for multi-venue trading workflows."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any

from backend.integrations.base import IntegrationError, MissingCredentialError, ProviderProfile
from backend.integrations.execution.mode import (
    current_trading_mode,
    is_paper_mode,
    live_trading_blockers,
)
from backend.integrations.execution.normalization import (
    float_or_none,
    normalize_ccxt_order,
    normalize_ccxt_trade,
)
from backend.integrations.provider_profiles import PROVIDER_PROFILES
from backend.models import ExchangeBalances, ExecutionBalance, ExecutionOrder, ExecutionStatus, ExecutionTrade

logger = logging.getLogger(__name__)

_EXECUTION_TOOLS = [
    "get_exchange_balances",
    "get_open_orders",
    "place_order",
    "cancel_order",
    "get_order_history",
    "get_trade_history",
    "get_execution_status",
]

_VENUE_DEFAULTS: dict[str, dict[str, Any]] = {
    "bitmart": {
        "provider_profile": "bitmart",
        "default_account_type": "spot",
        "required_credentials": ("API_KEY", "SECRET", "MEMO"),
        "live_urls": (
            "https://api-cloud-v2.bitmart.com",
            "https://api-cloud.bitmart.com",
        ),
        "default_maker_fee_bps": 8.0,
        "default_taker_fee_bps": 10.0,
    },
    "binance": {
        "default_account_type": "spot",
        "required_credentials": ("API_KEY", "SECRET"),
        "default_maker_fee_bps": 10.0,
        "default_taker_fee_bps": 10.0,
    },
    "bybit": {
        "default_account_type": "spot",
        "required_credentials": ("API_KEY", "SECRET"),
        "default_maker_fee_bps": 10.0,
        "default_taker_fee_bps": 10.0,
    },
    "kraken": {
        "default_account_type": "spot",
        "required_credentials": ("API_KEY", "SECRET"),
        "default_maker_fee_bps": 16.0,
        "default_taker_fee_bps": 26.0,
    },
}


class VenueExecutionClient:
    """Venue-aware backend execution adapter with BitMart as the default venue."""

    def __init__(self, exchange_id: str = "bitmart") -> None:
        self.exchange_id = exchange_id.strip().lower() or "bitmart"
        self._settings = _VENUE_DEFAULTS.get(self.exchange_id, {})
        self._env_prefix = self.exchange_id.upper().replace("-", "_")
        self.provider = self._build_provider_profile()
        self.account_type = os.getenv(
            f"{self._env_prefix}_ACCOUNT_TYPE",
            self._settings.get("default_account_type", "spot"),
        ).strip() or self._settings.get("default_account_type", "spot")
        self._api_key = os.getenv(f"{self._env_prefix}_API_KEY", "").strip()
        self._secret = os.getenv(f"{self._env_prefix}_SECRET", "").strip()
        self._memo = os.getenv(f"{self._env_prefix}_MEMO", "").strip()
        self._password = os.getenv(f"{self._env_prefix}_PASSWORD", "").strip()
        self._exchange: Any | None = None
        self._public_exchange: Any | None = None
        self._markets_loaded = False
        self._public_markets_loaded = False

    def _build_provider_profile(self) -> ProviderProfile:
        profile_key = self._settings.get("provider_profile")
        if profile_key and profile_key in PROVIDER_PROFILES:
            return PROVIDER_PROFILES[profile_key]
        return ProviderProfile(
            name=self._env_prefix,
            category="execution",
            purpose=f"Execution, balances, and order/trade history via CCXT for {self.exchange_id}.",
            auth_method="API key and secret",
            env_var=f"{self._env_prefix}_API_KEY",
            internal_tools=list(_EXECUTION_TOOLS),
            benefiting_agents=["orchestrator_trader", "portfolio_monitor", "risk_manager"],
        )

    @property
    def required_credentials(self) -> tuple[str, ...]:
        return tuple(self._settings.get("required_credentials", ("API_KEY", "SECRET")))

    @property
    def credential_env_names(self) -> list[str]:
        return [f"{self._env_prefix}_{suffix}" for suffix in self.required_credentials]

    @property
    def configured(self) -> bool:
        return all(bool(os.getenv(name, "").strip()) for name in self.credential_env_names)

    @property
    def rate_limit_enabled(self) -> bool:
        return True

    def require_credentials(self) -> None:
        if self.configured:
            return
        missing = [name for name in self.credential_env_names if not os.getenv(name, "").strip()]
        raise MissingCredentialError(
            f"{self.provider.name} is not configured. Set the following backend env vars: {', '.join(missing)}"
        )

    def _import_ccxt(self) -> Any:
        try:
            import ccxt  # type: ignore
        except ImportError as exc:
            raise IntegrationError("CCXT is not installed. Add the 'ccxt' dependency to enable exchange execution.") from exc
        return ccxt

    def _check_paper_mode_url(self) -> None:
        if not is_paper_mode():
            blockers = live_trading_blockers()
            if blockers:
                raise IntegrationError(
                    "Live trading unlock is incomplete: " + " ".join(blockers)
                )
            return
        live_urls: tuple[str, ...] = tuple(self._settings.get("live_urls", ()))
        override_url = os.getenv(f"{self._env_prefix}_BASE_URL", "").strip().rstrip("/")
        if override_url and live_urls:
            for live_url in live_urls:
                if override_url.startswith(live_url):
                    raise IntegrationError(
                        f"HERMES_PAPER_MODE is active but {self._env_prefix}_BASE_URL points to a live endpoint: {override_url}. "
                        "Unset HERMES_PAPER_MODE or switch to a sandbox URL to proceed."
                    )
        raise IntegrationError(
            f"Paper trading mode is active. Real order placement on {self.provider.name} is disabled. "
            f"Current mode is {current_trading_mode()!r}. "
            "Set HERMES_TRADING_MODE=live and complete the live trading unlock env vars to enable live trading."
        )

    def _build_exchange(self, *, authenticated: bool) -> Any:
        ccxt = self._import_ccxt()
        try:
            exchange_cls = getattr(ccxt, self.exchange_id)
        except AttributeError as exc:
            raise IntegrationError(f"CCXT does not support exchange '{self.exchange_id}'.") from exc

        config: dict[str, Any] = {
            "enableRateLimit": True,
            "options": {"defaultType": self.account_type},
        }
        if authenticated:
            self.require_credentials()
            config.update({"apiKey": self._api_key, "secret": self._secret})
            if self._memo:
                config["memo"] = self._memo
            if self._password or self._memo:
                config["password"] = self._password or self._memo
            self._check_paper_mode_url()

        override_url = os.getenv(f"{self._env_prefix}_BASE_URL", "").strip()
        if override_url:
            config["urls"] = {"api": override_url.rstrip("/")}

        try:
            return exchange_cls(config)
        except Exception as exc:  # pragma: no cover
            raise IntegrationError(f"Failed to initialize the {self.provider.name} execution client.") from exc

    def _get_exchange(self) -> Any:
        if self._exchange is None:
            self._exchange = self._build_exchange(authenticated=True)
        return self._exchange

    def _get_public_exchange(self) -> Any:
        if self._public_exchange is None:
            self._public_exchange = self._build_exchange(authenticated=False)
        return self._public_exchange

    def _ensure_markets_loaded(self, *, public: bool = False) -> None:
        if public:
            if self._public_markets_loaded:
                return
            exchange = self._get_public_exchange()
            self._call_exchange("load_markets", exchange.load_markets)
            self._public_markets_loaded = True
            return
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
            logger.warning("%s %s failed: %s", self.provider.name, operation, exc.__class__.__name__)
            raise IntegrationError(f"{self.provider.name} {operation} failed.") from exc

    def estimate_fee_bps(self, symbol: str | None = None, *, order_type: str = "market") -> float:
        fee_side = "MAKER" if order_type in {"limit", "stop_limit"} else "TAKER"
        env_value = os.getenv(f"{self._env_prefix}_{fee_side}_FEE_BPS", "").strip()
        if env_value:
            try:
                return float(env_value)
            except ValueError:
                logger.debug("Ignoring invalid %s_%s_FEE_BPS value: %s", self._env_prefix, fee_side, env_value)
        try:
            self._ensure_markets_loaded(public=True)
            exchange = self._get_public_exchange()
            market = (exchange.markets or {}).get(symbol or "") if symbol else None
            fee_value = None if market is None else market.get("maker" if fee_side == "MAKER" else "taker")
            if fee_value is not None:
                fee_float = float(fee_value)
                return fee_float * 10000 if fee_float <= 1 else fee_float
        except Exception:
            logger.debug("Falling back to default %s fee bps for %s", fee_side.lower(), self.provider.name)
        return float(self._settings.get(f"default_{fee_side.lower()}_fee_bps", 10.0))

    def get_public_order_book(self, *, symbol: str, limit: int = 10) -> dict[str, Any]:
        self._ensure_markets_loaded(public=True)
        exchange = self._get_public_exchange()
        return self._call_exchange("fetch_order_book", exchange.fetch_order_book, symbol, limit)

    def get_routing_quote(
        self,
        *,
        symbol: str,
        side: str,
        amount: float,
        order_type: str,
        price: float | None = None,
        depth_levels: int = 5,
    ) -> dict[str, Any]:
        snapshot = self.get_public_order_book(symbol=symbol, limit=max(depth_levels, 5))
        bids = snapshot.get("bids") or []
        asks = snapshot.get("asks") or []
        best_bid = float_or_none(bids[0][0]) if bids else None
        best_ask = float_or_none(asks[0][0]) if asks else None
        mid = None
        if best_bid and best_ask:
            mid = (best_bid + best_ask) / 2
        elif best_bid:
            mid = best_bid
        elif best_ask:
            mid = best_ask

        spread_bps = None
        if best_bid and best_ask and mid:
            spread_bps = ((best_ask - best_bid) / mid) * 10000

        levels = asks if side.lower() == "buy" else bids
        available_notional_usd = 0.0
        for level in levels[:depth_levels]:
            if len(level) < 2:
                continue
            level_price = float_or_none(level[0]) or 0.0
            level_amount = float_or_none(level[1]) or 0.0
            available_notional_usd += level_price * level_amount

        reference_price = price or mid
        target_notional_usd = (reference_price * amount) if reference_price else None
        liquidity_ratio = None
        if target_notional_usd and target_notional_usd > 0:
            liquidity_ratio = min(available_notional_usd / target_notional_usd, 1.0)
        liquidity_penalty_bps = 25.0 if liquidity_ratio is None else (1.0 - liquidity_ratio) * 50.0
        fee_bps = self.estimate_fee_bps(symbol, order_type=order_type)
        score = fee_bps + (spread_bps or 0.0) + liquidity_penalty_bps

        return {
            "venue": self.exchange_id,
            "provider": self.provider.name,
            "fee_bps": round(fee_bps, 4),
            "spread_bps": None if spread_bps is None else round(spread_bps, 4),
            "available_notional_usd": round(available_notional_usd, 4),
            "target_notional_usd": None if target_notional_usd is None else round(target_notional_usd, 4),
            "liquidity_ratio": None if liquidity_ratio is None else round(liquidity_ratio, 4),
            "score": round(score, 4),
            "best_bid": best_bid,
            "best_ask": best_ask,
        }

    def _normalize_order(self, order: dict[str, Any]) -> ExecutionOrder:
        return normalize_ccxt_order(provider_name=self.provider.name, order=order)

    def _normalize_trade(self, trade: dict[str, Any]) -> ExecutionTrade:
        return normalize_ccxt_trade(provider_name=self.provider.name, trade=trade)

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
                    free=float_or_none(free_map.get(asset)),
                    used=float_or_none(used_map.get(asset)),
                    total=float_or_none(totals),
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
        logger.info("Submitting %s order for %s %s %s", self.provider.name, symbol, side, order_type)
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
        logger.info("%s order submitted successfully for %s as %s", self.provider.name, normalized.symbol, normalized.order_id)
        return normalized

    def cancel_order(self, *, order_id: str, symbol: str | None = None) -> ExecutionOrder:
        exchange = self._get_exchange()
        logger.info("Cancelling %s order %s", self.provider.name, order_id)
        order = self._call_exchange("cancel_order", exchange.cancel_order, order_id, symbol)
        normalized = self._normalize_order(order)
        logger.info("%s order %s cancellation acknowledged", self.provider.name, normalized.order_id)
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
        return [self._normalize_trade(trade) for trade in trades]

    def get_execution_status(self, *, order_id: str | None = None, symbol: str | None = None) -> ExecutionStatus:
        if not self.configured:
            return ExecutionStatus(
                exchange=self.provider.name,
                configured=False,
                connected=False,
                rate_limit_enabled=self.rate_limit_enabled,
                account_type=self.account_type,
                detail=f"{self.provider.name} credentials are not configured.",
                checked_at=datetime.now(timezone.utc).isoformat(),
            )
        exchange = self._get_exchange()
        order: ExecutionOrder | None = None
        detail = f"{self.provider.name} execution client configured."
        if order_id:
            raw_order = self._call_exchange("fetch_order", exchange.fetch_order, order_id, symbol)
            order = self._normalize_order(raw_order)
            detail = f"Fetched {self.provider.name} status for order {order.order_id}."
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
