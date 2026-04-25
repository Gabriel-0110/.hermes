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
    strategy_id: str | None = None
    strategy_template_id: str | None = None
    metadata: dict | None = None


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
        carry_trade_max_equity_pct: float = 30.0
        try:
            redis = get_redis_client()
            limits_raw = redis.get(_LIMITS_KEY)
            if limits_raw:
                limits = json.loads(limits_raw)
                max_position_usd = limits.get("max_position_usd")
                drawdown_limit_pct = float(limits.get("drawdown_limit_pct", 10.0))
            carry_trade_max_equity_pct = float(limits.get("carry_trade_max_equity_pct", 30.0))
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

        if _is_carry_trade(args):
            try:
                from backend.tools.get_portfolio_state import get_portfolio_state

                portfolio = get_portfolio_state({})
                current_equity = portfolio.get("data", {}).get("total_equity_usd")
                if current_equity is not None:
                    carry_cap_usd = float(current_equity) * (carry_trade_max_equity_pct / 100.0)
                    effective_max = min(effective_max, carry_cap_usd)
                    reasons.append(
                        f"carry_trade capped at {carry_trade_max_equity_pct:.1f}% of equity "
                        f"(cap_usd={carry_cap_usd:.2f})"
                    )
                    if args.proposed_size_usd > carry_cap_usd:
                        reasons.append(
                            f"proposed carry allocation resized from {args.proposed_size_usd:.2f} to {carry_cap_usd:.2f}"
                        )
            except Exception as exc:
                logger.warning("get_risk_approval: carry cap evaluation failed: %s", exc)
                reasons.append("carry_trade_cap_evaluation_failed")

        size_multiplier = 0.5 if severity == "medium" else 1.0
        approved_size = effective_max * size_multiplier

        approved = realized_vol < 0.08 and severity != "high" and approved_size > 0

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


def _is_carry_trade(args: GetRiskApprovalInput) -> bool:
    metadata = args.metadata if isinstance(args.metadata, dict) else {}
    if metadata.get("carry_trade") is True:
        return True

    for value in (args.strategy_id, args.strategy_template_id):
        normalized = str(value or "").strip().lower()
        if "carry" in normalized:
            return True
    return False

