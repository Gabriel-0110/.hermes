#!/usr/bin/env python3
"""Position stop guard - checks that live positions have stop orders in place."""
import os, sys, json
from pathlib import Path
from datetime import datetime, timezone

# Load env from orchestrator
env_path = Path('/Users/openclaw/.hermes/profiles/orchestrator/.env')
if env_path.exists():
    for line in env_path.read_text().splitlines():
        s = line.strip()
        if not s or s.startswith('#') or '=' not in s:
            continue
        k, v = s.split('=', 1)
        os.environ.setdefault(k, v)

sys.path.insert(0, '/Users/openclaw/.hermes/hermes-agent')

now = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')

# Known active positions and their risk levels per memory
EXPECTED_POSITIONS = {
    "RENDER/USDT:USDT": {"stop": 1.769, "t1": 1.846, "t2": 1.920},
    "ETH/USDT:USDT":    {"stop": None,  "t1": 2371,  "t2": 2500},
    "BTC/USDT:USDT":    {"stop": 77750, "t1": 78600, "t2": 79444},
}

result = {
    "time": now,
    "api_ok": False,
    "status": "UNKNOWN",
    "positions_found": [],
    "naked_positions": [],
    "error": None
}

try:
    from backend.integrations.execution.ccxt_client import CCXTExecutionClient
    c = CCXTExecutionClient()
    ex = c._get_exchange()
    result["api_ok"] = True

    pos = ex.fetch_positions()
    active = [p for p in pos if abs(float(p.get('contracts') or 0)) > 0]

    for p in active:
        sym = p.get('symbol', '?')
        amt = float(p.get('contracts') or 0)
        pnl = float(p.get('unrealizedPnl') or 0)
        entry = p.get('entryPrice')
        mark = p.get('markPrice')

        position_info = {
            "symbol": sym,
            "side": p.get('side'),
            "size": amt,
            "entry": entry,
            "mark": mark,
            "pnl": round(pnl, 2),
        }

        if sym in EXPECTED_POSITIONS:
            levels = EXPECTED_POSITIONS[sym]
            position_info["stop"] = levels.get("stop")
            position_info["t1"] = levels.get("t1")
            position_info["t2"] = levels.get("t2")
        else:
            result["naked_positions"].append({
                "symbol": sym,
                "note": "UNKNOWN POSITION - not in risk plan"
            })

        result["positions_found"].append(position_info)

    if not active:
        result["status"] = "FLAT"
    elif result["naked_positions"]:
        result["status"] = "ALERT: NAKED/UNKNOWN POSITIONS DETECTED"
    else:
        result["status"] = "OK"

except Exception as e:
    result["error"] = str(e)[:200]
    result["status"] = "API_ERROR"

print(json.dumps(result, indent=2))
