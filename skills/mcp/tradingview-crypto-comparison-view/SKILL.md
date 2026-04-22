---
name: tradingview-crypto-comparison-view
description: Create a BTC/ETH/SOL view in TradingView via MCP, with a fallback to comparison overlays when multi-chart layouts are blocked by TradingView plan limits.
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [TradingView, MCP, crypto, charts]
---

# TradingView crypto comparison view

Use this when the goal is to set up a quick TradingView view for major crypto symbols like BTC, ETH, and SOL using the TradingView MCP tools.

## Goal

Preferred outcome:
- 3-chart layout with one symbol per pane

Reliable fallback:
- Single chart with BTC as the base symbol and ETH + SOL added as overlay comparison symbols

## Workflow

1. Verify TradingView MCP connectivity.
   - Run `mcp_tradingview_tv_health_check`
   - Confirm `cdp_connected: true` and `api_available: true`

2. Resolve symbols before changing the chart.
   - Use `mcp_tradingview_symbol_search` for each requested symbol
   - Pick concrete exchange-qualified symbols such as:
     - `BITSTAMP:BTCUSD`
     - `BITSTAMP:ETHUSD`
     - `COINBASE:SOLUSD`

3. Try to create the requested multi-chart layout first.
   - Use `mcp_tradingview_pane_set_layout` if available
   - Then verify with `mcp_tradingview_pane_list`
   - Do not trust the layout-set call alone; verify actual pane count afterward

4. If the pane count does not change, inspect the UI state.
   - Use `mcp_tradingview_tv_ui_state`
   - If a premium/trial/paywall modal appears, the layout change likely failed because the account cannot access multi-chart layouts

5. Fallback to comparison overlays on the current chart.
   - Keep BTC as the base chart symbol
   - Click `Compare symbols`
   - Search and add ETH and SOL from the compare dialog
   - Close the compare menu when finished

6. Verify the fallback view worked.
   - Use `mcp_tradingview_chart_get_state`
   - Expect one or more `Overlay` studies to appear
   - Use `mcp_tradingview_data_get_indicator(entity_id)` on each overlay study to confirm the actual compared symbols

7. Capture a screenshot for proof.
   - Use `mcp_tradingview_capture_screenshot region=chart`

## Verification checklist

A successful fallback view usually looks like:
- Base symbol remains BTC on the main chart
- `chart_get_state` shows `Overlay` studies
- `data_get_indicator` on those overlays shows symbols like `BITSTAMP:ETHUSD` and `COINBASE:SOLUSD`

## Pitfalls

- `mcp_tradingview_pane_set_layout` can report success even when TradingView does not actually switch layouts. Always verify with `mcp_tradingview_pane_list`.
- A TradingView premium/trial upsell modal can block multi-chart layouts. When this happens, use comparison overlays instead of repeatedly retrying pane layout changes.
- Text-based UI clicks may fail for layout choices like `3h`; coordinate clicks or DOM inspection may be needed to diagnose the menu, but if a paywall modal appears, stop pursuing the pane layout and switch to the overlay fallback.
- After adding comparison symbols, verify overlays by reading the indicator inputs rather than assuming the correct symbols were added.

## Reusable symbol set

For a common major-crypto view:
- BTC: `BITSTAMP:BTCUSD`
- ETH: `BITSTAMP:ETHUSD`
- SOL: `COINBASE:SOLUSD`
