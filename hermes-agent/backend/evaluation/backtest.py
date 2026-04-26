"""Historical strategy backtesting for scorer-based Hermes strategies."""

from __future__ import annotations

import logging
import math
import statistics
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field

from backend.evaluation.models import ReplayCase, ReplayResultRecord, ReplayRunRecord, ReplayRunStatus, ReplaySourceType
from backend.evaluation.storage import ReplayStorage
from backend.integrations import CoinGeckoClient, TwelveDataClient
from backend.models import OHLCVBar
from backend.strategies.registry import STRATEGY_REGISTRY, ScoredCandidate, get_strategy_scorer, resolve_strategy_name
from backend.workflows.models import TradingInputEvent

logger = logging.getLogger(__name__)

_DEFAULT_TIMEFRAMES = {
    "breakout": "4h",
    "mean_reversion": "1h",
    "momentum": "4h",
}

_DEFAULT_HOLDING_BARS = {
    "breakout": 8,
    "mean_reversion": 4,
    "momentum": 6,
}

_ROUND_TRIP_FEE_PCT = 0.001


class BacktestTrade(BaseModel):
    symbol: str
    strategy_name: str
    direction: str
    confidence: float
    rationale: str
    entry_time: str
    exit_time: str
    entry_price: float
    exit_price: float
    holding_bars: int
    return_pct: float
    pnl_usd: float


class BacktestMetrics(BaseModel):
    trade_count: int = 0
    win_rate: float = 0.0
    sharpe: float = 0.0
    max_drawdown: float = 0.0
    total_pnl_usd: float = 0.0


class StrategyBacktestSummary(BaseModel):
    strategy_name: str
    timeframe: str
    symbols: list[str]
    from_iso: str
    to_iso: str
    provider_map: dict[str, str] = Field(default_factory=dict)
    replay_case_id: str
    replay_run_id: str
    metrics: BacktestMetrics
    trades: list[BacktestTrade] = Field(default_factory=list)


def run_strategy_backtest(
    *,
    strategy_name: str,
    from_iso: str,
    to_iso: str,
    symbols: list[str],
    timeframe: str | None = None,
    initial_capital: float = 10_000.0,
    database_url: str | None = None,
) -> StrategyBacktestSummary:
    strategy_key = resolve_strategy_name(strategy_name)
    if strategy_key is None:
        raise ValueError(
            f"Unknown strategy {strategy_name!r}. Available: {sorted(STRATEGY_REGISTRY)}"
        )

    start_at = _parse_iso8601(from_iso)
    end_at = _parse_iso8601(to_iso)
    if end_at <= start_at:
        raise ValueError("--to must be later than --from")

    normalized_symbols = [_normalize_symbol(symbol) for symbol in symbols]
    if not normalized_symbols:
        raise ValueError("At least one symbol is required")

    effective_timeframe = timeframe or _DEFAULT_TIMEFRAMES.get(strategy_key) or STRATEGY_REGISTRY[strategy_key].timeframes[0]
    scorer = get_strategy_scorer(strategy_key)
    min_confidence = _min_confidence_for_strategy(strategy_key)
    size_usd = _position_size_for_strategy(strategy_key)
    holding_bars = _DEFAULT_HOLDING_BARS.get(strategy_key, 4)

    provider_map: dict[str, str] = {}
    trades: list[BacktestTrade] = []

    for symbol in normalized_symbols:
        bars, provider_name = _load_historical_bars(symbol, effective_timeframe, start_at, end_at)
        provider_map[symbol] = provider_name
        trades.extend(
            _run_symbol_backtest(
                strategy_name=strategy_key,
                scorer=scorer,
                symbol=symbol,
                bars=bars,
                timeframe=effective_timeframe,
                holding_bars=holding_bars,
                min_confidence=min_confidence,
                size_usd=size_usd,
            )
        )

    trades.sort(key=lambda trade: trade.exit_time)
    metrics = _summarize_trades(trades, initial_capital=initial_capital)

    storage = ReplayStorage(database_url=database_url)
    replay_case = ReplayCase(
        source_type=ReplaySourceType.BACKTEST_CLI,
        label=f"backtest:{strategy_key}:{','.join(normalized_symbols)}",
        input_event=TradingInputEvent(
            event_type="backtest_request",
            source="backtest_cli",
            received_at=datetime.now(UTC),
            strategy=strategy_key,
            timeframe=effective_timeframe,
            symbol=normalized_symbols[0] if len(normalized_symbols) == 1 else None,
            payload={
                "symbols": normalized_symbols,
                "from": start_at.isoformat(),
                "to": end_at.isoformat(),
                "strategy_name": strategy_key,
                "timeframe": effective_timeframe,
            },
            metadata={"replay_source_type": ReplaySourceType.BACKTEST_CLI.value},
        ),
        source_payload={
            "provider_map": provider_map,
            "symbols": normalized_symbols,
        },
        expected_outcome={
            "trade_count": metrics.trade_count,
            "total_pnl_usd": metrics.total_pnl_usd,
        },
        metadata={
            "initial_capital": initial_capital,
            "timeframe": effective_timeframe,
            "strategy_name": strategy_key,
        },
    )
    storage.save_replay_case(replay_case)

    replay_run = ReplayRunRecord(
        replay_case_id=replay_case.id,
        workflow_name="strategy_backtest",
        workflow_version="v1",
        mode="backtest",
        status=ReplayRunStatus.RUNNING,
        configuration={
            "strategy_name": strategy_key,
            "timeframe": effective_timeframe,
            "symbols": normalized_symbols,
            "from": start_at.isoformat(),
            "to": end_at.isoformat(),
            "initial_capital": initial_capital,
        },
        metadata={"provider_map": provider_map},
    )
    storage.save_replay_run(replay_run)
    summary = StrategyBacktestSummary(
        strategy_name=strategy_key,
        timeframe=effective_timeframe,
        symbols=normalized_symbols,
        from_iso=start_at.isoformat(),
        to_iso=end_at.isoformat(),
        provider_map=provider_map,
        replay_case_id=replay_case.id,
        replay_run_id=replay_run.id,
        metrics=metrics,
        trades=trades,
    )
    storage.update_replay_run(
        replay_run.id,
        status=ReplayRunStatus.COMPLETED.value,
        metadata={
            **replay_run.metadata,
            "summary": summary.model_dump(mode="json"),
        },
    )
    storage.save_replay_result(
        ReplayResultRecord(
            replay_run_id=replay_run.id,
            replay_case_id=replay_case.id,
            decision="execute" if metrics.total_pnl_usd >= 0 else "reject",
            status=ReplayRunStatus.COMPLETED.value,
            should_execute=metrics.total_pnl_usd >= 0,
            output=summary.model_dump(mode="json"),
            state={"trades": [trade.model_dump(mode="json") for trade in trades]},
            metadata={"provider_map": provider_map},
        )
    )
    return summary


