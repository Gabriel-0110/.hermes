"""Local validation runner for the Hermes trading workflow graph."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging

from .deps import TradingWorkflowDeps
from .graph import run_trading_workflow
from .models import TradingInputEvent


def build_sample_event() -> TradingInputEvent:
    return TradingInputEvent(
        symbol="BTCUSDT",
        timeframe="15m",
        strategy="momentum_v1",
        signal="entry",
        direction="buy",
        price=68_500.0,
        alert_id="alert_sample_btc_001",
        correlation_id="corr_sample_btc_001",
        payload={"origin": "validation_runner", "confidence_hint": 0.74},
        metadata={"environment": "local"},
    )


async def _run(model: str | None) -> None:
    deps = TradingWorkflowDeps(agent_model=model)
    result = await run_trading_workflow(build_sample_event(), deps=deps)
    payload = {
        "output": result.output.model_dump(mode="json"),
        "state": result.state.model_dump(mode="json"),
    }
    print(json.dumps(payload, indent=2, sort_keys=True, default=str))


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the local Hermes trading workflow validation graph")
    parser.add_argument(
        "--model",
        default=None,
        help="Optional PydanticAI model name such as openai:gpt-5.2. If omitted, TestModel validates deterministic outputs.",
    )
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(levelname)s %(name)s: %(message)s",
    )
    asyncio.run(_run(args.model))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
