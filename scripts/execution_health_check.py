#!/usr/bin/env python3
"""Cron wrapper for the execution health check job.

Queries the exchange for API connectivity, balances, and open orders,
then prints a markdown-formatted summary for the cron prompt context.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def _find_workspace_root(script_path: Path) -> Path:
    for candidate in (script_path.parent, *script_path.parents):
        if (candidate / "hermes-agent").is_dir():
            return candidate
    raise RuntimeError(f"Could not locate workspace root from {script_path}")


def _infer_hermes_home(script_path: Path, workspace_root: Path) -> Path:
    configured_home = os.environ.get("HERMES_HOME", "").strip()
    if configured_home:
        return Path(configured_home).expanduser().resolve()

    try:
        relative = script_path.relative_to(workspace_root)
    except ValueError:
        relative = None

    if relative is not None and len(relative.parts) >= 3:
        if relative.parts[0] == "profiles" and relative.parts[2] == "scripts":
            profile_home = workspace_root / relative.parts[0] / relative.parts[1]
            if profile_home.is_dir():
                return profile_home.resolve()

    active_profile_path = workspace_root / "active_profile"
    if active_profile_path.exists():
        active_profile = active_profile_path.read_text(encoding="utf-8").strip()
        if active_profile and active_profile != "default":
            profile_home = workspace_root / "profiles" / active_profile
            if profile_home.is_dir():
                return profile_home.resolve()

    return workspace_root.resolve()


def _maybe_reexec_project_python(workspace_root: Path) -> None:
    if os.environ.get("_HERMES_RUNTIME_JOB_REEXEC") == "1":
        return

    project_python = workspace_root / ".venv" / "bin" / "python"
    if not project_python.exists():
        return

    try:
        current_python = Path(sys.executable).resolve()
        target_python = project_python.resolve()
    except OSError:
        return

    if current_python == target_python:
        return

    env = os.environ.copy()
    env["_HERMES_RUNTIME_JOB_REEXEC"] = "1"
    os.execve(str(target_python), [str(target_python), *sys.argv], env)


def _bootstrap() -> Path:
    script_path = Path(__file__).resolve()
    workspace_root = _find_workspace_root(script_path)
    _maybe_reexec_project_python(workspace_root)

    hermes_home = _infer_hermes_home(script_path, workspace_root)
    os.environ["HERMES_HOME"] = str(hermes_home)
    os.chdir(workspace_root)

    agent_root = workspace_root / "hermes-agent"
    sys.path.insert(0, str(agent_root))

    from hermes_cli.env_loader import load_hermes_dotenv

    load_hermes_dotenv(hermes_home=hermes_home, project_env=agent_root / ".env")

    try:
        from hermes_logging import setup_logging

        setup_logging(mode="cron")
    except Exception:
        pass

    return workspace_root


PROJECT_ROOT = _bootstrap()
AGENT_ROOT = PROJECT_ROOT / "hermes-agent"

from backend.jobs.execution_health_check import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
