"""Policy-first validation and normalization for trade proposals."""

from __future__ import annotations

from typing import Any

from backend.models import RiskState
from backend.integrations.execution.mode import current_trading_mode, live_trading_blockers
from backend.tools.get_portfolio_state import get_portfolio_state
from backend.tools.get_risk_approval import get_risk_approval
from backend.tools.get_risk_state import get_risk_state

from .models import PolicyDecision, RiskRejectionReason, TradeProposal
from .safety import approval_required, get_kill_switch_state

_QUOTE_SUFFIXES = ("USDT", "USDC", "USD", "BTC", "ETH")


def _tool_data(response: dict | None, default):
    if not isinstance(response, dict):
        return default
    data = response.get("data")
    return default if data is None else data


def _normalize_symbol_token(value: str | None) -> str:
    return "".join(ch for ch in str(value or "").upper() if ch.isalnum())


def _symbol_aliases(value: str | None) -> set[str]:
    normalized = _normalize_symbol_token(value)
    if not normalized:
        return set()
    aliases = {normalized}
    for quote in _QUOTE_SUFFIXES:
        if normalized.endswith(quote) and len(normalized) > len(quote):
            aliases.add(normalized[: -len(quote)])
            break
    return aliases


def _portfolio_positions() -> list[dict[str, Any]]:
    try:
        snapshot = get_portfolio_state({})
    except Exception:
        return []
    positions = _tool_data(snapshot, {}).get("positions") if isinstance(_tool_data(snapshot, {}), dict) else []
    return positions if isinstance(positions, list) else []


def _current_symbol_notional(symbol: str, positions: list[dict[str, Any]]) -> float:
    target_aliases = _symbol_aliases(symbol)
    if not target_aliases:
        return 0.0

    total = 0.0
    for position in positions:
        if not isinstance(position, dict):
            continue
        if not (_symbol_aliases(position.get("symbol")) & target_aliases):
            continue
        try:
            total += abs(float(position.get("notional_usd") or 0.0))
        except (TypeError, ValueError):
            continue
    return total


def _load_risk_state() -> RiskState | None:
    try:
        response = get_risk_state({})
        data = _tool_data(response, {})
        if isinstance(data, dict):
            return RiskState.model_validate(data)
    except Exception:
        return None
    return None


def _resolve_symbol_limits(state: RiskState, symbol: str) -> dict[str, float | None]:
    symbol_limits = state.symbol_limits or {}
    for alias in _symbol_aliases(symbol):
        candidate = symbol_limits.get(alias)
        if isinstance(candidate, dict):
            return {
                "max_notional_usd": _float_or_none(candidate.get("max_notional_usd")),
                "max_leverage": _float_or_none(candidate.get("max_leverage")),
            }
    return {"max_notional_usd": None, "max_leverage": None}


def _extract_requested_leverage(proposal: TradeProposal) -> float | None:
    candidates: list[Any] = [
        proposal.leverage,
        proposal.metadata.get("leverage"),
        proposal.metadata.get("requested_leverage"),
    ]
    for leg in proposal.legs:
        candidates.extend(
            [
                leg.leverage,
                leg.metadata.get("leverage"),
                leg.metadata.get("requested_leverage"),
            ]
        )

    leverage_values = [value for value in (_float_or_none(candidate) for candidate in candidates) if value is not None]
    if not leverage_values:
        return None
    return max(leverage_values)


def _apply_shared_risk_limits(
    proposal: TradeProposal,
    *,
    approved_size_usd: float,
    warnings: list[str],
    blockers: list[str],
    rejection_reasons: list[RiskRejectionReason],
    trace: list[str],
) -> float:
    risk_state = _load_risk_state()
    if risk_state is None:
        trace.append("risk_limits=unavailable")
        return approved_size_usd

    for warning in risk_state.warnings:
        if warning not in warnings:
            warnings.append(warning)

    symbol_limits = _resolve_symbol_limits(risk_state, proposal.symbol)
    notional_cap = symbol_limits.get("max_notional_usd") or risk_state.max_position_usd
    current_notional = _current_symbol_notional(proposal.symbol, _portfolio_positions())
    trace.append(
        "risk_limits="
        f"current_symbol_notional={current_notional:.2f},"
        f"notional_cap={notional_cap if notional_cap is not None else 'none'},"
        f"max_leverage={symbol_limits.get('max_leverage') or risk_state.max_leverage or 'none'}"
    )

    if notional_cap is not None:
        remaining_capacity = float(notional_cap) - current_notional
        if remaining_capacity <= 0:
            blockers.append(
                f"Position limit exceeded for {proposal.symbol}: current exposure {current_notional:.2f} USD "
                f"already meets/exceeds the configured cap of {float(notional_cap):.2f} USD."
            )
            rejection_reasons.append(RiskRejectionReason.POSITION_LIMIT_EXCEEDED)
            trace.append("risk_limits=position_cap_blocked")
            return 0.0
        if approved_size_usd > remaining_capacity:
            warnings.append(
                f"Proposal resized from {approved_size_usd:.2f} USD to {remaining_capacity:.2f} USD to stay within the configured position cap for {proposal.symbol}."
            )
            approved_size_usd = remaining_capacity
            trace.append("risk_limits=position_cap_resized")

    requested_leverage = _extract_requested_leverage(proposal)
    leverage_cap = symbol_limits.get("max_leverage") or risk_state.max_leverage
    if leverage_cap is not None and requested_leverage is not None and requested_leverage > float(leverage_cap):
        blockers.append(
            f"Requested leverage {requested_leverage:g}x exceeds the configured cap of {float(leverage_cap):g}x for {proposal.symbol}."
        )
        rejection_reasons.append(RiskRejectionReason.LEVERAGE_LIMIT_EXCEEDED)
        trace.append("risk_limits=leverage_cap_blocked")

    return max(approved_size_usd, 0.0)


def _float_or_none(value: Any) -> float | None:
    if value in (None, "", "-"):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


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
    execution_mode = "paper" if current_trading_mode() != "live" else "live"
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

    approved_size_usd = proposal.requested_size_usd
    if max_size_usd is not None:
        approved_size_usd = min(approved_size_usd, float(max_size_usd))
        if approved_size_usd < proposal.requested_size_usd:
            warnings.append(
                f"Proposal resized from {proposal.requested_size_usd:.2f} USD to "
                f"{approved_size_usd:.2f} USD by policy."
            )
            trace.append("size=resized")

    approved_size_usd = _apply_shared_risk_limits(
        proposal,
        approved_size_usd=approved_size_usd,
        warnings=warnings,
        blockers=blockers,
        rejection_reasons=rejection_reasons,
        trace=trace,
    )

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
