"""Policy-first validation and normalization for trade proposals."""

from __future__ import annotations

import logging
from typing import Any

from backend.integrations.execution.mode import current_trading_mode, live_trading_blockers
from backend.regime.detector import get_current_regime
from backend.regime.models import MarketRegime
from backend.strategies.registry import STRATEGY_REGISTRY, resolve_strategy_name
from backend.tools.get_portfolio_state import get_portfolio_state
from backend.tools.get_risk_approval import get_risk_approval

from .models import PolicyDecision, RiskRejectionReason, TradeProposal
from .safety import approval_required, get_kill_switch_state

logger = logging.getLogger(__name__)


def _portfolio_warnings() -> list[str]:
    try:
        snapshot = get_portfolio_state({})
    except Exception as exc:
        return [f"Portfolio state unavailable during policy evaluation: {exc}"]

    warnings = list(snapshot.get("meta", {}).get("warnings") or [])
    data = snapshot.get("data") or {}
    if not data.get("updated_at"):
        warnings.append("No persisted portfolio snapshot is available.")
    return warnings


def normalize_trade_proposal(payload: TradeProposal | dict[str, Any]) -> TradeProposal:
    """Normalize inbound proposal-like payloads into the canonical proposal model."""

    if isinstance(payload, TradeProposal):
        return payload
    return TradeProposal.model_validate(payload)


def evaluate_trade_proposal(proposal: TradeProposal) -> PolicyDecision:
    proposal = normalize_trade_proposal(proposal)
    mode = current_trading_mode()

    if mode == "disabled":
        return PolicyDecision(
            proposal_id=proposal.proposal_id,
            status="rejected",
            execution_mode="disabled",
            approved=False,
            approved_size_usd=0.0,
            requires_operator_approval=False,
            blocking_reasons=["Trading is disabled. Set HERMES_TRADING_MODE to 'paper' or 'live' to enable."],
            rejection_reasons=[RiskRejectionReason.LIVE_TRADING_DISABLED],
            policy_trace=["execution_mode=disabled", "trading_disabled=blocked"],
        )

    execution_mode = "paper" if mode != "live" else "live"
    trace: list[str] = [f"execution_mode={execution_mode}"]
    warnings = _portfolio_warnings()
    blockers: list[str] = []
    rejection_reasons: list[RiskRejectionReason] = []

    kill_switch = get_kill_switch_state()
    kill_switch_active = bool(kill_switch.get("active"))
    kill_switch_reason = kill_switch.get("reason")
    if kill_switch_active:
        reason = kill_switch_reason or "Operator kill switch active."
        blockers.append(reason)
        rejection_reasons.append(RiskRejectionReason.KILL_SWITCH_ACTIVE)
        trace.append("kill_switch=active")
    else:
        trace.append("kill_switch=inactive")

    live_blockers = live_trading_blockers()
    if execution_mode == "live" and live_blockers:
        blockers.extend(live_blockers)
        rejection_reasons.append(RiskRejectionReason.LIVE_TRADING_DISABLED)
        trace.append("live_trading_unlock=blocked")
    else:
        trace.append("live_trading_unlock=ok")

    risk_response = get_risk_approval(
        {
            "symbol": proposal.symbol,
            "proposed_size_usd": proposal.requested_size_usd,
            "strategy_id": proposal.strategy_id,
            "strategy_template_id": proposal.strategy_template_id,
            "metadata": proposal.metadata,
        }
    )
    risk_payload = risk_response.get("data") or {}
    risk_reasons = list(risk_payload.get("reasons") or [])
    approved_by_risk = bool(risk_payload.get("approved"))
    max_size_usd = risk_payload.get("max_size_usd")
    if not approved_by_risk:
        blockers.extend(risk_reasons or ["Risk engine rejected proposal."])
        rejection_reasons.append(RiskRejectionReason.RISK_APPROVAL_REJECTED)
        trace.append("risk_gate=rejected")
    else:
        trace.append("risk_gate=approved")

    try:
        regime_snapshot = get_current_regime()
        current_regime = regime_snapshot.regime
    except Exception:
        current_regime = MarketRegime.UNKNOWN
    trace.append(f"regime={current_regime}")

    strategy_key = resolve_strategy_name(proposal.strategy_id, proposal.strategy_template_id)
    strategy_def = STRATEGY_REGISTRY.get(strategy_key) if strategy_key else None
    if strategy_def is not None:
        if current_regime not in strategy_def.allowed_regimes:
            blockers.append(
                f"Regime mismatch: current regime is '{current_regime}', "
                f"but strategy '{strategy_def.name}' is only allowed in {sorted(strategy_def.allowed_regimes)}."
            )
            rejection_reasons.append(RiskRejectionReason.REGIME_MISMATCH)
            trace.append("regime_gate=rejected")
        else:
            trace.append("regime_gate=approved")
    else:
        trace.append("regime_gate=skipped")

    approved_size_usd = proposal.requested_size_usd
    if max_size_usd is not None:
        approved_size_usd = min(approved_size_usd, float(max_size_usd))
        if approved_size_usd < proposal.requested_size_usd:
            warnings.append(
                f"Proposal resized from {proposal.requested_size_usd:.2f} USD to "
                f"{approved_size_usd:.2f} USD by policy."
            )
            trace.append("size=resized")

    requires_operator_approval = (
        proposal.require_operator_approval
        if proposal.require_operator_approval is not None
        else approval_required()
    )

    if blockers:
        status = "rejected"
        approved = False
        approved_size_usd = 0.0
    elif requires_operator_approval:
        status = "manual_review"
        approved = True
        rejection_reasons.append(RiskRejectionReason.APPROVAL_REQUIRED)
        trace.append("approval=required")
    else:
        status = "approved"
        approved = True
        trace.append("approval=not_required")

    if not proposal.strategy_template_id:
        warnings.append("No strategy_template_id was provided; proposal is less audit-friendly.")

    return PolicyDecision(
        proposal_id=proposal.proposal_id,
        status=status,
        execution_mode=execution_mode,
        approved=approved,
        approved_size_usd=approved_size_usd,
        requires_operator_approval=requires_operator_approval,
        live_trading_blockers=live_blockers,
        blocking_reasons=blockers,
        warnings=warnings,
        risk_confidence=risk_payload.get("confidence"),
        stop_guidance=risk_payload.get("stop_guidance"),
        policy_trace=trace,
        raw_risk_payload=risk_payload if isinstance(risk_payload, dict) else {},
        rejection_reasons=rejection_reasons,
    )
