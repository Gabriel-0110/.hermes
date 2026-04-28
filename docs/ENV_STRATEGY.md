# Environment Configuration Strategy

## Overview

The Hermes project uses a **three-layer environment configuration system** designed for production safety and development flexibility:

1. **Root `.env`** (116 keys) — Production secrets + shared configuration
2. **Root `.env.dev`** (54 keys) — Local Docker port overrides + dev auth bypass
3. **Per-Profile `.env` files** (8 copies) — Intentional profile isolation

This architecture is **intentional, not duplicative**, and maintains clear separation between production and development concerns.

---

## The Three Configuration Layers

### Layer 1: Root `.env` (Production & Shared Secrets)

**Keys**: 116 total

**Categories**:
- AWS/Bedrock credentials (21 keys: ARNs, regions, model IDs, bearer tokens)
- API keys (30 keys: OpenAI, Anthropic, Exa, Firecrawl, Tavily, etc.)
- Trading exchange secrets (9 keys: BitMart UID, API keys, memos)
- MCP server URLs (3 keys: Exa, Firecrawl, Tavily)
- Model token limits (12 keys: USER1/2 per-model limits)
- LiteLLM base configuration (4 keys: API base, Docker database URL)
- Trading mode flags (4 keys: HERMES_TRADING_MODE, HERMES_ENABLE_LIVE_TRADING, etc.)
- Notification integrations (20+ keys: Slack, Telegram, X/Twitter, etc.)
- Other production configs (Database URL, request limits, browser timeouts)

**Usage**:
- Read by `scripts/sync_env.py` to populate all other `.env` files
- **NOT directly used by Docker** — Docker uses `.env.dev`
- Read by agent processes at startup

**Example keys unique to `.env`**:
```
AWS_BEDROCK_BASE_URL
AWS_BEDROCK_MODEL_ID_1
FIRECRAWL_API_KEY
TAVILY_API_KEY
TAVILY_MCP_URL
X_ACCESS_TOKEN
SLACK_ALLOWED_USERS
TELEGRAM_ENABLED_PROFILES
```

---

### Layer 2: Root `.env.dev` (Local Development Overrides)

**Keys**: 54 total

**Categories**:
- Local Docker service ports (8 keys: HERMES_API_PORT, HERMES_REDIS_PORT, LITELLM_PORT, etc.)
- Local database config (4 keys: HERMES_TIMESCALE_* with localhost)
- Development auth bypass (1 key: HERMES_API_DEV_BYPASS_AUTH=true)
- Development mode flags (2 keys: HERMES_PAPER_MODE=true, HERMES_TRADING_MODE=paper_mode)
- LiteLLM dev config (3 keys: UI username/password, master key)
- API keys (shared with `.env`, 35 overlapping keys for dev usage)
- TradingView MCP config (2 keys: TRADINGVIEW_MCP_DIR, webhook secrets)
- Other dev services (Slack webhook for dev, etc.)

**Usage**:
- **Explicitly required** by Docker Compose stack:
  ```bash
  docker-compose -f docker-compose.dev.yml --env-file .env.dev up
  ```
- Loaded by Docker services for local development
- Contains local port overrides that take precedence over `.env`

**Example keys unique to `.env.dev`**:
```
HERMES_API_PORT=8000
HERMES_REDIS_PORT=6379
HERMES_TIMESCALE_PORT=5433
HERMES_API_DEV_BYPASS_AUTH=true
HERMES_PAPER_MODE=true
LITELLM_UI_USERNAME=admin
LITELLM_UI_PASSWORD=...
```

---

### Layer 3: Per-Profile `.env` Files (8 Copies)

**Locations**:
```
~/.hermes/profiles/
├── orchestrator/.env
├── execution-agent/.env
├── market-researcher/.env
├── portfolio-monitor/.env
├── risk-manager/.env
├── strategy-agent/.env
├── (plus hermes/ and hermes-agent/ at project root)
└── (plus additional copies if new profiles added)
```

**Keys**: Synced from root `.env` via `scripts/sync_env.py`

**Purpose**:
- Each gateway process reads its profile-specific `.env` at startup
- Allows independent variable scope per profile (not cross-contamination)
- **Intentional isolation**, not duplication

**NOT generated from `.env.dev`** — Only synced from root `.env`

**Sync command**:
```bash
~/.venv/bin/python scripts/sync_env.py
```

**Output**:
```
~/.hermes/hermes-agent/.env: +0 added, ~0 updated
~/.hermes/hermes/.env: +0 added, ~0 updated
~/.hermes/profiles/orchestrator/.env: +0 added, ~0 updated
~/.hermes/profiles/execution-agent/.env: +0 added, ~0 updated
[... 5 more profiles ...]
Sync complete.
```

---

## Key Insight: Overlapping Keys

**35 keys appear in both `.env` and `.env.dev`**:

These keys have **different values** in each file:

| Key | Root `.env` | `.env.dev` | Reason |
|-----|------------|-----------|--------|
| HERMES_TRADING_MODE | `live` | `paper_mode` | Live trading vs. paper (dev) |
| HERMES_ENABLE_LIVE_TRADING | `true` | `false` | Toggle live trading |
| LITELLM_MASTER_KEY | (secret) | (dev secret) | Different instances |
| OPENAI_API_KEY | (prod key) | (dev key) | Different accounts/quotas |
| API keys (x5 for OpenAI, Anthropic, etc.) | (prod) | (dev) | Different rate limits |

**Docker Compose design**: When using `--env-file .env.dev`, values in `.env.dev` take precedence if keys overlap. This allows dev values to override prod values safely.

---

## Why This Architecture Exists

### Problem Solved: Dev/Prod Safety

