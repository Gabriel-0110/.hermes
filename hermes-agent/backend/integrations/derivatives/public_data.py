"""Shared multi-venue helpers for public derivatives market data."""

from __future__ import annotations

from typing import Any

from backend.models import FundingRatesSnapshot, OrderBookLevel, OrderBookSnapshot

from ._utils import SUPPORTED_PUBLIC_DERIVATIVE_VENUES, canonical_symbol, utc_now_iso, venue_symbol
from .binance_public_client import BinancePublicClient
from .bitmart_public_client import BitMartPublicClient
from .bybit_public_client import BybitPublicClient
from .okx_public_client import OKXPublicClient

FundingSnapshotBundle = tuple[str, object, FundingRatesSnapshot]
OrderBookBundle = tuple[str, object, OrderBookSnapshot]

_PUBLIC_CLIENT_FACTORIES = {
    "bitmart": BitMartPublicClient,
    "binance": BinancePublicClient,
    "bybit": BybitPublicClient,
    "okx": OKXPublicClient,
}


def resolve_requested_venues(value: str | list[str] | None) -> list[str]:
    if value is None:
        return ["bitmart"]

    raw_tokens: list[str] = []
    if isinstance(value, str):
        normalized = value.strip().lower()
        if not normalized:
            return ["bitmart"]
        if normalized in {"all", "aggregate", "*"}:
            return list(SUPPORTED_PUBLIC_DERIVATIVE_VENUES)
        raw_tokens = [token.strip().lower() for token in normalized.split(",") if token.strip()]
    else:
        for item in value:
            token = str(item or "").strip().lower()
            if not token:
                continue
            if token in {"all", "aggregate", "*"}:
                return list(SUPPORTED_PUBLIC_DERIVATIVE_VENUES)
            raw_tokens.extend(part.strip().lower() for part in token.split(",") if part.strip())

    if not raw_tokens:
        return ["bitmart"]

    venues: list[str] = []
    seen: set[str] = set()
    invalid: list[str] = []
    for token in raw_tokens:
        if token not in SUPPORTED_PUBLIC_DERIVATIVE_VENUES:
            invalid.append(token)
            continue
        if token not in seen:
            venues.append(token)
            seen.add(token)

    if invalid:
        supported = ", ".join(SUPPORTED_PUBLIC_DERIVATIVE_VENUES)
        raise ValueError(f"Unsupported venue(s): {', '.join(sorted(set(invalid)))}. Supported venues: {supported}.")

    return venues or ["bitmart"]


def create_public_client(venue: str):
    venue_id = str(venue or "").strip().lower()
    try:
        return _PUBLIC_CLIENT_FACTORIES[venue_id]()
    except KeyError as exc:
        supported = ", ".join(SUPPORTED_PUBLIC_DERIVATIVE_VENUES)
        raise ValueError(f"Unsupported venue: {venue_id}. Supported venues: {supported}.") from exc


def fetch_funding_rate_snapshots(
    *,
    symbols: list[str] | None,
    venues: list[str],
    limit: int,
) -> tuple[list[FundingSnapshotBundle], list[tuple[str, str, Exception]]]:
    snapshots: list[FundingSnapshotBundle] = []
    errors: list[tuple[str, str, Exception]] = []

    for venue in venues:
        client = create_public_client(venue)
        requested_symbols = [venue_symbol(symbol, venue) for symbol in symbols] if symbols else None
        try:
            snapshot = client.get_funding_rates(requested_symbols, limit=limit)
            snapshots.append((venue, client, snapshot))
        except Exception as exc:  # noqa: BLE001 - provider failures are collected per venue.
            provider_name = getattr(getattr(client, "provider", None), "name", venue.upper())
            errors.append((venue, provider_name, exc))

    return snapshots, errors


def fetch_order_book_snapshots(
    *,
    symbol: str,
    venues: list[str],
    limit: int,
) -> tuple[list[OrderBookBundle], list[tuple[str, str, Exception]]]:
    snapshots: list[OrderBookBundle] = []
    errors: list[tuple[str, str, Exception]] = []

    for venue in venues:
        client = create_public_client(venue)
        exchange_symbol = venue_symbol(symbol, venue)
        try:
            snapshot = client.get_order_book(exchange_symbol, limit=limit)
            snapshots.append((venue, client, snapshot))
        except Exception as exc:  # noqa: BLE001 - provider failures are collected per venue.
            provider_name = getattr(getattr(client, "provider", None), "name", venue.upper())
            errors.append((venue, provider_name, exc))

    return snapshots, errors


