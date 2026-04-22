# LiteLLM virtual keys for Hermes profiles

This workspace is now wired so each Hermes role profile can point at the same local LiteLLM proxy while using a different virtual key.

## 1. Fix the root env first

Update `~/.hermes/.env` with a real admin key and a Postgres URL LiteLLM accepts:

- `DATABASE_URL` must use `postgresql://...`, not SQLAlchemy-style `postgresql+psycopg://...`
- `LITELLM_MASTER_KEY` must start with `sk-`
- `LITELLM_PORT` defaults to `4001` in this workspace to avoid the existing port-4000 conflict
- `LITELLM_API_BASE` defaults to `http://localhost:4001/v1`

## 2. Start the proxy

### Docker

Use the DB-backed image:

- `cd ~/.hermes/hermes-agent`
- `scripts/start-litellm-docker.sh`

### Local CLI

- `cd ~/.hermes/hermes-agent`
- `scripts/start-litellm.sh`

Both helpers now fail fast if `DATABASE_URL` is missing, if `LITELLM_MASTER_KEY` does not start with `sk-`, or if the database URL uses the wrong scheme for LiteLLM.
They also default to loading `~/.hermes/.env` and `~/.hermes/litellm_config.yaml`, so you do not need to export everything into your shell by hand first.
The Docker helper automatically rewrites `localhost` / `127.0.0.1` database hosts to `host.docker.internal` so a host-local Postgres instance remains reachable from the LiteLLM container on macOS.

## 3. Generate one key per profile

Each profile is mapped to a LiteLLM route:

| Profile | Route |
| --- | --- |
| `orchestrator` | `orchestrator-default` |
| `market-researcher` | `research-default` |
| `portfolio-monitor` | `portfolio-default` |
| `risk-manager` | `risk-default` |
| `strategy-agent` | `strategy-default` |

Generate and write a key straight into a profile env file:

- `scripts/generate-litellm-key.sh orchestrator --write-env ~/.hermes/profiles/orchestrator/.env`
- `scripts/generate-litellm-key.sh market-researcher --write-env ~/.hermes/profiles/market-researcher/.env`
- `scripts/generate-litellm-key.sh portfolio-monitor --write-env ~/.hermes/profiles/portfolio-monitor/.env`
- `scripts/generate-litellm-key.sh risk-manager --write-env ~/.hermes/profiles/risk-manager/.env`
- `scripts/generate-litellm-key.sh strategy-agent --write-env ~/.hermes/profiles/strategy-agent/.env`

Optional limits can be supplied via environment variables before you run the script:

- `LITELLM_KEY_DURATION=30d`
- `LITELLM_KEY_MAX_BUDGET=25`
- `LITELLM_KEY_TPM_LIMIT=120000`
- `LITELLM_KEY_RPM_LIMIT=120`

## 4. What changed in the profiles

The role profiles under `~/.hermes/profiles/` now:

- use `model.provider: litellm`
- use the route name as the default model
- expect a profile-local `LITELLM_API_KEY`
- no longer depend on inline upstream provider secrets in `config.yaml`

The root workspace config at `~/.hermes/config.yaml` now follows the same pattern for the default non-profile experience:

- `model.provider: litellm`
- default route `orchestrator-default`
- shared `litellm_gateway` routes for all five primary roles

## 5. Verify a key

After generating a key, verify spend and metadata through LiteLLM:

- `curl "$LITELLM_API_BASE/key/info?key=<generated-key>" -H "Authorization: Bearer $LITELLM_MASTER_KEY"`

You can also open `http://localhost:4000/ui` if you set `LITELLM_UI_USERNAME` and `LITELLM_UI_PASSWORD` before starting the Docker proxy.
In this workspace, if you use the default env values above, the UI will be on `http://localhost:4001/ui`.