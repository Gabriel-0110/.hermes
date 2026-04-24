"""Live execution readiness classification for exchange clients."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable, Literal, Protocol

from pydantic import BaseModel, Field

from backend.integrations.execution.mode import is_paper_mode, live_trading_blockers
from backend.integrations.execution.private_read import classify_private_read_exception


ReadinessState = Literal[
    "not_live",
    "blocked_missing_credentials",
    "degraded_private_access",
    "read_only_live",
    "api_execution_ready",
]


class ReadinessClient(Protocol):
    provider: Any
    exchange_id: str
    account_type: str
    configured: bool
    credential_env_names: list[str]


class LiveExecutionReadiness(BaseModel):
    exchange: str
    venue: str
    account_type: str
    status: ReadinessState
    live_env_unlocked: bool
    credentials_configured: bool
    private_reads_working: bool
    private_read_failure: str | None = None
    signed_writes_verified: bool
    signed_write_failure: str | None = None
    copy_trading_api_supported: bool = False
    copy_trading_api_verified: bool = False
    blockers: list[str] = Field(default_factory=list)
    checked_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @property
    def api_execution_ready(self) -> bool:
        return self.status == "api_execution_ready"


def classify_live_execution_readiness(
    client: ReadinessClient,
    *,
    private_read_probe: Callable[[], Any] | None = None,
    signed_write_probe: Callable[[], bool] | None = None,
) -> LiveExecutionReadiness:
    """Return a safe, operator-facing readiness classification.

    The classifier short-circuits before private exchange calls when live trading
    is not explicitly unlocked or credentials are missing.
    """

    exchange = str(getattr(client.provider, "name", client.exchange_id.upper()))
    exchange_label = "BitMart" if exchange.upper() == "BITMART" else exchange
    blockers = live_trading_blockers()
    if is_paper_mode() and not any("HERMES_TRADING_MODE" in blocker for blocker in blockers):
        blockers.append("HERMES_PAPER_MODE must be disabled for live API execution.")
    live_unlocked = not blockers
    if not live_unlocked:
        return LiveExecutionReadiness(
            exchange=exchange,
            venue=client.exchange_id,
            account_type=client.account_type,
            status="not_live",
            live_env_unlocked=False,
            credentials_configured=client.configured,
            private_reads_working=False,
            private_read_failure=None,
            signed_writes_verified=False,
            signed_write_failure=None,
            blockers=blockers,
        )

    if not client.configured:
        missing = ", ".join(client.credential_env_names)
        return LiveExecutionReadiness(
            exchange=exchange,
            venue=client.exchange_id,
            account_type=client.account_type,
            status="blocked_missing_credentials",
            live_env_unlocked=True,
            credentials_configured=False,
            private_reads_working=False,
            private_read_failure=None,
            signed_writes_verified=False,
            signed_write_failure=None,
            blockers=[f"{exchange_label} credentials are not configured. Missing one or more of: {missing}."],
        )

    try:
        if private_read_probe is not None:
            private_read_probe()
    except Exception as exc:
        failure = classify_private_read_exception(exc)
        return LiveExecutionReadiness(
            exchange=exchange,
            venue=client.exchange_id,
            account_type=client.account_type,
            status="degraded_private_access",
            live_env_unlocked=True,
            credentials_configured=True,
            private_reads_working=False,
            private_read_failure=failure,
            signed_writes_verified=False,
            signed_write_failure=None,
            blockers=[f"Private {exchange_label} read probe failed [{failure}]: {exc}"],
        )

    write_verified = False
    write_failure: str | None = None
    if signed_write_probe is not None:
        try:
            write_result = signed_write_probe()
            if isinstance(write_result, bool):
                write_verified = write_result
            else:
                write_verified = bool(getattr(write_result, "verified", False))
                status = getattr(write_result, "status", None)
                write_failure = None if write_verified else str(status or "unknown_write_failure")
        except Exception as exc:
            write_failure = str(getattr(exc, "classification", None) or getattr(exc, "status", None) or "unknown_write_failure")
            return LiveExecutionReadiness(
                exchange=exchange,
                venue=client.exchange_id,
                account_type=client.account_type,
                status="read_only_live",
                live_env_unlocked=True,
                credentials_configured=True,
                private_reads_working=True,
                private_read_failure=None,
                signed_writes_verified=False,
                signed_write_failure=write_failure,
                blockers=[f"Signed {exchange_label} write probe failed [{write_failure}]: {exc}"],
            )

    if write_verified:
        return LiveExecutionReadiness(
            exchange=exchange,
            venue=client.exchange_id,
            account_type=client.account_type,
            status="api_execution_ready",
            live_env_unlocked=True,
            credentials_configured=True,
            private_reads_working=True,
            private_read_failure=None,
            signed_writes_verified=True,
            signed_write_failure=None,
        )

    blocker = (
        f"Signed {exchange_label} write capability check failed [{write_failure}]."
        if write_failure
        else f"Signed {exchange_label} write capability has not been verified."
    )
    return LiveExecutionReadiness(
        exchange=exchange,
        venue=client.exchange_id,
        account_type=client.account_type,
        status="read_only_live",
        live_env_unlocked=True,
        credentials_configured=True,
        private_reads_working=True,
        private_read_failure=None,
        signed_writes_verified=False,
        signed_write_failure=write_failure,
        blockers=[blocker],
    )


def execution_support_matrix(readiness: LiveExecutionReadiness) -> dict[str, Any]:
    """Flatten readiness into an operator-facing support matrix."""

    return {
        "live_env_unlocked": readiness.live_env_unlocked,
        "credentials_configured": readiness.credentials_configured,
        "private_futures_reads_working": readiness.private_reads_working,
        "signed_futures_writes_verified": readiness.signed_writes_verified,
        "readiness_state": readiness.status,
        "read_failure_category": readiness.private_read_failure,
        "write_failure_category": readiness.signed_write_failure,
        "copy_trading_api_automation_supported": readiness.copy_trading_api_supported,
        "copy_trading_api_automation_verified": readiness.copy_trading_api_verified,
        "blockers": list(readiness.blockers),
    }
