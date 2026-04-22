"""get_risk_state — Read current risk policy state: kill-switch, limits, and live drawdown."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from backend.models import RiskState
from backend.redis_client import get_redis_client
from backend.tools._helpers import envelope, provider_ok, run_tool

logger = logging.getLogger(__name__)

_KILL_SWITCH_KEY = "hermes:risk:kill_switch"
_LIMITS_KEY = "hermes:risk:limits"
_PEAK_EQUITY_KEY = "hermes:risk:equity_peak"


def get_risk_state(_: dict | None = None) -> dict:
    def _run() -> dict:
        redis = get_redis_client()
        warnings: list[str] = []

        # --- Kill switch ---
        kill_switch_active = False
        kill_switch_reason: str | None = None
        kill_switch_set_at: str | None = None
        try:
            ks_raw = redis.get(_KILL_SWITCH_KEY)
            if ks_raw:
                ks = json.loads(ks_raw)
                kill_switch_active = bool(ks.get("active", False))
                kill_switch_reason = ks.get("reason")
                kill_switch_set_at = ks.get("set_at")
        except Exception as exc:
            logger.warning("Failed to read kill switch from Redis: %s", exc)
            warnings.append("kill_switch_read_failed")

        # --- Risk limits ---
        max_position_usd: float | None = None
        max_daily_loss_usd: float | None = None
        drawdown_limit_pct: float = 10.0
        try:
            limits_raw = redis.get(_LIMITS_KEY)
            if limits_raw:
                limits = json.loads(limits_raw)
                max_position_usd = limits.get("max_position_usd")
                max_daily_loss_usd = limits.get("max_daily_loss_usd")
                drawdown_limit_pct = float(limits.get("drawdown_limit_pct", 10.0))
        except Exception as exc:
            logger.warning("Failed to read risk limits from Redis: %s", exc)
            warnings.append("limits_read_failed")

        # --- Drawdown from portfolio state ---
        current_equity_usd: float | None = None
        peak_equity_usd: float | None = None
        current_drawdown_pct: float | None = None
        try:
            from backend.tools.get_portfolio_state import get_portfolio_state

            portfolio = get_portfolio_state({})
            current_equity_usd = portfolio.get("data", {}).get("total_equity_usd")

            if current_equity_usd is not None:
                # Update peak if higher than recorded
                peak_raw = redis.get(_PEAK_EQUITY_KEY)
                peak_equity_usd = float(peak_raw) if peak_raw else current_equity_usd
                if current_equity_usd > peak_equity_usd:
                    peak_equity_usd = current_equity_usd
                    redis.set(_PEAK_EQUITY_KEY, str(peak_equity_usd))

                if peak_equity_usd and peak_equity_usd > 0:
                    current_drawdown_pct = round((peak_equity_usd - current_equity_usd) / peak_equity_usd * 100, 2)

                if current_drawdown_pct is not None and current_drawdown_pct >= drawdown_limit_pct:
                    warnings.append(f"drawdown_limit_breached: {current_drawdown_pct:.1f}% >= {drawdown_limit_pct:.1f}%")
        except Exception as exc:
            logger.warning("Failed to compute drawdown: %s", exc)
            warnings.append("drawdown_compute_failed")

        state = RiskState(
            kill_switch_active=kill_switch_active,
            kill_switch_reason=kill_switch_reason,
            kill_switch_set_at=kill_switch_set_at,
            max_position_usd=max_position_usd,
            max_daily_loss_usd=max_daily_loss_usd,
            drawdown_limit_pct=drawdown_limit_pct,
            current_equity_usd=current_equity_usd,
            peak_equity_usd=peak_equity_usd,
            current_drawdown_pct=current_drawdown_pct,
            warnings=warnings,
        )
        return envelope("get_risk_state", [provider_ok("REDIS")], state.model_dump(mode="json"))

    return run_tool("get_risk_state", _run)
