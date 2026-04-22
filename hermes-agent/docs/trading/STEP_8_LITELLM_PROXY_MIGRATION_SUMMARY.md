# Step 8 LiteLLM Proxy Migration Summary

## What changed

- Added a repo-local [litellm_config.yaml](../../litellm_config.yaml) template with named routes for Hermes / Paperclip:
  - `orchestrator-default`
  - `research-cheap`
  - `research-strong`
  - `risk-stable`
  - `strategy-default`
  - `local-fast`
- Added [docker-compose.litellm.yml](../../docker-compose.litellm.yml) for running LiteLLM as a local gateway container.
- Added helper scripts:
  - [scripts/start-litellm.sh](../../scripts/start-litellm.sh)
  - [scripts/start-litellm-docker.sh](../../scripts/start-litellm-docker.sh)
- Added `litellm_gateway` config normalization in [hermes_cli/config.py](../../hermes_cli/config.py).
  Hermes now synthesizes a named `providers.litellm` entry and `model_aliases` from that block.
- Added LiteLLM-related env var registry entries:
  - `LITELLM_API_KEY`
  - `LITELLM_MASTER_KEY`
  - `LITELLM_API_BASE`
  - `LITELLM_PORT`
- Added database-backed virtual-key setup expectations:
  - `LITELLM_DATABASE_URL` / standard Postgres URL
  - `general_settings.master_key`
  - `general_settings.database_url`
  - `scripts/generate-litellm-key.sh` for `/key/generate`
- Updated [cli-config.yaml.example](../../cli-config.yaml.example), [AGENT_PROFILES.md](AGENT_PROFILES.md), [INTEGRATIONS.md](INTEGRATIONS.md), and [website/docs/integrations/providers.md](../../website/docs/integrations/providers.md).

## New operating model

- Hermes and Paperclip should point at LiteLLM as the OpenAI-compatible endpoint.
- Agent-facing configs should use named route ids, not provider-native model slugs.
- Upstream provider keys stay in backend env only.
- Hermes agents may use a LiteLLM client key, but they should never see raw upstream provider secrets.
- LiteLLM virtual keys should be generated from the master/admin key and can be scoped with `user_id`, `team_id`, budgets, and RPM/TPM limits.

## Suggested Hermes config

```yaml
model:
  default: orchestrator-default
  provider: litellm

litellm_gateway:
  enabled: true
  provider_name: litellm
  api_base: http://localhost:4000/v1
  api_key_env: LITELLM_API_KEY
  default_route: orchestrator-default
  routes:
    orchestrator-default: orchestrator-default
    research-cheap: research-cheap
    research-strong: research-strong
    risk-stable: risk-stable
    strategy-default: strategy-default
    local-fast: local-fast
```

## Migration notes

- Existing LM Studio / other local OpenAI-compatible setups still work. `local-fast` is reserved as the stable route name for that local path.
- Existing direct-provider Hermes configs still work. LiteLLM is additive and optional.
- Spend controls are intentionally left at the LiteLLM boundary. This keeps agent prompts and tool calls free of provider billing logic while giving the backend one place to enforce policy later.