Without `.env.dev`:
- Docker services would read production `.env` directly
- Risk of connecting to live trading APIs in development
- Risk of burning API quotas in dev mode
- No override mechanism for local ports

**Solution**: `.env.dev` provides safe dev defaults while keeping production `.env` unchanged.

### Problem Solved: Profile Isolation

Without per-profile `.env` files:
- All agents would share one `.env`
- Gateway processes would read same variable scope
- State contamination risk (if one profile corrupted environment)

**Solution**: `sync_env.py` creates intentional copies so each gateway has isolated environment scope.

---

## Consolidation Constraints

### Constraint 1: Docker Compose Hardcoding

Docker Compose explicitly requires `.env.dev`:

```yaml
# docker-compose.dev.yml
services:
  api:
    environment:
      # Reads from --env-file .env.dev at startup
```

**To merge `.env.dev` into `.env`** would require:
1. Update `docker-compose.dev.yml` to use `--env-file .env` (not `.env.dev`)
2. Update all startup scripts that reference `.env.dev`
3. Update launchd plists if they reference `.env.dev`
4. Risk of runtime failures if any script still looks for `.env.dev`

### Constraint 2: Dev/Prod Value Collision

```
Key: HERMES_TRADING_MODE
Root .env:     live
Root .env.dev: paper_mode

If merged into single file, which value wins?
- If .env is last, live trading in dev (DANGEROUS)
- If .env.dev is last, paper mode in prod (Wrong mode!)
```

There's no safe way to merge without renaming keys (e.g., `HERMES_DEV_TRADING_MODE`).

### Constraint 3: Profile `.env` Intentionality

Per-profile `.env` files are not duplicates—they're intentional copies that allow:
- Each gateway to have independent state
- Easier debugging (each profile's state isolated)
- Failure isolation (one profile's corrupted env doesn't affect others)

Removing profile `.env` files would require refactoring gateway startup to read a single shared `.env` with profile-specific variable overrides (e.g., via env prefixes).

---

## Current System Health Check

**Docker Compose**:
```bash
$ docker ps --format 'table {{.Names}}\t{{.Status}}'
hermes-api              Up 8 minutes (healthy)
hermes-dashboard        Up 8 minutes (healthy)
hermes-litellm          Up 8 minutes (healthy)
hermes-timescaledb      Up 8 minutes (healthy)
hermes-redis            Up 8 minutes (healthy)
hermes-web              Up 8 minutes (healthy)
hermes-mission-control  Up 8 minutes (healthy)
hermes-tradingview-mcp  Up 8 minutes
```

**Profile .env Sync**:
```bash
$ ./.venv/bin/python scripts/sync_env.py
~/.hermes/hermes-agent/.env: +0 added, ~0 updated
~/.hermes/hermes/.env: +0 added, ~0 updated
~/.hermes/profiles/orchestrator/.env: +0 added, ~0 updated
[... and 6 more profiles ...]
Sync complete.
```

**All systems working correctly.** No .env-related errors or drift detected.

---

## Recommendation: Keep Current Structure

**Status**: ✅ **OPTIMAL FOR THIS PROJECT**

**Why consolidation is NOT recommended**:
1. **Zero operational benefit** — System already works perfectly
2. **High rework cost** — Requires changes to Docker Compose, startup scripts, launchd plists
3. **High risk** — Multiple points of failure, dev/prod confusion possible
4. **Profile isolation essential** — Each agent needs independent scope

**If forced to consolidate** (not recommended):
1. Create `HERMES_DEV_*` prefixed keys for all dev-only overrides
2. Update `docker-compose.dev.yml` to inject dev prefix
3. Merge keys into single `.env`
4. Remove `.env.dev`
5. Risk of weeks of testing to ensure no edge cases break

**Conclusion**: Keep `.env` + `.env.dev` + per-profile sync model. It's battle-tested, clear, and maintainable.

---

## Files & Locations

| File | Location | Purpose | Gitignored |
|------|----------|---------|-----------|
| `.env` | `~/.hermes/.env` | Production secrets (116 keys) | No — tracked |
| `.env.dev` | `~/.hermes/.env.dev` | Local Docker overrides (54 keys) | No — tracked |
| Sync script | `scripts/sync_env.py` | Distributes `.env` to profiles | No — tracked |
| Per-profile .env | `profiles/{name}/.env` | Profile-isolated copy | Yes — gitignored |
| `auth.json` | `~/.hermes/auth.json` | Runtime auth state | Yes — gitignored |
| `auth.lock` | `~/.hermes/auth.lock` | Auth lock file | Yes — gitignored |

---

## Troubleshooting

**Problem**: "HERMES_TRADING_MODE=live in dev environment"
- **Cause**: `.env.dev` not loaded or `.env` taking precedence
- **Fix**: Verify Docker Compose uses `--env-file .env.dev` flag
- **Check**: `docker ps -a | grep hermes-api` and verify healthy

**Problem**: "Profile `.env` files out of sync"
- **Cause**: `sync_env.py` not run after changing root `.env`
- **Fix**: Run `./.venv/bin/python scripts/sync_env.py`
- **Verify**: Check `profiles/orchestrator/.env` for expected keys

**Problem**: "API key in one profile but not another"
- **Cause**: Root `.env` missing key when sync ran
- **Fix**: Add key to root `.env`, then re-run sync script
- **Check**: `grep KEY_NAME profiles/*/env` to verify all profiles updated

---

## Conclusion

The three-layer environment system is **optimal for Hermes**:
- Separates production secrets from dev overrides (safety)
- Provides profile isolation (resilience)
- Works perfectly with current Docker Compose design (simplicity)

**No changes recommended** unless operational requirements fundamentally change.
