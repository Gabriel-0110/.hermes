"""Shared helpers for safe internal trading tools."""

from __future__ import annotations

import logging
from typing import Any, Callable, Iterable

from pydantic import BaseModel, ValidationError

from backend.integrations.base import IntegrationError, MissingCredentialError
from backend.models import NormalizedResponse, ProviderStatus, ToolEnvelope
from backend.observability.context import clear_pending_tool_input, get_audit_context, get_pending_tool_input, set_pending_tool_input
from backend.observability.service import get_observability_service

logger = logging.getLogger(__name__)


def validate(model: type[BaseModel], payload: dict[str, Any]) -> BaseModel:
    set_pending_tool_input(payload)
    return model.model_validate(payload)


def envelope(source: str, providers: Iterable[ProviderStatus], data: Any, warnings: list[str] | None = None, ok: bool = True) -> dict[str, Any]:
    return NormalizedResponse(
        meta=ToolEnvelope(source=source, providers=list(providers), warnings=warnings or [], ok=ok),
        data=data,
    ).model_dump(mode="json")


def provider_ok(provider: str, detail: str | None = None) -> ProviderStatus:
    return ProviderStatus(provider=provider, ok=True, detail=detail)


def provider_error(provider: str, detail: str) -> ProviderStatus:
    return ProviderStatus(provider=provider, ok=False, detail=detail)


def run_tool(source: str, fn: Callable[[], Any]) -> dict[str, Any]:
    observability = get_observability_service()
    audit = get_audit_context()
    try:
        result = fn()
        observability.record_tool_call(
            tool_name=source,
            status="completed",
            context=audit,
            summarized_input=get_pending_tool_input(),
            summarized_output=result,
            metadata={"source": source},
        )
        return result
    except ValidationError as exc:
        logger.info("%s input validation failed: %s", source, exc)
        observability.record_tool_call(
            tool_name=source,
            status="invalid_input",
            context=audit,
            summarized_input=get_pending_tool_input(),
            summarized_output={"error": "invalid_input"},
            error_message=str(exc),
            metadata={"source": source},
        )
        observability.record_system_error(
            status="invalid_input",
            context=audit,
            tool_name=source,
            summarized_input=get_pending_tool_input(),
            error_message=str(exc),
            error_type="ValidationError",
            metadata={"source": source},
            is_failure=False,
        )
        return envelope(source, [], {"error": "invalid_input", "detail": str(exc)}, ok=False)
    except MissingCredentialError as exc:
        logger.info("%s missing credentials: %s", source, exc)
        observability.record_tool_call(
            tool_name=source,
            status="provider_not_configured",
            context=audit,
            summarized_input=get_pending_tool_input(),
            summarized_output={"error": "provider_not_configured"},
            error_message=str(exc),
            metadata={"source": source},
        )
        observability.record_system_error(
            status="provider_not_configured",
            context=audit,
            tool_name=source,
            summarized_input=get_pending_tool_input(),
            error_message=str(exc),
            error_type=exc.__class__.__name__,
            metadata={"source": source},
            is_failure=False,
        )
        return envelope(source, [], {"error": "provider_not_configured", "detail": str(exc)}, ok=False)
    except IntegrationError as exc:
        logger.warning("%s integration failed: %s", source, exc)
        observability.record_tool_call(
            tool_name=source,
            status="provider_failure",
            context=audit,
            summarized_input=get_pending_tool_input(),
            summarized_output={"error": "provider_failure"},
            error_message=str(exc),
            metadata={"source": source},
        )
        observability.record_system_error(
            status="provider_failure",
            context=audit,
            tool_name=source,
            summarized_input=get_pending_tool_input(),
            error_message=str(exc),
            error_type=exc.__class__.__name__,
            metadata={"source": source},
        )
        return envelope(source, [], {"error": "provider_failure", "detail": str(exc)}, ok=False)
    except Exception as exc:
        logger.exception("%s unexpected failure", source)
        observability.record_tool_call(
            tool_name=source,
            status="failed",
            context=audit,
            summarized_input=get_pending_tool_input(),
            summarized_output={"error": exc.__class__.__name__},
            error_message=str(exc),
            metadata={"source": source},
        )
        observability.record_system_error(
            status="failed",
            context=audit,
            tool_name=source,
            summarized_input=get_pending_tool_input(),
            error_message=str(exc),
            error_type=exc.__class__.__name__,
            metadata={"source": source},
        )
        return envelope(source, [], {"error": "unexpected_failure", "detail": str(exc)}, ok=False)
    finally:
        clear_pending_tool_input()
