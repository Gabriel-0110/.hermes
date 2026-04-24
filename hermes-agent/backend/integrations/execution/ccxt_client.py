"""Shared CCXT-backed execution client for backend-only exchange access."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from decimal import ROUND_DOWN, Decimal
from typing import Any, Union

import requests

from backend.integrations.base import IntegrationError, MissingCredentialError
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
from backend.integrations.execution.readiness import classify_live_execution_readiness
from backend.integrations.execution.private_read import (
    ClassifiedPrivateReadError,
    classify_private_read_exception,
    parse_bitmart_private_read_response,
)
from backend.integrations.provider_profiles import PROVIDER_PROFILES
from backend.models import ExchangeBalances, ExecutionBalance, ExecutionOrder, ExecutionStatus, ExecutionTrade

logger = logging.getLogger(__name__)


class CCXTExecutionClient:
    """Backend-only execution adapter with BitMart as the first supported exchange."""

    provider = PROVIDER_PROFILES["bitmart"]
    exchange_id = "bitmart"
    # Hermes trading desk is built around BitMart derivatives / perpetual futures.
    # Using spot here routes private CCXT calls to the wrong API namespace and can
    # produce auth failures even when credentials are valid.
    account_type = "swap"

    def __init__(self) -> None:
        self._api_key = os.getenv("BITMART_API_KEY", "").strip()
        self._secret = os.getenv("BITMART_SECRET", "").strip()
        self._memo = os.getenv("BITMART_MEMO", "").strip()
        self._uid = os.getenv("BITMART_UID", "").strip()
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
                ("BITMART_UID", self._uid),
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
                    "uid": self._uid,
                    "enableRateLimit": True,
                    "options": {"defaultType": self.account_type},
                    "userAgent": self._USER_AGENT,
                    "headers": {"User-Agent": self._USER_AGENT},
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
        except ClassifiedPrivateReadError:
            raise
        except Exception as exc:
            logger.warning("BitMart %s failed: %s", operation, exc.__class__.__name__)
            if operation in {"fetch_open_orders", "fetch_orders", "fetch_my_trades", "fetch_order", "load_markets"}:
                classification = classify_private_read_exception(exc)
                raise ClassifiedPrivateReadError(
                    f"BitMart private read {operation} failed [{classification}]: {exc}",
                    classification=classification,
                    operation=operation,
                ) from exc
            raise IntegrationError(f"BitMart {operation} failed.") from exc

    def _normalize_order(self, order: dict[str, Any]) -> ExecutionOrder:
        return normalize_ccxt_order(provider_name=self.provider.name, order=order)

    def _normalize_trade(self, trade: dict[str, Any]) -> ExecutionTrade:
        return normalize_ccxt_trade(provider_name=self.provider.name, trade=trade)

    # ------------------------------------------------------------------
    # Direct REST helpers (bypass CCXT for balance reads — KEYED only)
    # ------------------------------------------------------------------

    _SPOT_BALANCE_URL = "https://api-cloud.bitmart.com/account/v1/wallet"
    _FUTURES_BALANCE_URL = "https://api-cloud-v2.bitmart.com/contract/private/assets-detail"
    _TRANSFER_URL = "https://api-cloud-v2.bitmart.com/account/v1/transfer-contract"
    # IMPORTANT: Must be this exact UA — Cloudflare WAF returns HTTP 403 / error 1010 for
    # generic User-Agents (e.g. python-requests, Go-http-client, CCXT default).
    _USER_AGENT = "bitmart-skills/futures/v2026.3.23"
    _REST_HEADERS_BASE = {"User-Agent": _USER_AGENT}

    # Per-currency decimal precision for transfers. Extend this dict when adding
    # non-USDT assets (e.g. BTC=8, ETH=8).
    _TRANSFER_PRECISION: dict[str, int] = {"USDT": 2}

    @staticmethod
    def _floor_transfer_amount(amount: Union[str, float, Decimal], decimals: int = 2) -> str:
        """Floor *amount* to *decimals* decimal places and return as a plain string.

        Uses Decimal arithmetic throughout — no float multiplication — so values
        like ``291.45585285`` are truncated exactly to ``"291.45"`` rather than
        being subject to IEEE-754 rounding surprises.

        Examples::

            _floor_transfer_amount("291.45585285")  ->  "291.45"
            _floor_transfer_amount(291.45999, 2)   ->  "291.45"
            _floor_transfer_amount("300", 2)        ->  "300"
            _floor_transfer_amount("200.50", 2)     ->  "200.50"
        """
        quant = Decimal(10) ** -decimals  # Decimal('0.01') for decimals=2
        floored = Decimal(str(amount)).quantize(quant, rounding=ROUND_DOWN)
        # Drop trailing ".00" for whole numbers; keep significant fractional zeros ("200.50").
        if floored == floored.to_integral_value():
            return str(floored.to_integral_value())
        return str(floored)

    def _fetch_spot_balances_rest(self) -> list[ExecutionBalance]:
        """Fetch spot balances via the KEYED /account/v1/wallet endpoint (no signature required)."""
        headers = {**self._REST_HEADERS_BASE, "X-BM-KEY": self._api_key}
        try:
            resp = requests.get(self._SPOT_BALANCE_URL, headers=headers, timeout=15)
        except Exception as exc:
            raise IntegrationError(f"BitMart spot balance REST request failed: {exc}") from exc
        body = parse_bitmart_private_read_response(resp, operation="spot balance")

        balances: list[ExecutionBalance] = []
        for item in (body.get("data") or {}).get("wallet") or []:
            # /account/v1/wallet uses "currency"; /spot/v1/wallet uses "id"
            asset = item.get("currency") or item.get("id")
            if not asset:
                continue
            available = float_or_none(item.get("available"))
            frozen = float_or_none(item.get("frozen"))
            total = None
            if available is not None and frozen is not None:
                total = available + frozen
            elif available is not None:
                total = available
            balances.append(ExecutionBalance(asset=str(asset), free=available, used=frozen, total=total))
        return balances

    def _fetch_futures_balances_rest(self) -> list[ExecutionBalance]:
        """Fetch futures balances via the KEYED /contract/private/assets-detail endpoint."""
        headers = {**self._REST_HEADERS_BASE, "X-BM-KEY": self._api_key}
        try:
            resp = requests.get(self._FUTURES_BALANCE_URL, headers=headers, timeout=15)
        except Exception as exc:
            raise IntegrationError(f"BitMart futures balance REST request failed: {exc}") from exc
        body = parse_bitmart_private_read_response(resp, operation="futures balance")

        balances: list[ExecutionBalance] = []
        for item in body.get("data") or []:
            asset = item.get("currency")
            if not asset:
                continue
            available = float_or_none(item.get("available_balance"))
            frozen = float_or_none(item.get("frozen_balance"))
            equity = float_or_none(item.get("equity"))
            total = equity if equity is not None else (
                (available or 0.0) + (frozen or 0.0) if available is not None else None
            )
            balances.append(ExecutionBalance(asset=str(asset), free=available, used=frozen, total=total))
        return balances

    def get_exchange_balances(self) -> ExchangeBalances:
        self.require_credentials()
        is_futures = self.account_type in ("contract", "futures", "swap")
        try:
            if is_futures:
                balances = self._fetch_futures_balances_rest()
            else:
                balances = self._fetch_spot_balances_rest()
        except IntegrationError:
            raise
        except Exception as exc:
            raise IntegrationError(f"BitMart balance fetch failed: {exc}") from exc

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
        reduce_only: bool = False,
        position_side: str | None = None,
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
        if reduce_only:
            params["reduceOnly"] = True
        if position_side:
            params["positionSide"] = position_side.upper()
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

    def transfer_funds(
        self,
        *,
        amount: Union[str, float, Decimal],
        direction: str,
        currency: str = "USDT",
    ) -> dict[str, Any]:
        """Transfer funds between spot and futures accounts.

        Args:
            amount: Transfer amount as string, float, or Decimal
                (e.g. ``"300"``, ``291.45585285``, or ``Decimal("291.45")``).  
                Floored to the precision in ``_TRANSFER_PRECISION`` for the
                given currency (USDT → 2 d.p. = min unit 0.01 USDT).  
                Pass the raw available balance — this method floors it safely.
            direction: Either ``"spot_to_contract"`` or ``"contract_to_spot"``.
            currency: Only ``"USDT"`` is supported by BitMart.

        Returns:
            The parsed response dict from BitMart (code 1000 = success).

        Raises:
            IntegrationError: On HTTP error, Cloudflare block, or BitMart business error.
        """
        import hashlib
        import hmac
        import json
        import time

        import requests

        self.require_credentials()
        self._check_paper_mode_url()

        if direction not in ("spot_to_contract", "contract_to_spot"):
            raise IntegrationError(
                f"Invalid transfer direction {direction!r}. "
                "Must be 'spot_to_contract' or 'contract_to_spot'."
            )

        # Floor to BitMart-accepted precision using Decimal (no float math).
        # _TRANSFER_PRECISION maps currency -> decimal places; USDT=2, others default 2.
        decimals = self._TRANSFER_PRECISION.get(currency, 2)
        amount_str = self._floor_transfer_amount(amount, decimals)
        if Decimal(amount_str) <= 0:
            raise IntegrationError(
                f"Transfer amount {amount!r} floors to {amount_str!r} after applying "
                f"{decimals}-decimal precision for {currency} — nothing to transfer. "
                f"Minimum transferable amount is 0.{'0' * (decimals - 1)}1 {currency}."
            )
        body: dict[str, Any] = {"amount": amount_str, "currency": currency, "type": direction}
        body_json = json.dumps(body, separators=(",", ":"))
        ts = str(int(time.time() * 1000))
        prehash = f"{ts}#{self._memo}#{body_json}"
        signature = hmac.new(
            self._secret.encode(), prehash.encode(), hashlib.sha256
        ).hexdigest()
        headers = {
            "Content-Type": "application/json",
            "User-Agent": self._USER_AGENT,
            "X-BM-KEY": self._api_key,
            "X-BM-SIGN": signature,
            "X-BM-TIMESTAMP": ts,
        }
        logger.info(
            "BitMart transfer: %s %s USDT (%s)", direction, amount_str, currency
        )

        # Retry up to 5 times for transient server errors (502, 503, 504).
        # Backoff: 2s, 4s, 8s, 16s between attempts (~30s total window).
        # Signature timestamp must be regenerated on each attempt (replay protection).
        _MAX_ATTEMPTS = 5
        _RETRY_STATUSES = {502, 503, 504}
        for attempt in range(1, _MAX_ATTEMPTS + 1):
            ts = str(int(time.time() * 1000))
            prehash = f"{ts}#{self._memo}#{body_json}"
            signature = hmac.new(
                self._secret.encode(), prehash.encode(), hashlib.sha256
            ).hexdigest()
            headers["X-BM-SIGN"] = signature
            headers["X-BM-TIMESTAMP"] = ts

            try:
                resp = requests.post(
                    self._TRANSFER_URL, data=body_json, headers=headers, timeout=30
                )
            except Exception as exc:
                if attempt < _MAX_ATTEMPTS:
                    wait = 2 ** attempt  # 2, 4, 8, 16
                    logger.warning(
                        "BitMart transfer request failed (attempt %d/%d): %s — retrying in %ds",
                        attempt, _MAX_ATTEMPTS, exc, wait,
                    )
                    time.sleep(wait)
                    continue
                raise IntegrationError(f"BitMart transfer request failed: {exc}") from exc

            if resp.status_code == 403:
                raise IntegrationError(
                    f"BitMart transfer blocked (HTTP 403). "
                    "This is a Cloudflare WAF rejection — check User-Agent and rate limits. "
                    f"Body: {resp.text[:200]}"
                )

            if resp.status_code in _RETRY_STATUSES:
                if attempt < _MAX_ATTEMPTS:
                    wait = 2 ** attempt  # 2, 4, 8, 16
                    logger.warning(
                        "BitMart transfer HTTP %d (attempt %d/%d) — retrying in %ds",
                        resp.status_code, attempt, _MAX_ATTEMPTS, wait,
                    )
                    time.sleep(wait)
                    continue
                raise IntegrationError(
                    f"BitMart transfer HTTP {resp.status_code} after {_MAX_ATTEMPTS} attempts: {resp.text[:200]}"
                )

            # Non-retryable status — fall through to JSON parsing below.
            break

        try:
            data = resp.json()
        except Exception as exc:
            raise IntegrationError(
                f"BitMart transfer returned non-JSON (HTTP {resp.status_code}): {resp.text[:200]}"
            ) from exc

        if data.get("code") != 1000:
            raise IntegrationError(
                f"BitMart transfer error {data.get('code')}: {data.get('message')} "
                f"(trace={data.get('trace')})"
            )
        logger.info("BitMart transfer successful: %s", data.get("data"))
        return data

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
        readiness = classify_live_execution_readiness(
            self,
            private_read_probe=lambda: self.get_exchange_balances(),
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
                detail="BitMart credentials are not configured.",
                checked_at=datetime.now(timezone.utc).isoformat(),
            )
        order: ExecutionOrder | None = None
        detail = f"BitMart execution readiness: {readiness.status}."
        if order_id:
            exchange = self._get_exchange()
            raw_order = self._call_exchange("fetch_order", exchange.fetch_order, order_id, symbol)
            order = self._normalize_order(raw_order)
            detail = f"Fetched BitMart status for order {order.order_id}."
        return ExecutionStatus(
            exchange=self.provider.name,
            configured=True,
            connected=readiness.private_reads_working,
            rate_limit_enabled=self.rate_limit_enabled,
            account_type=self.account_type,
            readiness_status=readiness.status,
            readiness=readiness.model_dump(mode="json"),
            detail=detail,
            order=order,
            checked_at=datetime.now(timezone.utc).isoformat(),
        )
