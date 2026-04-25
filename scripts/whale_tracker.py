#!/usr/bin/env python3
"""Cron wrapper for the Hermes whale tracker job."""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
AGENT_ROOT = PROJECT_ROOT / "hermes-agent"
sys.path.insert(0, str(AGENT_ROOT))

from backend.jobs.whale_tracker import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())