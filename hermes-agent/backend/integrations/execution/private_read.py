"""Private exchange read-path error classification."""

from __future__ import annotations

from typing import Any, Literal

from backend.integrations.base import IntegrationError


PrivateReadFailureClassification = Literal[
    "cloudflare_waf",
    "service_unavailable_or_challenge",
    "rate_limited_private_access",
    "malformed_response",
    "auth_failed",
    "exchange_business_error",
    "transport_error",
]


class ClassifiedPrivateReadError(IntegrationError):
    """Private read failure with a stable machine-readable classification."""

    def __init__(
        self,
        message: str,
        *,
        classification: PrivateReadFailureClassification,
        operation: str,
        status_code: int | None = None,
        exchange_code: Any = None,
    ) -> None:
        super().__init__(message)
        self.classification = classification
        self.operation = operation
        self.status_code = status_code
        self.exchange_code = exchange_code


def _body_preview(response: Any) -> str:
    return str(getattr(response, "text", "") or "")[:300]


def _is_auth_error(code: Any, message: str) -> bool:
    text = f"{code} {message}".lower()
    auth_terms = ("auth", "signature", "sign", "api key", "apikey", "unauthorized", "permission", "memo", "invalid key")
    return any(term in text for term in auth_terms)


def _raise(
    *,
    operation: str,
    classification: PrivateReadFailureClassification,
    status_code: int | None,
    message: str,
    exchange_code: Any = None,
) -> None:
    raise ClassifiedPrivateReadError(
        f"BitMart private read {operation} failed [{classification}]: {message}",
        classification=classification,
        operation=operation,
        status_code=status_code,
        exchange_code=exchange_code,
    )


def parse_bitmart_private_read_response(
    response: Any,
    *,
    operation: str,
    success_code: int = 1000,
) -> dict[str, Any]:
    """Parse a BitMart private read response or raise a classified error."""

    status_code = int(getattr(response, "status_code", 0) or 0)
    preview = _body_preview(response)
    lowered = preview.lower()

    if status_code == 403 or "cloudflare" in lowered or "error code: 1010" in lowered or " waf" in lowered:
        _raise(
            operation=operation,
            classification="cloudflare_waf",
            status_code=status_code,
            message=f"Cloudflare/WAF rejection. Body: {preview}",
        )
    if status_code == 429:
        _raise(
            operation=operation,
            classification="rate_limited_private_access",
            status_code=status_code,
            message=f"HTTP 429 rate limit. Body: {preview}",
        )
    if status_code in {502, 503, 504}:
        _raise(
            operation=operation,
            classification="service_unavailable_or_challenge",
            status_code=status_code,
            message=f"HTTP {status_code} service/challenge response. Body: {preview}",
        )
    if status_code >= 400:
        _raise(
            operation=operation,
            classification="transport_error",
            status_code=status_code,
            message=f"HTTP {status_code}. Body: {preview}",
        )

    try:
        payload = response.json()
    except Exception as exc:
        _raise(
            operation=operation,
            classification="malformed_response",
            status_code=status_code,
            message=f"Non-JSON or malformed JSON response. Body: {preview}",
        )
        raise AssertionError("unreachable") from exc

    if not isinstance(payload, dict):
        _raise(
            operation=operation,
            classification="malformed_response",
            status_code=status_code,
            message=f"JSON response was {type(payload).__name__}, expected object.",
        )

    code = payload.get("code")
    if code == success_code:
        return payload
    message = str(payload.get("message") or payload.get("msg") or preview or "unknown BitMart API error")
    _raise(
        operation=operation,
        classification="auth_failed" if _is_auth_error(code, message) else "exchange_business_error",
        status_code=status_code,
        message=f"code={code} message={message!r} trace={payload.get('trace')!r}",
        exchange_code=code,
    )
    raise AssertionError("unreachable")


def classify_private_read_exception(exc: BaseException) -> PrivateReadFailureClassification:
    if isinstance(exc, ClassifiedPrivateReadError):
        return exc.classification
    parts = [str(exc)]
    cause = getattr(exc, "__cause__", None)
    context = getattr(exc, "__context__", None)
    if cause is not None:
        parts.append(str(cause))
    if context is not None:
        parts.append(str(context))
    text = " ".join(parts).lower()
    if "cloudflare" in text or "waf" in text or "error code: 1010" in text or "http 403" in text:
        return "cloudflare_waf"
    if "429" in text or "rate limit" in text or "too many request" in text:
        return "rate_limited_private_access"
    if "503" in text or "502" in text or "504" in text or "just a moment" in text or "challenge" in text:
        return "service_unavailable_or_challenge"
    if "json" in text or "html" in text or "malformed" in text:
        return "malformed_response"
    if _is_auth_error(None, text):
        return "auth_failed"
    return "transport_error"
