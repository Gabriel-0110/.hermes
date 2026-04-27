# Hermes — Project Usage and Operations Guide

> **Version:** 1.1 | **Date:** 2026-04-27 | **Active Profile:** orchestrator

---

## Executive Summary

Hermes is an **AI-driven cryptocurrency futures trading system** built on BitMart as the primary exchange. It combines a multi-agent AI architecture (powered by LLMs through LiteLLM) with a structured trading pipeline: market research, strategy generation, risk management, portfolio monitoring, and order execution.

The system has two major codebases:

1. **hermes** — The product monorepo: FastAPI REST API, Next.js web dashboard, Mission Control UI, TimescaleDB/Redis data tier, and shared Python packages.
2. **hermes-agent** — A fork of Nous Research's Hermes Agent: the AI agent runtime that powers the autonomous trading desk with tool-calling, cron scheduling, messaging gateway (Telegram/Slack/Discord), and a backend of 60+ trading-specific tools.

The system operates in **paper** or **live** trading mode with a triple-lock live trading safety gate. Currently configured for BitMart futures (swap/cross margin).

**Key Numbers:**

- 6 agent profiles (orchestrator, market-researcher, strategy-agent, risk-manager, portfolio-monitor, execution-agent)
- 60+ backend trading tools
- 70+ agent platform tools
- 25+ TimescaleDB hypertables
- 5 registered trading strategies
- 14 cron jobs across profiles
- 603 test files
- 7 Docker services in the unified dev stack

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Setup Guide](#2-setup-guide)
3. [Configuration Guide](#3-configuration-guide)
4. [Feature Inventory](#4-feature-inventory)
5. [Commands Guide](#5-commands-guide)
6. [API Documentation](#6-api-documentation)
7. [Database and Storage Guide](#7-database-and-storage-guide)
8. [Agents, Tools, and Models Guide](#8-agents-tools-and-models-guide)
9. [Operational Guide](#9-operational-guide)
10. [Testing Guide](#10-testing-guide)
11. [Troubleshooting Guide](#11-troubleshooting-guide)
12. [Security Review](#12-security-review)
13. [Production Readiness Report](#13-production-readiness-report)
14. [Future Development Guide](#14-future-development-guide)
15. [Action Plan](#15-action-plan)
16. [Appendix](#16-appendix)

---

## 1. Architecture Overview

### 1.1 High-Level System Diagram

```mermaid
graph TB
    subgraph "User Layer"
        TELEGRAM[Telegram Bot]
        SLACK[Slack Bot]
        DISCORD[Discord Bot]
        CLI[hermes CLI]
        WEB[Web Dashboard :3000]
        MC[Mission Control :3100]
    end

    subgraph "Agent Runtime (hermes-agent)"
        GW[Gateway / Message Router]
        AGENT[Agent Core + LLM Loop]
        TOOLS[60+ Trading Tools]
        CRON[Cron Scheduler]
        SKILLS[Skills Hub]
    end

    subgraph "LLM Gateway"
        LITELLM[LiteLLM :4000]
        BEDROCK[AWS Bedrock]
        OPENROUTER[OpenRouter]
        LMSTUDIO[LM Studio :1234]
    end

    subgraph "Product API (hermes monorepo)"
        API[FastAPI :8000]
        BRIDGE[hermes-agent Bridge]
    end

    subgraph "Data Tier"
        TSDB[(TimescaleDB :5433)]
        REDIS[(Redis :6379)]
        SQLITE[(state.db - local)]
    end

    subgraph "External Services"
        BITMART[BitMart Exchange API]
        COINGECKO[CoinGecko]
        CMC[CoinMarketCap]
        TRADINGVIEW[TradingView Webhooks/MCP]
        CRYPTOPANIC[CryptoPanic]
        NEWSAPI[NewsAPI]
        ETHERSCAN[Etherscan]
        NANSEN[Nansen]
        DEFI[DeFiLlama]
        FRED[FRED / Macro Data]
    end

    TELEGRAM --> GW
    SLACK --> GW
    DISCORD --> GW
    CLI --> AGENT
    WEB --> API
    MC --> API

    GW --> AGENT
    AGENT --> TOOLS
    AGENT --> CRON
    AGENT --> SKILLS
    AGENT --> LITELLM

    LITELLM --> BEDROCK
    LITELLM --> OPENROUTER
    LITELLM --> LMSTUDIO

    API --> BRIDGE
    BRIDGE --> TOOLS

    TOOLS --> TSDB
    TOOLS --> REDIS
    TOOLS --> BITMART
    TOOLS --> COINGECKO
    TOOLS --> CMC
    TOOLS --> TRADINGVIEW
    TOOLS --> CRYPTOPANIC
    TOOLS --> NEWSAPI
    TOOLS --> ETHERSCAN
    TOOLS --> NANSEN
    TOOLS --> DEFI
    TOOLS --> FRED

    AGENT --> TSDB
    AGENT --> REDIS
    LITELLM --> TSDB
```

### 1.2 Component Responsibilities

| Component | Location | Purpose |
| --- | --- | --- |
| **hermes-agent** | `hermes-agent/` | AI agent runtime: LLM orchestration, tool calling, multi-platform gateway, cron scheduler |
| **hermes (product)** | `hermes/` | REST API, web UI, Mission Control, shared Python packages |
| **Backend (trading)** | `hermes-agent/backend/` | All trading logic: strategies, execution, risk, integrations, observability, DB models |
| **Gateway** | `hermes-agent/gateway/` | Multi-platform message router (Telegram, Slack, Discord, etc.) |
| **Agent core** | `hermes-agent/agent/` | LLM interaction, prompt building, context compression, model routing |
| **Tools (platform)** | `hermes-agent/tools/` | 70+ general tools: terminal, file ops, web, browser, MCP, skills, memory |
| **Tools (trading)** | `hermes-agent/backend/tools/` | 60+ trading-specific tools: market data, execution, risk, portfolio |
| **Profiles** | `profiles/` | Per-agent config: SOUL.md, config.yaml, cron jobs, channel directory |
| **LiteLLM** | Docker service | Unified LLM gateway with model routing and fallback chains |
| **TimescaleDB** | Docker service | Time-series database for all trading, workflow, and observability data |
| **Redis** | Docker service | Kill switch, event bus, caching, pub/sub |

### 1.3 Trading Workflow (Signal-to-Execution)

```mermaid
sequenceDiagram
    participant TV as TradingView / Cron Scanner
    participant EB as Event Bus (Redis Stream)
    participant WF as Trading Workflow Graph
    participant RES as Researcher Agent
    participant STRAT as Strategy Agent
    participant RISK as Risk Manager Agent
    participant ORCH as Orchestrator Agent
    participant EXEC as Execution Agent
    participant EXCH as BitMart Exchange
    participant OBS as Observability (TimescaleDB)

    TV->>EB: Signal Event (tradingview_signal_ready)
    EB->>WF: Consume Event
    WF->>RES: Gather Market Context
    RES->>WF: ResearcherOutput (market data, sentiment)
    WF->>STRAT: Generate Strategy
    STRAT->>WF: StrategyOutput (direction, confidence, sizing)
    WF->>RISK: Evaluate Risk
    RISK->>WF: RiskOutput (approved/rejected, size limits)
    WF->>ORCH: Orchestrate Decision
    ORCH->>WF: OrchestratorOutput (execute/skip/watch)

    alt Execution Approved
        WF->>EB: execution_requested event
        EB->>EXEC: Consume & Execute
        EXEC->>EXCH: place_order (via CCXT)
        EXCH->>EXEC: Order Result
        EXEC->>OBS: Record Execution Event
    else Rejected
        WF->>OBS: Record Rejection + Reason
    end

    WF->>OBS: Record All Workflow Steps
```

### 1.4 Agent Profile Architecture

```mermaid
graph LR
    subgraph "Orchestrator (Claude Opus 4.6)"
        O[Main Agent<br/>orchestrator-default]
    end

    subgraph "Specialist Agents"
        MR[Market Researcher<br/>research-default<br/>Claude Sonnet 4.6]
        SA[Strategy Agent<br/>strategy-default<br/>Claude Sonnet 4.6]
        RM[Risk Manager<br/>risk-default<br/>Claude Sonnet 4.6]
        PM[Portfolio Monitor<br/>portfolio-default<br/>Claude Sonnet 4.6]
        EA[Execution Agent<br/>execution-default<br/>Qwen 3.5 9B via LM Studio]
    end

    O --> MR
    O --> SA
    O --> RM
    O --> PM
    O --> EA

    MR -.->|research data| SA
    SA -.->|trade candidates| RM
    RM -.->|approved trades| O
    O -.->|delegate_task| EA
    PM -.->|position alerts| RM
```

### 1.5 Data Flow

**Inbound data sources:**

- TradingView webhook alerts → `tradingview_alert_events` table
- CoinGecko, CoinMarketCap, TwelveData → market price/indicator tools
- CryptoPanic, NewsAPI, LunarCrush → sentiment/news tools
- Etherscan, Nansen → on-chain/wallet tools
- DeFiLlama → DeFi protocol/TVL/yield tools
- FRED → macro economic data tools
- BitMart API → positions, balances, order book, trades, funding rates

**Outbound data:**

- BitMart API → order placement, order cancellation
- Telegram/Slack/Discord → notifications, alerts, cron output
- TimescaleDB → all workflow, decision, execution, portfolio events
- Redis → kill switch state, event bus, caching

---

## 2. Setup Guide

### 2.1 Prerequisites

- **macOS** (Darwin, primary dev platform) or Linux
- **Python 3.11+** (3.14 is in use based on `__pycache__` files)
- **Node.js 20+** (for web dashboard, Mission Control)
- **Docker & Docker Compose** (for unified dev stack)
- **uv** (Python package manager, for hermes-agent venv)
- **Git**
- **LM Studio** (optional, for local model execution-agent)
- **AWS credentials** (for Bedrock-hosted Claude models)

### 2.2 First-Time Setup

```bash
# 1. Clone the repository
cd ~/.hermes

# 2. Create environment file from template
cp .env.dev.example .env.dev
# Edit .env.dev — fill in at minimum:
#   - LITELLM_MASTER_KEY (any sk-* string)
#   - AWS_ACCESS_KEY_ID + AWS_SECRET_ACCESS_KEY (for Bedrock)
#   - At least one of: OPENAI_API_KEY, ANTHROPIC_API_KEY, GOOGLE_API_KEY
#   - BITMART_API_KEY + BITMART_SECRET + BITMART_MEMO (for exchange)
#   - TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID (optional, for notifications)

# 3. Start the Docker dev stack
make dev-up

# 4. Verify health
make dev-check

# 5. Set up hermes-agent Python environment
cd hermes-agent
python -m venv .venv  # or: uv venv
source .venv/bin/activate
pip install -e ".[all]"  # or: uv pip install -e ".[all]"

# 6. Start the agent gateway
cd ~/.hermes
./start_gateway.sh
# Or manually:
# cd hermes-agent && ../.venv/bin/python -m hermes_cli.main gateway run --replace
```

### 2.3 Verifying the Stack

After `make dev-check`, you should see:

| Service | Port | Health URL | Expected |
| --- | --- | --- | --- |
| TimescaleDB | 5433 | N/A (pg_isready) | Running |
| Redis | 6379 | N/A (redis-cli ping) | Running |
| LiteLLM | 4000 | `http://localhost:4000/health/liveliness` | 200 |
| Dashboard | 9119 | `http://localhost:9119/api/status` | 200 |
| API | 8000 | `http://localhost:8000/api/v1/healthz` | 200 |
| Web | 3000 | `http://localhost:3000` | 200 |
| Mission Control | 3100 | `http://localhost:3100` | 200 |

---

## 3. Configuration Guide

### 3.1 Environment Variables

#### Critical Variables (Required)

| Variable | Purpose | Example | Sensitive | Component |
| --- | --- | --- | --- | --- |
| `LITELLM_MASTER_KEY` | Auth key for LiteLLM gateway | `sk-hermes-dev-xxxx` | Yes | LiteLLM, all agents |
| `AWS_ACCESS_KEY_ID` | AWS Bedrock access | `AKIA...` | Yes | LiteLLM → Bedrock |
| `AWS_SECRET_ACCESS_KEY` | AWS Bedrock secret | `wJal...` | Yes | LiteLLM → Bedrock |
| `BITMART_API_KEY` | Exchange read/write | (from BitMart) | Yes | Backend tools |
| `BITMART_SECRET` | Exchange signing | (from BitMart) | Yes | Backend tools |
| `BITMART_MEMO` | Exchange memo field | (from BitMart) | Yes | Backend tools |

#### Trading Mode Controls

| Variable | Purpose | Default | Values |
| --- | --- | --- | --- |
| `HERMES_TRADING_MODE` | Trading mode selector | `paper` | `paper`, `live`, `disabled` |
| `HERMES_ENABLE_LIVE_TRADING` | Live trading gate #2 | `false` | `true`/`false` |
| `HERMES_LIVE_TRADING_ACK` | Live trading gate #3 | (empty) | Must match exact phrase |
| `HERMES_PAPER_MODE` | Force paper mode | (empty) | truthy to force paper |
| `HERMES_REQUIRE_APPROVAL` | Require operator approval | (empty) | truthy to require |
| `HERMES_BITMART_VERIFY_SIGNED_WRITES` | Verify write signatures | `false` | `true`/`false` |

**Live Trading Triple Lock:** All three of `HERMES_TRADING_MODE=live`, `HERMES_ENABLE_LIVE_TRADING=true`, and `HERMES_LIVE_TRADING_ACK=<exact phrase>` must be set simultaneously. Missing any one keeps the system in paper mode.

#### LLM Provider Keys (At Least One Required)

| Variable | Provider | Used By |
| --- | --- | --- |
| `OPENAI_API_KEY` | OpenAI | LiteLLM fallback |
| `ANTHROPIC_API_KEY` | Anthropic | LiteLLM fallback |
| `GOOGLE_API_KEY` | Google/Gemini | LiteLLM fallback |
| `OPENROUTER_API_KEY` | OpenRouter | LiteLLM fallback |
| `LM_STUDIO_API_KEY` | LM Studio (local) | execution-agent |

#### Market Data Providers (All Optional)

| Variable | Provider | Degrades If Missing |
| --- | --- | --- |
| `COINGECKO_API_KEY` | CoinGecko | Price data limited |
| `COINMARKETCAP_API_KEY` | CoinMarketCap | Rankings limited |
| `TWELVEDATA_API_KEY` | TwelveData | Indicator data missing |
| `CRYPTOPANIC_API_KEY` | CryptoPanic | News sentiment missing |
| `NEWS_API_KEY` | NewsAPI | General news missing |
| `LUNARCRUSH_API_KEY` | LunarCrush | Social sentiment missing |
| `ETHERSCAN_API_KEY` | Etherscan | On-chain data missing |
| `NANSEN_API_KEY` | Nansen | Wallet labels missing |

#### Notification Channels (Optional)

| Variable | Service | Purpose |
| --- | --- | --- |
| `TELEGRAM_BOT_TOKEN` | Telegram | Bot messaging |
| `TELEGRAM_CHAT_ID` | Telegram | Default chat target |
| `SLACK_WEBHOOK_URL` | Slack | Webhook notifications |

#### Service Ports (Override Defaults)

| Variable | Default | Service |
| --- | --- | --- |
| `LITELLM_PORT` | 4000 | LiteLLM gateway + UI |
| `HERMES_API_PORT` | 8000 | FastAPI product API |
| `HERMES_WEB_PORT` | 3000 | Next.js web dashboard |
| `HERMES_MISSION_CONTROL_PORT` | 3100 | Mission Control UI |
| `HERMES_DASHBOARD_PORT` | 9119 | Agent dashboard |
| `HERMES_TIMESCALE_PORT` | 5433 | TimescaleDB |
| `HERMES_REDIS_PORT` | 6379 | Redis |

### 3.2 Configuration Files

| File | Purpose |
| --- | --- |
| `.env.dev` | Docker dev stack environment (from `.env.dev.example`) |
| `config.yaml` | Root agent configuration (model, gateway, display, tools, etc.) |
| `SOUL.md` | Root agent personality/system prompt |
| `litellm_config.yaml` | LiteLLM model routing and fallback configuration |
| `channel_directory.json` | Slack/Telegram channel ID mappings |
| `active_profile` | Which profile is currently active (text file) |
| `processes.json` | Background process definitions (currently empty) |
| `auth.json` | Authentication state (OAuth tokens — **sensitive**) |
| `profiles/<name>/config.yaml` | Per-profile agent configuration |
| `profiles/<name>/SOUL.md` | Per-profile agent personality |
| `profiles/<name>/cron/jobs.json` | Per-profile cron job definitions |
| `profiles/<name>/channel_directory.json` | Per-profile channel mappings |

### 3.3 LiteLLM Model Routing

The LiteLLM gateway (`litellm_config.yaml`) defines 6 model routes with fallback chains:

| Route | Primary Model | Fallback 1 | Fallback 2 |
| --- | --- | --- | --- |
| `orchestrator-default` | Claude Opus 4.6 (Bedrock) | Claude Sonnet 4.6 (Bedrock) | Qwen3 Coder 480B (OpenRouter) |
| `research-default` | Claude Sonnet 4.6 (Bedrock) | Claude Haiku 4.5 (Bedrock) | Qwen3 Coder 480B (OpenRouter) |
| `portfolio-default` | Claude Sonnet 4.6 (Bedrock) | Claude Haiku 4.5 (Bedrock) | Qwen3 Coder 480B (OpenRouter) |
| `risk-default` | Claude Sonnet 4.6 (Bedrock) | Claude Haiku 4.5 (Bedrock) | Qwen 3.5 9B (LM Studio local) |
| `strategy-default` | Claude Sonnet 4.6 (Bedrock) | Claude Haiku 4.5 (Bedrock) | Qwen3 Coder 480B (OpenRouter) |
| `execution-default` | Qwen 3.5 9B (LM Studio local) | — | — |

**Fallback triggers:** Rate limit (429), overload (529), service error (503), connection failure. Cooldown: 60s per model.

---

## 4. Feature Inventory

### 4.1 Feature Summary Table

| Feature | Status | Location | Description |
| --- | --- | --- | --- |
| Multi-agent orchestration | Ready | `profiles/`, `backend/workflows/` | 6 specialized agents with role-based SOUL.md |
| Trading workflow graph | Ready | `backend/workflows/graph.py` | Pydantic-graph based signal→research→strategy→risk→execution pipeline |
| BitMart futures execution | Ready | `backend/integrations/execution/` | CCXT-based order placement, paper/live modes |
| Paper trading mode | Ready | `backend/trading/safety.py` | Triple-lock live gate, default paper |
| Kill switch | Ready | `backend/trading/safety.py`, Redis | Redis-backed global order halt |
| Policy engine | Ready | `backend/trading/policy_engine.py` | Rule-based trade approval/rejection |
| Position sizing | Ready | `backend/trading/sizing.py` | Risk-based position sizing |
| Exit management | Ready | `backend/trading/exit_manager.py` | Stop-loss/take-profit management |
| Operator approval queue | Ready | `backend/approvals.py` | Pending trade approvals for human review |
| TradingView webhook ingestion | Ready | `backend/tradingview/` | Webhook receiver, normalizer, event store |
| TradingView MCP integration | Ready | Docker service, `mcp_servers` config | MCP server for TradingView data |
| Strategy: Momentum | Ready | `backend/strategies/momentum.py` | RSI, MA crossover, MACD, regime-aware |
| Strategy: Mean Reversion | Ready | `backend/strategies/mean_reversion.py` | RSI extremes, z-score, Bollinger Bands |
| Strategy: Breakout | Ready | `backend/strategies/breakout.py` | ATR expansion, volume surge, BB squeeze |
| Strategy: Delta-Neutral Carry | Ready | `backend/strategies/delta_neutral_carry.py` | Funding rate harvest, spot/perp basis |
| Strategy: Whale Follower | Ready | `backend/strategies/whale_follower.py` | On-chain whale accumulation tracking |
| Chronos forecasting | Ready | `backend/strategies/chronos_scoring.py` | Amazon Chronos time-series forecasts |
| Market regime detection | Ready | `backend/regime/detector.py` | Trend/range/volatility regime classification |
| Portfolio sync | Ready | `backend/services/portfolio_sync.py` | Exchange↔DB portfolio reconciliation |
| Portfolio snapshots | Ready | `backend/jobs/portfolio_sync.py` | Periodic balance/position snapshotting |
| Drawdown guard | Ready | `backend/jobs/drawdown_guard.py` | Automatic drawdown monitoring & kill switch |
| Execution health check | Ready | `backend/jobs/execution_health_check.py` | API connectivity, balances, open orders, readiness status with markdown report |
| Strategy evaluator | Ready | `backend/jobs/strategy_evaluator.py` | Periodic strategy scoring runs |
| Whale tracker | Ready | `backend/jobs/whale_tracker.py` | On-chain whale activity monitor |
| Copy trader curator | Ready | `backend/jobs/copy_trader_curator.py` | Leaderboard scoring for copy trading |
| Capital rotation | Ready | `backend/jobs/capital_rotation.py` | Cross-strategy capital allocation |
| Learning loop | Ready | `backend/jobs/learning_loop.py` | Strategy weight optimization from outcomes |
| Cron scheduler | Ready | `hermes-agent/cron/` | Per-profile recurring job execution |
| Observability service | Ready | `backend/observability/` | Full audit trail for decisions, workflows, tools |
| Event bus | Ready | `backend/event_bus/` | Redis Streams-based async event pipeline |
| Evaluation/replay | Ready | `backend/evaluation/` | Backtesting, replay, regression comparison |
| Telegram gateway | Ready | `gateway/platforms/telegram.py` | Two-way Telegram bot integration |
| Slack gateway | Ready | `gateway/platforms/slack.py` | Slack bot with channel routing |
| Discord gateway | Ready | `gateway/platforms/discord.py` | Discord bot integration |
| REST API (product) | Ready | `hermes/apps/api/` | FastAPI with health, execution, risk, portfolio, agents, observability routes |
| Web Dashboard | Ready | `hermes/` (Next.js) | Web UI at :3000 |
| Mission Control | Ready | `hermes/` (Next.js) | Operator console at :3100 |
| hermes CLI | Ready | `hermes-agent/hermes_cli/` | Full CLI: chat, gateway, cron, profiles, config |
| Skills system | Ready | `hermes-agent/tools/skills_*.py` | Composable skill modules for agents |
| Memory system | Ready | `hermes-agent/agent/memory_*.py` | Long-term agent memory (per-profile) |
| Context compression | Ready | `hermes-agent/agent/context_compressor.py` | LLM context window management |
| Smart model routing | Ready | `hermes-agent/agent/smart_model_routing.py` | Cheap→expensive routing for simple queries |
| Voice/TTS/STT | Partial | `hermes-agent/tools/voice_mode.py` | Edge TTS, Whisper STT — requires extras |
| Browser tool | Partial | `hermes-agent/tools/browser_tool.py` | Playwright-based web browsing |
| Multi-venue execution | Partial | `backend/integrations/execution/multi_venue.py` | Currently BitMart only |
| Notification retry worker | Ready | `backend/integrations/notifications/retry_worker.py` | Exponential backoff for failed notifications |
| Funding rate monitor | Ready | `scripts/funding_rate_monitor.py` | Standalone funding rate data collector |

### 4.2 External Market Data Integrations

| Integration | Client Location | API Key Required | Data Provided |
| --- | --- | --- | --- |
| CoinGecko | `backend/integrations/market_data/coingecko_client.py` | Optional (rate limited without) | Prices, market cap, volume. Has retry with exponential backoff (5 attempts). |
| CoinMarketCap | `backend/integrations/market_data/coinmarketcap_client.py` | Yes | Rankings, market overview |
| TwelveData | `backend/integrations/market_data/twelvedata_client.py` | Yes | Technical indicators (RSI, ATR, EMA computed), OHLCV |
| CryptoPanic | `backend/integrations/news_sentiment/cryptopanic_client.py` | Yes | Crypto news feed |
| NewsAPI | `backend/integrations/news_sentiment/newsapi_client.py` | Yes | General news headlines |
| LunarCrush | `backend/integrations/news_sentiment/lunarcrush_client.py` | Yes | Social sentiment metrics |
| Etherscan | `backend/integrations/onchain/etherscan_client.py` | Yes | ETH transactions, gas |
| Nansen | `backend/integrations/onchain/nansen_client.py` | Yes | Labeled wallet activity |
| DeFiLlama | `backend/integrations/defi/defillama_client.py` | No | TVL, yields, protocol data |
| FRED | `backend/integrations/macro/fred_client.py` | No | Macro economic indicators |
| BitMart (public) | `backend/integrations/derivatives/bitmart_public_client.py` | No | Order book, funding, trades |
| Binance (public) | `backend/integrations/derivatives/binance_public_client.py` | No | Cross-reference data |
| Bybit (public) | `backend/integrations/derivatives/bybit_public_client.py` | No | Cross-reference data |
| OKX (public) | `backend/integrations/derivatives/okx_public_client.py` | No | Cross-reference data |

---

## 5. Commands Guide

### 5.1 Make Targets (Root Workspace)

| Command | Description | When to Use |
| --- | --- | --- |
| `make dev-up` | Start full Docker stack (TimescaleDB, Redis, LiteLLM, Dashboard, API, Web, Mission Control) | First startup or after changes |
| `make dev-down` | Stop all Docker services | Shutting down |
| `make dev-check` | Health check all services with HTTP probes | Verify stack is healthy |
| `make dev-logs` | Follow Docker container logs | Debugging service issues |
| `make dev-ps` | List running containers | Check service status |
| `make dev-bootstrap` | Create `.env.dev` from template if missing | First-time setup |
| `make dev-clean-legacy` | Remove old split-stack containers | After migrating from legacy setup |
| `make test` | Run backend + tools + CLI tests (pytest, auto-parallelized) | Before commits |
| `make test-bitmart-sandbox` | Run BitMart sandbox integration tests | Testing exchange connectivity |
| `make lint` | Run ruff linter on hermes-agent | Code quality |
| `make typecheck` | Run mypy on backend/ | Type checking |

### 5.2 hermes CLI Commands

The `hermes` CLI is the primary interface for managing the agent system.

```bash
# Start the messaging gateway (Telegram/Slack/Discord)
hermes gateway run --replace

# Interactive chat session
hermes

# Profile management
hermes profile list
hermes profile switch orchestrator
hermes profile switch execution-agent

# Cron job management
hermes cron list
hermes cron add --name "My Job" --schedule "every 15m" --prompt "Check something"
hermes cron enable <job-id>
hermes cron disable <job-id>

# Configuration
hermes config show
hermes config set agent.max_turns 90

# Model management
hermes model list
hermes model switch <model-name>

# Diagnostics
hermes doctor  # System health check
hermes status  # Current system status
hermes logs    # View agent logs
```

### 5.3 Gateway Startup

```bash
# Recommended: use the start script
./start_gateway.sh

# Manual equivalent
cd hermes-agent
../.venv/bin/python -m hermes_cli.main gateway run --replace
```

The gateway connects to configured platforms (Telegram, Slack, Discord) and routes messages to the active profile's agent. It also starts the cron scheduler for the active profile.

### 5.4 Scripts

| Script | Location | Purpose | Schedule |
| --- | --- | --- | --- |
| `drawdown_guard.py` | `scripts/` | Monitors drawdown, triggers kill switch if threshold breached | Cron: every 15m |
| `execution_health_check.py` | `scripts/`, `backend/jobs/` | Checks BitMart API connectivity, balances, open orders; outputs markdown health report | Cron: every 15m |
| `funding_rate_monitor.py` | `scripts/` | Collects and aggregates funding rate data across exchanges | Cron: every 240m |
| `portfolio_sync.py` | `scripts/` | Syncs live portfolio from BitMart to TimescaleDB | Cron: every 5m |
| `strategy_evaluator.py` | `scripts/` | Runs strategy scoring cycle on watchlist symbols | Cron: every 240m |
| `whale_tracker.py` | `scripts/` | Tracks large on-chain transactions | Cron: every 240m |
| `sync_env.py` | `scripts/` | Synchronizes environment variables across profile configs | Manual |
| `ensure_project_stack.sh` | `scripts/` | Ensures Docker stack is running | Manual |
| `run_hermes_agent_tests.py` | `scripts/` | Test runner wrapper | Manual |
| `tradingview_pine_inject.js` | `scripts/` | TradingView Pine Script injection | Manual |
| `tv_build_views.js` | `scripts/` | Build TradingView chart layouts | Manual |

---

## 6. API Documentation

### 6.1 API Overview

**Base URL:** `http://localhost:8000/api/v1`
**Framework:** FastAPI
**Auth:** API key via `HERMES_API_KEY` header (bypassed in dev with `HERMES_API_DEV_BYPASS_AUTH=true`)
**Docs:** `http://localhost:8000/docs` (Swagger UI), `http://localhost:8000/redoc` (ReDoc)

### 6.2 Endpoints

#### Health

| Method | Path | Auth | Description |
| --- | --- | --- | --- |
| GET | `/healthz` | No | Health check |

```bash
curl http://localhost:8000/api/v1/healthz
# {"status":"ok","service":"hermes-api","environment":"development"}
```

#### Execution

| Method | Path | Auth | Description |
| --- | --- | --- | --- |
| GET | `/execution/` | No | Execution surface: safety status, pending signals, recent events |
| GET | `/execution/signals/pending` | No | List pending TradingView signal events |
| GET | `/execution/events` | No | Recent execution events |
| GET | `/execution/alerts/recent` | No | Recent TradingView alerts |
| GET | `/execution/movements` | No | Recent movement journal entries |
| POST | `/execution/place` | **Yes** | Place a trade order directly |
| POST | `/execution/proposals/evaluate` | No | Evaluate a trade proposal through policy engine |
| POST | `/execution/proposals/submit` | **Yes** | Submit a trade proposal for controlled execution |
| GET | `/execution/positions/monitor` | No | Position monitoring snapshot |
| GET | `/execution/approvals/pending` | No | List pending operator approvals |
| POST | `/execution/approvals/{id}/approve` | **Yes** | Approve a pending execution |
| POST | `/execution/approvals/{id}/reject` | **Yes** | Reject a pending execution |

**Place Order Example:**

```bash
curl -X POST http://localhost:8000/api/v1/execution/place \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $HERMES_API_KEY" \
  -d '{
    "symbol": "BTC/USDT:USDT",
    "side": "buy",
    "order_type": "market",
    "amount": 0.001
  }'
```

#### Risk

| Method | Path | Auth | Description |
| --- | --- | --- | --- |
| GET | `/risk/` | No | Risk dashboard: kill switch, safety, positions, rejections |
| GET | `/risk/kill-switch` | No | Kill switch state |
| POST | `/risk/kill-switch/activate` | **Yes** | Activate kill switch |
| POST | `/risk/kill-switch/deactivate` | **Yes** | Deactivate kill switch |
| GET | `/risk/portfolio` | No | Risk-view of portfolio |
| GET | `/risk/portfolio/monitor` | No | Position monitor from risk perspective |
| GET | `/risk/rejections` | No | Recent risk rejections |
| POST | `/risk/evaluate` | No | Evaluate trade risk for a symbol/size |
| GET | `/risk/candidates` | No | Current scored trade candidates |

**Activate Kill Switch:**

```bash
curl -X POST http://localhost:8000/api/v1/risk/kill-switch/activate \
  -H "Authorization: Bearer $HERMES_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"reason": "Emergency stop", "operator": "gabriel"}'
```

#### Portfolio

| Method | Path | Auth | Description |
| --- | --- | --- | --- |
| GET | `/portfolio/` | No | Latest portfolio state |
| POST | `/portfolio/sync` | **Yes** | Trigger live portfolio sync from exchange |

#### Agents

| Method | Path | Auth | Description |
| --- | --- | --- | --- |
| GET | `/agents/` | No | List all agents with recent activity |
| GET | `/agents/{agent_id}` | No | Agent detail with decisions and workflows |
| GET | `/agents/{agent_id}/timeline` | No | Flattened event timeline for an agent |

#### Observability

| Method | Path | Auth | Description |
| --- | --- | --- | --- |
| GET | `/observability/` | No | Dashboard snapshot |
| GET | `/observability/workflows` | No | List recent workflow runs |
| GET | `/observability/workflows/{id}` | No | Workflow run detail |
| GET | `/observability/failures` | No | Recent failures |
| GET | `/observability/timeline/{correlation_id}` | No | Event timeline by correlation ID |

#### Resources

| Method | Path | Auth | Description |
| --- | --- | --- | --- |
| GET | `/resources/` | No | Resource catalog |

### 6.3 Dashboard API (Agent Backend, Port 9119)

The hermes-agent dashboard exposes its own API at `:9119/api/`. This is what the product API bridges to. The dashboard is the actual execution engine — the product API at `:8000` delegates to it.

**Note:** The API Docker service (`hermes-api`) now passes exchange credentials (`BITMART_*`) and market data provider keys (`COINGECKO_API_KEY`, `COINMARKETCAP_API_KEY`, `TWELVEDATA_API_KEY`, `CRYPTOPANIC_API_KEY`, `NEWS_API_KEY`, `ETHERSCAN_API_KEY`) through to enable direct bridge calls that need external connectivity.

---

## 7. Database and Storage Guide

### 7.1 TimescaleDB (Primary Database)

**Type:** PostgreSQL 17 + TimescaleDB 2.18.2
**Host Port:** 5433 (default, to avoid conflicts with local PostgreSQL)
**Database:** `hermes_trading`
**User:** `hermes` / Password: `hermes` (dev defaults)
**Connection:** `postgresql+psycopg://hermes:hermes@localhost:5433/hermes_trading`

#### Tables (All TimescaleDB Hypertables)

| Table | Time Column | Purpose | Key Fields |
| --- | --- | --- | --- |
| `tradingview_alert_events` | `event_time` | Raw TradingView webhook alerts | symbol, signal, direction, price, processing_status |
| `tradingview_internal_events` | `event_time` | Normalized internal signal events | event_type, delivery_status, alert_event_id |
| `agent_signals` | `signal_time` | Agent-generated signals | agent_id, symbol, direction, confidence |
| `portfolio_snapshots` | `snapshot_time` | Periodic portfolio state snapshots | account_id, total_equity_usd, positions |
| `risk_events` | `event_time` | Risk-related events | symbol, severity, event_type |
| `notifications_sent` | `sent_time` | Notification delivery log | channel, delivered, retry_count |
| `workflow_runs` | `created_at` | Workflow execution records | workflow_name, status, correlation_id |
| `workflow_steps` | `created_at` | Individual workflow step records | workflow_step, status, agent_name |
| `tool_calls` | `created_at` | Tool invocation audit trail | tool_name, status, agent_name |
| `agent_decisions` | `created_at` | Agent decision records | agent_name, decision, status |
| `execution_events` | `created_at` | Execution lifecycle events | event_type, status, symbol |
| `movement_journal` | `movement_time` | Financial movement ledger | symbol, side, quantity, price, execution_mode |
| `paper_shadow_fills` | `fill_time` | Paper trade fill records | symbol, side, shadow_price, pnl_divergence_usd |
| `risk_limits` | N/A (non-hypertable) | Risk limit configuration | scope, max_position_usd, max_leverage |
| `system_errors` | `created_at` | Error tracking | error_type, is_failure |
| `replay_cases` | `created_at` | Backtesting/replay case definitions | source_type, input_payload, expected_outcome |
| `replay_runs` | `created_at` | Replay execution records | replay_case_id, status, model_name |
| `replay_results` | `created_at` | Replay output records | decision, should_execute, execution_intent |
| `evaluation_scores` | `created_at` | Strategy evaluation scores | rule_name, metric_name, passed |
| `regression_comparisons` | `created_at` | A/B comparison between replay runs | baseline_replay_run_id, candidate_replay_run_id |
| `chronos_forecasts` | `forecast_time` | Cached Chronos time-series forecasts | symbol, interval, horizon, median_price |
| `research_memos` | `memo_time` | Agent research knowledge base | symbol, tags, content, source_agent |
| `strategy_evaluations` | `eval_time` | Strategy scoring records | strategy_name, symbol, direction, confidence |
| `copy_trader_scores` | `score_time` | Copy trader leaderboard snapshots | trader_id, score, sharpe_30d, rank |
| `copy_trader_switch_proposals` | N/A | Operator approval for copy trader switches | status, candidate_trader_id |
| `policy_traces` | N/A | Policy engine decision audit trail | proposal_id, approved, trace |
| `strategy_weight_overrides` | N/A | Learning loop weight adjustments | strategy, symbol, regime, weight |
| `operator_snapshots` | N/A | Exchange state snapshots for reconciliation | exchange, total_equity_usd |

#### Bootstrap Behavior

The schema is auto-created by `backend/db/bootstrap.py`:

1. Creates the `timescaledb` extension
2. Runs `Base.metadata.create_all()` (SQLAlchemy declarative models)
3. Converts eligible tables to TimescaleDB hypertables
4. Skips tables that are already hypertables (idempotent)

#### Connecting Manually

```bash
psql -h localhost -p 5433 -U hermes -d hermes_trading

# List all tables
\dt

# Check hypertable status
SELECT hypertable_name FROM timescaledb_information.hypertables;

# Recent portfolio snapshots
SELECT snapshot_time, account_id, total_equity_usd FROM portfolio_snapshots ORDER BY snapshot_time DESC LIMIT 5;

# Recent workflow runs
SELECT created_at, workflow_name, status FROM workflow_runs ORDER BY created_at DESC LIMIT 10;

# Kill switch state (via Redis, but also check risk_events)
SELECT * FROM risk_events ORDER BY event_time DESC LIMIT 5;
```

### 7.2 Redis

**Port:** 6379
**Persistence:** AOF (appendonly yes)
**Uses:**

- Kill switch state: key `hermes:risk:kill_switch`
- Event bus: Redis Streams for `execution_requested` and other trading events
- Caching: Various tool result caches
- Pub/sub: Real-time event notifications

```bash
# Connect
redis-cli -p 6379

# Check kill switch
GET hermes:risk:kill_switch

# List stream keys
KEYS hermes:*
```

### 7.3 SQLite (Local Agent State)

**File:** `state.db` (root directory)
**Purpose:** Agent session state, conversation history, local caching
**Managed by:** hermes-agent runtime

### 7.4 File-Based Storage

| Path | Purpose |
| --- | --- |
| `memories/` | Agent long-term memory (Markdown files) |
| `sessions/` | Session dumps and request logs |
| `logs/` | Application logs |
| `cache/` | Temporary caches |
| `completions/` | LLM completion logs |
| `reports/` | Generated reports |
| `sandboxes/` | Code execution sandboxes |

---

## 8. Agents, Tools, and Models Guide

### 8.1 Agent Profiles

#### Orchestrator (Active by Default)

- **Model:** Claude Opus 4.6 via Bedrock (`orchestrator-default`)
- **Context:** 200,000 tokens
- **Max Turns:** 90
- **Role:** Ultimate trading desk decision maker. Coordinates all other agents. Does NOT call `place_order` directly — delegates to execution-agent via `delegate_task`.
- **SOUL:** Aggressive autonomous trading desk operator, authorized for live execution delegation.
- **Cron Jobs:** None (reactive, not scheduled)

#### Market Researcher

- **Model:** Claude Sonnet 4.6 via Bedrock (`research-default`)
- **Context:** 200,000 tokens
- **Max Turns:** 90
- **Role:** Market intelligence engine. Runs news scans, sentiment analysis, on-chain monitoring.
- **SOUL:** Pure research — never generates trades or executes.
- **Cron Jobs:**
  - News & Sentiment Scanner (every 2h) → Slack
  - On-Chain & Whale Activity Monitor (every 4h) → Slack
  - Funding Rate + Market Conditions (every 4h) → Slack

#### Strategy Agent

- **Model:** Claude Sonnet 4.6 via Bedrock (`strategy-default`)
- **Context:** 200,000 tokens
- **Max Turns:** 90
- **Role:** Setup scanner and trade-plan construction. Produces structured trade candidates.
- **SOUL:** Strategist only — does not approve or execute.
- **Cron Jobs:**
  - Technical Scanner (BTC ETH SOL RENDER XRP AVAX, every 4h) → Slack
  - Funding Rate Arbitrage Scanner (every 6h) → Slack

#### Risk Manager

- **Model:** Claude Sonnet 4.6 via Bedrock (`risk-default`)
- **Context:** 200,000 tokens
- **Max Turns:** 90
- **Role:** Hard risk gatekeeper. Validates proposed trades, enforces limits, escalates violations.
- **SOUL:** Guardian — does not originate trades or execute orders.
- **Cron Jobs:**
  - Risk Guard — Drawdown & Exposure Monitor (every 15m) → Slack
  - Drawdown Guard (every 15m) → Slack
  - Bot B — Execution Prep State (every 15m) → Slack

#### Portfolio Monitor

- **Model:** Claude Sonnet 4.6 via Bedrock (`portfolio-default`)
- **Context:** 200,000 tokens
- **Max Turns:** 90
- **Role:** Source of truth for positions, balances, exposure, reconciliation, PnL.
- **SOUL:** Ledger and tripwire — does not generate setups or execute.
- **Cron Jobs:**
  - Live Portfolio Snapshot (every 15m) → Slack
  - Portfolio Sync to Dashboard (every 5m) → Slack
  - Bot C — Position Protector (every 15m) → Slack

#### Execution Agent

- **Model:** Qwen 3.5 9B via LM Studio local (`execution-default`)
- **Context:** 32,768 tokens
- **Max Turns:** 12
- **Reasoning Effort:** Low
- **Role:** Mechanical order execution. Takes approved tickets, calls `place_order`, reports result.
- **SOUL:** Executes what it's given. Does not evaluate, modify, or debate trades.
- **Cron Jobs:**
  - Execution Health Check (every 15m) → Slack
  - Position Stop Guard (every 10m) → Slack

### 8.2 Backend Trading Tools (60+)

These tools are available to agents via the `hermes-cli` toolset. Grouped by category:

#### Market Data Tools

| Tool | Purpose |
| --- | --- |
| `get_crypto_prices` | Current cryptocurrency prices |
| `get_ohlcv` | OHLCV candlestick data |
| `get_market_overview` | Broad market summary |
| `get_indicator_snapshot` | Technical indicator values (SMA20, EMA20, RSI14, ATR14) |
| `get_order_book` | Order book depth |
| `get_recent_trades` | Recent trade history |
| `get_funding_rates` | Perpetual funding rates across exchanges |
| `get_volatility_metrics` | Volatility measures (ATR, BB width, etc.) |
| `get_liquidation_zones` | Estimated liquidation levels |
| `get_asset_rankings` | Market cap / volume rankings |
| `get_correlation_inputs` | Cross-asset correlation data |

#### News & Sentiment Tools

| Tool | Purpose |
| --- | --- |
| `get_crypto_news` | Crypto-specific news feed |
| `get_general_news` | General market news |
| `get_social_sentiment` | Social media sentiment metrics |
| `get_social_spike_alerts` | Viral/trending alerts |

#### On-Chain Tools

| Tool | Purpose |
| --- | --- |
| `get_onchain_signal_summary` | Aggregated on-chain signals |
| `get_onchain_wallet_data` | Specific wallet analysis |
| `get_labeled_wallet_activity` | Whale/smart money tracking |
| `get_wallet_transactions` | Transaction history |
| `get_smart_money_flows` | Net smart money direction |
| `get_token_activity` | Token transfer activity |

#### DeFi Tools

| Tool | Purpose |
| --- | --- |
| `get_defi_protocols` | DeFi protocol listings |
| `get_defi_protocol_details` | Detailed protocol metrics |
| `get_defi_yields` | Yield farming rates |
| `get_defi_chain_overview` | Per-chain TVL and activity |
| `get_defi_dex_overview` | DEX volume and liquidity |
| `get_defi_fees_overview` | Protocol fee data |
| `get_defi_open_interest` | Open interest across venues |
| `get_defi_regime_summary` | DeFi market regime |

#### Macro Tools

| Tool | Purpose |
| --- | --- |
| `get_macro_observations` | Key macro data points |
| `get_macro_series` | Time-series macro data |
| `get_macro_regime_summary` | Macro environment classification |
| `get_event_risk_summary` | Upcoming event risk calendar |
| `get_event_risk_macro_context` | Event risk with macro overlay |

#### Execution Tools

| Tool | Purpose |
| --- | --- |
| `get_execution_status` | API readiness check |
| `get_execution_quality` | Fill quality metrics |
| `place_order` | Submit an order to the exchange |
| `cancel_order` | Cancel an open order |
| `preview_execution_order` | Dry-run an order without submitting |
| `get_open_orders` | List open orders |
| `get_order_history` | Historical order records |

#### Portfolio & Risk Tools

| Tool | Purpose |
| --- | --- |
| `get_portfolio_state` | Current portfolio from DB |
| `get_portfolio_valuation` | Portfolio valuation breakdown |
| `get_exchange_balances` | Live exchange balances |
| `get_risk_state` | Current risk metrics |
| `get_risk_approval` | Submit trade for risk approval |
| `set_kill_switch` | Activate/deactivate kill switch |
| `get_trade_history` | Historical trade records |

#### Strategy Tools

| Tool | Purpose |
| --- | --- |
| `list_strategies` | Available strategy definitions |
| `evaluate_strategy` | Run a strategy scorer (returns ScoredCandidate with chronos_score + sizing_hints) |
| `list_trade_candidates` | Current scored candidates |
| `run_strategy_cycle` | Full strategy evaluation cycle |
| `get_chronos_score` | Chronos forecast for a symbol |
| `get_forecast_projection` | Price projection |

#### Notification Tools

| Tool | Purpose |
| --- | --- |
| `send_notification` | Send message to configured channel |
| `send_trade_alert` | Trading-specific alert |
| `send_risk_alert` | Risk-specific alert |
| `send_execution_update` | Execution status update |
| `send_daily_summary` | End-of-day summary |

#### Research & Memory Tools

| Tool | Purpose |
| --- | --- |
| `save_research_memo` | Persist research findings to DB |
| `get_research_memos` | Retrieve saved research |

#### TradingView Tools

| Tool | Purpose |
| --- | --- |
| `get_recent_tradingview_alerts` | Recent TV webhook alerts |
| `get_tradingview_alert_by_symbol` | Symbol-specific TV alerts |
| `get_tradingview_alert_context` | Full context for a TV alert |
| `get_pending_signal_events` | Unprocessed TV signals |

### 8.3 LLM Provider Configuration

The system uses **LiteLLM** as a unified gateway. All agent profiles connect to `http://localhost:4000/v1` with the `LITELLM_API_KEY`.

**Primary provider:** AWS Bedrock (Claude Opus/Sonnet/Haiku)
**Fallback providers:** OpenRouter (Qwen3 Coder 480B), LM Studio (Qwen 3.5 9B local)

To change a model for a profile, edit:

1. `litellm_config.yaml` — add/modify the model route
2. `profiles/<name>/config.yaml` — update `model.default` and `litellm_gateway.default_route`

### 8.4 MCP Servers

Currently one MCP server is configured:

```yaml
mcp_servers:
  tradingview:
    command: node
    args: ["/Users/openclaw/Coding/tradingview-mcp-jackson/src/server.js"]
    enabled: true
```

This provides TradingView data access as MCP tools to the agent.

---

## 9. Operational Guide

### 9.1 Starting the System from Zero

```bash
# Step 1: Start infrastructure
cd ~/.hermes
make dev-up
# Wait for all services to be healthy (~60-120s)

# Step 2: Verify infrastructure
make dev-check

# Step 3 (optional): Start LM Studio if using local execution model
# Open LM Studio, load qwen/qwen3.5-9b, start server on port 1234

# Step 4: Start the agent gateway
./start_gateway.sh
# This starts the active profile (orchestrator by default)
# with its cron jobs and messaging platform connections

# Step 5: Verify agent is running
# Check logs:
tail -f profiles/orchestrator/logs/agent.log
# Or check gateway state:
cat gateway_state.json
```

### 9.2 Confirming System Health

```bash
# Docker services
make dev-check

# Database connectivity
psql -h localhost -p 5433 -U hermes -d hermes_trading -c "SELECT 1"

# Redis connectivity
redis-cli -p 6379 PING

# LiteLLM health
curl -s http://localhost:4000/health/liveliness

# API health
curl -s http://localhost:8000/api/v1/healthz

# Kill switch status
curl -s http://localhost:8000/api/v1/risk/kill-switch

# Execution readiness
curl -s http://localhost:8000/api/v1/execution/ | python3 -m json.tool

# Portfolio state
curl -s http://localhost:8000/api/v1/portfolio/ | python3 -m json.tool
```

### 9.3 Day-to-Day Operations

**Morning Check:**

1. `make dev-check` — verify all services are running
2. Check Slack channels for overnight cron alerts
3. `curl localhost:8000/api/v1/risk/` — review risk dashboard
4. `curl localhost:8000/api/v1/portfolio/` — review portfolio state
5. `curl localhost:8000/api/v1/execution/approvals/pending` — check pending approvals

**Active Monitoring:**

- Slack channels receive automated cron output from each profile
- Each profile has its own Slack channel for organized output:
  - Strategy scans → strategy channel
  - Risk alerts → risk channel
  - Portfolio updates → portfolio channel
  - Execution status → execution channel

**Interacting with the Agent:**

- Send messages via Telegram to the configured bot
- Use the hermes CLI for direct interaction: `hermes`
- Use the Web Dashboard at `http://localhost:3000`
- Use Mission Control at `http://localhost:3100`

### 9.4 Switching Profiles

```bash
# See available profiles
ls profiles/

# Switch to a different profile
hermes profile switch risk-manager

# Check which profile is active
cat active_profile
```

### 9.5 Managing Cron Jobs

```bash
# List all cron jobs for active profile
hermes cron list

# Jobs are defined in profiles/<name>/cron/jobs.json
# Each job has:
#   - schedule (interval or cron expression)
#   - script (Python script to run as data source)
#   - prompt (LLM prompt to analyze the script output)
#   - deliver (destination: slack:<channel_id>, telegram, etc.)
#   - enabled/paused state
```

### 9.6 Emergency Procedures

**Activate Kill Switch (stops all new trades):**

```bash
curl -X POST http://localhost:8000/api/v1/risk/kill-switch/activate \
  -H "Authorization: Bearer $HERMES_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"reason": "Emergency", "operator": "gabriel"}'
```

**Deactivate Kill Switch:**

```bash
curl -X POST http://localhost:8000/api/v1/risk/kill-switch/deactivate \
  -H "Authorization: Bearer $HERMES_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"operator": "gabriel"}'
```

**Stop All Services:**

```bash
make dev-down
# Also stop the gateway process if running
```

### 9.7 Stopping and Restarting

```bash
# Restart just the gateway
./start_gateway.sh  # --replace flag handles existing process

# Restart Docker stack
make dev-down && make dev-up

# Restart a single service
docker restart hermes-litellm
docker restart hermes-api
docker restart hermes-dashboard
```

---

## 10. Testing Guide

### 10.1 Test Framework

- **Framework:** pytest 9.x with pytest-asyncio and pytest-xdist (parallel)
- **Test Count:** 603 test files in `hermes-agent/tests/`
- **Markers:**
  - `integration` — requires external API keys
  - `bitmart_sandbox` — requires BitMart sandbox credentials + `HERMES_BITMART_SANDBOX=1`
- **Default:** runs non-integration, non-sandbox tests with auto-parallelization (`-n auto`)

### 10.2 Running Tests

```bash
# All non-integration tests (from workspace root)
make test

# From hermes-agent directory
cd hermes-agent
.venv/bin/pytest tests/backend tests/tools tests/hermes_cli -q

# Specific test categories
.venv/bin/pytest tests/backend/ -q          # Backend/trading tests
.venv/bin/pytest tests/tools/ -q            # Tool tests
.venv/bin/pytest tests/agent/ -q            # Agent core tests
.venv/bin/pytest tests/hermes_cli/ -q       # CLI tests

# BitMart sandbox integration tests
HERMES_BITMART_SANDBOX=1 .venv/bin/pytest -m bitmart_sandbox tests/integration/ -q

# Single test file
.venv/bin/pytest tests/backend/test_approvals.py -v

# With verbose output
.venv/bin/pytest tests/backend/ -v --no-header
```

### 10.3 Test Organization

| Directory | Focus | Count (approx) |
| --- | --- | --- |
| `tests/backend/` | Trading logic, strategies, integrations, DB, execution | ~150+ |
| `tests/tools/` | Tool functionality, security, edge cases | ~100+ |
| `tests/agent/` | Agent core: prompt building, context compression, model routing | ~50+ |
| `tests/hermes_cli/` | CLI commands, config, profiles | ~50+ |
| `tests/gateway/` | Messaging platform integration | ~30+ |
| `tests/cron/` | Cron scheduler tests | ~20+ |
| `tests/acp/` | Agent Communication Protocol tests | ~10+ |

### 10.4 Manual Validation Checklist

1. [ ] `make dev-check` passes for all services
2. [ ] API responds: `curl localhost:8000/api/v1/healthz`
3. [ ] Portfolio query works: `curl localhost:8000/api/v1/portfolio/`
4. [ ] Kill switch query works: `curl localhost:8000/api/v1/risk/kill-switch`
5. [ ] Agent can be reached via Telegram/Slack
6. [ ] Cron jobs are scheduled: `hermes cron list`
7. [ ] LiteLLM UI accessible: `http://localhost:4000/ui`
8. [ ] Web dashboard loads: `http://localhost:3000`
9. [ ] Mission Control loads: `http://localhost:3100`

---

## 11. Troubleshooting Guide

### 11.1 Common Issues

#### Service Won't Start / Port Already in Use

**Symptoms:** `make dev-up` fails, container restart loops
**Cause:** Another process using the same port
**Fix:**

```bash
# Find what's using a port
lsof -i :4000  # LiteLLM
lsof -i :5433  # TimescaleDB
lsof -i :6379  # Redis

# Kill the conflicting process or change ports in .env.dev
```

#### LiteLLM Health Check Fails

**Symptoms:** LiteLLM container unhealthy, agents can't reach LLM
**Cause:** Missing API keys, bad config, database connection issue
**Fix:**

```bash
# Check logs
docker logs hermes-litellm

# Verify API keys are set
docker exec hermes-litellm env | grep -E 'API_KEY|AWS'

# Test directly
curl http://localhost:4000/health/liveliness
```

#### Database Connection Failures

**Symptoms:** "connection refused" errors, tables not found
**Cause:** TimescaleDB not running or not bootstrapped
**Fix:**

```bash
# Check container
docker ps | grep timescale
docker logs hermes-timescaledb

# Test connection
psql -h localhost -p 5433 -U hermes -d hermes_trading -c '\dt'

# If tables missing, the bootstrap runs on first backend connection
```

#### Agent Not Responding

**Symptoms:** Messages not answered, gateway appears stuck
**Cause:** Gateway crash, LLM timeout, profile misconfiguration
**Fix:**

```bash
# Check gateway logs
tail -50 profiles/orchestrator/logs/agent.log
tail -50 profiles/orchestrator/logs/errors.log

# Restart gateway
./start_gateway.sh

# Check active profile
cat active_profile
```

#### BitMart API Errors

**Symptoms:** "readiness_status != api_execution_ready", order placement fails
**Cause:** Missing/expired API keys, network issues, wrong account type
**Fix:**

```bash
# Check credentials are set
env | grep BITMART

# Test via the readiness tool
curl -s http://localhost:8000/api/v1/execution/ | python3 -m json.tool

# Verify account type is swap (futures)
# Check BITMART_ACCOUNT_TYPE=swap in .env
```

#### Kill Switch Unexpectedly Active

**Symptoms:** All trades rejected with "Kill switch is active"
**Cause:** Drawdown guard triggered, or manual activation
**Fix:**

```bash
# Check state
curl -s http://localhost:8000/api/v1/risk/kill-switch

# Deactivate (requires API key)
curl -X POST http://localhost:8000/api/v1/risk/kill-switch/deactivate \
  -H "Authorization: Bearer $HERMES_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"operator": "gabriel"}'

# Check Redis directly
redis-cli GET hermes:risk:kill_switch
```

#### Import / Module Errors

**Symptoms:** `ModuleNotFoundError`, `ImportError`
**Cause:** Virtual environment not activated, missing dependencies
**Fix:**

```bash
cd hermes-agent
source .venv/bin/activate
pip install -e ".[all]"
```

#### Cron Jobs Not Running

**Symptoms:** No cron output in Slack channels
**Cause:** Gateway not running, jobs paused, wrong deliver target
**Fix:**

```bash
# Check gateway is running
ps aux | grep hermes_cli

# List jobs
hermes cron list

# Check job state in the profile's cron/jobs.json
cat profiles/orchestrator/cron/jobs.json | python3 -m json.tool

# Check cron output directory
ls profiles/orchestrator/cron/output/
```

#### LLM Rate Limits / Timeouts

**Symptoms:** 429 errors, slow responses, fallback model used
**Cause:** API rate limits hit, model overloaded
**Fix:**

- LiteLLM has automatic fallback chains configured
- Check LiteLLM dashboard: `http://localhost:4000/ui`
- If persistent, add more API keys for key rotation in `.env.dev`

---

## 12. Security Review

### 12.1 Secrets Management

| Item | Status | Risk | Recommendation |
| --- | --- | --- | --- |
| `.env` files contain real secrets | **Warning** | High | Ensure `.env` files are in `.gitignore`. They are currently tracked in some locations. |
| `auth.json` contains OAuth tokens | **Warning** | High | Must not be committed. Verify `.gitignore` coverage. |
| API keys in `litellm_config.yaml` | Safe | Low | Uses `os.environ/` references, not hardcoded values |
| BitMart credentials | **Critical** | Very High | Real exchange keys — protect as highest priority |
| `LITELLM_MASTER_KEY` | Moderate | Medium | Change from default `sk-hermes-dev-change-me` in production |

### 12.2 Authentication

| Surface | Auth Status | Notes |
| --- | --- | --- |
| Product API (`:8000`) | **Key-based** | `HERMES_API_KEY` header. Dev bypass via `HERMES_API_DEV_BYPASS_AUTH=true` |
| LiteLLM (`:4000`) | **Key-based** | Master key required |
| Dashboard (`:9119`) | **None** | No authentication — expose only on localhost |
| Web (`:3000`) | **None** | No authentication — expose only on localhost |
| Mission Control (`:3100`) | **None** | No authentication — expose only on localhost |
| Telegram Bot | **Token-based** | Bot token + authorized chat IDs |
| TradingView Webhooks | **Secret header** | `X-TV-Secret` header validation |

### 12.3 Trading Safety

| Control | Implementation | Status |
| --- | --- | --- |
| Triple-lock live gate | 3 env vars must all be set | Ready |
| Kill switch | Redis-backed, API-accessible | Ready |
| Policy engine | Rule-based pre-trade validation | Ready |
| Operator approval | Pending queue with approve/reject | Ready |
| Position sizing limits | `risk_limits` table | Ready |
| Execution agent isolation | Separate model, limited turns, no discretion | Ready |
| Paper mode default | `HERMES_TRADING_MODE=paper` | Ready |

### 12.4 Recommendations

1. **Never commit `.env` files** — verify all `.env` paths are in `.gitignore`
2. **Rotate the LiteLLM master key** from the default before any non-local use
3. **Add authentication to Dashboard/Web/Mission Control** before exposing to a network
4. **Use a secrets manager** (AWS Secrets Manager, Vault) for production deployments
5. **Enable `HERMES_BITMART_VERIFY_SIGNED_WRITES`** in production
6. **Enable `HERMES_REQUIRE_APPROVAL`** until confident in autonomous execution
7. **Audit `auth.json`** — ensure it doesn't contain long-lived tokens unencrypted

---

## 13. Production Readiness Report

### 13.1 Rating Table

| Component | Status | Risk | Reason |
| --- | --- | --- | --- |
| TimescaleDB schema & bootstrap | **Ready** | Low | Auto-bootstraps, hypertables configured |
| Redis event bus | **Ready** | Low | Standard Redis Streams usage |
| LiteLLM model routing | **Ready** | Low | Fallback chains configured |
| Trading workflow graph | **Ready** | Medium | Well-structured but depends on LLM quality |
| BitMart execution (paper) | **Ready** | Low | Shadow fills tracked |
| BitMart execution (live) | **Ready but gated** | High | Triple lock in place; needs real-money testing |
| Policy engine | **Ready** | Medium | Rules need tuning based on trading experience |
| Kill switch | **Ready** | Low | Simple, reliable Redis-backed mechanism |
| Agent profiles & SOUL.md | **Ready** | Low | Well-defined roles and boundaries |
| Cron scheduler | **Ready** | Low | Tick-based, per-profile isolation |
| Notification system | **Ready** | Low | Telegram/Slack with retry worker |
| FastAPI product API | **Ready** | Medium | Missing auth on dashboard/web surfaces |
| Web Dashboard | **Partial** | Medium | Requires build step; no auth |
| Mission Control | **Partial** | Medium | Requires build step; no auth |
| Test suite | **Ready** | Low | 603 test files, good coverage |
| Observability | **Ready** | Low | Full audit trail in TimescaleDB |
| Documentation | **Partial** | Medium | This guide fills a major gap |
| CI/CD | **Missing** | High | No GitHub Actions or deployment pipeline found |
| Monitoring/alerting | **Partial** | Medium | Cron-based, no Grafana/Prometheus |
| Backup/restore | **Missing** | High | No automated DB backup |
| Multi-venue support | **Partial** | Low | Only BitMart currently |

### 13.2 What's Ready

- Full trading pipeline: signal → research → strategy → risk → execution
- All 5 trading strategies with scoring
- 6 specialized agent profiles with distinct roles
- 60+ trading tools and 70+ platform tools
- TimescaleDB time-series storage with 25+ tables
- Paper trading mode with shadow fills
- Kill switch and policy engine
- Operator approval queue
- Cron-based monitoring (14 jobs across profiles)
- Telegram/Slack/Discord messaging gateway
- REST API with execution, risk, portfolio, agents, observability endpoints
- Comprehensive test suite (603 files)

### 13.3 What Needs Work

- **CI/CD pipeline** — no automated testing/deployment workflows
- **Database backups** — no automated backup/restore for TimescaleDB
- **Dashboard authentication** — web UIs exposed without auth
- **Production deployment config** — only Docker Compose dev stack exists
- **Secrets management** — env files with real secrets
- **Performance monitoring** — no Prometheus/Grafana stack
- **Data retention policies** — hypertables grow indefinitely

---

## 14. Future Development Guide

### 14.1 Directory Conventions

```text
├── ~/.hermes/
├── hermes/                          # Product monorepo
│   ├── apps/api/src/hermes_api/     # FastAPI REST API
│   ├── packages/                    # Shared Python packages
│   └── infrastructure/              # Dockerfiles, DB init scripts
├── hermes-agent/                    # Agent runtime (fork of Nous Hermes)
│   ├── agent/                       # Core LLM loop, prompt building
│   ├── backend/                     # ALL trading logic lives here
│   │   ├── db/                      # SQLAlchemy models, bootstrap
│   │   ├── integrations/            # External API clients
│   │   ├── strategies/              # Trading strategy scorers
│   │   ├── trading/                 # Execution, risk, safety
│   │   ├── tools/                   # Trading-specific agent tools
│   │   ├── workflows/               # Pydantic-graph trading workflow
│   │   ├── jobs/                    # Background job implementations
│   │   └── event_bus/               # Redis Streams event pipeline
│   ├── gateway/                     # Multi-platform message router
│   ├── tools/                       # Platform tools (file, web, etc.)
│   ├── hermes_cli/                  # CLI interface
│   ├── cron/                        # Cron scheduler
│   └── tests/                       # 603 test files
├── profiles/                        # Per-agent configurations
│   ├── orchestrator/
│   ├── market-researcher/
│   ├── strategy-agent/
│   ├── risk-manager/
│   ├── portfolio-monitor/
│   └── execution-agent/
├── scripts/                         # Standalone operational scripts
├── docs/                            # Documentation
└── config.yaml                      # Root config
```

### 14.2 How to Add a New Trading Strategy

1. Create `hermes-agent/backend/strategies/my_strategy.py`:

   ```python
   from backend.strategies.registry import ScoredCandidate
   
   def score_my_strategy(*, symbol: str, ohlcv: list, indicators: dict, **kwargs) -> ScoredCandidate:
       # Your scoring logic here
       return ScoredCandidate(
           symbol=symbol,
           direction="long",  # or "short" or "watch"
           confidence=0.65,
           rationale="...",
           strategy_name="my_strategy",
           chronos_score=0.72,       # optional: Chronos forecast score
           sizing_hints={"max_usd": 500},  # optional: sizing guidance
       )
   ```

2. Register in `backend/strategies/registry.py`:

   ```python
   STRATEGY_REGISTRY["my_strategy"] = StrategyDefinition(
       name="my_strategy",
       strategy_type="momentum",
       description="...",
       timeframes=["4h"],
   )
   ```

3. Add scorer resolver in `get_strategy_scorer()`:

   ```python
   if normalized == "my_strategy":
       from backend.strategies.my_strategy import score_my_strategy
       return score_my_strategy
   ```

4. Add tests in `tests/backend/test_my_strategy.py`

### 14.3 How to Add a New Backend Tool

1. Create `hermes-agent/backend/tools/my_tool.py`:

   ```python
   def my_tool(*, symbol: str, ...) -> dict:
       """One-line description for the agent."""
       # Implementation
       return {"result": "..."}
   ```

2. Register in `hermes-agent/backend/tools/__init__.py` (follow existing pattern)

3. Add to the appropriate toolset in `hermes-agent/toolsets.py`

4. Add tests in `tests/tools/test_my_tool.py` or `tests/backend/test_my_tool.py`

### 14.4 How to Add a New API Route

1. Create route file: `hermes/apps/api/src/hermes_api/api/routes/my_route.py`
2. Define domain models: `hermes/apps/api/src/hermes_api/domain/my_domain.py`
3. Add bridge function: `hermes/apps/api/src/hermes_api/integrations/hermes_agent.py`
4. Register in router: `hermes/apps/api/src/hermes_api/api/router.py`
5. Add tests: `hermes/apps/api/tests/test_my_route.py`

### 14.5 How to Add a New Database Table

1. Add SQLAlchemy model in `hermes-agent/backend/db/models.py`
2. If time-series data, add hypertable spec in `backend/db/bootstrap.py`
3. Tables are auto-created on bootstrap (no manual migration needed for new tables)
4. Add repository methods in `backend/db/repositories.py` if needed

### 14.6 How to Add a New Agent Profile

1. Create directory: `profiles/my-agent/`
2. Create `SOUL.md` — define the agent's personality and role
3. Create `config.yaml` — copy from an existing profile, adjust model and settings
4. Create `cron/jobs.json` — define scheduled jobs (or `{"jobs": []}`)
5. Create `channel_directory.json` — Slack/Telegram channel mappings
6. Add model route in `litellm_config.yaml` if using a new model
7. Switch to test: `hermes profile switch my-agent`

### 14.7 High-Risk Areas (Modify with Caution)

| Area | Why It's Risky |
| --- | --- |
| `backend/trading/execution_service.py` | Dispatches real orders |
| `backend/trading/safety.py` | Kill switch and trading mode gates |
| `backend/trading/policy_engine.py` | Trade approval logic |
| `backend/integrations/execution/ccxt_client.py` | Direct exchange API calls |
| `backend/integrations/execution/mode.py` | Paper/live mode determination |
| `litellm_config.yaml` | Model routing — wrong config = wrong model making decisions |
| `profiles/*/SOUL.md` | Agent behavior — careless edits can lead to bad trades |
| `backend/db/bootstrap.py` | Database schema — changes affect all data |

---

## 15. Action Plan

### 15.1 Immediate Fixes (Priority: Critical)

| # | Task | Impact | Risk | Files |
| --- | --- | --- | --- | --- |
| 1 | Verify `.env` and `auth.json` are in `.gitignore` everywhere | Security | High | `.gitignore`, `hermes-agent/.gitignore` |
| 2 | Change default `LITELLM_MASTER_KEY` | Security | Medium | `.env.dev` |
| 3 | Add authentication to Dashboard (`:9119`) | Security | Medium | `hermes-agent/Dockerfile`, dashboard config |

### 15.2 Short-Term Improvements (1-2 weeks)

| # | Task | Impact | Complexity | Files |
| --- | --- | --- | --- | --- |
| 4 | Add CI/CD pipeline (GitHub Actions) | Reliability | Medium | `.github/workflows/` |
| 5 | Add automated TimescaleDB backup | Data safety | Low | Docker compose, cron |
| 6 | Add Prometheus metrics endpoint | Observability | Medium | API, dashboard |
| 7 | Add TimescaleDB data retention policies | Storage | Low | `backend/db/bootstrap.py` |
| 8 | Add health check cron that alerts on failures | Reliability | Low | `scripts/`, cron jobs |

### 15.3 Medium-Term Improvements (1-2 months)

| # | Task | Impact | Complexity | Files |
| --- | --- | --- | --- | --- |
| 9 | Add Grafana dashboards for trading metrics | Observability | Medium | New service in docker-compose |
| 10 | Add web UI authentication (OAuth/JWT) | Security | Medium | `hermes/` frontend |
| 11 | Add multi-venue support (Binance, Bybit) | Capability | High | `backend/integrations/execution/` |
| 12 | Add automated strategy backtesting pipeline | Quality | High | `backend/evaluation/` |
| 13 | Production deployment guide (K8s/ECS) | Operations | High | `infrastructure/` |

### 15.4 Production-Hardening Tasks

| # | Task | Impact | Complexity |
| --- | --- | --- | --- |
| 14 | Secrets manager integration (AWS SM / Vault) | Security | Medium |
| 15 | Database connection pooling configuration | Performance | Low |
| 16 | Rate limiter on public API endpoints | Security | Low |
| 17 | TLS/HTTPS for all services | Security | Medium |
| 18 | Log aggregation (ELK/CloudWatch) | Observability | Medium |

### 15.5 Nice-to-Have Improvements

| # | Task | Impact | Complexity |
| --- | --- | --- | --- |
| 19 | Mobile notification app | UX | High |
| 20 | Portfolio performance analytics dashboard | Insight | Medium |
| 21 | Strategy marketplace (share/import strategies) | Capability | High |
| 22 | Voice interaction mode | UX | Medium |

---

## 16. Appendix

### 16.1 Repository Structure (Key Files)

```text
~/.hermes/
├── Makefile                           # Dev stack orchestration
├── docker-compose.dev.yml             # Unified Docker stack (7 services)
├── config.yaml                        # Root agent config
├── SOUL.md                            # Root agent personality
├── litellm_config.yaml                # LLM model routing
├── start_gateway.sh                   # Gateway startup script
├── active_profile                     # Current profile (text file)
├── auth.json                          # OAuth state (SENSITIVE)
├── channel_directory.json             # Messaging channel mappings
├── gateway_state.json                 # Gateway runtime state
├── processes.json                     # Background processes
├── state.db                           # SQLite agent state
├── .env.dev                           # Docker env vars (SENSITIVE)
├── .env.dev.example                   # Template for .env.dev
│
├── hermes/                            # Product monorepo
│   ├── pyproject.toml                 # Python deps (FastAPI, ccxt, etc.)
│   ├── docker-compose.yml             # Legacy per-repo compose
│   ├── apps/api/                      # FastAPI REST API
│   ├── packages/                      # Shared Python packages
│   └── infrastructure/                # Docker, DB init, scripts
│
├── hermes-agent/                      # AI Agent runtime
│   ├── pyproject.toml                 # Python deps (openai, anthropic, etc.)
│   ├── run_agent.py                   # Agent entry point
│   ├── cli.py                         # Interactive CLI
│   ├── hermes_cli/                    # Full CLI application
│   ├── agent/                         # Core LLM loop
│   ├── backend/                       # Trading backend (biggest package)
│   │   ├── db/                        # Models, bootstrap, session
│   │   ├── integrations/              # 14 external API clients
│   │   ├── strategies/                # 5 trading strategies
│   │   ├── trading/                   # Execution, risk, safety
│   │   ├── tools/                     # 60+ trading tools
│   │   ├── workflows/                 # Pydantic-graph pipeline
│   │   ├── jobs/                      # 8 background jobs
│   │   ├── event_bus/                 # Redis Streams pipeline
│   │   ├── evaluation/                # Backtesting/replay
│   │   ├── regime/                    # Market regime detection
│   │   ├── portfolio/                 # Rebalancer
│   │   └── observability/             # Audit trail service
│   ├── gateway/                       # Multi-platform messaging
│   │   └── platforms/                 # 15+ platform adapters
│   ├── tools/                         # 70+ platform tools
│   ├── cron/                          # Scheduler
│   └── tests/                         # 603 test files
│
├── profiles/                          # Agent profile configs
│   ├── orchestrator/                  # Claude Opus 4.6
│   ├── market-researcher/             # Claude Sonnet 4.6
│   ├── strategy-agent/                # Claude Sonnet 4.6
│   ├── risk-manager/                  # Claude Sonnet 4.6
│   ├── portfolio-monitor/             # Claude Sonnet 4.6
│   └── execution-agent/              # Qwen 3.5 9B (local)
│
├── scripts/                           # Operational scripts
├── docs/                              # Documentation
├── reports/                           # Generated reports
├── memories/                          # Agent memories
├── sessions/                          # Session logs
├── logs/                              # Application logs
├── skills/                            # Composable skills
└── teams/                             # Team definitions
```

### 16.2 Service Dependency Map

```mermaid
graph TD
    TSDB[TimescaleDB :5433] --> LITELLM[LiteLLM :4000]
    TSDB --> DASHBOARD[Dashboard :9119]
    TSDB --> API[API :8000]
    REDIS[Redis :6379] --> DASHBOARD
    LITELLM --> DASHBOARD
    TVMCP[TradingView MCP] --> DASHBOARD
    DASHBOARD --> API
    API --> WEB[Web :3000]
    API --> MC[Mission Control :3100]
```

**Startup order:** TimescaleDB → Redis → LiteLLM → TradingView MCP → Dashboard → API → Web / Mission Control

### 16.3 Cron Job Summary (All Profiles)

| Profile | Job Name | Frequency | Deliver To |
| --- | --- | --- | --- |
| execution-agent | Execution Health Check | 15m | Slack |
| execution-agent | Position Stop Guard | 10m | Slack |
| market-researcher | News & Sentiment Scanner | 2h | Slack |
| market-researcher | On-Chain & Whale Monitor | 4h | Slack |
| market-researcher | Funding Rate + Market Conditions | 4h | Slack |
| strategy-agent | Technical Scanner (6 symbols) | 4h | Slack |
| strategy-agent | Funding Rate Arbitrage Scanner | 6h | Slack |
| risk-manager | Risk Guard — Drawdown & Exposure | 15m | Slack |
| risk-manager | Drawdown Guard | 15m | Slack |
| risk-manager | Bot B — Execution Prep State | 15m | Slack |
| portfolio-monitor | Live Portfolio Snapshot | 15m | Slack |
| portfolio-monitor | Portfolio Sync to Dashboard | 5m | Slack |
| portfolio-monitor | Bot C — Position Protector | 15m | Slack |
| orchestrator | (none) | — | — |

### 16.4 Model Cost Tiers

| Model | Provider | Approximate Cost | Used By |
| --- | --- | --- | --- |
| Claude Opus 4.6 | Bedrock | $$$$ (highest) | Orchestrator only |
| Claude Sonnet 4.6 | Bedrock | $$ (moderate) | Research, Strategy, Risk, Portfolio |
| Claude Haiku 4.5 | Bedrock | $ (low) | Fallback for all routes |
| Qwen3 Coder 480B | OpenRouter | Free tier | Last-resort fallback |
| Qwen 3.5 9B | LM Studio (local) | Free (local GPU) | Execution agent, Risk fallback |

### 16.5 Glossary

| Term | Definition |
| --- | --- |
| **Profile** | A named agent configuration (SOUL.md + config.yaml + cron jobs) |
| **SOUL.md** | System prompt that defines an agent's personality and behavioral rules |
| **Toolset** | A named group of tools available to an agent |
| **Kill Switch** | Redis-backed global halt that blocks all new trade executions |
| **Policy Engine** | Rule-based system that evaluates trade proposals before execution |
| **Shadow Fill** | Paper-mode simulated trade execution record |
| **Hypertable** | TimescaleDB time-partitioned table for time-series data |
| **Event Bus** | Redis Streams-based async event pipeline for trading events |
| **Gateway** | Multi-platform message routing system (Telegram/Slack/Discord/etc.) |
| **LiteLLM** | Unified LLM gateway that abstracts provider differences |
| **Delegate Task** | Orchestrator sending work to a specialist agent (e.g., execution-agent) |
| **Triple Lock** | Three env vars that must all be set to enable live trading |
| **MCP** | Model Context Protocol — tool interface standard |

---

*Generated 2026-04-27, updated to v1.1 same day. Based on actual repository inspection of `~/.hermes/`.*
