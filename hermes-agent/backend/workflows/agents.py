"""PydanticAI helpers for typed node outputs in the trading workflow."""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel
from pydantic_ai import Agent
from pydantic_ai.models.test import TestModel

from backend.observability import derived_audit_context
from backend.observability.service import get_observability_service

from .deps import TradingWorkflowDeps

logger = logging.getLogger(__name__)


def _build_agent(
    *,
    name: str,
    system_prompt: str,
    output_model: type[BaseModel],
    deps: TradingWorkflowDeps,
    fallback_output: BaseModel,
) -> Agent[None, Any]:
    model = deps.agent_model
    if model is None:
        model = TestModel(custom_output_args=fallback_output.model_dump(mode="json"))

    return Agent(
        model=model,
        output_type=output_model,
        system_prompt=system_prompt,
        defer_model_check=True,
        name=name,
        instrument=False,
    )


async def run_typed_agent(
    *,
    name: str,
    system_prompt: str,
    prompt: str,
    output_model: type[BaseModel],
    deps: TradingWorkflowDeps,
    fallback_output: BaseModel,
) -> BaseModel:
    """Run a typed PydanticAI agent and fall back to deterministic output if needed."""

    observability = get_observability_service()

    if not deps.use_pydantic_ai:
        observability.record_agent_decision(
            agent_name=name,
            status="fallback",
            decision=getattr(fallback_output, "decision", None),
            summarized_input={"prompt": prompt},
            summarized_output=fallback_output.model_dump(mode="json"),
            metadata={"reason": "pydantic_ai_disabled"},
        )
        return fallback_output

    with derived_audit_context(agent_name=name):
        agent = _build_agent(
            name=name,
            system_prompt=system_prompt,
            output_model=output_model,
            deps=deps,
            fallback_output=fallback_output,
        )
        try:
            result = await agent.run(prompt)
            observability.record_agent_decision(
                agent_name=name,
                status="completed",
                decision=getattr(result.output, "decision", None),
                summarized_input={"prompt": prompt},
                summarized_output=result.output.model_dump(mode="json"),
                metadata={"used_fallback": False},
            )
            return result.output
        except Exception as exc:
            logger.exception("workflow agent failed; using deterministic fallback", extra={"agent_name": name})
            observability.record_system_error(
                status="agent_failure",
                agent_name=name,
                error_message=str(exc),
                error_type=exc.__class__.__name__,
                summarized_input={"prompt": prompt},
                metadata={"deterministic_fallback": deps.deterministic_fallback},
            )
            if deps.deterministic_fallback:
                observability.record_agent_decision(
                    agent_name=name,
                    status="fallback",
                    decision=getattr(fallback_output, "decision", None),
                    summarized_input={"prompt": prompt},
                    summarized_output=fallback_output.model_dump(mode="json"),
                    error_message=str(exc),
                    metadata={"used_fallback": True},
                )
                return fallback_output
            raise
