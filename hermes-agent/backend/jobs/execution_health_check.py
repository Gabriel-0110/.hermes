"""Execution health check job.

Queries the configured exchange for API connectivity, account balances,
and open orders, then prints a markdown-formatted summary suitable for
the cron prompt context.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime

from backend.integrations.base import IntegrationError, MissingCredentialError
from backend.integrations.execution import VenueExecutionClient
from backend.models import ExchangeBalances, ExecutionOrder

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class ExecutionHealthSummary:
    exchange: str
    account_type: str
    configured: bool
    connected: bool
    readiness_status: str | None
    futures_equity_usd: float | None
    spot_usdt_balance: float | None
    open_orders_count: int
    balances: list[dict] = field(default_factory=list)
    open_orders: list[ExecutionOrder] = field(default_factory=list)
    checked_at: str = ""
    error: str | None = None

    def to_markdown(self) -> str:
        lines = [
            "# Execution Health Check",
            "",
            f"- Exchange: `{self.exchange}`",
            f"- Account type: `{self.account_type}`",
            f"- Configured: {'yes' if self.configured else 'no'}",
            f"- Connected: {'yes' if self.connected else 'no'}",
            f"- Readiness: `{self.readiness_status or 'unknown'}`",
            f"- Checked at: {self.checked_at}",
        ]
        if self.error:
            lines += ["", f"**Error:** {self.error}"]
            return "\n".join(lines)

        lines += [""]
        if self.futures_equity_usd is not None:
            lines.append(f"- Futures equity: ${self.futures_equity_usd:,.2f} USDT")
        if self.spot_usdt_balance is not None:
            lines.append(f"- Spot USDT balance: ${self.spot_usdt_balance:,.2f}")
        lines.append(f"- Open orders: {self.open_orders_count}")

        if self.balances:
            lines += ["", "## Balances"]
            for b in self.balances:
                asset = b.get("asset", "?")
                total = b.get("total")
                free = b.get("free")
                used = b.get("used")
                parts = [f"**{asset}**"]
                if total is not None:
                    parts.append(f"total={total:.4f}")
                if free is not None:
                    parts.append(f"free={free:.4f}")
                if used is not None and used > 0:
                    parts.append(f"used={used:.4f}")
                lines.append("- " + "  ".join(parts))

        if self.open_orders:
            lines += ["", "## Open Orders"]
            for order in self.open_orders:
                price_str = f"@ {order.price}" if order.price else ""
                lines.append(
                    f"- `{order.symbol}` {order.side} {order.order_type} "
                    f"{order.amount} {price_str}  (id: {order.order_id})"
                )

        if not self.configured:
            lines += ["", "**STATUS: NOT_CONFIGURED** — exchange credentials missing."]
        elif not self.connected:
            lines += ["", "**STATUS: CRITICAL** — exchange API is unreachable or auth failed."]
        else:
            lines += ["", "**STATUS: OK**"]

        return "\n".join(lines)


def run_execution_health_check(
    *,
    exchange_id: str = "bitmart",
    account_type: str | None = None,
) -> ExecutionHealthSummary:
    now = datetime.now(UTC).isoformat()
    try:
        client = VenueExecutionClient(exchange_id, account_type=account_type)
    except Exception as exc:
        return ExecutionHealthSummary(
            exchange=exchange_id,
            account_type=account_type or "unknown",
            configured=False,
            connected=False,
            readiness_status="error",
            futures_equity_usd=None,
            spot_usdt_balance=None,
            open_orders_count=0,
            checked_at=now,
            error=f"Client init failed: {exc}",
        )

    # API connectivity + readiness
    try:
        status = client.get_execution_status()
        configured = status.configured
        connected = status.connected
        readiness_status = status.readiness_status
    except Exception as exc:
        return ExecutionHealthSummary(
            exchange=exchange_id,
            account_type=account_type or "unknown",
            configured=False,
            connected=False,
            readiness_status="error",
            futures_equity_usd=None,
            spot_usdt_balance=None,
            open_orders_count=0,
            checked_at=now,
            error=f"Status check failed: {exc}",
        )

    futures_equity_usd: float | None = None
    spot_usdt_balance: float | None = None
    raw_balances: list[dict] = []
    open_orders: list[ExecutionOrder] = []

    # Balances
    try:
        exchange_balances: ExchangeBalances = client.get_exchange_balances()
        raw_balances = [
            {
                "asset": b.asset,
                "free": b.free,
                "used": b.used,
                "total": b.total,
            }
            for b in exchange_balances.balances
            if b.total and b.total > 0
        ]
        # Extract key balance figures
        for b in exchange_balances.balances:
            if b.asset.upper() in ("USDT", "USD"):
                if exchange_balances.account_type in ("contract", "futures", "swap"):
                    if b.total is not None:
                        futures_equity_usd = (futures_equity_usd or 0.0) + b.total
                else:
                    if b.total is not None:
                        spot_usdt_balance = (spot_usdt_balance or 0.0) + b.total
    except (IntegrationError, MissingCredentialError) as exc:
        logger.warning("Balance fetch failed: %s", exc)
    except Exception as exc:
        logger.warning("Unexpected balance fetch error: %s", exc)

    # Open orders
    try:
        open_orders = client.get_open_orders()
    except (IntegrationError, MissingCredentialError) as exc:
        logger.warning("Open orders fetch failed: %s", exc)
    except Exception as exc:
        logger.warning("Unexpected open orders error: %s", exc)

    return ExecutionHealthSummary(
        exchange=status.exchange,
        account_type=status.account_type,
        configured=configured,
        connected=connected,
        readiness_status=readiness_status,
        futures_equity_usd=futures_equity_usd,
        spot_usdt_balance=spot_usdt_balance,
        open_orders_count=len(open_orders),
        balances=raw_balances,
        open_orders=open_orders,
        checked_at=now,
    )


def main() -> int:
    summary = run_execution_health_check()
    print(summary.to_markdown())
    return 0 if summary.connected else 1


if __name__ == "__main__":
    raise SystemExit(main())
