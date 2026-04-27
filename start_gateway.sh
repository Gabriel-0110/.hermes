#!/bin/zsh
cd /Users/openclaw/.hermes/hermes-agent
exec /Users/openclaw/.hermes/.venv/bin/python -m hermes_cli.main gateway run --replace
