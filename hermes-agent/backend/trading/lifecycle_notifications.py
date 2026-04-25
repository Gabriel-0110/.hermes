"""Lifecycle notification helpers for trading events.

Reuses the existing ``send_notification`` infrastructure to emit operator
alerts at key lifecycle points: proposal created/blocked/approved, approval
gates, paper/live execution outcomes, kill-switch activations, and portfolio
sync results.

Notification channels are controlled by the ``HERMES_NOTIFY_CHANNELS``
environment variable (comma-separated: ``log``, ``slack``, ``telegram``).
Default is ``log`` only, which records the event in the observability audit
trail without sending external messages.

All functions in this module are **fire-and-forget**: they catch every
exception internally and never raise, so calling code never breaks the
trading path.
"""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------
# Channel resolution
# --------------------------------------------------------------------------


def _default_channels() -> list[str]:
    """Return the operator-configured notification channels.

    Reads ``HERMES_NOTIFY_CHANNELS`` (e.g. ``"slack,telegram"``).
    Defaults to ``["log"]`` so events always appear in the audit trail.
    """
    raw = os.getenv("HERMES_NOTIFY_CHANNELS", "log")
    channels = [c.strip().lower() for c in raw.split(",") if c.strip()]
    return channels or ["log"]


# --------------------------------------------------------------------------
# Internal dispatcher
# --------------------------------------------------------------------------


def _emit(
    *,
    title: str,
    message: str,
    severity: str = "info",
    notification_type: str,
    metadata: dict[str, Any] | None = None,
) -> None:
    """Dispatch a lifecycle notification through the configured channels.

    Silently swallows any error so callers are never affected.
    """
    try:
        from backend.tools.send_notification import _dispatch_notification, SendNotificationInput

        args = SendNotificationInput(
            channels=_default_channels(),
            title=title,
            message=message,
            severity=severity,
            notification_type=notification_type,
            metadata=metadata or {},
        )
        _dispatch_notification(args)
    except Exception as exc:
        logger.debug("lifecycle_notifications: emit failed (%s): %s", notification_type, exc)


# --------------------------------------------------------------------------
# Proposal lifecycle
# --------------------------------------------------------------------------


def notify_proposal_created(
    *,
    proposal_id: str,
    symbol: str,
    side: str,
    size_usd: float,
    source_agent: str,
    execution_mode: str,
) -> None:
    """Emit when a trade proposal enters evaluation."""
    mode_tag = "[PAPER] " if execution_mode != "live" else ""
    _emit(
        title=f"{mode_tag}Proposal created — {symbol}",
        message=(
            f"{mode_tag}New trade proposal submitted: {symbol} {side.upper()} "
            f"${size_usd:,.2f} from {source_agent}."
        ),
        severity="info",
        notification_type="proposal_created",
        metadata={
            "proposal_id": proposal_id,
            "symbol": symbol,
            "side": side,
            "size_usd": size_usd,
            "execution_mode": execution_mode,
            "source_agent": source_agent,
        },
    )


def notify_proposal_blocked(
    *,
    proposal_id: str,
    symbol: str,
    execution_mode: str,
    blocking_reasons: list[str],
) -> None:
    """Emit when a proposal is rejected by policy/risk."""
    mode_tag = "[PAPER] " if execution_mode != "live" else ""
    reasons_text = "; ".join(blocking_reasons) if blocking_reasons else "policy rejected"
    _emit(
        title=f"{mode_tag}Proposal blocked — {symbol}",
        message=f"{mode_tag}Proposal for {symbol} was blocked by policy: {reasons_text}",
        severity="warning",
        notification_type="proposal_blocked",
        metadata={
            "proposal_id": proposal_id,
            "symbol": symbol,
            "execution_mode": execution_mode,
            "blocking_reasons": ", ".join(blocking_reasons),
        },
    )


