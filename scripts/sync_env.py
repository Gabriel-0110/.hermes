#!/usr/bin/env python3
"""Synchronize Hermes trading-desk environment keys across profiles.

Root source of truth: /Users/openclaw/.hermes/.env

Notes:
- Host-run agent profiles use the host-mapped TimescaleDB URL on localhost:5433.
- The legacy /Users/openclaw/.hermes/hermes docker app .env must use Docker service
  DNS names (timescaledb:5432, redis:6379), not host localhost mappings.
"""
from __future__ import annotations

import os
from pathlib import Path

ROOT_ENV = Path("/Users/openclaw/.hermes/.env")

SYNC_KEYS = [
    "BITMART_API_KEY", "BITMART_API_SECRET", "BITMART_API_MEMO",
    "BITMART_UID", "BITMART_SECRET", "BITMART_MEMO",
    "HERMES_TRADING_MODE", "HERMES_ENABLE_LIVE_TRADING", "HERMES_LIVE_TRADING_ACK",
    "COINGECKO_API_KEY", "COINMARKETCAP_API_KEY", "TWELVEDATA_API_KEY",
    "CRYPTOPANIC_API_KEY", "NEWS_API_KEY", "NEWSAPI_KEY",
    "ETHERSCAN_API_KEY", "LUNARCRUSH_API_KEY", "NANSEN_API_KEY",
    "FRED_API_KEY", "HERMES_BITMART_VERIFY_SIGNED_WRITES",
    "DATABASE_URL", "REDIS_URL",
    "TAVILY_API_KEY", "TAVILY_API_NAME", "TAVILY_MCP_URL",
    "FIRECRAWL_API_KEY", "FIRECRAWL_API_URL", "FIRECRAWL_MCP_URL",
    "EXA_API_KEY", "EXA_MCP_URL",
]

TARGET_ENVS = [
    Path("/Users/openclaw/.hermes/hermes-agent/.env"),
    Path("/Users/openclaw/.hermes/hermes/.env"),
    Path("/Users/openclaw/.hermes/profiles/orchestrator/.env"),
    Path("/Users/openclaw/.hermes/profiles/risk-manager/.env"),
    Path("/Users/openclaw/.hermes/profiles/market-researcher/.env"),
    Path("/Users/openclaw/.hermes/profiles/strategy-agent/.env"),
    Path("/Users/openclaw/.hermes/profiles/portfolio-monitor/.env"),
    Path("/Users/openclaw/.hermes/profiles/execution-agent/.env"),
]

TARGET_OVERRIDES = {
    Path("/Users/openclaw/.hermes/hermes/.env"): {
        "DATABASE_URL": "postgresql+psycopg://hermes:hermes@timescaledb:5432/hermes_trading",
        "REDIS_URL": "redis://redis:6379/0",
    }
}


def parse_env(path: Path) -> dict[str, str]:
    pairs: dict[str, str] = {}
    if not path.exists():
        return pairs
    for line in path.read_text().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        pairs[key.strip()] = value.strip()
    return pairs


def sync_env_file(path: Path, source_pairs: dict[str, str], keys_to_sync: list[str]) -> tuple[list[str], list[str]]:
    lines = path.read_text().splitlines(keepends=True) if path.exists() else []
    existing_keys: set[str] = set()
    added: list[str] = []
    updated: list[str] = []
    effective_pairs = dict(source_pairs)
    effective_pairs.update(TARGET_OVERRIDES.get(path, {}))

    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            key, _, _ = stripped.partition("=")
            key = key.strip()
            existing_keys.add(key)
            if key in keys_to_sync and key in effective_pairs:
                new_line = f"{key}={effective_pairs[key]}\n"
                if line != new_line:
                    lines[i] = new_line
                    updated.append(key)

    missing_lines: list[str] = []
    for key in keys_to_sync:
        if key not in existing_keys and key in effective_pairs:
            missing_lines.append(f"{key}={effective_pairs[key]}\n")
            added.append(key)

    if missing_lines:
        if lines and not lines[-1].endswith("\n"):
            lines[-1] += "\n"
        if lines and lines[-1].strip():
            lines.append("\n")
        lines.append("# === Synced from root .env by Hermes orchestrator ===\n")
        lines.extend(missing_lines)

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(lines))
    return added, updated


def main() -> int:
    if not ROOT_ENV.exists():
        raise SystemExit(f"Root env not found: {ROOT_ENV}")
    root_pairs = parse_env(ROOT_ENV)
    if "NEWS_API_KEY" in root_pairs and "NEWSAPI_KEY" not in root_pairs:
        root_pairs["NEWSAPI_KEY"] = root_pairs["NEWS_API_KEY"]
    root_pairs.setdefault("DATABASE_URL", "postgresql://hermes:hermes@localhost:5433/hermes_trading")
    root_pairs.setdefault("REDIS_URL", "redis://localhost:6379/0")

    for target in TARGET_ENVS:
        added, updated = sync_env_file(target, root_pairs, SYNC_KEYS)
        short = str(target).replace("/Users/openclaw/", "~/")
        print(f"{short}: +{len(added)} added, ~{len(updated)} updated")
    print("Sync complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
