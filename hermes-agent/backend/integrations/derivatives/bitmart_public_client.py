"""BitMart public REST client — no API key required for futures market data.

Covers:
- Futures order book depth  (api-cloud-v2.bitmart.com/contract/public/depth)
- Futures funding rates      (api-cloud-v2.bitmart.com/contract/public/details)
- Futures open interest      (api-cloud-v2.bitmart.com/contract/public/open-interest)
- Liquidation pressure proxy (OI + contract details)
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from backend.integrations.base import IntegrationError
from backend.integrations.provider_profiles import PROVIDER_PROFILES
from backend.models import (
    FundingRateEntry,
    FundingRatesSnapshot,
    LiquidationEntry,
    LiquidationZonesSnapshot,
    OrderBookLevel,
    OrderBookSnapshot,
    RecentTradesSnapshot,
    TradeRecord,
)

logger = logging.getLogger(__name__)

BASE = "https://api-cloud-v2.bitmart.com"
TIMEOUT = 10.0
HEADERS = {"User-Agent": "hermes-agent/trading-integrations"}


def _retry_http():
    return retry(
        retry=retry_if_exception_type(httpx.HTTPError),
        wait=wait_exponential(multiplier=0.5, min=0.5, max=4),
        stop=stop_after_attempt(3),
        reraise=True,
    )


class BitMartPublicClient:
    """Free public BitMart futures REST endpoints — never requires an API key."""

    provider = PROVIDER_PROFILES["bitmart_public"]

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

    # ------------------------------------------------------------------
    # Order Book (Futures depth)
    # ------------------------------------------------------------------

    @_retry_http()
    def get_order_book(self, symbol: str, *, limit: int = 20) -> OrderBookSnapshot:
        """Fetch futures order book for `symbol` (e.g. 'BTCUSDT').

        BitMart /contract/public/depth returns up to 50 levels.
        Each level is [price_str, qty_str, cumulative_qty_str].
        """
        response = self._client.get(
            "/contract/public/depth",
            params={"symbol": symbol.upper()},
        )
        self._raise(response, "order book")

        data = response.json().get("data", {})
        raw_bids: list[list[str]] = data.get("bids", [])
        raw_asks: list[list[str]] = data.get("asks", [])

        # Slice to requested limit (API max is 50)
        raw_bids = raw_bids[:limit]
        raw_asks = raw_asks[:limit]

        bids = [OrderBookLevel(price=float(b[0]), amount=float(b[1])) for b in raw_bids if len(b) >= 2]
        asks = [OrderBookLevel(price=float(a[0]), amount=float(a[1])) for a in raw_asks if len(a) >= 2]

        best_bid = bids[0].price if bids else None
        best_ask = asks[0].price if asks else None
        spread = (best_ask - best_bid) if (best_bid and best_ask) else None
        spread_pct = (spread / best_bid * 100) if (spread and best_bid) else None

        bid_depth_usd = sum(b.price * b.amount for b in bids) if bids else None
        ask_depth_usd = sum(a.price * a.amount for a in asks) if asks else None
        total_depth = (bid_depth_usd or 0) + (ask_depth_usd or 0)
        imbalance = ((bid_depth_usd or 0) - (ask_depth_usd or 0)) / total_depth if total_depth else None

        return OrderBookSnapshot(
            symbol=symbol.upper(),
            exchange="BITMART",
            bids=bids,
            asks=asks,
            best_bid=best_bid,
            best_ask=best_ask,
            spread=spread,
            spread_pct=round(spread_pct, 6) if spread_pct is not None else None,
            bid_depth_usd=round(bid_depth_usd, 2) if bid_depth_usd is not None else None,
            ask_depth_usd=round(ask_depth_usd, 2) if ask_depth_usd is not None else None,
            imbalance=round(imbalance, 4) if imbalance is not None else None,
            as_of=datetime.now(timezone.utc).isoformat(),
        )

    # ------------------------------------------------------------------
    # Funding Rates
    # ------------------------------------------------------------------

    @_retry_http()
    def get_funding_rates(self, symbols: list[str] | None = None, *, limit: int = 20) -> FundingRatesSnapshot:
        """Fetch current funding rates.

        If `symbols` is None, fetches all contracts via /contract/public/details
        and returns top `limit` by absolute funding rate.
        If `symbols` is provided, queries each individually via
        /contract/public/funding-rate (per-symbol endpoint, more fields).
        """
        if symbols:
            entries = []
            for sym in symbols:
                entry = self._get_funding_rate_single(sym.upper())
                if entry:
                    entries.append(entry)
        else:
            entries = self._get_all_funding_rates(limit=limit)

        return FundingRatesSnapshot(
            symbols=entries,
            as_of=datetime.now(timezone.utc).isoformat(),
        )

    @_retry_http()
    def _get_funding_rate_single(self, symbol: str) -> FundingRateEntry | None:
        """Fetch funding rate for one symbol via /contract/public/funding-rate."""
        response = self._client.get(
            "/contract/public/funding-rate",
            params={"symbol": symbol},
        )
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError:
            return None
        d = response.json().get("data", {})
        return FundingRateEntry(
            symbol=symbol,
            funding_rate=_safe_float(d.get("rate_value")),
            mark_price=None,  # not in this endpoint
            index_price=None,
            next_funding_time=_ms_to_iso(d.get("funding_time")),
        )

    def _get_all_funding_rates(self, *, limit: int) -> list[FundingRateEntry]:
        """Fetch all USDT perpetuals from /contract/public/details and rank by abs funding."""
        response = self._client.get("/contract/public/details")
        self._raise(response, "contract details")

        contracts: list[dict[str, Any]] = response.json().get("data", {}).get("symbols", [])
        # Keep only active USDT-settled perpetuals
        contracts = [
            c for c in contracts
            if str(c.get("symbol", "")).endswith("USDT")
            and c.get("status", "") == "Trading"
            and c.get("expire_timestamp", 1) == 0  # 0 = no expiry = perpetual
            and c.get("funding_rate") not in (None, "")
        ]
        contracts.sort(key=lambda c: abs(float(c.get("funding_rate") or 0)), reverse=True)
        contracts = contracts[:limit]

        return [
            FundingRateEntry(
                symbol=str(c.get("symbol", "")),
                funding_rate=_safe_float(c.get("funding_rate")),
                mark_price=_safe_float(c.get("last_price")),
                index_price=_safe_float(c.get("index_price")),
                next_funding_time=None,
            )
            for c in contracts
        ]

    @_retry_http()
    def get_open_interest(self, symbol: str) -> float | None:
        """Fetch current open interest USD for a futures symbol."""
        response = self._client.get(
            "/contract/public/open-interest",
            params={"symbol": symbol.upper()},
        )
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError:
            return None
        d = response.json().get("data", {})
        return _safe_float(d.get("open_interest_value") or d.get("open_interest"))

    # ------------------------------------------------------------------
    # Liquidation Pressure (OI + contract details as proxy)
    # ------------------------------------------------------------------

    @_retry_http()
    def get_liquidation_pressure(self, symbol: str, *, limit: int = 10) -> LiquidationZonesSnapshot:
        """Estimate liquidation pressure via open interest + contract details.

        BitMart does not expose a force-orders feed. We use:
        - /contract/public/open-interest  → current OI value
        - /contract/public/details        → funding rate, last price, change_24h as proxy
        """
        sym = symbol.upper()

        # Open interest
        oi_resp = self._client.get("/contract/public/open-interest", params={"symbol": sym})
        self._raise(oi_resp, "open interest")
        oi_data = oi_resp.json().get("data", {})
        oi_value = _safe_float(oi_data.get("open_interest_value"))

        # Contract details for funding rate and price change
        det_resp = self._client.get("/contract/public/details", params={"symbol": sym})
        self._raise(det_resp, "contract details")
        contracts = det_resp.json().get("data", {}).get("symbols", [])
        contract = contracts[0] if contracts else {}

        funding_rate = _safe_float(contract.get("funding_rate"))
        change_24h = _safe_float(contract.get("change_24h"))
        expected_funding = _safe_float(contract.get("expected_funding_rate"))

        # Derive a rough dominant side from funding rate sign:
        # Positive funding = longs pay shorts → crowded long, risk = long liquidation
        # Negative funding = shorts pay longs → crowded short, risk = short liquidation
        dominant: str
        if funding_rate is not None:
            if funding_rate > 0.0001:
                dominant = "longs"
            elif funding_rate < -0.0001:
                dominant = "shorts"
            else:
                dominant = "balanced"
        else:
            dominant = "balanced"

        # No actual liquidation events available; create a single synthetic entry summarising OI
        entries: list[LiquidationEntry] = []
        if oi_value:
            entries.append(LiquidationEntry(
                symbol=sym,
                side="OI_PROXY",
                price=_safe_float(contract.get("last_price")),
                quantity=None,
                usd_value=round(oi_value, 2),
                timestamp=datetime.now(timezone.utc).isoformat(),
            ))

        return LiquidationZonesSnapshot(
            symbol=sym,
            recent_liquidations=entries,
            total_longs_liquidated_usd=None,   # not available from public API
            total_shorts_liquidated_usd=None,
            dominant_side=dominant,
            open_interest_usd=oi_value,
            long_short_ratio=None,             # not available from public API
            long_account_pct=None,
            short_account_pct=None,
            as_of=datetime.now(timezone.utc).isoformat(),
        )

    # ------------------------------------------------------------------
    # Recent Trades / Tape
    # ------------------------------------------------------------------

    @_retry_http()
    def get_recent_trades(self, symbol: str, *, limit: int = 50) -> RecentTradesSnapshot:
        """Fetch recent public trades (tape/time-and-sales) for a futures symbol.

        BitMart /contract/public/trades returns the most recent N trades.
        Each trade has: symbol, deal_price, deal_vol, way (1=buy, 2=sell),
        and create_time (ms epoch).
        """
        sym = symbol.upper()
        response = self._client.get(
            "/contract/public/trades",
            params={"symbol": sym, "limit": min(limit, 100)},
        )
        self._raise(response, "recent trades")

        raw_trades = response.json().get("data", {}).get("trades", [])
        if not isinstance(raw_trades, list):
            raw_trades = []

        trades: list[TradeRecord] = []
        for t in raw_trades[:limit]:
            try:
                way = int(t.get("way", 0))
                side: str
                if way == 1:
                    side = "buy"
                elif way == 2:
                    side = "sell"
                else:
                    side = "unknown"

                price = _safe_float(t.get("deal_price") or t.get("price"))
                size = _safe_float(t.get("deal_vol") or t.get("size") or t.get("qty"))
                ts_ms = t.get("create_time") or t.get("timestamp")
                if ts_ms:
                    ts = datetime.fromtimestamp(int(ts_ms) / 1000, tz=timezone.utc).isoformat()
                else:
                    ts = datetime.now(timezone.utc).isoformat()

                if price is not None and size is not None:
                    trades.append(TradeRecord(price=price, size=size, side=side, timestamp=ts))
            except Exception:
                continue

        # Compute tape analytics
        buy_trades = [t for t in trades if t.side == "buy"]
        sell_trades = [t for t in trades if t.side == "sell"]
        buy_vol = sum(t.price * t.size for t in buy_trades) if buy_trades else None
        sell_vol = sum(t.price * t.size for t in sell_trades) if sell_trades else None

        total_notional = sum(t.price * t.size for t in trades)
        total_size = sum(t.size for t in trades)
        vwap = total_notional / total_size if total_size > 0 else None

        return RecentTradesSnapshot(
            symbol=sym,
            exchange="bitmart_futures",
            trades=trades,
            buy_volume=round(buy_vol, 2) if buy_vol is not None else None,
            sell_volume=round(sell_vol, 2) if sell_vol is not None else None,
            buy_count=len(buy_trades),
            sell_count=len(sell_trades),
            vwap=round(vwap, 6) if vwap is not None else None,
            as_of=datetime.now(timezone.utc).isoformat(),
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _raise(self, response: httpx.Response, context: str) -> None:
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise IntegrationError(
                f"BitMart {context} request failed: {exc.response.status_code}"
            ) from exc
        body = response.json()
        code = body.get("code")
        if code is not None and int(code) != 1000:
            raise IntegrationError(
                f"BitMart {context} API error: code={code} message={body.get('message')}"
            )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe_float(value: Any) -> float | None:
    if value in (None, "", "-"):
        return None
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _ms_to_iso(ms: Any) -> str | None:
    if ms is None:
        return None
    try:
        return datetime.fromtimestamp(int(ms) / 1000, tz=timezone.utc).isoformat()
    except (TypeError, ValueError, OSError):
        return None
