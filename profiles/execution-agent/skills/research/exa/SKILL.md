---
name: exa
description: |
  Exa gives AI agents fast, reliable web search with neural relevance,
  structured outputs, content extraction, and deep research modes.
  Covers the full API surface: search types, contents, outputSchema,
  domain filtering, freshness control, and MCP integration.
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [Research, Web, Search, Exa, API, MCP]
    related_skills: [arxiv, firecrawl, agent-browser]
---

> **Canonical reference:** https://docs.exa.ai/reference/search-api-guide-for-coding-agents
>
> If anything below looks outdated or contradicts real API behavior, fetch that URL — it is the source of truth for search types, parameters, and response shape. Report staleness back to the user.

# Exa

Exa provides neural web search, content extraction, and structured outputs for AI agents. The MCP server is already running locally at `http://localhost:3302/sse`.

## Configuration

| Setting | Value |
|---------|-------|
| API Key | `EXA_API_KEY` in `.env` |
| MCP SSE | `http://localhost:3302/sse` |
| Remote MCP | `https://mcp.exa.ai/mcp?exaApiKey=YOUR_KEY` |
| Search Type | `auto` (default — balanced relevance and speed) |
| Content | `highlights` with `maxCharacters` |

---

## MCP Server

The Exa MCP server is running as a persistent launchd service (`ai.hermes.mcp-exa`) on port 3302.

**SSE endpoint:** `http://localhost:3302/sse`

**Remote MCP URL (with API key):**
```
https://mcp.exa.ai/mcp?exaApiKey=457ccd8f-1e64-4e7f-9b81-e3c3f39b5e8c
```

**Enable all tools:**
```
https://mcp.exa.ai/mcp?exaApiKey=457ccd8f-1e64-4e7f-9b81-e3c3f39b5e8c&tools=web_search_exa,web_search_advanced_exa,get_code_context_exa,crawling_exa,company_research_exa,people_search_exa,deep_researcher_start,deep_researcher_check
```

**Available tools (enabled by default):**
- `web_search_exa`
- `get_code_context_exa`
- `company_research_exa`

**Optional tools (enable via `tools=`):**
- `web_search_advanced_exa`
- `crawling_exa`
- `people_search_exa`
- `deep_researcher_start`
- `deep_researcher_check`

---

## Quick Start (cURL)

```bash
curl -X POST 'https://api.exa.ai/search' \
  -H 'x-api-key: YOUR_API_KEY' \
  -H 'Content-Type: application/json' \
  -d '{
  "query": "React hooks best practices 2024",
  "type": "auto",
  "num_results": 10,
  "contents": {
    "highlights": {
      "max_characters": 4000
    }
  }
}'
```

---

## Search Type Reference

| Type | Best For | Approx Latency | Depth |
|------|----------|----------------|-------|
| `auto` | Most queries — balanced relevance and speed | ~1 second | Smart |
| `fast` | Latency-sensitive queries that still need good relevance | ~450 ms | Basic |
| `instant` | Chat, voice, autocomplete, quick lookups | ~250 ms | Basic |
| `deep-lite` | Cheaper synthesis when full deep search is overkill | 4 seconds | Deep |
| `deep` | Research, enrichment, thorough results | 4–15 seconds | Deep |
| `deep-reasoning` | Complex research, multi-step reasoning, hard synthesis tasks | 12–40 seconds | Deepest |

**Tip:** `type="auto"` works well for most queries. `outputSchema` works on every search type.

---

## Structured Outputs (outputSchema)

`outputSchema` works on **every** search type. Pass a JSON schema and Exa returns synthesized JSON in `output.content`, with field-level citations in `output.grounding`.

**Schema controls:** `type`, `description`, `required`, `properties`, `items`. Max nesting depth 2, max total properties 10. Do NOT add citation or confidence fields — grounding data is returned automatically.

```bash
curl -X POST 'https://api.exa.ai/search' \
  -H 'x-api-key: YOUR_API_KEY' \
  -H 'Content-Type: application/json' \
  -d '{
  "query": "articles about GPUs",
  "type": "auto",
  "outputSchema": {
    "type": "object",
    "description": "Companies mentioned in articles",
    "required": ["companies"],
    "properties": {
      "companies": {
        "type": "array",
        "description": "List of companies mentioned",
        "items": {
          "type": "object",
          "required": ["name"],
          "properties": {
            "name": { "type": "string", "description": "Name of the company" },
            "description": { "type": "string", "description": "Short description" }
          }
        }
      }
    }
  },
  "contents": {
    "highlights": { "max_characters": 4000 }
  }
}'
```

### Response Shape

