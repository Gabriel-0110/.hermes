"""Whale-flow event strategy for following fresh smart-money accumulation."""

from __future__ import annotations

from typing import Any

from backend.strategies.performance_priors import scale_confidence_by_prior
from backend.strategies.registry import ScoredCandidate, STRATEGY_REGISTRY
from backend.trading.bot_runner import proposal_from_candidate
from backend.trading.models import TradeProposal

TRACKED_BASE_SYMBOLS = ("BTC", "ETH", "SOL", "XRP", "ADA", "AVAX")
DEFAULT_WHALE_FOLLOW_SIZE_USD = 75.0
MAX_WHALE_FOLLOW_SIZE_USD = 150.0

_STRATEGY = STRATEGY_REGISTRY["whale_follower"]


def score_whale_follower(
    symbol: str,
    whale_flow: dict[str, Any],
    *,
    regime: str = "unknown",
) -> ScoredCandidate:
    execution_symbol = _normalize_execution_symbol(symbol or whale_flow.get("symbol"))
    base_symbol = _base_symbol(execution_symbol)

    reasons: list[str] = []
    if base_symbol not in TRACKED_BASE_SYMBOLS:
        reasons.append(f"{base_symbol} is outside the configured whale-follow universe")
        return ScoredCandidate(
            symbol=execution_symbol,
            direction="watch",
            confidence=0.01,
            rationale="; ".join(reasons),
            strategy_name=_STRATEGY.name,
            strategy_version=_STRATEGY.version,
        )

    total_accumulation = _to_float(whale_flow.get("total_accumulation_usd")) or 0.0
    unique_wallet_count = _coerce_int(whale_flow.get("unique_wallet_count")) or len(whale_flow.get("wallets") or [])
    trade_count = _coerce_int(whale_flow.get("trade_count")) or 0
    avg_profit_rate = _to_float(whale_flow.get("avg_profit_rate_7d"))
    avg_win_rate = _to_float(whale_flow.get("avg_win_rate_7d"))

    score = 0.0
    if total_accumulation >= 250_000:
        score += 0.45
        reasons.append(f"Fresh whale accumulation is ${total_accumulation:,.0f} (very strong)")
    elif total_accumulation >= 100_000:
        score += 0.35
        reasons.append(f"Fresh whale accumulation is ${total_accumulation:,.0f} (strong)")
    elif total_accumulation >= 50_000:
        score += 0.25
        reasons.append(f"Fresh whale accumulation crossed ${total_accumulation:,.0f}")
    else:
        reasons.append(f"Accumulation ${total_accumulation:,.0f} is below the trigger threshold")

    if unique_wallet_count >= 4:
        score += 0.15
        reasons.append(f"{unique_wallet_count} distinct smart-money wallets participated")
    elif unique_wallet_count >= 2:
        score += 0.10
        reasons.append(f"{unique_wallet_count} distinct wallets confirm the flow")

    if trade_count >= 6:
        score += 0.10
        reasons.append(f"{trade_count} qualifying BUY trades hit within the last hour")
    elif trade_count >= 3:
        score += 0.05
        reasons.append(f"{trade_count} qualifying BUY trades hit within the last hour")

    if avg_profit_rate is not None and avg_profit_rate >= 20:
        score += 0.05
        reasons.append(f"Average 7d wallet profit rate is {avg_profit_rate:.1f}%")
    if avg_win_rate is not None and avg_win_rate >= 60:
        score += 0.05
        reasons.append(f"Average 7d wallet win rate is {avg_win_rate:.1f}%")

    regime_lower = str(regime or "unknown").lower()
    if score > 0 and ("bull" in regime_lower or "risk_on" in regime_lower):
        score += 0.05
        reasons.append(f"Macro regime supports chasing flow: {regime}")
    elif "bear" in regime_lower or "risk_off" in regime_lower:
        score -= 0.05
        reasons.append(f"Macro regime tempers aggressive flow-following: {regime}")

    confidence = round(min(max(score, 0.01), 0.95), 2)
    confidence, prior = scale_confidence_by_prior(_STRATEGY.name, confidence)
    if prior.resolved_count and abs(prior.multiplier - 1.0) >= 0.02:
        reasons.append(
            f"Strategy prior adjusted confidence x{prior.multiplier:.2f} from {prior.resolved_count} resolved signals"
        )

    direction = "long" if score >= 0.25 else "watch"

    return ScoredCandidate(
        symbol=execution_symbol,
        direction=direction,
        confidence=confidence,
        rationale="; ".join(reasons) if reasons else "Insufficient whale-flow context",
        strategy_name=_STRATEGY.name,
        strategy_version=_STRATEGY.version,
    )


def build_whale_follow_proposal(
    candidate: ScoredCandidate,
    whale_flow: dict[str, Any],
    *,
    source_agent: str = "whale_flow_worker",
    strategy_id: str = "whale_follower/v1.0",
) -> TradeProposal:
    size_usd = size_for_whale_flow(whale_flow)
    return proposal_from_candidate(
        candidate,
        size_usd=size_usd,
        source_agent=source_agent,
        strategy_id=strategy_id,
        timeframe="30m",
        metadata={
            "signal_source": "whale_flow",
            "base_symbol": _base_symbol(candidate.symbol),
            "whale_flow": whale_flow,
        },
    )


def size_for_whale_flow(whale_flow: dict[str, Any]) -> float:
    total_accumulation = _to_float(whale_flow.get("total_accumulation_usd")) or 0.0
    if total_accumulation >= 250_000:
        return MAX_WHALE_FOLLOW_SIZE_USD
    if total_accumulation >= 100_000:
        return 100.0
    return DEFAULT_WHALE_FOLLOW_SIZE_USD


def _normalize_execution_symbol(value: Any) -> str:
    symbol = str(value or "").upper().strip()
    if not symbol:
        return "UNKNOWNUSDT"
    if "/" in symbol:
        symbol = symbol.replace("/", "")
    if symbol.endswith("USDT"):
        return symbol
    if symbol.endswith("USD"):
        return symbol[:-3] + "USDT"
    return f"{symbol}USDT"


def _base_symbol(symbol: str) -> str:
    normalized = str(symbol or "").upper().replace("/", "")
    for suffix in ("USDT", "USDC", "USD"):
        if normalized.endswith(suffix):
            return normalized[: -len(suffix)]
    return normalized


def _to_float(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _coerce_int(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None