#!/bin/bash
ulimit -n 65536
exec /Users/openclaw/.hermes/.venv/bin/python -m hermes_cli.main --profile execution-agent gateway run --replace