```json
{
  "output": {
    "content": {
      "companies": [
        {"name": "Nvidia", "description": "GPU and AI chip manufacturer"}
      ]
    },
    "grounding": [
      {
        "field": "companies[0].name",
        "citations": [{"url": "https://...", "title": "Source"}],
        "confidence": "high"
      }
    ]
  }
}
```

### When to Use Structured Outputs

- **Enrichment workflows** — extract specific fields (company info, people data, product details)
- **Data pipelines** — get structured data directly instead of parsing free text
- **Grounded answers** — prefer `outputSchema` on `/search` over the legacy `/answer` endpoint
- Use `deep-lite`/`deep`/`deep-reasoning` for multi-step reasoning or synthesis across many sources

---

## Content Configuration

Content is controlled via the `contents` object on `/search` (or top-level fields on `/contents`). `text`, `highlights`, and `summary` can be combined.

| Mode | Config | Best For |
|------|--------|----------|
| Text | `"text": {"maxCharacters": 20000}` | Full content extraction, RAG |
| Highlights | `"highlights": {"maxCharacters": 4000}` | Token-efficient excerpts |
| Summary | `"summary": {"query": "your question"}` | LLM-written summary per result |

### Tuning Knobs

- **`summary`** — `true` for generic summary, or `{"query": "..."}` to focus on a specific question
- **`text.verbosity`** — `"compact" | "full"` (default `"compact"`). Compact excludes navbars, banners, footers
- **`text.includeHtmlTags`** — boolean (default `false`). Preserves HTML structure
- **`text.maxCharacters`** — hard cap on text length. Always set to control token cost
- **`highlights.maxCharacters`** — total character budget across all highlights per result
- **`highlights.query`** — custom query to direct highlight selection

**Case conventions:** raw JSON/JS SDK uses camelCase (`maxCharacters`). Python SDK uses snake_case (`max_characters`).

**⚠️ Token usage:** `text: true` with no cap can blow up context. Prefer `highlights` with `maxCharacters` for agent workflows.

---

## Domain Filtering (Optional)

```json
{
  "includeDomains": ["arxiv.org", "github.com"],
  "excludeDomains": ["pinterest.com"]
}
```

Note: `excludeDomains` cannot be used with `category: "company"` or `category: "people"` — causes a 400 error.

---

## Content Freshness (maxAgeHours)

| Value | Behavior |
|-------|----------|
| `24` | Use cache if <24h old, else livecrawl |
| `1` | Use cache if <1h old, else livecrawl |
| `0` | Always livecrawl |
| `-1` | Never livecrawl (cache only) |
| *(omit)* | Default — cache when available, livecrawl as fallback (**recommended**) |

---

## /contents Endpoint

Use `/contents` when you already have URLs and need their content.

```bash
curl -X POST 'https://api.exa.ai/contents' \
  -H 'x-api-key: YOUR_API_KEY' \
  -H 'Content-Type: application/json' \
  -d '{
  "urls": ["https://example.com/article"],
  "text": { "max_characters": 20000 }
}'
```

**When to use `/contents` vs `/search`:**
- URLs from another source → `/contents`
- Need to refresh stale content → `/contents` with `maxAgeHours`
- Find AND get content in one call → `/search` with `contents`

---

## Troubleshooting

**⚠️ Common parameter mistakes — avoid these:**
- `useAutoprompt` → **deprecated**, remove it entirely
- `includeUrls` / `excludeUrls` → **do not exist**. Use `includeDomains` / `excludeDomains`
- `text`, `summary`, `highlights` at top-level of `/search` → **must be nested inside `contents`**
- `numSentences`, `highlightsPerUrl` → **deprecated**. Use `maxCharacters`
- `tokensNum` → **does not exist**. Use `contents.text.maxCharacters`
- `livecrawl: "always"` → **deprecated**. Use `contents.maxAgeHours: 0`
- `excludeDomains` + `category: "company"|"people"` → **400 error**

**Results not relevant?** Try `type: "auto"`, then `type: "deep"`. Refine query (use singular form, be specific).

**Need structured data?** Use `outputSchema` on any search type. `deep`/`deep-reasoning` gives higher-quality synthesis.

**Results too slow?** Use `type: "fast"` or `type: "instant"`. Reduce `numResults`. Skip contents if you only need URLs.

**No results?** Remove domain/date filters. Simplify query. Try `type: "auto"`.

---

## Resources

- Docs: https://exa.ai/docs
- API Reference: https://docs.exa.ai/reference/search-api-guide-for-coding-agents
- Dashboard: https://dashboard.exa.ai
- API Status: https://status.exa.ai
