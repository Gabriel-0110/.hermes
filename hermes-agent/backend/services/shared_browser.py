"""Persistent shared browser sessions for human handoff workflows.

This service owns long-lived Playwright persistent contexts keyed by a stable
session name.  It is intentionally separate from the existing task-scoped
browser tool so exchange logins, 2FA, CAPTCHA, and device-trust state can live
in one real headed browser profile that both Hermes and a human can control.
"""

from __future__ import annotations

import json
import logging
import os
import queue
import re
import subprocess
import threading
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Literal

from hermes_constants import get_hermes_home

logger = logging.getLogger(__name__)

BrowserMode = Literal["agent", "human", "paused", "stopped"]

AUTH_BLOCK_PATTERNS=(
    "sign in", "sign-in", "signin", "log in", "login", "sign up", "sign-up",
    "2fa", "two-factor", "two factor", "otp", "one-time password",
    "captcha", "recaptcha", "hcaptcha", "slider challenge", "security verification",
    "verify your identity", "verification required", "suspicious login",
    "approval required", "email verification", "sms verification",
)


@dataclass
class _ActionRequest:
    fn: Callable[[], dict[str, Any]]
    result_queue: queue.Queue



@dataclass
class BrowserSessionMetadata:
    """Persisted operator-visible state for a shared browser session."""

    session_name: str
    profile_dir: str
    current_mode: BrowserMode = "stopped"
    current_url: str = ""
    page_title: str = ""
    started_at: str | None = None
    last_activity_at: str | None = None
    authenticated_guess: bool = False
    last_handoff_at: str | None = None
    last_resume_at: str | None = None
    latest_screenshot_path: str | None = None
    last_error: str | None = None


class BrowserControlError(RuntimeError):
    """Raised when an action is invalid for the current browser control mode."""


