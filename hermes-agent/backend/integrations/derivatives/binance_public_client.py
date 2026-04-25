"""Binance public REST client for futures market data."""

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

BASE = "https://fapi.binance.com"
TIMEOUT = 10.0
HEADERS = {"User-Agent": "hermes-agent/trading-integrations"}
_VALID_DEPTH_LIMITS = (5, 10, 20, 50, 100, 500, 1000)


def _retry_http():
    return retry(
        retry=retry_if_exception_type(httpx.HTTPError),
        wait=wait_exponential(multiplier=0.5, min=0.5, max=4),
        stop=stop_after_attempt(3),
        reraise=True,
    )


class BinancePublicClient:
    """Public Binance USDⓈ-M futures market-data client."""

    provider = PROVIDER_PROFILES["binance_public"]

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
        exchange_symbol = venue_symbol(symbol, "binance")
        response = self._client.get(
            "/fapi/v1/depth",
            params={"symbol": exchange_symbol, "limit": _binance_depth_limit(limit)},
        )
        self._raise(response, "order book")

        data = response.json()
        return build_order_book_snapshot(
            symbol=exchange_symbol,
            exchange="BINANCE",
            raw_bids=data.get("bids", []),
            raw_asks=data.get("asks", []),
            limit=limit,
        )

    @_retry_http()
    def get_funding_rates(self, symbols: list[str] | None = None, *, limit: int = 20) -> FundingRatesSnapshot:
        response = self._client.get("/fapi/v1/premiumIndex")
        self._raise(response, "funding rates")

        data = response.json()
        rows: list[dict[str, Any]]
        if isinstance(data, list):
            rows = [row for row in data if isinstance(row, dict)]
        elif isinstance(data, dict):
            rows = [data]
        else:
            rows = []

        rows = [row for row in rows if str(row.get("symbol") or "").endswith("USDT")]
        row_map = {str(row.get("symbol") or "").upper(): row for row in rows}

        entries: list[FundingRateEntry] = []
        if symbols:
            for symbol in symbols:
                record = row_map.get(venue_symbol(symbol, "binance"))
                if record:
                    entries.append(self._entry_from_row(record))
        else:
            ranked = sorted(rows, key=lambda row: abs(safe_float(row.get("lastFundingRate")) or 0.0), reverse=True)
            entries = [self._entry_from_row(row) for row in ranked[:limit]]

        return FundingRatesSnapshot(
            symbols=entries,
            as_of=ms_to_iso(rows[0].get("time")) if rows else None,
            source="binance_futures_public",
        )

    def _entry_from_row(self, row: dict[str, Any]) -> FundingRateEntry:
        return FundingRateEntry(
            symbol=str(row.get("symbol") or "").upper(),
            exchange="BINANCE",
            funding_rate=safe_float(row.get("lastFundingRate")),
            funding_time=ms_to_iso(row.get("time")),
            mark_price=safe_float(row.get("markPrice")),
            index_price=safe_float(row.get("indexPrice")),
            next_funding_time=ms_to_iso(row.get("nextFundingTime")),
        )

    def _raise(self, response: httpx.Response, context: str) -> None:
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise IntegrationError(
                f"Binance {context} request failed: {exc.response.status_code}"
            ) from exc
        body = response.json()
        if isinstance(body, dict) and body.get("code") not in (None, 0):
            raise IntegrationError(
                f"Binance {context} API error: code={body.get('code')} message={body.get('msg') or body.get('message')}"
            )


def _binance_depth_limit(limit: int) -> int:
    for candidate in _VALID_DEPTH_LIMITS:
        if limit <= candidate:
            return candidate
    return _VALID_DEPTH_LIMITS[-1]
