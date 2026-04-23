#!/usr/bin/env python3
"""Launch the Hermes Agent web dashboard in service mode.

This entrypoint avoids the interactive CLI wrapper and skips the frontend rebuild
step performed by `hermes web`, making it suitable for long-running service
managers such as launchd.
"""

from __future__ import annotations

import os

from hermes_cli.web_server import start_server


def _host() -> str:
    return os.getenv("HERMES_DASHBOARD_HOST", "127.0.0.1").strip() or "127.0.0.1"


def _port() -> int:
    raw = os.getenv("HERMES_DASHBOARD_PORT", "9119").strip() or "9119"
    try:
        return int(raw)
    except ValueError:
        return 9119


if __name__ == "__main__":
    start_server(host=_host(), port=_port(), open_browser=False)
