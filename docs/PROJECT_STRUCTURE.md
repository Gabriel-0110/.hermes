# Hermes Project Structure & Organization

## Root Directory Layout

### Core Project Files (Required)

These files **must** remain at the root level as they are the project entry points:

- `README.md` — Main project documentation and navigation
- `Makefile` — Build and orchestration commands
- `docker-compose.dev.yml` — Local dev stack (8 containers: TimescaleDB, Redis, LiteLLM, API, Web, Dashboard, Mission Control, TradingView MCP)
- `docker-compose.yml` — Potential production compose (reference)
- `pyproject.toml` — Python project metadata and build config
- `package.json` — Node.js dependencies (dashboard)
- `config.yaml` — Main project configuration
- `SOUL.md` — Project mission/identity document

### Environment & Secrets (Required at Root)
- `.env` — **116 keys**: Production secrets, API keys, AWS Bedrock config, MCP URLs, model token limits
- `.env.dev` — **54 keys**: Local Docker port overrides, auth bypass, paper trading mode
  - **CRITICAL**: Explicitly required by Docker Compose via `--env-file .env.dev` flag
  - Cannot be merged into `.env` without reworking `docker-compose.dev.yml`
  - Contains 35 overlapping keys with `.env` + 19 unique dev-only keys
- `auth.json`, `auth.lock` — Runtime authentication state (gitignored)

### Legitimate Root Directories (Active & Necessary)

#### `cache/` — Multi-format Content Caching
**Status**: ✅ **ACTIVE** — Used by credential tools and TTS systems

Referenced in code:
```python
# hermes-agent/tools/credential_files.py:345-347
("cache/documents", "document_cache")
("cache/images", "image_cache")
("cache/audio", "audio_cache")

# hermes-agent/tools/tts_tool.py:97
get_hermes_dir("cache/audio", "audio_cache")
```

**Subdirectories**:
- `cache/documents/` — Cached document files
- `cache/images/` — Cached image files
- `cache/audio/` — Cached audio/TTS files
- `cache/screenshots/` — Browser screenshot cache

#### `skills/` — Shared Skill Scripts
**Status**: ✅ **ACTIVE** — Main skill library loaded by all agents

Referenced in code:
```python
# hermes-agent/hermes_constants.py:235-237
def get_skills_dir() -> Path:
    return get_hermes_home() / "skills"

# Used by: prompt_builder.py, skill_utils.py
```

**Purpose**: Skills are loaded at agent startup and distributed to each profile's `.env` file via `scripts/sync_env.py`.

#### `scripts/` — Utility & Bootstrap Scripts
**Status**: ✅ **ACTIVE** — Contains critical setup scripts

Key scripts:
- `sync_env.py` — Syncs root `.env` keys to all profile `.env` files
- `ensure_project_stack.sh` — Docker Compose bootstrap (called by launchd)
- `*.sh` — Various utility scripts

#### `profiles/` — Agent Profile Definitions
**Status**: ✅ **ACTIVE** — 6 trading agent profiles

Structure:
```
profiles/
├── orchestrator/          # Central coordinator
├── execution-agent/       # Order executor
├── market-researcher/     # Market intelligence
├── portfolio-monitor/     # Position tracking
├── risk-manager/          # Risk gatekeeper
└── strategy-agent/        # Trade idea generation
```

Each profile contains:
- `.env` — Synced from root `.env` (intentional isolation)
- `bin/start_gateway.sh` — Profile-specific startup
- `skills/` — Profile-specific skill overrides
- `sessions/` — Runtime session state (gitignored)
- `home/.codex/` — Cache directories

#### `teams/` — Team Configuration
**Status**: ✅ **ACTIVE** — Trading desk orchestration

Referenced in code:
```python
# teams/trading-desk/scripts/bitmart_paper_guard.py:12
ROOT = Path('/Users/openclaw/.hermes/teams/trading-desk')
```

**Structure**:
```
teams/
└── trading-desk/
    ├── TEAM.md          # Team manifest
    ├── agents.yaml      # Agent definitions
    ├── scripts/         # Team-specific tools
    └── skills/          # Team-specific skills
```

#### `docs/` — Project Documentation
**Status**: ✅ **ACTIVE** — Central documentation hub

**Key docs**:
- `PROJECT_USAGE_AND_OPERATIONS_GUIDE.md` — Operations manual
- `GATEWAY_RUNTIME.md` — Gateway state architecture
- `architecture/` — Architectural reference materials
- `workspace/` — Workspace configuration guides

#### `cron/` — Scheduled Job Definitions
**Status**: ✅ **ACTIVE** — Background task scheduling

**Files**:
- `jobs.json` — Cron job definitions
- `output/` — Job execution logs (runtime, gitignored)

