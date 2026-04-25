"""Bybit public REST client for linear perpetual market data."""

from __future__ import annotations

import logging
from typing import Any

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from backend.integrations.base import IntegrationError
from backend.integrations.provider_profiles import PROVIDER_PROFILES
from backend.models import FundingRateEntry, FundingRatesSnapshot, OrderBookSnapshot

from ._utils import build_order_book_snapshot, ms_to_iso, safe_float, venue_symbol

logger = logging.getLogger(__name__)

BASE = "https://api.bybit.com"
TIMEOUT = 10.0
HEADERS = {"User-Agent": "hermes-agent/trading-integrations"}


def _retry_http():
    return retry(
        retry=retry_if_exception_type(httpx.HTTPError),
        wait=wait_exponential(multiplier=0.5, min=0.5, max=4),
        stop=stop_after_attempt(3),
        reraise=True,
    )


class BybitPublicClient:
    """Public Bybit linear-perpetual market-data client."""

    provider = PROVIDER_PROFILES["bybit_public"]

    def __init__(self) -> None:
        self._client = httpx.Client(
            base_url=BASE,
            timeout=httpx.Timeout(TIMEOUT),
            headers=HEADERS,
            follow_redirects=True,
        )

    @property
    def configured(self) -> bool:
        return True

    @_retry_http()
    def get_order_book(self, symbol: str, *, limit: int = 20) -> OrderBookSnapshot:
        exchange_symbol = venue_symbol(symbol, "bybit")
        response = self._client.get(
            "/v5/market/orderbook",
            params={"category": "linear", "symbol": exchange_symbol, "limit": min(limit, 200)},
        )
        self._raise(response, "order book")

        result = response.json().get("result") or {}
        return build_order_book_snapshot(
            symbol=exchange_symbol,
            exchange="BYBIT",
            raw_bids=result.get("b", []),
            raw_asks=result.get("a", []),
            limit=limit,
        )

    @_retry_http()
    def get_funding_rates(self, symbols: list[str] | None = None, *, limit: int = 20) -> FundingRatesSnapshot:
        rows = self._fetch_tickers(symbols)
        row_map = {str(row.get("symbol") or "").upper(): row for row in rows}

        entries: list[FundingRateEntry] = []
        if symbols:
            for symbol in symbols:
                record = row_map.get(venue_symbol(symbol, "bybit"))
                if record:
                    entries.append(self._entry_from_row(record))
        else:
            ranked = sorted(rows, key=lambda row: abs(safe_float(row.get("fundingRate")) or 0.0), reverse=True)
            entries = [self._entry_from_row(row) for row in ranked[:limit]]

        return FundingRatesSnapshot(
            symbols=entries,
            as_of=ms_to_iso(rows[0].get("nextFundingTime")) if rows else None,
            source="bybit_linear_public",
        )

    def _fetch_tickers(self, symbols: list[str] | None) -> list[dict[str, Any]]:
        if symbols:
            rows: list[dict[str, Any]] = []
            for symbol in symbols:
                exchange_symbol = venue_symbol(symbol, "bybit")
                response = self._client.get(
                    "/v5/market/tickers",
                    params={"category": "linear", "symbol": exchange_symbol},
                )
                self._raise(response, "funding tickers")
                result = response.json().get("result") or {}
                items = result.get("list") or []
                if items:
                    rows.extend(item for item in items if isinstance(item, dict))
            return rows

        response = self._client.get("/v5/market/tickers", params={"category": "linear"})
        self._raise(response, "funding tickers")
        result = response.json().get("result") or {}
        items = result.get("list") or []
        return [item for item in items if isinstance(item, dict) and str(item.get("symbol") or "").endswith("USDT")]

    def _entry_from_row(self, row: dict[str, Any]) -> FundingRateEntry:
        return FundingRateEntry(
            symbol=str(row.get("symbol") or "").upper(),
            exchange="BYBIT",
            funding_rate=safe_float(row.get("fundingRate")),
            funding_time=ms_to_iso(row.get("nextFundingTime")),
            mark_price=safe_float(row.get("markPrice")),
            index_price=safe_float(row.get("indexPrice")),
            next_funding_time=ms_to_iso(row.get("nextFundingTime")),
            open_interest_usd=safe_float(row.get("openInterestValue") or row.get("openInterest")),
        )

    def _raise(self, response: httpx.Response, context: str) -> None:
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise IntegrationError(
                f"Bybit {context} request failed: {exc.response.status_code}"
            ) from exc
        body = response.json()
        if str(body.get("retCode", "0")) != "0":
            raise IntegrationError(
                f"Bybit {context} API error: code={body.get('retCode')} message={body.get('retMsg')}"
            )