def notify_approval_required(
    *,
    proposal_id: str,
    symbol: str,
    side: str,
    size_usd: float,
    execution_mode: str,
    approval_id: str | None = None,
) -> None:
    """Emit when operator approval is required before execution can proceed."""
    mode_tag = "[PAPER] " if execution_mode != "live" else ""
    _emit(
        title=f"{mode_tag}Approval required — {symbol}",
        message=(
            f"{mode_tag}Operator approval needed before executing "
            f"{symbol} {side.upper()} ${size_usd:,.2f}."
            + (f" approval_id={approval_id}" if approval_id else "")
        ),
        severity="warning",
        notification_type="approval_required",
        metadata={
            "proposal_id": proposal_id,
            "symbol": symbol,
            "side": side,
            "size_usd": size_usd,
            "execution_mode": execution_mode,
            "approval_id": approval_id or "",
        },
    )


def notify_approval_granted(
    *,
    approval_id: str,
    symbol: str,
    side: str,
    amount: float,
) -> None:
    """Emit when an operator grants approval for a pending execution."""
    _emit(
        title=f"Approval granted — {symbol}",
        message=f"Operator approved execution: {symbol} {side.upper()} {amount}. approval_id={approval_id}",
        severity="info",
        notification_type="approval_granted",
        metadata={
            "approval_id": approval_id,
            "symbol": symbol,
            "side": side,
            "amount": amount,
        },
    )


def notify_approval_rejected(
    *,
    approval_id: str,
    symbol: str,
    reason: str | None = None,
) -> None:
    """Emit when an operator rejects a pending execution approval."""
    _emit(
        title=f"Approval rejected — {symbol}",
        message=(
            f"Operator rejected execution approval for {symbol}."
            + (f" Reason: {reason}" if reason else "")
        ),
        severity="warning",
        notification_type="approval_rejected",
        metadata={
            "approval_id": approval_id,
            "symbol": symbol,
            "reason": reason or "",
        },
    )


# --------------------------------------------------------------------------
# Execution outcomes
# --------------------------------------------------------------------------


def notify_paper_execution_completed(
    *,
    symbol: str,
    side: str,
    size_usd: float,
    proposal_id: str | None = None,
    correlation_id: str | None = None,
) -> None:
    """Emit when a paper (simulated) execution completes successfully."""
    _emit(
        title=f"[PAPER] Simulated execution — {symbol}",
        message=(
            f"[PAPER] Simulated order filled: {symbol} {side.upper()} "
            f"${size_usd:,.2f}. No real funds were used."
        ),
        severity="info",
        notification_type="paper_execution_completed",
        metadata={
            "symbol": symbol,
            "side": side,
            "size_usd": size_usd,
            "proposal_id": proposal_id or "",
            "correlation_id": correlation_id or "",
            "execution_mode": "paper",
        },
    )


def notify_live_execution_submitted(
    *,
    symbol: str,
    side: str,
    order_id: str,
    amount: float,
    proposal_id: str | None = None,
    correlation_id: str | None = None,
) -> None:
    """Emit when a live order is successfully placed on the exchange."""
    _emit(
        title=f"Live order submitted — {symbol}",
        message=(
            f"LIVE order placed: {symbol} {side.upper()} {amount} "
            f"| order_id={order_id}"
        ),
        severity="info",
        notification_type="live_execution_submitted",
        metadata={
            "symbol": symbol,
            "side": side,
            "amount": amount,
            "order_id": order_id,
            "proposal_id": proposal_id or "",
            "correlation_id": correlation_id or "",
            "execution_mode": "live",
        },
    )


def notify_live_execution_failed(
    *,
    symbol: str,
    side: str,
    error: str,
    proposal_id: str | None = None,
    correlation_id: str | None = None,
) -> None:
    """Emit when a live order placement fails."""
    _emit(
        title=f"Live execution FAILED — {symbol}",
        message=f"LIVE order failed for {symbol} {side.upper()}: {error}",
        severity="error",
        notification_type="live_execution_failed",
        metadata={
            "symbol": symbol,
            "side": side,
            "error": error,
            "proposal_id": proposal_id or "",
            "correlation_id": correlation_id or "",
            "execution_mode": "live",
        },
    )