class SharedBrowserSession:
    """One named headed browser profile with serialized control transitions."""

    def __init__(self, session_name: str, profile_root: Path, metadata_root: Path):
        if not re.fullmatch(r"[A-Za-z0-9_.-]{1,80}", session_name):
            raise ValueError("Session names may only contain letters, numbers, dots, dashes, and underscores")
        self.session_name = session_name
        self.profile_dir = profile_root / session_name
        self.metadata_path = metadata_root / f"{session_name}.json"
        self.screenshot_dir = metadata_root / "screenshots" / session_name
        self._lock = threading.RLock()
        self._playwright = None
        self._context = None
        self._page = None
        self._owner_thread: threading.Thread | None = None
        self._owner_thread_id: int | None = None
        self._actions: queue.Queue[_ActionRequest | None] = queue.Queue()
        self.metadata = self._load_metadata()

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _load_metadata(self) -> BrowserSessionMetadata:
        if self.metadata_path.exists():
            try:
                data = json.loads(self.metadata_path.read_text(encoding="utf-8"))
                defaults = asdict(BrowserSessionMetadata(session_name=self.session_name, profile_dir=str(self.profile_dir)))
                defaults.update({k: v for k, v in data.items() if k in defaults})
                defaults["session_name"] = self.session_name
                defaults["profile_dir"] = str(self.profile_dir)
                return BrowserSessionMetadata(**defaults)
            except Exception as exc:
                logger.warning("Failed to read browser metadata %s: %s", self.metadata_path, exc)
        return BrowserSessionMetadata(session_name=self.session_name, profile_dir=str(self.profile_dir))

    def _save_metadata(self) -> None:
        self.metadata_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.metadata_path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(asdict(self.metadata), indent=2, sort_keys=True), encoding="utf-8")
        os.replace(tmp, self.metadata_path)

    def _touch(self) -> None:
        self.metadata.last_activity_at = self._now()

    def _in_owner_thread(self) -> bool:
        return self._owner_thread_id is not None and threading.get_ident() == self._owner_thread_id

    def _run_on_owner_thread(self, fn: Callable[[], dict[str, Any]]) -> dict[str, Any]:
        if self._in_owner_thread():
            return fn()
        self._ensure_owner_thread()
        result_queue: queue.Queue = queue.Queue(maxsize=1)
        self._actions.put(_ActionRequest(fn=fn, result_queue=result_queue))
        ok, payload = result_queue.get()
        if ok:
            return payload
        raise payload

    def _ensure_owner_thread(self) -> None:
        with self._lock:
            if self._owner_thread and self._owner_thread.is_alive():
                return
            self._actions = queue.Queue()
            thread = threading.Thread(
                target=self._owner_loop,
                name=f"shared-browser-{self.session_name}",
                daemon=True,
            )
            thread.start()
            self._owner_thread = thread

    def _owner_loop(self) -> None:
        self._owner_thread_id = threading.get_ident()
        while True:
            request = self._actions.get()
            if request is None:
                break
            try:
                result = request.fn()
            except Exception as exc:
                request.result_queue.put((False, exc))
            else:
                request.result_queue.put((True, result))
        self._owner_thread_id = None
        self._owner_thread = None

    def _ensure_started_locked(self) -> None:
        if self._context and self._page:
            return
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise BrowserControlError(
                "Playwright is not installed. Install with `pip install playwright` and run `playwright install chromium`."
            ) from exc

        self._ensure_browser_runtime_installed_locked()
        self.profile_dir.mkdir(parents=True, exist_ok=True)
        headed = os.getenv("HERMES_SHARED_BROWSER_HEADLESS", "").lower() not in {"1", "true", "yes"}
        self._playwright = sync_playwright().start()
        self._context = self._playwright.chromium.launch_persistent_context(
            user_data_dir=str(self.profile_dir),
            headless=not headed,
            viewport={"width": 1440, "height": 1000},
            args=["--disable-blink-features=AutomationControlled"],
        )
        self._page = self._context.pages[0] if self._context.pages else self._context.new_page()
        self.metadata.current_mode = "agent"
        self.metadata.started_at = self.metadata.started_at or self._now()
        self._refresh_page_state_locked()
        logger.info("Started shared browser session %s profile=%s headed=%s", self.session_name, self.profile_dir, headed)

    def _ensure_browser_runtime_installed_locked(self) -> None:
        sentinel = self.profile_dir.parent / ".playwright-browser-ready"
        if sentinel.exists():
            return
        try:
            subprocess.run(
                ["playwright", "install", "chromium"],
                check=True,
                capture_output=True,
                text=True,
                timeout=300,
            )
            sentinel.parent.mkdir(parents=True, exist_ok=True)
            sentinel.write_text(self._now(), encoding="utf-8")
        except Exception as exc:
            raise BrowserControlError(
                "Playwright Chromium runtime is missing and automatic install failed. "
                "Run `playwright install chromium` in the Hermes environment. "
                f"Underlying error: {type(exc).__name__}: {exc}"
            ) from exc

    def _refresh_page_state_locked(self) -> None:
        try:
            if self._page:
                self.metadata.current_url = self._page.url or ""
                self.metadata.page_title = self._page.title() or ""
                self.metadata.authenticated_guess = not self._auth_block_detected_locked()
                self.metadata.last_error = None
        except Exception as exc:
            self.metadata.last_error = f"{type(exc).__name__}: {exc}"
        self._touch()
        self._save_metadata()

    def _require_agent_locked(self) -> None:
        if self.metadata.current_mode != "agent":
            raise BrowserControlError(
                f"Browser session '{self.session_name}' is in {self.metadata.current_mode} mode; "
                "agent actions are blocked until `/browser resume <session>`."
            )
        self._ensure_started_locked()

    def _auth_block_detected_locked(self) -> bool:
        haystack = " ".join([self.metadata.current_url or "", self.metadata.page_title or ""]).lower()
        try:
            if self._page:
                body = self._page.locator("body").inner_text(timeout=1500).lower()
                haystack = f"{haystack} {body[:8000]}"
        except Exception:
            pass
        return any(pattern in haystack for pattern in AUTH_BLOCK_PATTERNS)

    def _handoff_if_auth_locked(self) -> dict[str, Any] | None:
        self._refresh_page_state_locked()
        if not self._auth_block_detected_locked():
            return None
        self.metadata.current_mode = "human"
        self.metadata.last_handoff_at = self._now()
        screenshot = self.snapshot_locked()
        self._save_metadata()
        return {
            "success": False,
            "handoff_required": True,
            "message": "Authentication or security verification appears to be required. Automation is paused for manual completion.",
            "session": asdict(self.metadata),
            "screenshot_path": screenshot.get("screenshot_path"),
        }

    def start(self, url: str | None = None) -> dict[str, Any]:
        def _op() -> dict[str, Any]:
            with self._lock:
                self._ensure_started_locked()
                if url:
                    self._page.goto(url, wait_until="domcontentloaded", timeout=60_000)
                handoff = self._handoff_if_auth_locked()
                if handoff:
                    return handoff
                return {"success": True, "session": asdict(self.metadata)}

        return self._run_on_owner_thread(_op)

    def stop(self) -> dict[str, Any]:
        def _op() -> dict[str, Any]:
            with self._lock:
                try:
                    if self._context:
                        self._context.close()
                    if self._playwright:
                        self._playwright.stop()
                    self.metadata.last_error = None
                except Exception as exc:
                    self.metadata.last_error = f"{type(exc).__name__}: {exc}"
                    logger.warning("Error stopping shared browser %s: %s", self.session_name, exc)
                finally:
                    self._context = None
                    self._page = None
                    self._playwright = None
                    self.metadata.current_mode = "stopped"
                    self._touch()
                    self._save_metadata()
                return {"success": True, "session": asdict(self.metadata)}

        result = self._run_on_owner_thread(_op)
        with self._lock:
            if self._owner_thread and self._owner_thread.is_alive() and not self._in_owner_thread():
                self._actions.put(None)
                self._owner_thread.join(timeout=5)
                self._owner_thread = None
                self._owner_thread_id = None
        return result

    def status(self) -> dict[str, Any]:
        def _op() -> dict[str, Any]:
            with self._lock:
                if self._page:
                    self._refresh_page_state_locked()
                return {"success": True, "running": bool(self._page), "session": asdict(self.metadata)}

        return self._run_on_owner_thread(_op) if self._page or self._owner_thread else _op()

    def navigate(self, url: str) -> dict[str, Any]:
        def _op() -> dict[str, Any]:
            with self._lock:
                self._require_agent_locked()
                self._page.goto(url, wait_until="domcontentloaded", timeout=60_000)
                handoff = self._handoff_if_auth_locked()
                if handoff:
                    return handoff
                return {"success": True, "session": asdict(self.metadata)}

        return self._run_on_owner_thread(_op)

    def click(self, selector: str) -> dict[str, Any]:
        def _op() -> dict[str, Any]:
            with self._lock:
                self._require_agent_locked()
                self._page.locator(selector).first.click(timeout=15_000)
                handoff = self._handoff_if_auth_locked()
                if handoff:
                    return handoff
                return {"success": True, "session": asdict(self.metadata)}

        return self._run_on_owner_thread(_op)

    def type_text(self, selector: str, text: str, clear: bool = True) -> dict[str, Any]:
        def _op() -> dict[str, Any]:
            with self._lock:
                self._require_agent_locked()
                loc = self._page.locator(selector).first
                loc.fill(text, timeout=15_000) if clear else loc.type(text, timeout=15_000)
                handoff = self._handoff_if_auth_locked()
                if handoff:
                    return handoff
                return {"success": True, "session": asdict(self.metadata)}

        return self._run_on_owner_thread(_op)

    def wait(self, seconds: float = 1.0, selector: str | None = None) -> dict[str, Any]:
        def _op() -> dict[str, Any]:
            with self._lock:
                self._require_agent_locked()
                if selector:
                    self._page.locator(selector).first.wait_for(timeout=max(int(seconds * 1000), 1000))
                else:
                    self._page.wait_for_timeout(max(int(seconds * 1000), 0))
                handoff = self._handoff_if_auth_locked()
                if handoff:
                    return handoff
                return {"success": True, "session": asdict(self.metadata)}

        return self._run_on_owner_thread(_op)

    def snapshot_locked(self) -> dict[str, Any]:
        self.screenshot_dir.mkdir(parents=True, exist_ok=True)
        path = self.screenshot_dir / f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')}.png"
        if self._page:
            self._page.screenshot(path=str(path), full_page=False)
            self.metadata.latest_screenshot_path = str(path)
            self._refresh_page_state_locked()
        return {"success": True, "screenshot_path": str(path), "session": asdict(self.metadata)}

    def snapshot(self) -> dict[str, Any]:
        def _op() -> dict[str, Any]:
            with self._lock:
                self._ensure_started_locked()
                return self.snapshot_locked()

        return self._run_on_owner_thread(_op)

    def handoff(self) -> dict[str, Any]:
        def _op() -> dict[str, Any]:
            with self._lock:
                self._ensure_started_locked()
                self.metadata.current_mode = "human"
                self.metadata.last_handoff_at = self._now()
                snap = self.snapshot_locked()
                self._save_metadata()
                return {"success": True, "session": asdict(self.metadata), "screenshot_path": snap.get("screenshot_path")}

        return self._run_on_owner_thread(_op)

    def resume(self) -> dict[str, Any]:
        def _op() -> dict[str, Any]:
            with self._lock:
                self._ensure_started_locked()
                self.metadata.current_mode = "agent"
                self.metadata.last_resume_at = self._now()
                self._refresh_page_state_locked()
                return {"success": True, "session": asdict(self.metadata)}

        return self._run_on_owner_thread(_op)

    def lock_mode(self, mode: BrowserMode) -> dict[str, Any]:
        if mode == "stopped":
            return self.stop()

        def _op() -> dict[str, Any]:
            with self._lock:
                self._ensure_started_locked()
                self.metadata.current_mode = mode
                if mode == "human":
                    self.metadata.last_handoff_at = self._now()
                if mode == "agent":
                    self.metadata.last_resume_at = self._now()
                self._refresh_page_state_locked()
                return {"success": True, "session": asdict(self.metadata)}

        return self._run_on_owner_thread(_op)


class SharedBrowserService:
    """Thread-safe registry for named shared browser sessions."""

    def __init__(self) -> None:
        root = Path(os.getenv("HERMES_BROWSER_PROFILE_ROOT", get_hermes_home() / "browser-profiles")).expanduser()
        state = Path(os.getenv("HERMES_BROWSER_STATE_DIR", get_hermes_home() / "browser-state")).expanduser()
        self.profile_root = root
        self.metadata_root = state / "sessions"
        self._lock = threading.RLock()
        self._sessions: dict[str, SharedBrowserSession] = {}

    def get(self, session_name: str) -> SharedBrowserSession:
        with self._lock:
            if session_name not in self._sessions:
                self._sessions[session_name] = SharedBrowserSession(session_name, self.profile_root, self.metadata_root)
            return self._sessions[session_name]

    def list_metadata(self) -> list[dict[str, Any]]:
        self.metadata_root.mkdir(parents=True, exist_ok=True)
        rows = []
        for path in sorted(self.metadata_root.glob("*.json")):
            try:
                rows.append(json.loads(path.read_text(encoding="utf-8")))
            except Exception:
                logger.debug("Skipping unreadable browser metadata %s", path)
        return rows


shared_browser_service = SharedBrowserService()
