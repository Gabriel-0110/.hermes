"""Hermes tools for persistent shared browser sessions."""

from __future__ import annotations

import json
from typing import Any

from backend.services.shared_browser import BrowserControlError, shared_browser_service
from tools.registry import registry


def _json_result(fn) -> str:
    try:
        return json.dumps(fn(), ensure_ascii=False)
    except BrowserControlError as exc:
        return json.dumps({"success": False, "error": str(exc)}, ensure_ascii=False)
    except Exception as exc:
        return json.dumps({"success": False, "error": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False)


def shared_browser_action(action: str, session: str = "exchange-main", **kwargs: Any) -> str:
    """Run a control-plane action against a named persistent browser session."""

    name = (session or "exchange-main").strip()
    browser = shared_browser_service.get(name)
    action = (action or "status").strip().lower()

    def run() -> dict[str, Any]:
        if action == "start":
            return browser.start(url=kwargs.get("url") or None)
        if action == "stop":
            return browser.stop()
        if action == "status":
            return browser.status()
        if action in {"open", "navigate"}:
            url = kwargs.get("url")
            if not url:
                return {"success": False, "error": "url is required for open/navigate"}
            return browser.navigate(url)
        if action == "click":
            selector = kwargs.get("selector")
            if not selector:
                return {"success": False, "error": "selector is required for click"}
            return browser.click(selector)
        if action in {"type", "fill"}:
            selector = kwargs.get("selector")
            text = kwargs.get("text", "")
            if not selector:
                return {"success": False, "error": "selector is required for type"}
            return browser.type_text(selector, text, clear=bool(kwargs.get("clear", True)))
        if action == "wait":
            return browser.wait(seconds=float(kwargs.get("seconds") or 1), selector=kwargs.get("selector") or None)
        if action == "snapshot":
            return browser.snapshot()
        if action == "handoff":
            return browser.handoff()
        if action == "resume":
            return browser.resume()
        if action == "unlock":
            return browser.resume()
        if action in {"lock", "mode"}:
            mode = kwargs.get("mode")
            if mode not in {"agent", "human", "paused", "stopped"}:
                return {"success": False, "error": "mode must be one of agent, human, paused, stopped"}
            return browser.lock_mode(mode)
        if action == "list":
            return {"success": True, "sessions": shared_browser_service.list_metadata()}
        return {"success": False, "error": f"Unknown shared browser action: {action}"}

    return _json_result(run)


SHARED_BROWSER_SCHEMA = {
    "name": "shared_browser",
    "description": (
        "Control a named persistent headed browser session shared with the human operator. "
        "Use this for exchange sites and authentication-sensitive flows. If auth, CAPTCHA, "
        "2FA, OTP, slider, or security verification appears, stop automation and hand off."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": [
                    "start", "stop", "status", "open", "navigate", "click", "type",
                    "wait", "snapshot", "handoff", "resume", "lock", "unlock", "mode", "list",
                ],
            },
            "session": {
                "type": "string",
                "description": "Named persistent session, for example bitmart-main or exchange-main.",
                "default": "exchange-main",
            },
            "url": {"type": "string", "description": "URL for start/open/navigate."},
            "selector": {"type": "string", "description": "CSS selector for click/type/wait."},
            "text": {"type": "string", "description": "Text to type."},
            "seconds": {"type": "number", "description": "Seconds to wait.", "default": 1},
            "mode": {"type": "string", "enum": ["agent", "human", "paused", "stopped"]},
            "clear": {"type": "boolean", "description": "Clear field before typing.", "default": True},
        },
        "required": ["action"],
    },
}


def _check_shared_browser_requirements() -> bool:
    try:
        import playwright  # noqa: F401
        return True
    except ImportError:
        return False


registry.register(
    name="shared_browser",
    toolset="browser",
    schema=SHARED_BROWSER_SCHEMA,
    handler=lambda args, **kw: shared_browser_action(**args),
    check_fn=_check_shared_browser_requirements,
    emoji="🧭",
)
