"""OKX public REST client for swap market data."""

from __future__ import annotations

import logging
from typing import Any

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from backend.integrations.base import IntegrationError
from backend.integrations.provider_profiles import PROVIDER_PROFILES
from backend.models import FundingRateEntry, FundingRatesSnapshot, OrderBookSnapshot

from ._utils import build_order_book_snapshot, canonical_symbol, ms_to_iso, safe_float, utc_now_iso, venue_symbol

logger = logging.getLogger(__name__)

BASE = "https://www.okx.com"
TIMEOUT = 10.0
HEADERS = {"User-Agent": "hermes-agent/trading-integrations"}


def _retry_http():
    return retry(
        retry=retry_if_exception_type(httpx.HTTPError),
        wait=wait_exponential(multiplier=0.5, min=0.5, max=4),
        stop=stop_after_attempt(3),
        reraise=True,
    )


class OKXPublicClient:
    """Public OKX swap market-data client."""

    provider = PROVIDER_PROFILES["okx_public"]

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
        inst_id = venue_symbol(symbol, "okx")
        response = self._client.get(
            "/api/v5/market/books",
            params={"instId": inst_id, "sz": min(limit, 400)},
        )
        self._raise(response, "order book")

        data = response.json().get("data") or []
        book = data[0] if data else {}
        return build_order_book_snapshot(
            symbol=inst_id,
            exchange="OKX",
            raw_bids=book.get("bids", []),
            raw_asks=book.get("asks", []),
            limit=limit,
        )

    def get_funding_rates(self, symbols: list[str] | None = None, *, limit: int = 20) -> FundingRatesSnapshot:
        inst_ids = [venue_symbol(symbol, "okx") for symbol in symbols] if symbols else self._list_instruments(limit=limit)
        entries: list[FundingRateEntry] = []
        for inst_id in inst_ids:
            entry = self._get_funding_rate_single(inst_id)
            if entry is not None:
                entries.append(entry)

        if not symbols:
            entries.sort(key=lambda entry: abs(entry.funding_rate or 0.0), reverse=True)
            entries = entries[:limit]

        return FundingRatesSnapshot(
            symbols=entries,
            as_of=utc_now_iso(),
            source="okx_swap_public",
        )

    @_retry_http()
    def _get_funding_rate_single(self, inst_id: str) -> FundingRateEntry | None:
        response = self._client.get("/api/v5/public/funding-rate", params={"instId": inst_id})
        self._raise(response, "funding rate")

        data = response.json().get("data") or []
        row = data[0] if data else None
        if not isinstance(row, dict):
            return None

        mark_price = self._get_mark_price(inst_id)
        index_price = self._get_index_price(inst_id)

        return FundingRateEntry(
            symbol=canonical_symbol(str(row.get("instId") or inst_id)),
            exchange="OKX",
            funding_rate=safe_float(row.get("fundingRate")),
            funding_time=ms_to_iso(row.get("fundingTime") or row.get("ts")),
            mark_price=mark_price,
            index_price=index_price,
            next_funding_time=ms_to_iso(row.get("nextFundingTime")),
        )

    @_retry_http()
    def _get_mark_price(self, inst_id: str) -> float | None:
        response = self._client.get(
            "/api/v5/public/mark-price",
            params={"instType": "SWAP", "instId": inst_id},
        )
        self._raise(response, "mark price")
        data = response.json().get("data") or []
        row = data[0] if data else {}
        return safe_float(row.get("markPx"))

    @_retry_http()
    def _get_index_price(self, inst_id: str) -> float | None:
        index_inst_id = inst_id.replace("-SWAP", "")
        response = self._client.get(
            "/api/v5/market/index-tickers",
            params={"instId": index_inst_id},
        )
        self._raise(response, "index price")
        data = response.json().get("data") or []
        row = data[0] if data else {}
        return safe_float(row.get("idxPx"))

    @_retry_http()
    def _list_instruments(self, *, limit: int) -> list[str]:
        response = self._client.get("/api/v5/public/instruments", params={"instType": "SWAP"})
        self._raise(response, "instrument list")
        rows = response.json().get("data") or []
        inst_ids = [
            str(row.get("instId") or "")
            for row in rows
            if isinstance(row, dict)
            and str(row.get("quoteCcy") or "").upper() == "USDT"
            and str(row.get("state") or "").lower() == "live"
        ]
        return inst_ids[: max(limit, 1)]

    def _raise(self, response: httpx.Response, context: str) -> None:
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise IntegrationError(
                f"OKX {context} request failed: {exc.response.status_code}"
            ) from exc
        body = response.json()
        if str(body.get("code", "0")) != "0":
            raise IntegrationError(
                f"OKX {context} API error: code={body.get('code')} message={body.get('msg')}"
            )
