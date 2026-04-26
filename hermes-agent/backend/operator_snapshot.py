"""Operator balance snapshot import and reconciliation."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.db import HermesTimeSeriesRepository, ensure_time_series_schema, session_scope
from backend.db.session import get_engine

logger = logging.getLogger(__name__)

REQUIRED_TOP_LEVEL_KEYS = {"as_of_utc", "exchange"}


def validate_operator_snapshot(data: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for key in REQUIRED_TOP_LEVEL_KEYS:
        if key not in data:
            errors.append(f"Missing required field: {key}")
    if "capital" in data:
        capital = data["capital"]
        if not isinstance(capital, dict):
            errors.append("'capital' must be an object")
    return errors


def _compute_totals(data: dict[str, Any]) -> dict[str, float | None]:
    capital = data.get("capital") or {}
    available = capital.get("available_usdt")
    invested = capital.get("invested_usdt")
    pnl = data.get("pnl") or {}
    unrealized = pnl.get("unrealized_total_usdt")

    total = None
    if available is not None and invested is not None:
        total = float(available) + float(invested)
        if unrealized is not None:
            total += float(unrealized)

    return {
        "total_equity_usd": total,
        "available_usd": float(available) if available is not None else None,
        "invested_usd": float(invested) if invested is not None else None,
        "unrealized_pnl_usd": float(unrealized) if unrealized is not None else None,
    }


def _reconcile_with_exchange(data: dict[str, Any]) -> dict[str, Any] | None:
    exchange = data.get("exchange", "").lower()
    if exchange != "bitmart":
        return None
    try:
        from backend.integrations.execution import VenueExecutionClient

        client = VenueExecutionClient("bitmart")
        if not client.configured:
            logger.warning("operator_snapshot: BitMart not configured — skipping reconciliation")
            return {"status": "skipped", "reason": "bitmart_not_configured"}

        balances = client.get_exchange_balances()
        live_total = sum(float(b.total or 0) for b in balances.balances)

        totals = _compute_totals(data)
        operator_total = totals.get("total_equity_usd") or 0.0

        divergence_pct = 0.0
        if operator_total > 0:
            divergence_pct = abs(live_total - operator_total) / operator_total * 100

        return {
            "status": "reconciled",
            "live_total_usd": live_total,
            "operator_total_usd": operator_total,
            "divergence_pct": round(divergence_pct, 2),
            "alert": divergence_pct > 1.0,
        }
    except Exception as exc:
        logger.warning("operator_snapshot: reconciliation failed: %s", exc)
        return {"status": "failed", "error": str(exc)}


def import_operator_snapshot(data: dict[str, Any], *, reconcile: bool = True) -> dict[str, Any]:
    errors = validate_operator_snapshot(data)
    if errors:
        return {"ok": False, "errors": errors}

    as_of_str = data["as_of_utc"]
    try:
        as_of = datetime.fromisoformat(as_of_str)
        if as_of.tzinfo is None:
            as_of = as_of.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError) as exc:
        return {"ok": False, "errors": [f"Invalid as_of_utc: {exc}"]}

    totals = _compute_totals(data)
    divergence = _reconcile_with_exchange(data) if reconcile else None

    ensure_time_series_schema(get_engine())
    with session_scope() as session:
        repo = HermesTimeSeriesRepository(session)
        row = repo.insert_operator_snapshot(
            exchange=data["exchange"],
            as_of_utc=as_of,
            raw_json=data,
            total_equity_usd=totals["total_equity_usd"],
            available_usd=totals["available_usd"],
            invested_usd=totals["invested_usd"],
            unrealized_pnl_usd=totals["unrealized_pnl_usd"],
            divergence_summary=divergence,
        )

    if divergence and divergence.get("alert"):
        logger.warning(
            "operator_snapshot: divergence alert! %.2f%% divergence detected for %s",
            divergence["divergence_pct"],
            data["exchange"],
        )
        try:
            from backend.tools.send_notification import send_notification

            send_notification({
                "title": f"Balance divergence alert: {data['exchange']}",
                "message": (
                    f"Operator snapshot diverges {divergence['divergence_pct']:.1f}% from live. "
                    f"Operator: ${divergence.get('operator_total_usd', 0):.2f}, "
                    f"Live: ${divergence.get('live_total_usd', 0):.2f}"
                ),
                "severity": "warning",
            })
        except Exception as exc:
            logger.warning("operator_snapshot: notification failed: %s", exc)

    return {
        "ok": True,
        "snapshot_id": row.id,
        "exchange": row.exchange,
        "as_of_utc": row.as_of_utc.isoformat(),
        "totals": totals,
        "divergence": divergence,
    }


def import_from_file(path: str) -> dict[str, Any]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return import_operator_snapshot(data)


def import_from_stdin(raw: str) -> dict[str, Any]:
    data = json.loads(raw)
    return import_operator_snapshot(data)
