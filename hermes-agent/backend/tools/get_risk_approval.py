from __future__ import annotations

import json
import logging

from pydantic import BaseModel

from backend.models import RiskApproval
from backend.redis_client import get_redis_client
from backend.tools._helpers import envelope, run_tool, validate
from backend.tools.get_event_risk_summary import get_event_risk_summary
from backend.tools.get_volatility_metrics import get_volatility_metrics

logger = logging.getLogger(__name__)

_KILL_SWITCH_KEY = "hermes:risk:kill_switch"
_LIMITS_KEY = "hermes:risk:limits"


class GetRiskApprovalInput(BaseModel):
    symbol: str
    proposed_size_usd: float


def get_risk_approval(payload: dict) -> dict:
    def _run() -> dict:
        args = validate(GetRiskApprovalInput, payload)

        # --- Kill switch check (hard gate) ---
        try:
            redis = get_redis_client()
            ks_raw = redis.get(_KILL_SWITCH_KEY)
            if ks_raw:
                ks = json.loads(ks_raw)
                if ks.get("active"):
                    approval = RiskApproval(
                        approved=False,
                        max_size_usd=0.0,
                        confidence=0.0,
                        reasons=[f"KILL SWITCH ACTIVE: {ks.get('reason', 'no reason set')}"],
                        stop_guidance="Kill switch is engaged. No new positions allowed until cleared via set_kill_switch.",
                    )
                    return envelope("get_risk_approval", [], approval.model_dump(mode="json"))
        except Exception as exc:
            logger.warning("get_risk_approval: kill switch read failed: %s", exc)

        # --- Load risk limits ---
        max_position_usd: float | None = None
        drawdown_limit_pct: float = 10.0
        try:
            redis = get_redis_client()
            limits_raw = redis.get(_LIMITS_KEY)
            if limits_raw:
                limits = json.loads(limits_raw)
                max_position_usd = limits.get("max_position_usd")
                drawdown_limit_pct = float(limits.get("drawdown_limit_pct", 10.0))
        except Exception as exc:
            logger.warning("get_risk_approval: limits read failed: %s", exc)

        # --- Market risk checks ---
        volatility = get_volatility_metrics({"symbol": args.symbol})
        event_risk = get_event_risk_summary({"query": args.symbol})
        realized_vol = volatility["data"].get("realized_volatility") or 0
        severity = event_risk["data"].get("severity", "medium")

        reasons = [
            f"realized_volatility={realized_vol}",
            f"event_risk_severity={severity}",
        ]

        # Position size cap
        effective_max = args.proposed_size_usd
        if max_position_usd is not None:
            effective_max = min(effective_max, max_position_usd)
            if args.proposed_size_usd > max_position_usd:
                reasons.append(f"proposed_size capped at max_position_usd={max_position_usd}")

        size_multiplier = 0.5 if severity == "medium" else 1.0
        approved_size = effective_max * size_multiplier

        approved = realized_vol < 0.08 and severity != "high"

        approval = RiskApproval(
            approved=approved,
            max_size_usd=approved_size,
            confidence=0.65 if approved else 0.35,
            reasons=reasons,
            stop_guidance="Use volatility-adjusted invalidation and re-check before execution.",
        )
        providers = volatility["meta"]["providers"] + event_risk["meta"]["providers"]
        return envelope("get_risk_approval", providers, approval.model_dump(mode="json"))

    return run_tool("get_risk_approval", _run)

