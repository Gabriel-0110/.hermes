#!/usr/bin/env python3
"""Hermes startup validation — checks environment variables and service reachability.

Run this before starting the stack to surface configuration gaps early:

    python hermes-agent/scripts/startup_check.py

The script loads .env from the hermes-agent directory if present, then checks:
  - Required infrastructure env vars (DATABASE_URL, REDIS_URL, LITELLM_MASTER_KEY)
  - LLM provider keys (at least one must be present)
  - Optional notification / market-data credentials (warns if absent)
  - Live connectivity to TimescaleDB, Redis, and LiteLLM

Exit codes:
  0  All critical checks passed (optional warnings are allowed)
  1  One or more critical checks failed
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable


# ---------------------------------------------------------------------------
# Result model
# ---------------------------------------------------------------------------

@dataclass
class CheckResult:
    name: str
    passed: bool
    critical: bool = True
    detail: str = ""


_results: list[CheckResult] = []


def _record(name: str, *, critical: bool, fn: Callable[[], str | None]) -> None:
    try:
        detail = fn() or ""
        _results.append(CheckResult(name, passed=True, critical=critical, detail=detail))
    except Exception as exc:
        _results.append(CheckResult(name, passed=False, critical=critical, detail=str(exc)))


# ---------------------------------------------------------------------------
# Environment variable checks
# ---------------------------------------------------------------------------

_REQUIRED_ENV: list[tuple[str, str]] = [
    ("DATABASE_URL", "PostgreSQL/TimescaleDB connection string"),
    ("REDIS_URL", "Redis connection URL"),
    ("LITELLM_MASTER_KEY", "LiteLLM admin key (must start with sk-)"),
]

_PROVIDER_ENV: list[tuple[str, str]] = [
    ("OPENAI_API_KEY", "OpenAI"),
    ("OPENAI_API_KEY_1", "OpenAI key-rotation slot 1"),
    ("ANTHROPIC_API_KEY", "Anthropic"),
    ("ANTHROPIC_API_KEY_1", "Anthropic key-rotation slot 1"),
    ("GOOGLE_API_KEY", "Google / Gemini"),
    ("OPENROUTER_API_KEY", "OpenRouter"),
    ("LM_STUDIO_BASE_URL", "LM Studio local endpoint"),
]

_NOTIFICATION_ENV: list[tuple[str, str]] = [
    ("TELEGRAM_BOT_TOKEN", "Telegram bot token"),
    ("TELEGRAM_CHAT_ID", "Telegram destination chat ID"),
    ("SLACK_WEBHOOK_URL", "Slack incoming webhook URL"),
]

_MARKET_DATA_ENV: list[tuple[str, str]] = [
    ("COINGECKO_API_KEY", "CoinGecko"),
    ("COINMARKETCAP_API_KEY", "CoinMarketCap"),
    ("TWELVEDATA_API_KEY", "TwelveData"),
    ("FRED_API_KEY", "FRED"),
    ("CRYPTOPANIC_API_KEY", "CryptoPanic"),
    ("NEWS_API_KEY", "NewsAPI"),
    ("LUNARCRUSH_API_KEY", "LunarCrush"),
    ("ETHERSCAN_API_KEY", "Etherscan"),
    ("TRADINGVIEW_WEBHOOK_SECRET", "TradingView webhook shared secret"),
]

_EXCHANGE_ENV: list[tuple[str, str]] = [
    ("BITMART_API_KEY", "BitMart API key"),
    ("BITMART_SECRET", "BitMart secret"),
    ("BITMART_MEMO", "BitMart memo / passphrase"),
]


def _check_required_env() -> str:
    missing = [f"  ✗ {var}  ({desc})" for var, desc in _REQUIRED_ENV if not os.environ.get(var, "").strip()]
    if missing:
        raise RuntimeError("Missing required env vars:\n" + "\n".join(missing))
    return "All required env vars present."


def _check_provider_env() -> str:
    present = [var for var, _ in _PROVIDER_ENV if os.environ.get(var, "").strip()]
    if not present:
        raise RuntimeError(
            "No LLM provider key is set. Set at least one of: "
            + ", ".join(var for var, _ in _PROVIDER_ENV)
        )
    missing = [f"  ~ {var}  ({desc})" for var, desc in _PROVIDER_ENV if not os.environ.get(var, "").strip()]
    return f"{len(present)} provider key(s) present. Not set:\n" + "\n".join(missing) if missing else f"{len(present)} provider key(s) present."


def _check_optional_group(spec: list[tuple[str, str]], label: str) -> str:
    present = [var for var, _ in spec if os.environ.get(var, "").strip()]
    missing = [f"  ~ {var}  ({desc})" for var, desc in spec if not os.environ.get(var, "").strip()]
    summary = f"{label}: {len(present)}/{len(spec)} vars set."
    return summary + ("\nNot set:\n" + "\n".join(missing) if missing else "")


# ---------------------------------------------------------------------------
# Service connectivity checks
# ---------------------------------------------------------------------------

def _check_postgres() -> str:
    database_url = os.environ.get("DATABASE_URL", "").strip()
    if not database_url:
        raise RuntimeError("DATABASE_URL is not set — skipping connectivity check.")
    try:
        import psycopg  # type: ignore[import]
    except ImportError:
        raise RuntimeError("psycopg is not installed; run: pip install psycopg[binary]")

    # psycopg expects postgresql:// not postgresql+psycopg://
    url = database_url
    for prefix in ("postgresql+psycopg://", "postgres+psycopg://"):
        if url.startswith(prefix):
            url = "postgresql://" + url[len(prefix):]
            break

    with psycopg.connect(url, connect_timeout=5) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT version()")
            row = cur.fetchone()
    version_str = (row[0] if row else "unknown")[:80]
    return f"Connected — {version_str}"


def _check_redis() -> str:
    redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0").strip()
    try:
        import redis as redis_lib  # type: ignore[import]
    except ImportError:
        raise RuntimeError("redis-py is not installed; run: pip install redis")

    client = redis_lib.from_url(redis_url, socket_connect_timeout=5, socket_timeout=5)
    if not client.ping():
        raise RuntimeError("Redis PING did not return True.")
    return f"PING OK — {redis_url}"


def _check_litellm() -> str:
    base_url = os.environ.get("LITELLM_BASE_URL", "http://localhost:4000").strip()
    master_key = os.environ.get("LITELLM_MASTER_KEY", "").strip()
    import urllib.request
    import urllib.error

    req = urllib.request.Request(
        f"{base_url.rstrip('/')}/health/liveliness",
        headers={"Authorization": f"Bearer {master_key}"} if master_key else {},
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            if resp.status not in (200, 201):
                raise RuntimeError(f"LiteLLM liveliness returned HTTP {resp.status}")
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Cannot reach LiteLLM at {base_url}: {exc.reason}")
    return f"Liveliness OK — {base_url}"


# ---------------------------------------------------------------------------
# .env loader
# ---------------------------------------------------------------------------

def _load_dotenv(path: Path) -> None:
    """Minimal .env loader — sets vars that aren't already in the environment."""
    if not path.is_file():
        return
    with path.open() as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            os.environ.setdefault(key, val)


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def _print_report() -> bool:
    PASS = "\033[32m✓\033[0m"
    WARN = "\033[33m~\033[0m"
    FAIL = "\033[31m✗\033[0m"

    print("\n╔══ Hermes Startup Check ════════════════════════════════════════╗\n")
    any_critical_failed = False
    for r in _results:
        icon = PASS if r.passed else (FAIL if r.critical else WARN)
        tag = " [CRITICAL]" if (not r.passed and r.critical) else (" [WARN]" if not r.passed else "")
        print(f"  {icon}  {r.name}{tag}")
        for line in r.detail.splitlines():
            if line.strip():
                print(f"       {line}")
        if not r.passed and r.critical:
            any_critical_failed = True

    total = len(_results)
    passed = sum(1 for r in _results if r.passed)
    print(f"\n  {passed}/{total} checks passed")

    if any_critical_failed:
        print("\n  ✗ One or more CRITICAL checks failed.")
        print("    Fix the issues above before starting Hermes.\n")
    else:
        print("\n  ✓ System looks ready to start.\n")

    print("╚════════════════════════════════════════════════════════════════╝\n")
    return not any_critical_failed


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    # Load .env from hermes-agent root (two dirs up from scripts/)
    _load_dotenv(Path(__file__).parent.parent / ".env")
    # Also try workspace root
    _load_dotenv(Path(__file__).parent.parent.parent / ".env.dev")

    # Environment checks
    _record("Env — Core infrastructure", critical=True, fn=_check_required_env)
    _record("Env — LLM provider keys", critical=True, fn=_check_provider_env)
    _record(
        "Env — Notification channels",
        critical=False,
        fn=lambda: _check_optional_group(_NOTIFICATION_ENV, "Notification"),
    )
    _record(
        "Env — Market data providers",
        critical=False,
        fn=lambda: _check_optional_group(_MARKET_DATA_ENV, "Market data"),
    )
    _record(
        "Env — Exchange credentials",
        critical=False,
        fn=lambda: _check_optional_group(_EXCHANGE_ENV, "Exchange"),
    )

    # Service connectivity checks (only if env vars are present)
    _record("Service — TimescaleDB/Postgres", critical=True, fn=_check_postgres)
    _record("Service — Redis", critical=True, fn=_check_redis)
    _record("Service — LiteLLM gateway", critical=False, fn=_check_litellm)

    ok = _print_report()
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
