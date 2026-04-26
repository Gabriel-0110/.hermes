"""Venue-aware CCXT execution client for multi-venue trading workflows."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
import hashlib
import hmac
import json
import time
from typing import Any, Literal

import requests
from pydantic import BaseModel, Field

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
from backend.integrations.execution.readiness import classify_live_execution_readiness, execution_support_matrix
from backend.integrations.execution.private_read import ClassifiedPrivateReadError, classify_private_read_exception
from backend.observability.service import get_observability_service
from backend.integrations.provider_profiles import PROVIDER_PROFILES
from backend.models import ExchangeBalances, ExecutionBalance, ExecutionOrder, ExecutionStatus, ExecutionTrade

logger = logging.getLogger(__name__)

_BITMART_DIRECT_FUTURES_BASE_URL = "https://api-cloud-v2.bitmart.com"
_BITMART_DIRECT_FUTURES_ORDER_PATH = "/contract/private/submit-order"
_BITMART_DIRECT_USER_AGENT = "bitmart-skills/futures/v2026.3.23"


WriteCapabilityStatus = Literal[
    "dry_run_prepared",
    "write_verified",
    "cloudflare_waf",
    "rate_limited_write_access",
    "auth_failed",
    "unknown_write_failure",
]


class FuturesWriteCapabilityCheck(BaseModel):
    exchange: str
    venue: str
    account_type: str
    status: WriteCapabilityStatus
    verified: bool = False
    live_risking_order: bool = False
    request_path: str | None = None
    detail: str | None = None
    prepared_request: dict[str, Any] | None = None
    checked_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


def _is_truthy_env(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


_SENSITIVE_TELEMETRY_KEYS = {
    "authorization",
    "api_key",
    "apikey",
    "secret",
    "password",
    "private_key",
    "x-bm-key",
    "x-bm-sign",
    "signature",
    "headers",
}


def _sanitize_execution_telemetry(value: Any) -> Any:
    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        for key, item in value.items():
            key_str = str(key)
            if key_str.lower() in _SENSITIVE_TELEMETRY_KEYS or any(token in key_str.lower() for token in ("secret", "signature")):
                continue
            sanitized[key_str] = _sanitize_execution_telemetry(item)
        return sanitized
    if isinstance(value, list):
        return [_sanitize_execution_telemetry(item) for item in value[:50]]
    if isinstance(value, tuple):
        return [_sanitize_execution_telemetry(item) for item in value[:50]]
    if isinstance(value, str):
        return value[:300]
    return value


def _classify_write_failure(value: Any) -> str:
    parts = [str(value or "")]
    cause = getattr(value, "__cause__", None)
    context = getattr(value, "__context__", None)
    if cause is not None:
        parts.append(str(cause))
    if context is not None:
        parts.append(str(context))
    text = " ".join(parts).lower()
    if "cloudflare" in text or "waf" in text or "error code: 1010" in text or "http 403" in text:
        return "cloudflare_waf"
    if "429" in text or "rate limit" in text or "too many request" in text:
        return "rate_limited_write_access"
    if any(term in text for term in ("auth", "signature", "sign", "unauthorized", "permission", "api key", "memo")):
        return "auth_failed"
    return "unknown_write_failure"

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
        "default_account_type": "swap",
        "required_credentials": ("API_KEY", "SECRET", "MEMO", "UID"),
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


def notify_bracket_attachment_failed(*, symbol: str, order_id: str, failures: dict[str, Any]) -> None:
    logger.warning(
        "Bracket attachment failed for symbol=%s order_id=%s failures=%s",
        symbol, order_id, list(failures.keys()),
    )
    try:
        get_observability_service().record_execution_event(
            event_type="bracket_attachment_failed",
            status="failed",
            symbol=symbol,
            payload={"order_id": order_id, "failures": failures},
        )
    except Exception as exc:
        logger.debug("Failed to record bracket_attachment_failed event: %s", exc)


def _classify_bracket_failure(status_code: int, message: str) -> str:
    lowered = message.lower()
    auth_terms = ("auth", "signature", "sign", "key", "permission", "unauthorized", "memo")
    if status_code in {401, 403} or any(term in lowered for term in auth_terms):
        return "auth_failed"
    if status_code == 429 or "rate limit" in lowered:
        return "network_or_api_failure"
    if status_code >= 500 or "connection" in lowered or "timeout" in lowered:
        return "network_or_api_failure"
    return "exchange_validation_failed"


def _safe_child_client_order_id(parent_id: str | None, label: str) -> str | None:
    if not parent_id:
        return None
    suffix = label[:2]
    max_len = 32
    base = parent_id[: max_len - len(suffix)]
    return (base + suffix)[:max_len]


class VenueExecutionClient:
    """Venue-aware backend execution adapter with BitMart as the default venue."""

    def __init__(self, exchange_id: str = "bitmart", *, account_type: str | None = None) -> None:
        self.exchange_id = exchange_id.strip().lower() or "bitmart"
        self._settings = _VENUE_DEFAULTS.get(self.exchange_id, {})
        self._env_prefix = self.exchange_id.upper().replace("-", "_")
        self.provider = self._build_provider_profile()
        configured_account_type = account_type or os.getenv(
            f"{self._env_prefix}_ACCOUNT_TYPE",
            self._settings.get("default_account_type", "spot"),
        )
        self.account_type = configured_account_type.strip() or self._settings.get("default_account_type", "spot")
        self._api_key = os.getenv(f"{self._env_prefix}_API_KEY", "").strip()
        self._secret = os.getenv(f"{self._env_prefix}_SECRET", "").strip()
        self._memo = os.getenv(f"{self._env_prefix}_MEMO", "").strip()
        self._uid = os.getenv(f"{self._env_prefix}_UID", "").strip()
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
            if self._uid:
                config["uid"] = self._uid
            if self._password or self._memo:
                config["password"] = self._password or self._memo
            self._check_paper_mode_url()

        override_url = os.getenv(f"{self._env_prefix}_BASE_URL", "").strip()
        if override_url:
            base = override_url.rstrip("/")
            config["urls"] = {"api": {"spot": base, "swap": base}}

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
        except ClassifiedPrivateReadError:
            raise
        except Exception as exc:
            logger.warning("%s %s failed: %s", self.provider.name, operation, exc.__class__.__name__)
            if operation in {"fetch_balance", "fetch_open_orders", "fetch_orders", "fetch_my_trades", "fetch_order"}:
                classification = classify_private_read_exception(exc)
                raise ClassifiedPrivateReadError(
                    f"{self.provider.name} private read {operation} failed [{classification}]: {exc}",
                    classification=classification,
                    operation=operation,
                ) from exc
            raise IntegrationError(f"{self.provider.name} {operation} failed.") from exc

    def _record_execution_telemetry(
        self,
        *,
        event_type: str,
        status: str,
        symbol: str | None = None,
        payload: dict[str, Any] | None = None,
        error_message: str | None = None,
    ) -> None:
        sanitized_payload = _sanitize_execution_telemetry(payload or {})
        sanitized_payload.setdefault("venue", self.exchange_id)
        sanitized_payload.setdefault("exchange", self.provider.name)
        sanitized_payload.setdefault("account_type", self.account_type)
        try:
            get_observability_service().record_execution_event(
                status=status,
                event_type=event_type,
                tool_name="execution_client",
                symbol=symbol,
                payload=sanitized_payload,
                error_message=error_message,
                metadata={
                    "venue": self.exchange_id,
                    "exchange": self.provider.name,
                    "account_type": self.account_type,
                    "payload": sanitized_payload,
                },
            )
        except Exception as exc:  # pragma: no cover - telemetry must not break execution
            logger.debug("Failed to record execution telemetry event %s: %s", event_type, exc)

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
        stop_loss_price: float | None = None,
        take_profit_price: float | None = None,
        leverage: float | None = None,
        margin_mode: str | None = None,
        client_order_id: str | None = None,
        time_in_force: str | None = None,
        post_only: bool = False,
        reduce_only: bool = False,
        position_side: str | None = None,
    ) -> ExecutionOrder:
        request_payload = {
            "symbol": symbol,
            "side": side,
            "order_type": order_type,
            "amount": amount,
            "price": price,
            "stop_loss_price": stop_loss_price,
            "take_profit_price": take_profit_price,
            "leverage": leverage,
            "margin_mode": margin_mode,
            "client_order_id": client_order_id,
            "time_in_force": time_in_force,
            "post_only": post_only,
            "reduce_only": reduce_only,
            "position_side": position_side,
        }
        self._record_execution_telemetry(
            event_type="order_submit_requested",
            status="requested",
            symbol=symbol,
            payload=request_payload,
        )
        try:
            order = self._place_order_without_telemetry(
                symbol=symbol,
                side=side,
                order_type=order_type,
                amount=amount,
                price=price,
                stop_loss_price=stop_loss_price,
                take_profit_price=take_profit_price,
                leverage=leverage,
                margin_mode=margin_mode,
                client_order_id=client_order_id,
                time_in_force=time_in_force,
                post_only=post_only,
                reduce_only=reduce_only,
                position_side=position_side,
            )
        except Exception as exc:
            classification = _classify_write_failure(exc)
            self._record_execution_telemetry(
                event_type="order_submit_rejected",
                status=classification,
                symbol=symbol,
                payload={**request_payload, "error_classification": classification},
                error_message=str(exc),
            )
            raise
        self._record_execution_telemetry(
            event_type="order_submit_accepted",
            status="accepted",
            symbol=order.symbol,
            payload={
                "symbol": order.symbol,
                "order_id": order.order_id,
                "status": order.status,
                "side": order.side,
                "order_type": order.order_type,
                "amount": order.amount,
                "reduce_only": order.reduce_only,
            },
        )
        return order

    def _should_use_bitmart_direct_swap_submission(self, order_type: str) -> bool:
        normalized_type = (order_type or "").strip().lower()
        return (
            self.exchange_id == "bitmart"
            and self.account_type in {"contract", "futures", "swap"}
            and normalized_type in {"market", "limit"}
        )

    def _place_order_without_telemetry(
        self,
        *,
        symbol: str,
        side: str,
        order_type: str,
        amount: float,
        price: float | None = None,
        stop_loss_price: float | None = None,
        take_profit_price: float | None = None,
        leverage: float | None = None,
        margin_mode: str | None = None,
        client_order_id: str | None = None,
        time_in_force: str | None = None,
        post_only: bool = False,
        reduce_only: bool = False,
        position_side: str | None = None,
    ) -> ExecutionOrder:
        if self._should_use_bitmart_direct_swap_submission(order_type):
            return self._submit_bitmart_swap_order(
                symbol=symbol,
                side=side,
                order_type=order_type,
                amount=amount,
                price=price,
                stop_loss_price=stop_loss_price,
                take_profit_price=take_profit_price,
                leverage=leverage,
                margin_mode=margin_mode,
                client_order_id=client_order_id,
                time_in_force=time_in_force,
                post_only=post_only,
                reduce_only=reduce_only,
                position_side=position_side,
            )
        self._ensure_markets_loaded()
        exchange = self._get_exchange()
        params: dict[str, Any] = {}
        if client_order_id:
            params["clientOrderId"] = client_order_id
        if time_in_force:
            params["timeInForce"] = time_in_force
        if post_only:
            params["postOnly"] = True
        if reduce_only:
            params["reduceOnly"] = True
        if position_side:
            params["positionSide"] = position_side.upper()
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

    def _bitmart_swap_side_code(self, *, side: str, reduce_only: bool, position_side: str | None) -> int:
        normalized_side = (side or "").strip().lower()
        normalized_position_side = (position_side or "").strip().lower() or None
        if normalized_side not in {"buy", "sell"}:
            raise IntegrationError(f"Unsupported BitMart order side: {side!r}")
        if normalized_position_side == "long" and normalized_side != "sell" and reduce_only:
            raise IntegrationError("Closing a long BitMart futures position must use side='sell'.")
        if normalized_position_side == "short" and normalized_side != "buy" and reduce_only:
            raise IntegrationError("Closing a short BitMart futures position must use side='buy'.")
        if normalized_side == "buy":
            return 2 if reduce_only else 1
        return 3 if reduce_only else 4

    def _bitmart_futures_order_mode(self, *, order_type: str, time_in_force: str | None, post_only: bool) -> int | None:
        if post_only:
            if order_type != "limit":
                raise IntegrationError("BitMart post-only is only supported for limit orders.")
            return 4
        if time_in_force == "GTC":
            return 1
        if time_in_force == "FOK":
            return 2
        if time_in_force == "IOC":
            return 3
        return None

    def _build_bitmart_signed_futures_request(self, body: dict[str, Any]) -> dict[str, Any]:
        body_json = json.dumps(body, separators=(",", ":"))
        timestamp = str(int(time.time() * 1000))
        signature_payload = f"{timestamp}#{self._memo}#{body_json}"
        signature = hmac.new(self._secret.encode(), signature_payload.encode(), hashlib.sha256).hexdigest()
        base_url = os.getenv(f"{self._env_prefix}_BASE_URL", "").strip().rstrip("/") or _BITMART_DIRECT_FUTURES_BASE_URL
        return {
            "url": f"{base_url}{_BITMART_DIRECT_FUTURES_ORDER_PATH}",
            "body_json": body_json,
            "headers": {
                "Content-Type": "application/json",
                "User-Agent": _BITMART_DIRECT_USER_AGENT,
                "X-BM-KEY": self._api_key,
                "X-BM-SIGN": signature,
                "X-BM-TIMESTAMP": timestamp,
            },
        }

    def _classify_bitmart_write_response(
        self,
        *,
        response: Any,
        prepared_request: dict[str, Any],
    ) -> FuturesWriteCapabilityCheck:
        body_text = str(getattr(response, "text", "") or "")
        status_code = int(getattr(response, "status_code", 0) or 0)
        lowered = body_text.lower()
        if status_code == 403 or "cloudflare" in lowered or "error code: 1010" in lowered:
            return FuturesWriteCapabilityCheck(
                exchange=self.provider.name,
                venue=self.exchange_id,
                account_type=self.account_type,
                status="cloudflare_waf",
                request_path=_BITMART_DIRECT_FUTURES_ORDER_PATH,
                detail=f"Cloudflare/WAF rejection from BitMart futures write probe: HTTP {status_code}.",
                prepared_request=prepared_request,
            )
        if status_code == 429:
            return FuturesWriteCapabilityCheck(
                exchange=self.provider.name,
                venue=self.exchange_id,
                account_type=self.account_type,
                status="rate_limited_write_access",
                request_path=_BITMART_DIRECT_FUTURES_ORDER_PATH,
                detail="BitMart futures write probe was rate limited (HTTP 429).",
                prepared_request=prepared_request,
            )

        payload: dict[str, Any] = {}
        try:
            parsed = response.json()
            payload = parsed if isinstance(parsed, dict) else {}
        except Exception:
            payload = {}

        code = payload.get("code")
        message = str(payload.get("message") or body_text[:300] or "empty response body")
        auth_terms = ("auth", "signature", "sign", "key", "permission", "unauthorized", "memo")
        if status_code in {401, 403} or any(term in message.lower() for term in auth_terms):
            return FuturesWriteCapabilityCheck(
                exchange=self.provider.name,
                venue=self.exchange_id,
                account_type=self.account_type,
                status="auth_failed",
                request_path=_BITMART_DIRECT_FUTURES_ORDER_PATH,
                detail=f"BitMart futures write probe authentication failed: code={code} message={message!r}.",
                prepared_request=prepared_request,
            )

        if 200 <= status_code < 500 and code not in {None, 1000}:
            return FuturesWriteCapabilityCheck(
                exchange=self.provider.name,
                venue=self.exchange_id,
                account_type=self.account_type,
                status="write_verified",
                verified=True,
                request_path=_BITMART_DIRECT_FUTURES_ORDER_PATH,
                detail=(
                    "Signed BitMart futures write endpoint reached exchange business validation "
                    f"without a live-risking order: code={code} message={message!r}."
                ),
                prepared_request=prepared_request,
            )

        return FuturesWriteCapabilityCheck(
            exchange=self.provider.name,
            venue=self.exchange_id,
            account_type=self.account_type,
            status="unknown_write_failure",
            request_path=_BITMART_DIRECT_FUTURES_ORDER_PATH,
            detail=f"BitMart futures write probe returned HTTP {status_code}: {message!r}.",
            prepared_request=prepared_request,
        )

    def check_futures_write_capability(
        self,
        *,
        symbol: str = "BTCUSDT",
        verify_remote: bool = False,
    ) -> FuturesWriteCapabilityCheck:
        """Probe BitMart futures signed-write plumbing without market exposure.

        By default this only prepares a signed submit-order request and returns
        ``dry_run_prepared``. Passing ``verify_remote=True`` sends a deliberately
        invalid zero-size order to verify that the signed write path reaches
        exchange business validation; it should not open a live position.
        """

        if self.exchange_id != "bitmart" or self.account_type not in {"contract", "futures", "swap"}:
            return FuturesWriteCapabilityCheck(
                exchange=self.provider.name,
                venue=self.exchange_id,
                account_type=self.account_type,
                status="unknown_write_failure",
                detail="Futures write capability smoke checks are currently implemented only for BitMart swap/futures accounts.",
            )

        self.require_credentials()
        self._check_paper_mode_url()
        body = {
            "symbol": symbol,
            "type": "market",
            "side": 1,
            "size": 0,
            "open_type": os.getenv(f"{self._env_prefix}_MARGIN_MODE", "cross").strip().lower() or "cross",
        }
        self._record_execution_telemetry(
            event_type="bitmart_futures_write_probe_started",
            status="started",
            symbol=symbol,
            payload={
                "symbol": symbol,
                "verify_remote": verify_remote,
                "request_path": _BITMART_DIRECT_FUTURES_ORDER_PATH,
                "live_risking_order": False,
            },
        )
        signed = self._build_bitmart_signed_futures_request(body)
        safe_headers = dict(signed["headers"])
        if safe_headers.get("X-BM-KEY"):
            safe_headers["X-BM-KEY"] = "***"
        if safe_headers.get("X-BM-SIGN"):
            safe_headers["X-BM-SIGN"] = "***"
        prepared_request = {
            "method": "POST",
            "url": signed["url"],
            "path": _BITMART_DIRECT_FUTURES_ORDER_PATH,
            "headers": safe_headers,
            "body": body,
        }
        if not verify_remote:
            result = FuturesWriteCapabilityCheck(
                exchange=self.provider.name,
                venue=self.exchange_id,
                account_type=self.account_type,
                status="dry_run_prepared",
                request_path=_BITMART_DIRECT_FUTURES_ORDER_PATH,
                detail="Prepared signed BitMart futures write request; remote verification was not run.",
                prepared_request=prepared_request,
            )
            self._record_execution_telemetry(
                event_type="bitmart_futures_write_probe_result",
                status=result.status,
                symbol=symbol,
                payload={
                    "status": result.status,
                    "verified": result.verified,
                    "live_risking_order": result.live_risking_order,
                    "request_path": result.request_path,
                },
            )
            return result

        try:
            response = requests.post(
                signed["url"],
                data=signed["body_json"],
                headers=signed["headers"],
                timeout=30,
            )
        except Exception as exc:
            result = FuturesWriteCapabilityCheck(
                exchange=self.provider.name,
                venue=self.exchange_id,
                account_type=self.account_type,
                status="unknown_write_failure",
                request_path=_BITMART_DIRECT_FUTURES_ORDER_PATH,
                detail=f"BitMart futures write probe failed before a response was received: {exc}",
                prepared_request=prepared_request,
            )
            self._record_execution_telemetry(
                event_type="bitmart_futures_write_probe_result",
                status=result.status,
                symbol=symbol,
                payload={
                    "status": result.status,
                    "verified": result.verified,
                    "live_risking_order": result.live_risking_order,
                    "request_path": result.request_path,
                    "error_classification": result.status,
                },
                error_message=result.detail,
            )
            return result
        result = self._classify_bitmart_write_response(response=response, prepared_request=prepared_request)
        self._record_execution_telemetry(
            event_type="bitmart_futures_write_probe_result",
            status=result.status,
            symbol=symbol,
            payload={
                "status": result.status,
                "verified": result.verified,
                "live_risking_order": result.live_risking_order,
                "request_path": result.request_path,
                "error_classification": None if result.verified else result.status,
            },
            error_message=None if result.verified else result.detail,
        )
        return result

    def _submit_bitmart_swap_order(
        self,
        *,
        symbol: str,
        side: str,
        order_type: str,
        amount: float,
        price: float | None = None,
        stop_loss_price: float | None = None,
        take_profit_price: float | None = None,
        leverage: float | None = None,
        margin_mode: str | None = None,
        client_order_id: str | None = None,
        time_in_force: str | None = None,
        post_only: bool = False,
        reduce_only: bool = False,
        position_side: str | None = None,
    ) -> ExecutionOrder:
        self.require_credentials()
        exchange = self._get_exchange()
        self._ensure_markets_loaded()
        market = exchange.market(symbol)
        market_symbol = market.get("id") or symbol
        order_type_normalized = (order_type or "").strip().lower()
        if order_type_normalized not in {"market", "limit"}:
            raise IntegrationError(f"Unsupported direct BitMart futures order type: {order_type!r}")

        size_precise = exchange.amount_to_precision(symbol, amount)
        size = int(float(size_precise))
        if size <= 0:
            raise IntegrationError(f"BitMart futures order size resolved to {size}; a positive contract size is required.")

        request: dict[str, Any] = {
            "symbol": market_symbol,
            "type": order_type_normalized,
            "side": self._bitmart_swap_side_code(side=side, reduce_only=reduce_only, position_side=position_side),
            "size": size,
        }
        mode = self._bitmart_futures_order_mode(
            order_type=order_type_normalized,
            time_in_force=time_in_force,
            post_only=post_only,
        )
        if mode is not None:
            request["mode"] = mode
        if order_type_normalized == "limit":
            if price is None:
                raise IntegrationError("BitMart futures limit orders require a price.")
            request["price"] = exchange.price_to_precision(symbol, price)
        if client_order_id:
            request["client_order_id"] = client_order_id
        if not reduce_only:
            resolved_margin_mode = (margin_mode or os.getenv(f"{self._env_prefix}_MARGIN_MODE", "cross")).strip().lower() or "cross"
            request["open_type"] = resolved_margin_mode
        if leverage is not None:
            request["leverage"] = str(int(leverage)) if leverage == int(leverage) else str(leverage)
        if take_profit_price is not None:
            request["preset_take_profit_price"] = exchange.price_to_precision(symbol, take_profit_price)
            request["preset_take_profit_price_type"] = 1
        if stop_loss_price is not None:
            request["preset_stop_loss_price"] = exchange.price_to_precision(symbol, stop_loss_price)
            request["preset_stop_loss_price_type"] = 1

        signed = self._build_bitmart_signed_futures_request(request)
        logger.info("Submitting BITMART direct futures order for %s %s %s", symbol, side, order_type_normalized)
        try:
            response = requests.post(signed["url"], data=signed["body_json"], headers=signed["headers"], timeout=30)
        except Exception as exc:
            raise IntegrationError(f"BITMART submit-order request failed before a response was received: {exc}") from exc

        if response.status_code >= 400:
            body_preview = response.text[:300]
            raise IntegrationError(
                f"BITMART submit-order HTTP {response.status_code}: {body_preview or 'empty response body'}"
            )

        try:
            payload = response.json()
        except Exception as exc:
            raise IntegrationError(
                f"BITMART submit-order returned non-JSON content: {response.text[:300]}"
            ) from exc

        if payload.get("code") != 1000:
            raise IntegrationError(
                f"BITMART submit-order rejected the request: code={payload.get('code')} "
                f"message={payload.get('message')!r} trace={payload.get('trace')!r}"
            )

        data = payload.get("data") or {}
        submitted_at = datetime.now(timezone.utc).isoformat()
        order_id = str(data.get("order_id") or data.get("orderId") or "")

        order_metadata: dict[str, Any] = {}
        if leverage is not None:
            order_metadata["leverage"] = str(int(leverage)) if leverage == int(leverage) else str(leverage)

        bracket_orders: dict[str, dict[str, Any]] = {}
        if take_profit_price is not None or stop_loss_price is not None:
            bracket_targets = []
            if take_profit_price is not None:
                bracket_targets.append(("take_profit", take_profit_price))
            if stop_loss_price is not None:
                bracket_targets.append(("stop_loss", stop_loss_price))

            for label, trigger_price in bracket_targets:
                bracket_orders[label] = self._submit_bitmart_tp_sl_follow_up(
                    symbol=symbol,
                    market_symbol=market_symbol,
                    exchange=exchange,
                    label=label,
                    trigger_price=trigger_price,
                )

            all_ok = all(b["status"] == "submitted" for b in bracket_orders.values())
            order_metadata["bitmart_bracket_status"] = "submitted" if all_ok else "partial_failure"
            order_metadata["bitmart_bracket_orders"] = bracket_orders

            failures = {k: v for k, v in bracket_orders.items() if v["status"] == "failed"}
            if failures:
                notify_bracket_attachment_failed(
                    symbol=symbol,
                    order_id=order_id,
                    failures=failures,
                )

        return ExecutionOrder(
            order_id=order_id,
            exchange=self.provider.name,
            symbol=symbol,
            side=side,
            order_type=order_type_normalized,
            status="submitted",
            client_order_id=client_order_id,
            price=price if price is not None else float_or_none(data.get("price")),
            average_price=None,
            amount=float(size),
            filled=0.0,
            remaining=float(size),
            cost=None,
            time_in_force=time_in_force,
            post_only=post_only,
            reduce_only=reduce_only,
            created_at=submitted_at,
            updated_at=submitted_at,
            metadata=order_metadata or None,
        )

    def _submit_bitmart_tp_sl_follow_up(
        self,
        *,
        symbol: str,
        market_symbol: str,
        exchange: Any,
        label: str,
        trigger_price: float,
    ) -> dict[str, Any]:
        tp_sl_type = "take_profit" if label == "take_profit" else "stop_loss"
        body: dict[str, Any] = {
            "symbol": market_symbol,
            "type": tp_sl_type,
            "side": 2,
            "size": 0,
            "trigger_price": exchange.price_to_precision(symbol, trigger_price),
            "executive_price": exchange.price_to_precision(symbol, trigger_price),
            "price_type": 1,
            "plan_category": 2,
            "category": "market",
        }
        base_url = os.getenv(f"{self._env_prefix}_BASE_URL", "").strip().rstrip("/") or _BITMART_DIRECT_FUTURES_BASE_URL
        tp_sl_path = "/contract/private/submit-tp-sl-order"
        try:
            signed = self._build_bitmart_signed_futures_request(body)
            signed_url = f"{base_url}{tp_sl_path}"
            response = requests.post(signed_url, data=signed["body_json"], headers=signed["headers"], timeout=30)
        except Exception as exc:
            return {
                "status": "failed",
                "trigger_price": exchange.price_to_precision(symbol, trigger_price),
                "failure_category": "network_or_api_failure",
                "error": str(exc),
            }

        try:
            resp_data = response.json()
        except Exception:
            resp_data = {}

        if response.status_code >= 400 or resp_data.get("code") != 1000:
            message = str(resp_data.get("message") or response.text[:300])
            return {
                "status": "failed",
                "trigger_price": exchange.price_to_precision(symbol, trigger_price),
                "failure_category": _classify_bracket_failure(response.status_code, message),
                "error": message,
            }

        return {
            "status": "submitted",
            "trigger_price": exchange.price_to_precision(symbol, trigger_price),
            "order_id": str((resp_data.get("data") or {}).get("order_id", "")),
        }

    def preview_order_request(
        self,
        *,
        symbol: str,
        side: str,
        order_type: str,
        amount: float,
        price: float | None = None,
        stop_loss_price: float | None = None,
        take_profit_price: float | None = None,
        leverage: float | None = None,
        margin_mode: str | None = None,
        client_order_id: str | None = None,
        time_in_force: str | None = None,
        post_only: bool = False,
        reduce_only: bool = False,
        position_side: str | None = None,
    ) -> dict[str, Any]:
        exchange = self._get_public_exchange()
        market = exchange.market(symbol)
        market_symbol = market.get("id") or symbol
        order_type_normalized = (order_type or "").strip().lower()
        size_precise = exchange.amount_to_precision(symbol, amount)
        size = int(float(size_precise))

        entry_body: dict[str, Any] = {
            "symbol": market_symbol,
            "type": order_type_normalized,
            "side": self._bitmart_swap_side_code(side=side, reduce_only=reduce_only, position_side=position_side),
            "size": size,
        }
        if order_type_normalized == "limit" and price is not None:
            entry_body["price"] = exchange.price_to_precision(symbol, price)
        if client_order_id:
            entry_body["client_order_id"] = client_order_id
        if not reduce_only:
            resolved_margin_mode = (margin_mode or "cross").strip().lower()
            entry_body["open_type"] = resolved_margin_mode
        if leverage is not None:
            entry_body["leverage"] = str(int(leverage)) if leverage == int(leverage) else str(leverage)
        if take_profit_price is not None:
            entry_body["preset_take_profit_price"] = exchange.price_to_precision(symbol, take_profit_price)
            entry_body["preset_take_profit_price_type"] = 1
        if stop_loss_price is not None:
            entry_body["preset_stop_loss_price"] = exchange.price_to_precision(symbol, stop_loss_price)
            entry_body["preset_stop_loss_price_type"] = 1

        signed = self._build_bitmart_signed_futures_request(entry_body)
        safe_headers = dict(signed["headers"])
        safe_headers["X-BM-KEY"] = "***"
        safe_headers["X-BM-SIGN"] = "***"

        follow_ups: list[dict[str, Any]] = []
        for label, trigger_price in [("take_profit", take_profit_price), ("stop_loss", stop_loss_price)]:
            if trigger_price is None:
                continue
            child_id = _safe_child_client_order_id(client_order_id, label)
            tp_sl_body: dict[str, Any] = {
                "symbol": market_symbol,
                "type": label,
                "side": 2,
                "size": 0,
                "trigger_price": exchange.price_to_precision(symbol, trigger_price),
                "executive_price": exchange.price_to_precision(symbol, trigger_price),
                "price_type": 1,
                "plan_category": 2,
                "category": "market",
            }
            if child_id:
                tp_sl_body["client_order_id"] = child_id
            follow_ups.append({
                "label": label,
                "path": "/contract/private/submit-tp-sl-order",
                "body": tp_sl_body,
            })

        return {
            "mode": "dry_run",
            "entry": {
                "path": _BITMART_DIRECT_FUTURES_ORDER_PATH,
                "headers": safe_headers,
                "body": entry_body,
            },
            "follow_up_count": len(follow_ups),
            "follow_ups": follow_ups,
        }

    def modify_bracket_order(
        self,
        *,
        order_id: str,
        symbol: str,
        new_trigger_price: float,
        price_type: int = 1,
    ) -> dict[str, Any]:
        """Modify an existing TP/SL bracket order's trigger price.

        Uses BitMart's /contract/private/modify-tp-sl-order endpoint.
        Fails closed: returns failure dict on any error without cancelling
        the existing bracket.
        """
        self.require_credentials()
        exchange = self._get_exchange()
        self._ensure_markets_loaded()

        body: dict[str, Any] = {
            "order_id": order_id,
            "trigger_price": exchange.price_to_precision(symbol, new_trigger_price),
            "executive_price": exchange.price_to_precision(symbol, new_trigger_price),
            "price_type": price_type,
        }

        base_url = os.getenv(f"{self._env_prefix}_BASE_URL", "").strip().rstrip("/") or _BITMART_DIRECT_FUTURES_BASE_URL
        modify_path = "/contract/private/modify-tp-sl-order"

        self._record_execution_telemetry(
            event_type="bracket_modify_requested",
            status="requested",
            symbol=symbol,
            payload={"order_id": order_id, "new_trigger_price": new_trigger_price},
        )

        try:
            signed = self._build_bitmart_signed_futures_request(body)
            url = f"{base_url}{modify_path}"
            response = requests.post(url, data=signed["body_json"], headers=signed["headers"], timeout=30)
        except Exception as exc:
            result = {
                "status": "failed",
                "order_id": order_id,
                "failure_category": "network_or_api_failure",
                "error": str(exc),
            }
            self._record_execution_telemetry(
                event_type="bracket_modify_failed",
                status="failed",
                symbol=symbol,
                payload=result,
                error_message=str(exc),
            )
            return result

        try:
            resp_data = response.json()
        except Exception:
            resp_data = {}

        if response.status_code >= 400 or resp_data.get("code") != 1000:
            message = str(resp_data.get("message") or response.text[:300])
            result = {
                "status": "failed",
                "order_id": order_id,
                "failure_category": _classify_bracket_failure(response.status_code, message),
                "error": message,
            }
            self._record_execution_telemetry(
                event_type="bracket_modify_failed",
                status=result["failure_category"],
                symbol=symbol,
                payload=result,
                error_message=message,
            )
            return result

        result = {
            "status": "modified",
            "order_id": order_id,
            "new_trigger_price": exchange.price_to_precision(symbol, new_trigger_price),
        }
        self._record_execution_telemetry(
            event_type="bracket_modify_succeeded",
            status="modified",
            symbol=symbol,
            payload=result,
        )
        return result

    def cancel_order(self, *, order_id: str, symbol: str | None = None) -> ExecutionOrder:
        exchange = self._get_exchange()
        self._record_execution_telemetry(
            event_type="order_cancel_requested",
            status="requested",
            symbol=symbol,
            payload={"order_id": order_id, "symbol": symbol},
        )
        logger.info("Cancelling %s order %s", self.provider.name, order_id)
        try:
            order = self._call_exchange("cancel_order", exchange.cancel_order, order_id, symbol)
            normalized = self._normalize_order(order)
        except Exception as exc:
            classification = _classify_write_failure(exc)
            self._record_execution_telemetry(
                event_type="order_cancel_rejected",
                status=classification,
                symbol=symbol,
                payload={
                    "order_id": order_id,
                    "symbol": symbol,
                    "error_classification": classification,
                },
                error_message=str(exc),
            )
            raise
        self._record_execution_telemetry(
            event_type="order_cancel_accepted",
            status="accepted",
            symbol=normalized.symbol,
            payload={
                "order_id": normalized.order_id,
                "symbol": normalized.symbol,
                "status": normalized.status,
            },
        )
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
        signed_write_probe = None
        if self.exchange_id == "bitmart" and self.account_type in {"contract", "futures", "swap"}:
            def signed_write_probe() -> FuturesWriteCapabilityCheck:
                return self.check_futures_write_capability(
                    symbol=symbol or os.getenv("BITMART_WRITE_PROBE_SYMBOL", "BTCUSDT"),
                    verify_remote=_is_truthy_env(os.getenv("HERMES_BITMART_VERIFY_SIGNED_WRITES")),
                )
        readiness = classify_live_execution_readiness(
            self,
            private_read_probe=lambda: self.get_exchange_balances(),
            signed_write_probe=signed_write_probe,
        )
        if not self.configured:
            return ExecutionStatus(
                exchange=self.provider.name,
                configured=False,
                connected=False,
                rate_limit_enabled=self.rate_limit_enabled,
                account_type=self.account_type,
                readiness_status=readiness.status,
                readiness=readiness.model_dump(mode="json"),
                support_matrix=execution_support_matrix(readiness),
                detail=f"{self.provider.name} credentials are not configured.",
                checked_at=datetime.now(timezone.utc).isoformat(),
            )
        order: ExecutionOrder | None = None
        detail = f"{self.provider.name} execution readiness: {readiness.status}."
        if order_id:
            exchange = self._get_exchange()
            raw_order = self._call_exchange("fetch_order", exchange.fetch_order, order_id, symbol)
            order = self._normalize_order(raw_order)
            detail = f"Fetched {self.provider.name} status for order {order.order_id}."
        return ExecutionStatus(
            exchange=self.provider.name,
            configured=True,
            connected=readiness.private_reads_working,
            rate_limit_enabled=self.rate_limit_enabled,
            account_type=self.account_type,
            readiness_status=readiness.status,
            readiness=readiness.model_dump(mode="json"),
            support_matrix=execution_support_matrix(readiness),
            detail=detail,
            order=order,
            checked_at=datetime.now(timezone.utc).isoformat(),
        )