def format_backtest_report(summary: StrategyBacktestSummary) -> str:
    metrics = summary.metrics
    provider_parts = ", ".join(
        f"{symbol}:{provider}" for symbol, provider in sorted(summary.provider_map.items())
    ) or "n/a"
    return "\n".join(
        [
            f"Strategy backtest: {summary.strategy_name}",
            f"Window: {summary.from_iso} → {summary.to_iso}",
            f"Universe: {', '.join(summary.symbols)}",
            f"Timeframe: {summary.timeframe}",
            f"Providers: {provider_parts}",
            f"Replay run: {summary.replay_run_id}",
            f"Trade count: {metrics.trade_count}",
            f"Win rate: {metrics.win_rate * 100:.2f}%",
            f"Sharpe: {metrics.sharpe:.2f}",
            f"Max drawdown: {metrics.max_drawdown * 100:.2f}%",
            f"Total PnL: ${metrics.total_pnl_usd:,.2f}",
        ]
    )


def _run_symbol_backtest(
    *,
    strategy_name: str,
    scorer,
    symbol: str,
    bars: list[dict[str, Any]],
    timeframe: str,
    holding_bars: int,
    min_confidence: float,
    size_usd: float,
) -> list[BacktestTrade]:
    if len(bars) < 60:
        logger.warning("backtest: not enough bars for %s (%d)", symbol, len(bars))
        return []

    trades: list[BacktestTrade] = []
    warmup = 52
    index = warmup
    while index < len(bars) - holding_bars:
        window = bars[: index + 1]
        candidate = _score_window(
            strategy_name=strategy_name,
            scorer=scorer,
            symbol=symbol,
            bars=window,
            timeframe=timeframe,
        )
        if candidate.direction == "watch" or candidate.confidence < min_confidence:
            index += 1
            continue

        entry_bar = window[-1]
        exit_bar = bars[index + holding_bars]
        entry_price = float(entry_bar["close"])
        exit_price = float(exit_bar["close"])
        if entry_price <= 0:
            index += 1
            continue

        side_multiplier = 1.0 if candidate.direction == "long" else -1.0
        gross_return = side_multiplier * ((exit_price - entry_price) / entry_price)
        net_return = gross_return - _ROUND_TRIP_FEE_PCT
        pnl_usd = size_usd * net_return

        trades.append(
            BacktestTrade(
                symbol=symbol,
                strategy_name=strategy_name,
                direction=candidate.direction,
                confidence=candidate.confidence,
                rationale=candidate.rationale,
                entry_time=str(entry_bar["timestamp"]),
                exit_time=str(exit_bar["timestamp"]),
                entry_price=round(entry_price, 8),
                exit_price=round(exit_price, 8),
                holding_bars=holding_bars,
                return_pct=round(net_return, 6),
                pnl_usd=round(pnl_usd, 4),
            )
        )
        index += holding_bars + 1

    return trades


