#!/usr/bin/env python3
"""Execution health check - verifies API connectivity, positions, and order state."""
import os, sys, json
from pathlib import Path
from datetime import datetime, timezone

# Load env from orchestrator (has all exchange keys)
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
result = {
    "time": now,
    "api_ok": False,
    "positions": [],
    "open_orders_count": 0,
    "futures_equity": None,
    "spot_usdt": None,
    "error": None
}

try:
    from backend.integrations.execution.ccxt_client import CCXTExecutionClient
    c = CCXTExecutionClient()
    ex = c._get_exchange()

    # Balance check
    bal = ex.fetch_balance()
    result["api_ok"] = True

    usdt_free = bal.get('USDT', {}).get('free', 0) or 0
    result["spot_usdt"] = round(float(usdt_free), 2)

    # Futures positions
    try:
        pos = ex.fetch_positions()
        for p in pos:
            amt = float(p.get('contracts') or 0)
            if abs(amt) > 0:
                result["positions"].append({
                    "symbol": p.get('symbol', '?'),
                    "side": p.get('side', '?'),
                    "size": amt,
                    "pnl": round(float(p.get('unrealizedPnl') or 0), 2),
                    "entry": p.get('entryPrice'),
                    "mark": p.get('markPrice'),
                })
    except Exception as e:
        result["positions"] = [{"error": str(e)[:100]}]

    # Open orders
    try:
        orders = ex.fetch_open_orders()
        result["open_orders_count"] = len(orders)
    except Exception as e:
        result["open_orders_count"] = f"error: {str(e)[:80]}"

except Exception as e:
    result["error"] = str(e)[:200]

print(json.dumps(result, indent=2))