#### `logs/` — Runtime Logs
**Status**: ✅ **ACTIVE** — Application logging

**Files**:
- `agent.log.1`, `agent.log.2`, `.log.3` — Rotating agent logs
- `errors.log` (in profiles/) — Per-profile error logs

#### `sessions/` — Gateway Session State
**Status**: ✅ **ACTIVE** — Runtime session persistence

Referenced in code:
```python
# hermes-agent/mcp_serve.py:66
return get_hermes_home() / "sessions"

# hermes-agent/gateway/config.py:266
sessions_dir: Path = field(default_factory=lambda: get_hermes_home() / "sessions")
```

**Files**:
- `sessions/sessions.json` — Active session manifest

#### `sandboxes/` — Execution Sandboxes
**Status**: ✅ **ACTIVE** — Isolated execution environments

Referenced in code:
```python
# hermes-agent/tools/environments/base.py:50
p = get_hermes_home() / "sandboxes"
```

**Purpose**: Docker/Singularity containers for safe code execution.

#### `memories/` — Agent Memory & Knowledge Base
**Status**: ✅ **ACTIVE** — Persistent memory system

**Structure**:
```
memories/
├── user/           # User preferences (cross-session)
├── session/        # Session-specific notes
└── repo/           # Repository-specific facts
```

#### `hermes/` & `hermes-agent/` — Main Codebases
**Status**: ✅ **ACTIVE** — Core product and framework

- `hermes/` — Product dashboard + FastAPI (Next.js + Python)
- `hermes-agent/` — Agent framework + gateway (orchestrator dashboard)

#### `hermes_constants.py`, `hermes_logging.py`, `hermes_time.py`, `hermes_state.py`
**Status**: ✅ **ACTIVE** — Root-level utilities

These files are utility modules imported by the main codebases.

### Secondary Directories (Metadata & State)
- `bin/` — Compiled binaries (`tirith`)
- `completions/` — Shell completion scripts (`hermes.zsh`)
- `config.yaml` — Configuration (already root-level file)
- `state.db*` — SQLite database for gateway state (runtime)
- `active_profile` — Current active profile marker (runtime)

### Untracked/Runtime State (Gitignored)
- `auth.lock` — Authentication lock file
- `gateway_state.json` — Gateway runtime state (authoritative in profile-specific copy)
- `processes.json` — Process checkpoint
- `models_dev_cache.json` — Model metadata cache
- `context_length_cache.yaml` — Model context length cache
- `sticker_cache.json` — Sticker cache for messaging

---

## Environment Configuration Strategy

### Why Three `.env` Files Exist

#### 1. **Root `.env` (116 keys)**
- **Scope**: Production secrets + shared configuration
- **Keys**: AWS Bedrock ARNs, API keys (OpenAI, Anthropic, etc.), MCP URLs, trading exchange secrets
- **Usage**: Read by `scripts/sync_env.py` to populate other `.env` files
- **NOT used directly by Docker** — This is the source of truth

#### 2. **Root `.env.dev` (54 keys)**
- **Scope**: Local development overrides
- **Keys**: Docker port mappings, auth bypass flags, paper trading mode
- **Usage**: **Explicitly required** by Docker Compose
  ```yaml
  # docker-compose.dev.yml
  docker-compose -f docker-compose.dev.yml --env-file .env.dev up
  ```
- **Cannot be merged into `.env`** without architectural change
- **35 overlapping keys** with `.env` (API keys, trading mode flags)
- **19 unique keys** (HERMES_API_PORT, HERMES_REDIS_PORT, etc.)

#### 3. **Per-Profile `.env` Files (8 copies)**
- **Scope**: Profile-isolated runtime configuration
- **Synced by**: `scripts/sync_env.py` (one-way, from root `.env`)
- **NOT generated from `.env.dev`** — Only from root `.env`
- **Purpose**: Allows each gateway to have independent variable scope
- **Intentional design** — Not a duplication error

### Consolidation Constraints

**Constraint 1: Docker Compose Hardcoding**
```bash
# Current (working)
docker-compose -f docker-compose.dev.yml --env-file .env.dev up

# To merge would require:
docker-compose -f docker-compose.dev.yml --env-file .env up
# + Update all scripts calling this (bin/tirith, launchd plists, etc.)
```

**Constraint 2: Dev/Prod Value Collision**
```
Root .env:        HERMES_TRADING_MODE=live
Root .env.dev:    HERMES_TRADING_MODE=paper_mode

If merged, which value wins? Risk of production mode in dev environment.
```

**Constraint 3: Profile Isolation**
```
Profile .env files are intentionally separate so each agent can have
independent variable scope. Merging into root defeats the purpose.
```

