# Shared Intelligence Layer

The Shared Intelligence Layer exists to prevent every agent from building its own isolated view of the world.

## Purpose

This layer normalizes external data and internal state into reusable tools, registries, and schemas that all agents can consume consistently.

## Core Resource Areas

Hermes architecture currently assumes shared support for:

- market price feeds
- order book and depth feeds
- trades and tape
- technical indicators
- derivatives and funding data
- portfolio and account state
- risk policies
- strategy libraries
- news and sentiment
- on-chain intelligence
- execution connectors
- memory and research storage

## Why It Matters

- reduces duplicated integration logic
- makes testing and replay easier
- keeps policy and schema boundaries explicit
- gives Mission Control more reliable metadata to inspect

## Local vs Cloud Model Routing

The Shared Intelligence Layer is distinct from model routing, but the two interact. Local providers such as Ollama and LM Studio may be preferred for private or cost-sensitive tasks, while cloud providers such as OpenAI and Anthropic may be preferred for higher-complexity reasoning or managed uptime. Future routing should be explicit, observable, and overrideable by policy.