def _score_window(
    *,
    strategy_name: str,
    scorer,
    symbol: str,
    bars: list[dict[str, Any]],
    timeframe: str,
) -> ScoredCandidate:
    indicator_data = _build_indicator_snapshot(bars)
    regime = _infer_regime(indicator_data)
    if strategy_name == "breakout":
        return scorer(symbol, indicator_data, ohlcv_bars=bars[-30:], regime=regime, funding_data=None)
    return scorer(symbol, indicator_data, regime=regime, funding_data=None)


def _build_indicator_snapshot(bars: list[dict[str, Any]]) -> dict[str, float | None]:
    closes = [float(bar["close"]) for bar in bars]
    highs = [float(bar["high"]) for bar in bars]
    lows = [float(bar["low"]) for bar in bars]

    sma_20 = _sma(closes, 20)
    sma_50 = _sma(closes, 50)
    atr_14 = _atr(highs, lows, closes, 14)
    bb_upper, bb_lower = _bollinger(closes, 20, 2.0)
    return {
        "close": closes[-1],
        "price": closes[-1],
        "rsi": _rsi(closes, 14),
        "rsi_14": _rsi(closes, 14),
        "ma_20": sma_20,
        "ma_50": sma_50,
        "sma_20": sma_20,
        "sma_50": sma_50,
        "atr": atr_14,
        "atr_14": atr_14,
        "bb_upper": bb_upper,
        "bb_lower": bb_lower,
        "macd_histogram": _macd_histogram(closes),
    }


def _infer_regime(indicator_data: dict[str, float | None]) -> str:
    close = indicator_data.get("close")
    ma_20 = indicator_data.get("ma_20")
    ma_50 = indicator_data.get("ma_50")
    if close is None or ma_20 is None or ma_50 is None:
        return "unknown"
    if close > ma_20 > ma_50:
        return "bullish"
    if close < ma_20 < ma_50:
        return "bearish"
    return "ranging"


def _load_historical_bars(
    symbol: str,
    timeframe: str,
    start_at: datetime,
    end_at: datetime,
) -> tuple[list[dict[str, Any]], str]:
    provider_errors: list[str] = []

    twelvedata = TwelveDataClient()
    if twelvedata.configured:
        try:
            bars = twelvedata.get_ohlcv_range(_market_data_symbol(symbol), timeframe, start_at, end_at)
            normalized = _normalize_bars(bars)
            if normalized:
                return normalized, twelvedata.provider.name
        except Exception as exc:
            provider_errors.append(f"{twelvedata.provider.name}: {exc}")

    coingecko = CoinGeckoClient()
    if coingecko.configured:
        try:
            bars = coingecko.get_ohlcv_range(symbol, start_at, end_at)
            normalized = _normalize_bars(bars)
            if normalized:
                return normalized, coingecko.provider.name
        except Exception as exc:
            provider_errors.append(f"{coingecko.provider.name}: {exc}")

    details = "; ".join(provider_errors) if provider_errors else "no configured historical data providers"
    raise RuntimeError(f"Unable to load OHLCV for {symbol}: {details}")