### Recommendation: Keep Current Structure

**✅ RECOMMENDED**: Maintain `.env` + `.env.dev` + per-profile sync model

**Why**:
1. **Zero rework** — System already working, verified healthy
2. **Clear separation** — Production secrets vs. dev overrides
3. **Profile isolation maintained** — Each agent has independent scope
4. **Docker Compose unchanged** — No architectural risk

**If consolidation is critical** (future work):
1. Update `docker-compose.dev.yml` to use `--env-file .env` (removes `.env.dev`)
2. Migrate `.env.dev` keys into root `.env` with dev-suffixed keys (e.g., `HERMES_DEV_API_PORT`)
3. Update all startup scripts to reference new keys
4. Risk: More complex, more points of failure, no operational benefit

---

## Git & Tracking

### Tracked at Root
- `.env` — Encrypted/obfuscated secrets only
- `config.yaml` — Non-secret configuration
- `Makefile`, `docker-compose*.yml`, `pyproject.toml`, `package.json`
- Documentation (`README.md`, `SOUL.md`, `docs/`)
- Main codebases (`hermes/`, `hermes-agent/`, `profiles/`)

### Gitignored at Root
- `auth.json`, `auth.lock` — Runtime auth state
- `gateway_state.json`, `processes.json` — Runtime state
- `models_dev_cache.json`, `context_length_cache.yaml` — Cache files
- `.firecrawl/` — External tool cache
- Profile-specific state (in `profiles/*/`)
- Logs (`logs/`, `*.log`)

### Per-Profile Gitignored (Profile-specific)
Each profile's `.gitignore` excludes:
- `auth.lock`
- `.skills_prompt_snapshot.json`
- `gateway_state.json`
- `models_dev_cache.json`
- `state.db*` (SQLite + WAL/shared-memory)

---

## Cleanup & Maintenance

### Recently Cleaned (Phase 2)
- ✅ Removed: `port3000.html`, `port3100.html` (temp browser response dumps)
- ✅ Removed: `profiles/orchestrator/home/.codex/.tmp/plugins/.git` (orphaned nested repo)
- ✅ Removed: `profiles/execution-agent/cron/output/*` (old job execution logs)
- ✅ Removed: `.firecrawl/` (untracked external tool cache)
- ✅ Moved: `DESIGN.md`, `POST_*.md`, `RELEASE_READINESS.md` → `docs/`

### Recommended Future Cleanup
- Review old log rotation files (`logs/agent.log.*`) — Consider archival strategy
- Monitor `sessions/` size — Consider session history rotation
- Review `cron/output/` — Ensure new runs also gitignored
- Cache directory rotation — Consider TTL for old cache files

---

## Directory Size Overview

```
Large directories (by typical size):
├── hermes/                      ~500MB (Next.js build artifacts)
├── hermes-agent/                ~400MB (Python packages, tests)
├── profiles/*/home/.codex/      ~100MB+ (Model cache, state)
├── cache/images/                ~50MB+ (Accumulated images)
├── cache/documents/             ~20MB+ (Accumulated documents)
└── node_modules/                ~800MB+ (npm dependencies)

Runtime state (gitignored, always recreated):
├── sessions/                    ~5MB (session manifests)
├── logs/                        ~10MB (rotating logs)
├── sandboxes/                   ~Variable (container images)
└── state.db*                    ~5MB (SQLite database)
```

---

## Summary

| Folder | Status | Reason | Size |
|--------|--------|--------|------|
| `cache/` | ✅ Active | Content caching (docs, images, audio) | ~70MB |
| `skills/` | ✅ Active | Shared skill library | ~30MB |
| `profiles/` | ✅ Active | Agent profile definitions | ~200MB |
| `teams/` | ✅ Active | Team orchestration config | ~5MB |
| `docs/` | ✅ Active | Project documentation | ~20MB |
| `cron/` | ✅ Active | Job scheduling | ~1MB |
| `logs/` | ✅ Active | Application logs | ~10MB |
| `sessions/` | ✅ Active | Gateway session state | ~5MB |
| `sandboxes/` | ✅ Active | Execution environments | Variable |
| `memories/` | ✅ Active | Agent memory system | ~2MB |
| `hermes/` | ✅ Active | Product code | ~500MB |
| `hermes-agent/` | ✅ Active | Agent framework | ~400MB |
| `scripts/` | ✅ Active | Utility scripts | ~1MB |
| `bin/` | ✅ Active | Compiled binaries | ~5MB |
| `completions/` | ✅ Active | Shell completions | ~1KB |

**Total project size**: ~1.2GB (excluding node_modules / .venv)

All folders are legitimate and actively used by the codebase.
