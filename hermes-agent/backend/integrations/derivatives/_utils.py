"""Shared helpers for public derivatives market data clients."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from backend.models import OrderBookLevel, OrderBookSnapshot


SUPPORTED_PUBLIC_DERIVATIVE_VENUES: tuple[str, ...] = ("bitmart", "binance", "bybit", "okx")


def safe_float(value: Any) -> float | None:
    if value in (None, "", "-"):
        return None
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def ms_to_iso(ms: Any) -> str | None:
    if ms in (None, "", "-"):
        return None
    try:
        return datetime.fromtimestamp(int(ms) / 1000, tz=timezone.utc).isoformat()
    except (TypeError, ValueError, OSError):
        return None


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def canonical_symbol(symbol: str) -> str:
    normalized = str(symbol or "").strip().upper()
    if not normalized:
        return ""
    normalized = normalized.replace("/", "").replace("_", "").replace(":", "")
    normalized = normalized.replace("-", "")
    if normalized.endswith("SWAP"):
        normalized = normalized[:-4]
    if normalized.endswith("PERP"):
        normalized = normalized[:-4]
    if normalized.endswith("USD") and not normalized.endswith(("USDT", "USDC", "BUSD")):
        normalized = f"{normalized}T"
    return normalized


def venue_symbol(symbol: str, venue: str) -> str:
    canonical = canonical_symbol(symbol)
    venue_id = str(venue or "").strip().lower()
    if venue_id == "okx":
        if canonical.endswith("USDT"):
            return f"{canonical[:-4]}-USDT-SWAP"
        if canonical.endswith("USDC"):
            return f"{canonical[:-4]}-USDC-SWAP"
        return f"{canonical}-USDT-SWAP"
    return canonical


def build_order_book_snapshot(
    *,
    symbol: str,
    exchange: str,
    raw_bids: list[list[str]] | list[list[float]] | list[tuple[Any, ...]],
    raw_asks: list[list[str]] | list[list[float]] | list[tuple[Any, ...]],
    limit: int,
) -> OrderBookSnapshot:
    bids = [
        OrderBookLevel(price=float(level[0]), amount=float(level[1]))
        for level in list(raw_bids)[:limit]
        if len(level) >= 2
    ]
    asks = [
        OrderBookLevel(price=float(level[0]), amount=float(level[1]))
        for level in list(raw_asks)[:limit]
        if len(level) >= 2
    ]

    best_bid = bids[0].price if bids else None
    best_ask = asks[0].price if asks else None
    spread = (best_ask - best_bid) if (best_bid is not None and best_ask is not None) else None
    spread_pct = (spread / best_bid * 100) if (spread is not None and best_bid) else None

    bid_depth_usd = sum(level.price * level.amount for level in bids) if bids else None
    ask_depth_usd = sum(level.price * level.amount for level in asks) if asks else None
    total_depth = (bid_depth_usd or 0) + (ask_depth_usd or 0)
    imbalance = ((bid_depth_usd or 0) - (ask_depth_usd or 0)) / total_depth if total_depth else None

    return OrderBookSnapshot(
        symbol=canonical_symbol(symbol),
        exchange=exchange,
        bids=bids,
        asks=asks,
        best_bid=best_bid,
        best_ask=best_ask,
        spread=spread,
        spread_pct=round(spread_pct, 6) if spread_pct is not None else None,
        bid_depth_usd=round(bid_depth_usd, 2) if bid_depth_usd is not None else None,
        ask_depth_usd=round(ask_depth_usd, 2) if ask_depth_usd is not None else None,
        imbalance=round(imbalance, 4) if imbalance is not None else None,
        as_of=utc_now_iso(),
    )
