"""evaluate_strategy — run a named strategy scorer against a symbol and persist the result."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from pydantic import BaseModel, Field

from backend.strategies.registry import STRATEGY_REGISTRY
from backend.strategies.momentum import score_momentum
from backend.strategies.mean_reversion import score_mean_reversion
from backend.strategies.breakout import score_breakout
from backend.db import ensure_time_series_schema, session_scope
from backend.db.models import StrategyEvaluationRow
from backend.db.session import get_engine
from backend.tools._helpers import envelope, provider_ok, run_tool, validate
from backend.tools.get_funding_rates import get_funding_rates
from backend.tools.get_indicator_snapshot import get_indicator_snapshot
from backend.tools.get_market_overview import get_market_overview
from backend.tools.get_ohlcv import get_ohlcv

logger = logging.getLogger(__name__)


class EvaluateStrategyInput(BaseModel):
    strategy_name: str = Field(..., description="Name of the strategy to run (momentum, mean_reversion, breakout).")
    symbol: str = Field(..., description="Asset symbol to evaluate (e.g. 'BTC/USD' or 'BTC').")
    timeframe: str = Field(default="1h", description="Candle interval for indicator context.")


def evaluate_strategy(payload: dict) -> dict:
    def _run() -> dict:
        args = validate(EvaluateStrategyInput, payload)

        strategy_def = STRATEGY_REGISTRY.get(args.strategy_name)
        if strategy_def is None:
            available = list(STRATEGY_REGISTRY.keys())
            return envelope(
                "evaluate_strategy",
                [provider_ok("hermes_strategy_registry", f"strategy '{args.strategy_name}' not found")],
                {"error": f"Unknown strategy '{args.strategy_name}'. Available: {available}"},
                ok=False,
            )

        # Normalise symbol for indicator fetch
        raw_symbol = args.symbol.strip().upper()
        indicator_symbol = raw_symbol if "/" in raw_symbol else f"{raw_symbol}/USD"

        # Fetch market context
        overview_resp = get_market_overview({})
        regime = overview_resp.get("data", {}).get("regime", "unknown") if overview_resp.get("ok") else "unknown"

        ind_resp = get_indicator_snapshot({"symbol": indicator_symbol, "interval": args.timeframe})
        ind_data = ind_resp.get("data", {}) if ind_resp.get("ok") else {}

        funding_data = {}
        try:
            funding_resp = get_funding_rates({"symbols": [raw_symbol.replace("/", "").replace("USD", "USDT")], "limit": 1})
            funding_data = funding_resp.get("data", {}) if funding_resp.get("ok") or "data" in funding_resp else {}
        except Exception as exc:
            logger.debug("evaluate_strategy: funding-rate fetch failed for %s: %s", raw_symbol, exc)

        # Run selected strategy scorer
        name = args.strategy_name
        if name == "momentum":
            candidate = score_momentum(raw_symbol.split("/")[0], ind_data, regime, funding_data=funding_data)
        elif name == "mean_reversion":
            candidate = score_mean_reversion(raw_symbol.split("/")[0], ind_data, regime, funding_data=funding_data)
        elif name == "breakout":
            # Fetch OHLCV for volume analysis
            ohlcv_resp = get_ohlcv({"symbol": indicator_symbol, "interval": args.timeframe, "limit": 30})
            ohlcv_bars = ohlcv_resp.get("data", []) if ohlcv_resp.get("ok") else []
            candidate = score_breakout(raw_symbol.split("/")[0], ind_data, ohlcv_bars=ohlcv_bars, regime=regime, funding_data=funding_data)
        else:
            # Fallback — should not reach here due to registry check above
            candidate = score_momentum(raw_symbol.split("/")[0], ind_data, regime, funding_data=funding_data)

        # Persist evaluation
        now = datetime.now(UTC)
        row = StrategyEvaluationRow(
            eval_time=now,
            strategy_name=candidate.strategy_name,
            strategy_version=candidate.strategy_version,
            symbol=candidate.symbol,
            timeframe=args.timeframe,
            direction=candidate.direction,
            confidence=candidate.confidence,
            rationale=candidate.rationale,
            metadata_json={"regime": regime},
        )
        try:
            engine = get_engine()
            ensure_time_series_schema(engine)
            with session_scope() as session:
                session.add(row)
        except Exception as exc:
            logger.warning("evaluate_strategy: could not persist evaluation row: %s", exc)

        return envelope(
            "evaluate_strategy",
            [provider_ok("hermes_strategy_registry")],
            {
                "id": row.id,
                "strategy_name": candidate.strategy_name,
                "strategy_version": candidate.strategy_version,
                "symbol": candidate.symbol,
                "timeframe": args.timeframe,
                "direction": candidate.direction,
                "confidence": candidate.confidence,
                "rationale": candidate.rationale,
                "regime": regime,
                "eval_time": now.isoformat(),
            },
        )

    return run_tool("evaluate_strategy", _run)
