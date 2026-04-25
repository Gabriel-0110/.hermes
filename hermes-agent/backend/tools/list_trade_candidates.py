"""list_trade_candidates — Scan top crypto assets using the strategy registry."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from backend.db import ensure_time_series_schema, session_scope
from backend.db.models import StrategyEvaluationRow
from backend.db.session import get_engine
from backend.models import ListTradeCandidate
from backend.strategies.registry import STRATEGY_REGISTRY, ScoredCandidate
from backend.strategies.momentum import score_momentum
from backend.strategies.mean_reversion import score_mean_reversion
from backend.strategies.breakout import score_breakout
from backend.tools._helpers import envelope, run_tool
from backend.tools.get_funding_rates import get_funding_rates
from backend.tools.get_indicator_snapshot import get_indicator_snapshot
from backend.tools.get_market_overview import get_market_overview
from backend.tools.get_ohlcv import get_ohlcv

logger = logging.getLogger(__name__)

# Top liquid assets to scan by default
_SCAN_SYMBOLS = ["BTC/USD", "ETH/USD", "SOL/USD", "BNB/USD", "XRP/USD", "DOGE/USD", "ADA/USD", "AVAX/USD"]


def list_trade_candidates(_: dict | None = None) -> dict:
    def _run() -> dict:
        overview = get_market_overview({})
        regime = overview["data"].get("regime", "unknown") if overview.get("ok") else "unknown"
        all_providers = list(overview["meta"]["providers"])

        candidates: list[tuple[ScoredCandidate, str]] = []  # (candidate, strategy_name)
        warnings: list[str] = []
        funding_data = _fetch_funding_rates_for_symbols(_SCAN_SYMBOLS)

        for raw_symbol in _SCAN_SYMBOLS:
            clean = raw_symbol.split("/")[0]
            try:
                ind = get_indicator_snapshot({"symbol": raw_symbol})
                all_providers = _merge_providers(all_providers, ind["meta"]["providers"])
                ind_data = ind.get("data", {}) if ind.get("ok") else {}

                # Fetch OHLCV for breakout strategy
                ohlcv_bars: list[dict] = []
                try:
                    ohlcv_resp = get_ohlcv({"symbol": raw_symbol, "interval": "1h", "limit": 30})
                    if ohlcv_resp.get("ok"):
                        ohlcv_bars = ohlcv_resp.get("data", [])
                except Exception:
                    pass

                # Run all registered strategies and pick the best score
                scored: list[ScoredCandidate] = []
                for strategy_name in STRATEGY_REGISTRY:
                    try:
                        if strategy_name == "momentum":
                            s = score_momentum(clean, ind_data, regime, funding_data=funding_data, timeframe="1h")
                        elif strategy_name == "mean_reversion":
                            s = score_mean_reversion(clean, ind_data, regime, funding_data=funding_data, timeframe="1h")
                        elif strategy_name == "breakout":
                            s = score_breakout(clean, ind_data, ohlcv_bars=ohlcv_bars, regime=regime, funding_data=funding_data, timeframe="1h")
                        else:
                            continue
                        scored.append(s)
                    except Exception as exc:
                        logger.debug("list_trade_candidates: strategy %s failed for %s: %s", strategy_name, clean, exc)

                if not scored:
                    warnings.append(f"{clean}: all strategies failed — indicator data unavailable")
                    continue

                # Take the candidate with highest confidence (non-watch first, then watch)
                best = max(scored, key=lambda c: (c.direction != "watch", c.confidence))
                candidates.append((best, best.strategy_name))

            except Exception as exc:
                logger.warning("list_trade_candidates: scan failed for %s: %s", clean, exc)
                warnings.append(f"{clean}: scan error ({exc.__class__.__name__})")

        # Sort by confidence descending
        candidates.sort(key=lambda t: t[0].confidence, reverse=True)

        # Persist evaluations (fire and forget)
        _persist_evaluations([c for c, _ in candidates])

        if not candidates:
            warnings.append("No candidates scored — indicator data may be unavailable; check API keys.")
            fallback = [
                ListTradeCandidate(symbol="BTC", direction="watch", confidence=0.5, rationale=f"Fallback: indicator data unavailable; regime={regime}."),
                ListTradeCandidate(symbol="ETH", direction="watch", confidence=0.48, rationale="Fallback: await live indicator data."),
            ]
            return envelope(
                "list_trade_candidates",
                all_providers,
                [item.model_dump(mode="json") for item in fallback],
                warnings=warnings,
            )

        output = [
            {
                "symbol": c.symbol,
                "direction": c.direction,
                "confidence": c.confidence,
                "chronos_score": c.chronos_score,
                "rationale": c.rationale,
                "strategy_name": c.strategy_name,
                "strategy_version": c.strategy_version,
            }
            for c, _ in candidates
        ]

        return envelope(
            "list_trade_candidates",
            all_providers,
            output,
            warnings=warnings if warnings else None,
        )

    return run_tool("list_trade_candidates", _run)


def _persist_evaluations(candidates: list[ScoredCandidate]) -> None:
    """Persist strategy evaluations for the evaluation loop scaffold."""
    if not candidates:
        return
    try:
        engine = get_engine()
        ensure_time_series_schema(engine)
        now = datetime.now(UTC)
        rows = [
            StrategyEvaluationRow(
                eval_time=now,
                strategy_name=c.strategy_name,
                strategy_version=c.strategy_version,
                symbol=c.symbol,
                timeframe="1h",
                direction=c.direction,
                confidence=c.confidence,
                rationale=c.rationale,
                metadata_json={"chronos_score": c.chronos_score},
            )
            for c in candidates
        ]
        with session_scope() as session:
            session.add_all(rows)
    except Exception as exc:
        logger.debug("list_trade_candidates: evaluation persist failed (non-critical): %s", exc)


def _fetch_funding_rates_for_symbols(symbols: list[str]) -> dict[str, float]:
    try:
        normalized = []
        for raw in symbols:
            clean = raw.upper().replace("/", "").replace("USD", "USDT")
            normalized.append(clean if clean.endswith("USDT") else f"{clean}USDT")
        resp = get_funding_rates({"symbols": normalized, "limit": max(len(normalized), 1)})
        data = resp.get("data", {}) if resp.get("ok") or "data" in resp else {}
        entries = data.get("symbols", []) if isinstance(data, dict) else []
        out: dict[str, float] = {}
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            symbol = str(entry.get("symbol") or "").upper()
            try:
                rate = float(entry.get("funding_rate"))
            except (TypeError, ValueError):
                continue
            clean = symbol.replace("USDT", "").replace("USD", "")
            out[clean] = rate
            out[symbol] = rate
        return out
    except Exception as exc:
        logger.debug("list_trade_candidates: funding-rate fetch failed: %s", exc)
        return {}


def _f(v: object) -> float | None:
    if v is None:
        return None
    try:
        return float(v)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _merge_providers(existing: list, new: list) -> list:
    seen = {p.get("provider") if isinstance(p, dict) else getattr(p, "provider", None) for p in existing}
    for p in new:
        name = p.get("provider") if isinstance(p, dict) else getattr(p, "provider", None)
        if name not in seen:
            existing.append(p)
            seen.add(name)
    return existing