def notify_bracket_attachment_failed(
    *,
    symbol: str,
    exchange: str,
    entry_order_id: str | None,
    failures: dict[str, dict[str, Any]],
    parent_client_order_id: str | None = None,
) -> None:
    """Emit when best-effort post-entry TP/SL placement fails.

    The entry order may already be live, so this is escalated as a risk alert even
    though the parent placement succeeded.
    """

    failure_summaries: list[str] = []
    for label, details in failures.items():
        trigger = details.get("trigger_price")
        category = details.get("failure_category")
        error = details.get("error")
        summary = label.replace("_", " ")
        if trigger:
            summary += f" @ {trigger}"
        if category:
            summary += f" [{category}]"
        if error:
            summary += f": {error}"
        failure_summaries.append(summary)

    entry_ref = entry_order_id or "unknown"
    parent_ref = f" client_order_id={parent_client_order_id}." if parent_client_order_id else ""
    _emit(
        title=f"Bracket follow-up FAILED — {symbol}",
        message=(
            f"Entry order {entry_ref} on {exchange} was submitted, but follow-up bracket placement failed: "
            f"{' ; '.join(failure_summaries)}.{parent_ref} Immediate operator review is recommended."
        ),
        severity="high",
        notification_type="bracket_attachment_failed",
        metadata={
            "symbol": symbol,
            "exchange": exchange,
            "entry_order_id": entry_order_id or "",
            "parent_client_order_id": parent_client_order_id or "",
            "failed_legs": ", ".join(sorted(failures.keys())),
            "failure_count": len(failures),
        },
    )


# --------------------------------------------------------------------------
# Kill switch
# --------------------------------------------------------------------------


def notify_kill_switch_blocked(
    *,
    symbol: str,
    reason: str | None = None,
    trigger: str = "kill_switch",
) -> None:
    """Emit when an execution is blocked by the kill switch or drawdown guard."""
    trigger_label = "Drawdown guard" if trigger == "drawdown" else "Kill switch"
    detail = f" Reason: {reason}" if reason else ""
    _emit(
        title=f"🛑 {trigger_label} blocked — {symbol}",
        message=f"{trigger_label} blocked execution for {symbol}.{detail}",
        severity="critical",
        notification_type="kill_switch_blocked",
        metadata={
            "symbol": symbol,
            "reason": reason or "",
            "trigger": trigger,
        },
    )


# --------------------------------------------------------------------------
# Portfolio sync
# --------------------------------------------------------------------------


def notify_portfolio_sync_completed(
    *,
    account_id: str,
    total_equity_usd: float | None,
    positions_count: int,
) -> None:
    """Emit when a portfolio sync from the exchange succeeds."""
    equity_str = f"${total_equity_usd:,.2f}" if total_equity_usd is not None else "unknown"
    _emit(
        title=f"Portfolio sync completed — {account_id}",
        message=(
            f"Portfolio snapshot updated for account {account_id}. "
            f"Total equity: {equity_str} | Positions: {positions_count}"
        ),
        severity="info",
        notification_type="portfolio_sync_completed",
        metadata={
            "account_id": account_id,
            "total_equity_usd": total_equity_usd if total_equity_usd is not None else "",
            "positions_count": positions_count,
        },
    )


def notify_portfolio_sync_failed(
    *,
    account_id: str,
    error: str,
) -> None:
    """Emit when a portfolio sync fails."""
    _emit(
        title=f"Portfolio sync FAILED — {account_id}",
        message=f"Portfolio sync failed for account {account_id}: {error}",
        severity="error",
        notification_type="portfolio_sync_failed",
        metadata={
            "account_id": account_id,
            "error": error,
        },
    )
