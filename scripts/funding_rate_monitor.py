#!/usr/bin/env python3
"""Funding Rate Monitor - Hermes Trading Desk.

Checks BitMart perpetual funding rates + TwelveData RSI via curl subprocess.
Fires alerts when negative funding + oversold RSI converge (max conviction entry).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from typing import Optional

# Load env from file if vars not set
_env_file = os.path.expanduser("~/.hermes/.env")
if os.path.exists(_env_file):
    with open(_env_file) as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _, _v = _line.partition("=")
                os.environ.setdefault(_k.strip(), _v.strip().strip('"'))

TWELVEDATA_KEY = os.environ.get("TWELVEDATA_API_KEY", "")

SYMBOLS = {
    "ETHUSDT": "ETH/USD",
    "BTCUSDT": "BTC/USD",
    "SOLUSDT": "SOL/USD",
    "XRPUSDT": "XRP/USD",
}

FUNDING_ALERT_THRESHOLD = -0.00010    # -0.010%/8h triggers watch  (raw: -0.00010)
FUNDING_EXTREME_THRESHOLD = -0.00015  # -0.015%/8h = HIGH CONVICTION (raw: -0.00015)
RSI_OVERSOLD = 38.0
RSI_EXTREME_OVERSOLD = 30.0
INTERVAL = "4h"


def curl_get(url):
    # type: (str) -> Optional[dict]
    try:
        result = subprocess.run(
            ["curl", "-s", "--max-time", "8", url],
            capture_output=True, text=True, timeout=12
        )
        if result.returncode == 0 and result.stdout.strip():
            return json.loads(result.stdout)
    except Exception as e:
        print("  [WARN] curl failed for {}: {}".format(url[:60], e), file=sys.stderr)
    return None


def fetch_funding(symbol):
    # type: (str) -> Optional[float]
    url = "https://api-cloud-v2.bitmart.com/contract/public/details?symbol={}".format(symbol)
    d = curl_get(url)
    if d:
        syms = d.get("data", {}).get("symbols", [])
        if syms:
            return float(syms[0].get("funding_rate", 0))
    return None


def fetch_rsi(symbol_td):
    # type: (str) -> Optional[float]
    if not TWELVEDATA_KEY:
        return None
    sym_enc = symbol_td.replace("/", "%2F")
    url = (
        "https://api.twelvedata.com/rsi"
        "?symbol={}&interval={}&outputsize=1&apikey={}".format(
            sym_enc, INTERVAL, TWELVEDATA_KEY
        )
    )
    d = curl_get(url)
    if d:
        vals = d.get("values", [])
        if vals:
            return float(vals[0]["rsi"])
    return None


def annualize(rate_8h):
    # type: (float) -> float
    return rate_8h * 3 * 365 * 100


def main():
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    print("FUNDING RATE MONITOR -- {}".format(now))
    print("=" * 60)

    alerts = []
    high_conviction = []
    rows = []

    for bm_sym, td_sym in SYMBOLS.items():
        fr = fetch_funding(bm_sym)
        rsi = fetch_rsi(td_sym)

        if fr is not None:
            fr_str = "{:+.4f}%/8h  ann {:+.1f}%/yr".format(fr * 100, annualize(fr))
        else:
            fr_str = "N/A"
        rsi_str = "RSI={:.1f}".format(rsi) if rsi is not None else "RSI=N/A"
        rows.append("  {:<10} {:<36} {}".format(bm_sym, fr_str, rsi_str))

        if fr is not None and fr < FUNDING_ALERT_THRESHOLD:
            conviction = "MODERATE"
            rsi_label = ""
            if rsi is not None:
                if rsi < RSI_EXTREME_OVERSOLD:
                    rsi_label = "RSI {:.1f} DEEPLY OVERSOLD".format(rsi)
                    conviction = "HIGH CONVICTION -- FUNDING + RSI EXTREME"
                elif rsi < RSI_OVERSOLD:
                    rsi_label = "RSI {:.1f} oversold".format(rsi)
                    conviction = "HIGH CONVICTION -- FUNDING + RSI aligned"

            entry = {
                "symbol": bm_sym,
                "td_symbol": td_sym,
                "funding_8h": fr,
                "funding_ann_pct": annualize(fr),
                "rsi": rsi,
                "conviction": conviction,
                "rsi_label": rsi_label,
            }
            if conviction.startswith("HIGH"):
                high_conviction.append(entry)
            else:
                alerts.append(entry)

    for row in rows:
        print(row)
    print()

    if not alerts and not high_conviction:
        print("STATUS: NO_ACTION -- No symbols meet negative funding threshold.")
        print("  (threshold: {:.3f}%/8h | current ETH/BTC funding shown above)".format(
            FUNDING_ALERT_THRESHOLD * 100))
        return

    if high_conviction:
        print("!! HIGH CONVICTION ENTRIES DETECTED !!")
        for e in high_conviction:
            rsi_disp = "{:.1f}".format(e["rsi"]) if e["rsi"] is not None else "N/A"
            print("  {}: funding {:+.4f}%/8h  (ann {:+.1f}%/yr) | RSI {}".format(
                e["symbol"], e["funding_8h"] * 100, e["funding_ann_pct"], rsi_disp))
            print("  -> {}".format(e["conviction"]))
            print("  -> ACTION: Long entry. Longs collect funding every 8h as income.")
            print("  -> RISK: 2% account max. Stop below recent structure low.")
        print()

    if alerts:
        print("FUNDING ALERTS (funding threshold met -- awaiting RSI confirmation):")
        for e in alerts:
            print("  {}: {:+.4f}%/8h  (ann {:+.1f}%/yr) -- RSI {:.1f} not yet oversold".format(
                e["symbol"], e["funding_8h"] * 100, e["funding_ann_pct"],
                e["rsi"] if e["rsi"] else 0))
        print()

    if high_conviction:
        print("STATUS: HIGH_CONVICTION_ENTRY")
    else:
        print("STATUS: FUNDING_ALERT_WATCH")


if __name__ == "__main__":
    main()
