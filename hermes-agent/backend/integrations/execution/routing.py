"""Helpers for multi-venue execution routing and cross-venue reconciliation."""

from __future__ import annotations

import math
import os
from typing import Any, Iterable

from backend.integrations.base import IntegrationError

from .multi_venue import VenueExecutionClient


def normalize_venue_name(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip().lower()
    return normalized or None


def parse_venues(raw: Iterable[str] | str | None) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, str):
        items = raw.split(",")
    else:
        items = list(raw)
    venues: list[str] = []
    seen: set[str] = set()
    for item in items:
        venue = normalize_venue_name(item)
        if venue and venue not in seen:
            seen.add(venue)
            venues.append(venue)
    return venues


def configured_execution_venues() -> list[str]:
    venues = parse_venues(os.getenv("HERMES_EXECUTION_VENUES", "bitmart"))
    return venues or ["bitmart"]


def requested_execution_venues(*, venue: str | None = None, venues: Iterable[str] | str | None = None) -> list[str]:
    direct = normalize_venue_name(venue)
    if direct:
        return [direct]
    parsed = parse_venues(venues)
    return parsed or configured_execution_venues()


def get_execution_clients(
    *,
    venue: str | None = None,
    venues: Iterable[str] | str | None = None,
    configured_only: bool = False,
) -> list[VenueExecutionClient]:
    clients: list[VenueExecutionClient] = []
    for venue_name in requested_execution_venues(venue=venue, venues=venues):
        client = VenueExecutionClient(venue_name)
        if configured_only and not client.configured:
            continue
        clients.append(client)
    return clients


def not_configured_detail(venues: Iterable[str]) -> str:
    env_sets = [", ".join(VenueExecutionClient(venue).credential_env_names) for venue in venues]
    return "No configured execution venues were found. Expected one of: " + " | ".join(env_sets)


def aggregate_balance_snapshots(venue_balances: list[dict[str, Any]]) -> list[dict[str, Any]]:
    aggregates: dict[str, dict[str, Any]] = {}
    for snapshot in venue_balances:
        exchange = snapshot.get("exchange")
        for balance in snapshot.get("balances", []):
            asset = balance.get("asset")
            if not asset:
                continue
            row = aggregates.setdefault(
                asset,
                {
                    "asset": asset,
                    "free": 0.0,
                    "used": 0.0,
                    "total": 0.0,
                    "venues": [],
                },
            )
            row["free"] += float(balance.get("free") or 0.0)
            row["used"] += float(balance.get("used") or 0.0)
            row["total"] += float(balance.get("total") or 0.0)
            if exchange and exchange not in row["venues"]:
                row["venues"].append(exchange)
    return sorted(aggregates.values(), key=lambda item: item["asset"])


def reconcile_exchange_balances(
    *,
    venue: str | None = None,
    venues: Iterable[str] | str | None = None,
) -> dict[str, Any]:
    requested = requested_execution_venues(venue=venue, venues=venues)
    configured_clients = get_execution_clients(venue=venue, venues=venues, configured_only=True)
    warnings = [
        f"{client.provider.name} credentials are not configured."
        for client in get_execution_clients(venue=venue, venues=venues, configured_only=False)
        if not client.configured
    ]
    if not configured_clients:
        raise IntegrationError(not_configured_detail(requested))
    snapshots = [client.get_exchange_balances().model_dump(mode="json") for client in configured_clients]
    return {
        "requested_venues": requested,
        "configured_venues": [client.exchange_id for client in configured_clients],
        "venue_count": len(configured_clients),
        "venue_balances": snapshots,
        "aggregate_balances": aggregate_balance_snapshots(snapshots),
        "warnings": warnings,
    }


def select_order_venue(
    *,
    symbol: str,
    side: str,
    amount: float,
    order_type: str,
    price: float | None = None,
    venue: str | None = None,
    venues: Iterable[str] | str | None = None,
) -> dict[str, Any]:
    requested = requested_execution_venues(venue=venue, venues=venues)
    if venue:
        client = VenueExecutionClient(requested[0])
        return {
            "mode": "direct",
            "selected_venue": client.exchange_id,
            "selected_provider": client.provider.name,
            "considered": [
                {
                    "venue": client.exchange_id,
                    "provider": client.provider.name,
                    "configured": client.configured,
                }
            ],
            "warnings": [] if client.configured else [f"{client.provider.name} credentials are not configured."],
        }

    clients = get_execution_clients(venues=requested, configured_only=True)
    if not clients:
        raise IntegrationError(not_configured_detail(requested))

    considered: list[dict[str, Any]] = []
    warnings: list[str] = []
    best: dict[str, Any] | None = None
    fallback = clients[0] if clients else None

    for client in clients:
        try:
            quote = client.get_routing_quote(
                symbol=symbol,
                side=side,
                amount=amount,
                order_type=order_type,
                price=price,
            )
            quote["configured"] = True
        except IntegrationError as exc:
            quote = {
                "venue": client.exchange_id,
                "provider": client.provider.name,
                "configured": True,
                "score": math.inf,
                "detail": str(exc),
            }
            warnings.append(f"{client.provider.name} routing data unavailable: {exc}")
        considered.append(quote)
        score = float(quote.get("score") or math.inf)
        if math.isfinite(score) and (best is None or score < float(best.get("score") or math.inf)):
            best = quote

    if best is None and fallback is not None:
        best = {
            "venue": fallback.exchange_id,
            "provider": fallback.provider.name,
            "configured": True,
            "score": math.inf,
            "detail": "Fallback selected because no routing quotes were available.",
        }
        warnings.append("No venue routing quotes were available; used the first configured venue as fallback.")

    if best is None:
        raise IntegrationError(not_configured_detail(requested))

    return {
        "mode": "smart" if len(clients) > 1 else "single_venue",
        "selected_venue": best["venue"],
        "selected_provider": best["provider"],
        "considered": considered,
        "warnings": warnings,
    }
