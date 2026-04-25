#!/usr/bin/env python3
"""Cron wrapper for the nightly Hermes strategy evaluator job."""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
AGENT_ROOT = PROJECT_ROOT / "hermes-agent"
sys.path.insert(0, str(AGENT_ROOT))

from backend.jobs.strategy_evaluator import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())