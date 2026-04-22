"""Shared execution mode helpers.

Centralizes the decision for whether exchange execution should remain in paper
mode or is explicitly unlocked for live trading.
"""

from __future__ import annotations

import os

LIVE_TRADING_ACK_PHRASE = "I_ACKNOWLEDGE_LIVE_TRADING_RISK"


def _is_truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def current_trading_mode() -> str:
    mode = os.getenv("HERMES_TRADING_MODE", "paper").strip().lower()
    return mode if mode in {"paper", "live"} else "paper"


def is_paper_mode() -> bool:
    explicit = os.getenv("HERMES_PAPER_MODE")
    if explicit is not None and explicit.strip() != "":
        return _is_truthy(explicit)
    return current_trading_mode() != "live"


def live_trading_blockers() -> list[str]:
    blockers: list[str] = []
    if current_trading_mode() != "live":
        blockers.append("HERMES_TRADING_MODE must be set to 'live'.")
    if not _is_truthy(os.getenv("HERMES_ENABLE_LIVE_TRADING")):
        blockers.append("HERMES_ENABLE_LIVE_TRADING=true is required.")
    if os.getenv("HERMES_LIVE_TRADING_ACK", "").strip() != LIVE_TRADING_ACK_PHRASE:
        blockers.append(
            "HERMES_LIVE_TRADING_ACK must equal "
            f"{LIVE_TRADING_ACK_PHRASE!r}."
        )
    return blockers


def live_trading_enabled() -> bool:
    return not live_trading_blockers()
