# DefiLlama Migration Summary

## Goal

Add a shared DefiLlama integration to Hermes for DeFi protocol, chain, yield, DEX, fee, and open-interest intelligence while keeping the architecture compatible with Hermes Agents and Paperclip.

## Delivered

- Added shared client:
  [backend/integrations/defi/defillama_client.py](../../backend/integrations/defi/defillama_client.py)
- Added normalized schemas in:
  [backend/models.py](../../backend/models.py)
- Added backend tool wrappers:
  [backend/tools/get_defi_protocols.py](../../backend/tools/get_defi_protocols.py)
  [backend/tools/get_defi_protocol_details.py](../../backend/tools/get_defi_protocol_details.py)
  [backend/tools/get_defi_chain_overview.py](../../backend/tools/get_defi_chain_overview.py)
  [backend/tools/get_defi_yields.py](../../backend/tools/get_defi_yields.py)
  [backend/tools/get_defi_dex_overview.py](../../backend/tools/get_defi_dex_overview.py)
  [backend/tools/get_defi_fees_overview.py](../../backend/tools/get_defi_fees_overview.py)
  [backend/tools/get_defi_open_interest.py](../../backend/tools/get_defi_open_interest.py)
  [backend/tools/get_defi_regime_summary.py](../../backend/tools/get_defi_regime_summary.py)
- Registered the new tools in:
  [tools/trading_tools.py](../../tools/trading_tools.py)
- Updated least-privilege runtime toolsets in:
  [toolsets.py](../../toolsets.py)
- Updated agent-policy docs in:
  [AGENT_PROFILES.md](AGENT_PROFILES.md)
  [INTEGRATIONS.md](INTEGRATIONS.md)

## Design choices

- Free API only: Hermes uses `https://api.llama.fi` and does not introduce a paid-plan dependency.
- No duplicate integration layer: all DefiLlama logic is centralized in one shared client.
- Structured normalization: protocol, chain, metric, open-interest, and regime outputs are normalized into Pydantic schemas.
- Safe failure behavior: tools return sanitized envelopes instead of raw upstream failures.
- Future compatibility: the internal tool names stay stable even if the backend later upgrades to a paid plan or a broader endpoint surface.

## Important constraint captured in code

As verified on April 16, 2026:

- `/overview/dexs` is available on the free API.
- `/overview/fees` is available on the free API.
- `/overview/derivatives` requires a paid plan.
- `/pools` is not reliably available on the free `api.llama.fi` base URL.

Because of that:

- `get_defi_open_interest` returns a partial but explicit fallback using derivatives protocol TVL/trend data.
- `get_defi_yields` fails safely when the free base URL does not expose pools.
- `get_defi_regime_summary` includes warnings when parts of the free surface are unavailable.

## Next possible step

If Step 11 or later upgrades Hermes to a paid DefiLlama plan, the migration should happen inside the shared client only. The agent contracts and tool names should remain unchanged.
