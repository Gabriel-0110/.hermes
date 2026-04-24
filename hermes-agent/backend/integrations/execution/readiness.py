"""Live execution readiness classification for exchange clients."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable, Literal, Protocol

from pydantic import BaseModel, Field

from backend.integrations.execution.mode import is_paper_mode, live_trading_blockers


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
    signed_writes_verified: bool
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
            signed_writes_verified=False,
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
            signed_writes_verified=False,
            blockers=[f"{exchange_label} credentials are not configured. Missing one or more of: {missing}."],
        )

    try:
        if private_read_probe is not None:
            private_read_probe()
    except Exception as exc:
        return LiveExecutionReadiness(
            exchange=exchange,
            venue=client.exchange_id,
            account_type=client.account_type,
            status="degraded_private_access",
            live_env_unlocked=True,
            credentials_configured=True,
            private_reads_working=False,
            signed_writes_verified=False,
            blockers=[f"Private {exchange_label} read probe failed: {exc}"],
        )

    write_verified = False
    if signed_write_probe is not None:
        try:
            write_verified = bool(signed_write_probe())
        except Exception as exc:
            return LiveExecutionReadiness(
                exchange=exchange,
                venue=client.exchange_id,
                account_type=client.account_type,
                status="read_only_live",
                live_env_unlocked=True,
                credentials_configured=True,
                private_reads_working=True,
                signed_writes_verified=False,
                blockers=[f"Signed {exchange_label} write probe failed: {exc}"],
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
            signed_writes_verified=True,
        )

    return LiveExecutionReadiness(
        exchange=exchange,
        venue=client.exchange_id,
        account_type=client.account_type,
        status="read_only_live",
        live_env_unlocked=True,
        credentials_configured=True,
        private_reads_working=True,
        signed_writes_verified=False,
        blockers=[f"Signed {exchange_label} write capability has not been verified."],
    )