def _normalize_bars(bars: list[OHLCVBar | dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for bar in bars:
        if isinstance(bar, OHLCVBar):
            payload = bar.model_dump(mode="json")
        else:
            payload = dict(bar)
        try:
            timestamp = _parse_iso8601(str(payload["timestamp"]))
            normalized.append(
                {
                    "timestamp": timestamp.isoformat(),
                    "open": float(payload["open"]),
                    "high": float(payload["high"]),
                    "low": float(payload["low"]),
                    "close": float(payload["close"]),
                    "volume": float(payload["volume"]) if payload.get("volume") is not None else None,
                }
            )
        except (KeyError, TypeError, ValueError):
            continue
    normalized.sort(key=lambda bar: bar["timestamp"])
    return normalized


def _summarize_trades(trades: list[BacktestTrade], *, initial_capital: float) -> BacktestMetrics:
    if not trades:
        return BacktestMetrics()

    returns = [trade.return_pct for trade in trades]
    pnl_values = [trade.pnl_usd for trade in trades]
    equity = initial_capital
    peak = initial_capital
    max_drawdown = 0.0

    for pnl in pnl_values:
        equity += pnl
        peak = max(peak, equity)
        if peak > 0:
            max_drawdown = max(max_drawdown, (peak - equity) / peak)

    win_rate = sum(1 for value in returns if value > 0) / len(returns)
    sharpe = 0.0
    if len(returns) >= 2:
        deviation = statistics.stdev(returns)
        if deviation > 0:
            sharpe = (statistics.mean(returns) / deviation) * math.sqrt(len(returns))

    return BacktestMetrics(
        trade_count=len(trades),
        win_rate=round(win_rate, 4),
        sharpe=round(sharpe, 4),
        max_drawdown=round(max_drawdown, 4),
        total_pnl_usd=round(sum(pnl_values), 4),
    )


def _min_confidence_for_strategy(strategy_name: str) -> float:
    try:
        from backend.strategies.runners import BOT_RUNNER_REGISTRY

        runner_cls = BOT_RUNNER_REGISTRY.get(strategy_name)
        if runner_cls is not None:
            return float(getattr(runner_cls, "min_confidence", STRATEGY_REGISTRY[strategy_name].min_confidence))
    except Exception:
        pass
    return float(STRATEGY_REGISTRY[strategy_name].min_confidence)


def _position_size_for_strategy(strategy_name: str) -> float:
    try:
        from backend.strategies.runners import BOT_RUNNER_REGISTRY

        runner_cls = BOT_RUNNER_REGISTRY.get(strategy_name)
        if runner_cls is not None:
            return float(getattr(runner_cls, "default_size_usd", 100.0))
    except Exception:
        pass
    return 100.0


def _market_data_symbol(symbol: str) -> str:
    normalized = _normalize_symbol(symbol)
    return f"{normalized}/USD"


def _normalize_symbol(symbol: str) -> str:
    return str(symbol or "").strip().upper().replace("/USD", "").replace("/USDT", "")


def _parse_iso8601(value: str | datetime) -> datetime:
    if isinstance(value, datetime):
        dt = value
    else:
        text = str(value).strip().replace("Z", "+00:00")
        dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def _sma(values: list[float], period: int) -> float | None:
    if len(values) < period:
        return None
    window = values[-period:]
    return sum(window) / period


def _ema(values: list[float], period: int) -> float | None:
    if len(values) < period:
        return None
    multiplier = 2 / (period + 1)
    ema_value = sum(values[:period]) / period
    for value in values[period:]:
        ema_value = (value - ema_value) * multiplier + ema_value
    return ema_value


def _rsi(values: list[float], period: int = 14) -> float | None:
    if len(values) <= period:
        return None
    gains: list[float] = []
    losses: list[float] = []
    for previous, current in zip(values[-(period + 1) : -1], values[-period:]):
        delta = current - previous
        gains.append(max(delta, 0.0))
        losses.append(max(-delta, 0.0))
    average_gain = sum(gains) / period
    average_loss = sum(losses) / period
    if average_loss == 0:
        return 100.0
    rs = average_gain / average_loss
    return 100 - (100 / (1 + rs))


def _atr(highs: list[float], lows: list[float], closes: list[float], period: int = 14) -> float | None:
    if len(closes) <= period:
        return None
    true_ranges: list[float] = []
    for index in range(1, len(closes)):
        true_ranges.append(
            max(
                highs[index] - lows[index],
                abs(highs[index] - closes[index - 1]),
                abs(lows[index] - closes[index - 1]),
            )
        )
    if len(true_ranges) < period:
        return None
    return sum(true_ranges[-period:]) / period


def _bollinger(values: list[float], period: int = 20, stddev_mult: float = 2.0) -> tuple[float | None, float | None]:
    if len(values) < period:
        return None, None
    window = values[-period:]
    mean = sum(window) / period
    if len(window) < 2:
        return mean, mean
    deviation = statistics.pstdev(window)
    return mean + (deviation * stddev_mult), mean - (deviation * stddev_mult)


def _macd_histogram(values: list[float]) -> float | None:
    ema_fast = _ema(values, 12)
    ema_slow = _ema(values, 26)
    if ema_fast is None or ema_slow is None:
        return None
    macd_line_series: list[float] = []
    for index in range(26, len(values) + 1):
        fast = _ema(values[:index], 12)
        slow = _ema(values[:index], 26)
        if fast is None or slow is None:
            continue
        macd_line_series.append(fast - slow)
    if len(macd_line_series) < 9:
        return None
    signal_line = _ema(macd_line_series, 9)
    if signal_line is None:
        return None
    return macd_line_series[-1] - signal_line