def aggregate_funding_rate_snapshots(snapshots: list[FundingSnapshotBundle]) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    venue_snapshots: list[dict[str, Any]] = []

    for venue, client, snapshot in snapshots:
        venue_snapshots.append({"venue": venue, **snapshot.model_dump(mode="json")})
        provider_name = getattr(getattr(client, "provider", None), "name", venue.upper())
        for entry in snapshot.symbols:
            normalized_symbol = canonical_symbol(entry.symbol)
            payload = entry.model_dump(mode="json")
            payload["venue"] = venue
            payload["exchange"] = payload.get("exchange") or provider_name
            grouped.setdefault(normalized_symbol, []).append(payload)

    aggregated_symbols: list[dict[str, Any]] = []
    for symbol, entries in grouped.items():
        numeric_entries = [entry for entry in entries if entry.get("funding_rate") is not None]
        if not numeric_entries:
            continue
        highest = max(numeric_entries, key=lambda entry: float(entry.get("funding_rate") or 0.0))
        lowest = min(numeric_entries, key=lambda entry: float(entry.get("funding_rate") or 0.0))
        spread = float(highest.get("funding_rate") or 0.0) - float(lowest.get("funding_rate") or 0.0)
        average_rate = sum(float(entry.get("funding_rate") or 0.0) for entry in numeric_entries) / len(numeric_entries)
        aggregated_symbols.append(
            {
                "symbol": symbol,
                "venue_count": len(numeric_entries),
                "average_funding_rate": average_rate,
                "max_funding_rate": highest.get("funding_rate"),
                "max_funding_venue": highest.get("venue"),
                "max_funding_exchange": highest.get("exchange"),
                "min_funding_rate": lowest.get("funding_rate"),
                "min_funding_venue": lowest.get("venue"),
                "min_funding_exchange": lowest.get("exchange"),
                "funding_spread_8h": spread,
                "funding_spread_bps": spread * 10_000,
                "next_funding_time": highest.get("next_funding_time") or lowest.get("next_funding_time"),
                "venues": sorted(numeric_entries, key=lambda entry: str(entry.get("venue") or "")),
            }
        )

    aggregated_symbols.sort(key=lambda entry: abs(float(entry.get("funding_spread_8h") or 0.0)), reverse=True)

    requested_venues = [venue for venue, _client, _snapshot in snapshots]
    return {
        "aggregated": True,
        "requested_venues": requested_venues,
        "source": "aggregated_derivatives_public",
        "as_of": utc_now_iso(),
        "symbols": aggregated_symbols,
        "venue_snapshots": venue_snapshots,
    }


def aggregate_order_book_snapshots(snapshots: list[OrderBookBundle], *, limit: int) -> dict[str, Any]:
    if not snapshots:
        return {
            "aggregated": True,
            "requested_venues": [],
            "source": "aggregated_derivatives_public",
            "as_of": utc_now_iso(),
            "bids": [],
            "asks": [],
        }

    requested_venues = [venue for venue, _client, _snapshot in snapshots]
    canonical = canonical_symbol(snapshots[0][2].symbol)
    venue_snapshots = [{"venue": venue, **snapshot.model_dump(mode="json")} for venue, _client, snapshot in snapshots]

    aggregated_bids: list[OrderBookLevel] = []
    aggregated_asks: list[OrderBookLevel] = []
    best_bid_venue: str | None = None
    best_ask_venue: str | None = None

    for venue, _client, snapshot in snapshots:
        for level in snapshot.bids:
            aggregated_bids.append(OrderBookLevel(price=level.price, amount=level.amount, exchange=venue.upper()))
        for level in snapshot.asks:
            aggregated_asks.append(OrderBookLevel(price=level.price, amount=level.amount, exchange=venue.upper()))

    aggregated_bids.sort(key=lambda level: level.price, reverse=True)
    aggregated_asks.sort(key=lambda level: level.price)
    aggregated_bids = aggregated_bids[:limit]
    aggregated_asks = aggregated_asks[:limit]

    if aggregated_bids:
        best_bid_venue = aggregated_bids[0].exchange
    if aggregated_asks:
        best_ask_venue = aggregated_asks[0].exchange

    best_bid = aggregated_bids[0].price if aggregated_bids else None
    best_ask = aggregated_asks[0].price if aggregated_asks else None
    spread = (best_ask - best_bid) if (best_bid is not None and best_ask is not None) else None
    spread_pct = (spread / best_bid * 100) if (spread is not None and best_bid) else None
    bid_depth_usd = sum(level.price * level.amount for level in aggregated_bids) if aggregated_bids else None
    ask_depth_usd = sum(level.price * level.amount for level in aggregated_asks) if aggregated_asks else None
    total_depth = (bid_depth_usd or 0) + (ask_depth_usd or 0)
    imbalance = ((bid_depth_usd or 0) - (ask_depth_usd or 0)) / total_depth if total_depth else None

    mids = [
        (snapshot.best_bid + snapshot.best_ask) / 2
        for _venue, _client, snapshot in snapshots
        if snapshot.best_bid is not None and snapshot.best_ask is not None
    ]
    median_mid = sum(mids) / len(mids) if mids else None

    return {
        "symbol": canonical,
        "exchange": "AGGREGATED",
        "aggregated": True,
        "requested_venues": requested_venues,
        "best_bid": best_bid,
        "best_bid_exchange": best_bid_venue,
        "best_ask": best_ask,
        "best_ask_exchange": best_ask_venue,
        "spread": spread,
        "spread_pct": round(spread_pct, 6) if spread_pct is not None else None,
        "bid_depth_usd": round(bid_depth_usd, 2) if bid_depth_usd is not None else None,
        "ask_depth_usd": round(ask_depth_usd, 2) if ask_depth_usd is not None else None,
        "imbalance": round(imbalance, 4) if imbalance is not None else None,
        "mid_price": round(median_mid, 6) if median_mid is not None else None,
        "bids": [level.model_dump(mode="json") for level in aggregated_bids],
        "asks": [level.model_dump(mode="json") for level in aggregated_asks],
        "venue_snapshots": venue_snapshots,
        "as_of": utc_now_iso(),
        "source": "aggregated_derivatives_public",
    }
