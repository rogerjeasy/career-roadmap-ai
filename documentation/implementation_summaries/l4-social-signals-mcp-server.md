# L4 — Social Signals MCP Server

## 1. Context and Purpose

The Social Signals MCP Server is the third implemented component of the **L4 MCP Tool Server** layer. It sits between the L3 Specialist Agents and four external social/community platforms (HackerNews, Reddit, Twitter/X, Dev.to), acting as the sole broker for all social signal and trending-topic data.

```
L3 Agents (Market Intelligence, Roadmap Generation, Opportunity Matching)
    │
    │  mcp.call("social_signals", "get_trending_topics", {...})
    │  JSON-RPC 2.0 over HTTP  ─── X-MCP-API-Key ─── X-Correlation-ID
    ▼
┌──────────────────────────────────────────────────────────────────┐
│           Social Signals MCP Server  :3005                        │
│                                                                  │
│  POST /   ─── dispatcher ───► get_hackernews_signals             │
│                           ───► get_reddit_signals                │
│                           ───► get_twitter_signals               │
│                           ───► get_devto_signals                 │
│                           ───► get_trending_topics               │
│  GET /livez  GET /readyz  GET /metrics                           │
└──────────┬───────────────────────────────────────────────────────┘
           │  concurrent async HTTP
    ┌──────┼──────────┬─────────────┐
    ▼      ▼          ▼             ▼
  HN     Reddit    Twitter/X    Dev.to
(Algolia)(public) (Bearer Token)(public)
```

Agents never call social platforms directly. All external access is rate-limited, cached, audited, and normalized at this layer. The server surfaces developer community buzz — trending technologies, hot discussions, and ecosystem signals — so that agents can produce roadmaps and recommendations grounded in current market reality rather than static training data.

---

## 2. File Structure

```
mcp-servers/
├── shared/                              ← reused by all MCP servers
│   ├── __init__.py
│   ├── auth.py                          ← X-MCP-API-Key HMAC validation
│   ├── cache.py                         ← Redis response cache (SHA-256 keyed)
│   ├── rate_limiter.py                  ← sliding-window per-(user, tool) limiter
│   ├── error_handler.py                 ← JSON-RPC 2.0 error codes + builders
│   └── base_server.py                   ← MCPApp base (FastAPI + OTel + Prometheus)
│
└── social-signals/
    ├── pyproject.toml                   ← Poetry dependencies (port 3005)
    ├── config.py                        ← SocialSignalsSettings (pydantic-settings)
    ├── models.py                        ← Pydantic data models
    ├── observability.py                 ← Prometheus metrics + get_tracer()
    ├── server.py                        ← entry point, lifespan, dispatcher
    │
    ├── clients/
    │   ├── __init__.py
    │   ├── base_client.py               ← BaseSocialClient (abstract, retry, OTel)
    │   ├── hackernews_client.py         ← Algolia HN Search API (no key)
    │   ├── reddit_client.py             ← Reddit public JSON API (no key)
    │   ├── twitter_client.py            ← Twitter API v2 (Bearer Token)
    │   └── devto_client.py              ← Dev.to public API (key optional)
    │
    ├── tools/
    │   ├── __init__.py
    │   ├── get_hackernews_signals.py    ← HN stories / Ask HN / Show HN
    │   ├── get_reddit_signals.py        ← top posts from tech subreddits
    │   ├── get_twitter_signals.py       ← recent tweets by stack keyword
    │   ├── get_devto_signals.py         ← top articles by Dev.to tag
    │   └── get_trending_topics.py       ← cross-source aggregation + ranking
    │
    └── tests/
        ├── __init__.py
        ├── conftest.py                  ← sys.path setup + shared fixtures
        └── test_server.py               ← 14 tests (tools, errors, models)
```

---

## 3. JSON-RPC 2.0 Protocol

### Transport

All requests are `POST /` with `Content-Type: application/json`. The server speaks plain JSON-RPC 2.0 — no WebSocket, no SSE.

**Request envelope:**
```json
{
  "jsonrpc": "2.0",
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "method": "get_trending_topics",
  "params": { "stacks": ["Python", "FastAPI"], "limit": 10 }
}
```

**Success response:**
```json
{
  "jsonrpc": "2.0",
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "result": { ... }
}
```

**Error response:**
```json
{
  "jsonrpc": "2.0",
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "error": {
    "code": -32602,
    "message": "Invalid get_trending_topics parameters",
    "data": [ ... ]
  }
}
```

HTTP status is always `200 OK` — errors are expressed in the JSON body per the JSON-RPC spec.

### Error Codes

| Code | Name | Meaning |
|------|------|---------|
| `-32700` | `PARSE_ERROR` | Request body is not valid JSON |
| `-32600` | `INVALID_REQUEST` | Missing `jsonrpc: "2.0"` or `method` |
| `-32601` | `METHOD_NOT_FOUND` | Unknown method name |
| `-32602` | `INVALID_PARAMS` | Pydantic validation failure on params |
| `-32603` | `INTERNAL_ERROR` | Unexpected server exception |
| `-32000` | `RATE_LIMITED` | Per-user sliding window exceeded |
| `-32001` | `UNAUTHORIZED` | Invalid or missing `X-MCP-API-Key` |
| `-32002` | `UPSTREAM_ERROR` | Required source not configured (e.g., no clients available) |
| `-32003` | `TOOL_TIMEOUT` | Source fetch timed out |
| `-32004` | `CACHE_ERROR` | Redis operation failure |

### Request Headers

| Header | Required | Purpose |
|--------|----------|---------|
| `X-MCP-API-Key` | When `MCP_API_KEY` is set | Server authentication |
| `X-Correlation-ID` | No | Propagated into all logs and OTel spans |
| `X-User-ID` | No | Used as rate-limit key (falls back to `"anonymous"`) |

---

## 4. Tools

### 4.1 `get_hackernews_signals`

Searches HackerNews via the Algolia HN Search API for stories, Ask HN, and Show HN posts matching the requested tech stacks. Results are deduplicated by `objectID` and sorted by score descending.

**Params — `GetHackerNewsSignalsParams`:**

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `stacks` | `list[str]` (1–10 items) | required | Tech stacks to search for, e.g. `["Python", "FastAPI"]` |
| `tags` | `list[str]` | `["story"]` | HN tag filter: `story`, `ask_hn`, `show_hn`, `job` |
| `min_score` | `int` (≥0) | `10` | Minimum HN points threshold |
| `limit` | `int` (1–30) | `10` | Maximum signals to return |

**Result — `SocialSignalsResult`:**
```json
{
  "signals": [ ... ],
  "total_count": 8,
  "stacks_queried": ["Python", "FastAPI"],
  "source": "HackerNews",
  "fetched_at": "2026-05-07T10:30:00+00:00"
}
```

**Cache TTL:** 10 minutes  
**Rate limit:** 60 calls / minute / user

**Request lifecycle:**
```
1. Validate params → INVALID_PARAMS on failure
2. Rate-limit check → RATE_LIMITED on excess
3. Cache lookup → return cached result if hit
4. Per stack: GET /api/v1/search?query={stack}&tags={tags}&numericFilters=points>={min_score}
5. Deduplicate by objectID across stacks
6. Sort by score descending → slice to limit
7. Build SocialSignalsResult → write to cache → emit audit log
```

---

### 4.2 `get_reddit_signals`

Fetches top Reddit posts from tech-relevant subreddits. The client maintains a comprehensive stack→subreddit mapping that selects the most appropriate communities automatically. The public Reddit JSON API is used with no OAuth requirement.

**Params — `GetRedditSignalsParams`:**

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `stacks` | `list[str]` (1–10 items) | required | Tech stacks to search for |
| `subreddits` | `list[str]` | `[]` | Override subreddit list; auto-selected from stack map if empty |
| `time_filter` | `str` | `"week"` | Reddit time filter: `hour`, `day`, `week`, `month`, `year`, `all` |
| `sort` | `str` | `"top"` | Sort order: `hot`, `top`, `new`, `rising` |
| `limit` | `int` (1–25) | `10` | Maximum signals to return |

**Result — `SocialSignalsResult`:**
```json
{
  "signals": [ ... ],
  "total_count": 12,
  "stacks_queried": ["React", "TypeScript"],
  "source": "Reddit",
  "fetched_at": "2026-05-07T10:30:00+00:00"
}
```

**Stack → subreddit mapping (examples):**

| Stack keyword | Primary subreddits |
|---|---|
| `python` | `Python`, `learnpython` |
| `react` | `reactjs`, `webdev` |
| `kubernetes` | `kubernetes`, `devops` |
| `machine learning` | `MachineLearning`, `learnmachinelearning` |
| `llm` | `MachineLearning`, `LocalLLaMA`, `ChatGPT` |
| `rust` | `rust` |
| `docker` | `docker`, `devops` |

The mapping covers 35+ common career-relevant stacks. Unmapped stacks fall back to `r/programming`.

**Cache TTL:** 10 minutes  
**Rate limit:** 60 calls / minute / user

---

### 4.3 `get_twitter_signals`

Fetches recent English-language tweets mentioning the requested tech stacks. This tool is **optional** — it returns an empty `SocialSignalsResult` (no error) when `TWITTER_BEARER_TOKEN` is not configured. This allows the server to operate fully without a Twitter developer account.

**Params — `GetTwitterSignalsParams`:**

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `stacks` | `list[str]` (1–10 items) | required | Tech stacks to search for |
| `limit` | `int` (1–25) | `10` | Maximum signals to return (minimum 10 enforced by Twitter API) |

**Twitter query construction:**
```
("FastAPI" OR "LangChain") -is:retweet lang:en
```
Multi-word stacks are quoted; single-word stacks are unquoted. Retweets and non-English tweets are excluded.

**Signal score:** `like_count + retweet_count` — captures total engagement rather than just likes.

**Result — `SocialSignalsResult`:**
```json
{
  "signals": [ ... ],
  "total_count": 10,
  "stacks_queried": ["FastAPI"],
  "source": "Twitter/X",
  "fetched_at": "2026-05-07T10:30:00+00:00"
}
```

**Cache TTL:** 10 minutes  
**Rate limit:** 60 calls / minute / user

> **Note:** Twitter API v2 recent search is limited to tweets from the past 7 days on the Basic tier. Twitter/X rate limits are 500 000 tweets/month on the Basic tier.

---

### 4.4 `get_devto_signals`

Fetches top Dev.to articles for the requested tech stacks using the public Dev.to API. Dev.to is always available with no API key; a `DEVTO_API_KEY` is optional and increases rate limits. The client maintains a stack→Dev.to tag mapping that translates tech stack names to their canonical Dev.to tag form.

**Params — `GetDevToSignalsParams`:**

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `stacks` | `list[str]` (1–10 items) | required | Tech stacks to search for |
| `top_days` | `int` (1–365) | `7` | Articles from the last N days, sorted by reactions |
| `limit` | `int` (1–30) | `10` | Maximum signals to return |

**Stack → tag mapping (examples):**

| Stack keyword | Dev.to tags queried |
|---|---|
| `python` | `python`, `django` |
| `javascript` | `javascript`, `nodejs` |
| `machine learning` | `machinelearning`, `ai` |
| `llm` | `llm`, `ai` |
| `devops` | `devops`, `cicd` |
| `react` | `react`, `javascript` |

**Signal score:** `positive_reactions_count` (Dev.to's equivalent of upvotes).

**Result — `SocialSignalsResult`:**
```json
{
  "signals": [ ... ],
  "total_count": 9,
  "stacks_queried": ["TypeScript"],
  "source": "Dev.to",
  "fetched_at": "2026-05-07T10:30:00+00:00"
}
```

**Cache TTL:** 10 minutes  
**Rate limit:** 60 calls / minute / user

---

### 4.5 `get_trending_topics`

The aggregator tool. It fans out to all available sources concurrently, collects all signals, and groups them by tech stack keyword to produce a ranked list of trending topics. This is the tool most used by agents that need a holistic view of community buzz across platforms.

**Params — `GetTrendingTopicsParams`:**

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `stacks` | `list[str]` (1–10 items) | required | Tech stacks to analyse |
| `sources` | `list[SocialSource]` | `[]` | Filter to specific sources; empty = all available |
| `limit` | `int` (1–25) | `10` | Maximum trending topics to return |

**Result — `TrendingTopicsResult`:**
```json
{
  "topics": [
    {
      "topic": "Python",
      "stack": "Python",
      "signal_count": 23,
      "total_score": 4850,
      "sources": ["HackerNews", "Reddit", "Dev.to"],
      "top_signals": [ ... ]
    }
  ],
  "total_signals_analysed": 67,
  "stacks_queried": ["Python", "FastAPI", "LangChain"],
  "sources_queried": ["HackerNews", "Reddit", "Dev.to"],
  "fetched_at": "2026-05-07T10:30:00+00:00"
}
```

**Aggregation lifecycle:**
```
1. Validate params → INVALID_PARAMS on failure
2. Rate-limit check → RATE_LIMITED on excess
3. Cache lookup → return cached result if hit
4. _select_clients(clients, sources_filter) → list of active clients
   └─ if empty → UPSTREAM_ERROR
5. asyncio.gather(*[client.search(stacks, limit=15) for client in clients])
   └─ each client fails silently, returning []
6. Group signals by requested stack keyword
7. Rank topics by composite score:
      (signal_count × 0.4) + (total_score / max_score × 0.6)
8. Return top N topics with up to 3 representative signals each
9. Write to cache → emit audit log
```

**Top signals selection:** The 3 highest-scoring signals per topic are included in `top_signals`, giving agents concrete evidence of what is actually trending rather than just an aggregate count.

**Cache TTL:** 10 minutes  
**Rate limit:** 60 calls / minute / user

---

## 5. Data Models

### `SocialSignal`

The canonical normalised representation returned by all clients and tools. Every source-specific payload is mapped to this shape before leaving the client layer.

| Field | Type | Notes |
|-------|------|-------|
| `id` | `str` | Source-prefixed ID: `hn_<objectID>`, `reddit_<post_id>`, `twitter_<tweet_id>`, `devto_<article_id>` |
| `title` | `str` | Post/article title; tweets use the first 140 characters of text |
| `url` | `str` | Direct link to the post, thread, tweet, or article |
| `source` | `SocialSource` | Origin platform enum value |
| `score` | `int` | Platform engagement proxy: HN points, Reddit upvote score, tweet likes+retweets, Dev.to reactions |
| `comment_count` | `int` | Discussion depth: HN comments, Reddit comments, tweet replies, Dev.to comments |
| `author` | `str` | HN username, Reddit `u/`, Twitter `@username`, Dev.to username |
| `published_at` | `datetime \| None` | UTC publication timestamp |
| `tags` | `list[str]` | Platform-native tags: HN story tags, Reddit flair, tweet hashtags, Dev.to tags |
| `tech_stack` | `list[str]` | Stack keywords that matched this signal (set at search time) |
| `summary` | `str` | Short text snippet: first 300 chars of Reddit selftext, tweet body, or Dev.to description |
| `fetched_at` | `datetime` | UTC timestamp when this signal was fetched |

**`tags` and `tech_stack` deduplication:** Both fields run a case-insensitive deduplication validator that strips duplicates while preserving the original capitalisation of the first occurrence.

**`model_dump_api()` output** is the dict shape the `MarketIntelligenceAgent` and `OpportunityMatchingAgent` expect. All datetimes are serialised as ISO 8601 strings.

### `TrendingTopic`

| Field | Type | Notes |
|-------|------|-------|
| `topic` | `str` | The trending technology or concept name |
| `stack` | `str` | Primary tech stack category it maps to |
| `signal_count` | `int` | Number of matching signals found across all sources |
| `total_score` | `int` | Sum of all signal scores (engagement proxy) |
| `sources` | `list[SocialSource]` | Sources that contributed signals |
| `top_signals` | `list[dict]` | Up to 3 highest-scoring `SocialSignal` dicts |

### Enums

**`SocialSource`:**

| Value | Platform |
|-------|----------|
| `"HackerNews"` | Hacker News (Y Combinator) |
| `"Reddit"` | Reddit |
| `"Twitter/X"` | Twitter / X (formerly Twitter) |
| `"Dev.to"` | Dev.to (Forem) |
| `"unknown"` | Fallback |

### Tool Parameter Models

| Model | Used by |
|-------|---------|
| `GetHackerNewsSignalsParams` | `get_hackernews_signals` |
| `GetRedditSignalsParams` | `get_reddit_signals` |
| `GetTwitterSignalsParams` | `get_twitter_signals` |
| `GetDevToSignalsParams` | `get_devto_signals` |
| `GetTrendingTopicsParams` | `get_trending_topics` |

### Tool Result Models

| Model | Used by |
|-------|---------|
| `SocialSignalsResult` | `get_hackernews_signals`, `get_reddit_signals`, `get_twitter_signals`, `get_devto_signals` |
| `TrendingTopicsResult` | `get_trending_topics` |

---

## 6. Data Sources

### HackerNews — Algolia Search API

- **Auth:** None required
- **Endpoint:** `GET https://hn.algolia.com/api/v1/search`
- **Key params:** `query`, `tags` (comma-separated: `story,ask_hn,show_hn`), `numericFilters=points>=10`, `hitsPerPage`
- **Rate limits:** ~10 000 requests/hour unauthenticated
- **Field mapping:**

| Algolia field | `SocialSignal` field |
|---|---|
| `objectID` | `id` (prefixed `hn_`) |
| `title` / `story_title` | `title` |
| `url` | `url` (falls back to `ycombinator.com/item?id=`) |
| `points` | `score` |
| `num_comments` | `comment_count` |
| `author` | `author` |
| `created_at` | `published_at` |
| `_tags` (filtered) | `tags` (author and story prefixes stripped) |

- **Per-stack fetch:** One API call per stack keyword, then merged and deduplicated by `objectID`. Over-fetch by `+2` per stack to compensate for deduplication loss.

---

### Reddit — Public JSON API

- **Auth:** None required (User-Agent header mandatory)
- **Endpoint:** `GET https://www.reddit.com/r/{subreddit}/search.json`
- **Key params:** `q`, `sort=top`, `t=week`, `limit`, `restrict_sr=true`
- **Rate limits:** ~60 requests/minute with a descriptive User-Agent
- **User-Agent:** `CareerRoadmapAI/1.0 (by /u/career_roadmap_bot)` — Reddit blocks generic User-Agents
- **Field mapping:**

| Reddit JSON field | `SocialSignal` field |
|---|---|
| `data.id` | `id` (prefixed `reddit_`) |
| `data.title` | `title` |
| `data.url` | `url` |
| `data.score` | `score` |
| `data.num_comments` | `comment_count` |
| `data.author` | `author` |
| `data.created_utc` | `published_at` (Unix timestamp → UTC datetime) |
| `data.link_flair_text` | `tags` |
| `data.selftext[:300]` | `summary` |

- **Subreddit selection:** `_subreddits_for_stacks()` maps each stack to up to 2 subreddits. At most 2 subreddits per stack are queried to bound the total number of HTTP calls.

---

### Twitter/X — API v2 Recent Search

- **Auth:** `Authorization: Bearer {TWITTER_BEARER_TOKEN}` (required)
- **Endpoint:** `GET https://api.twitter.com/2/tweets/search/recent`
- **Key params:** `query`, `max_results` (10–100), `tweet.fields=public_metrics,created_at,entities`, `expansions=author_id`, `user.fields=username`
- **Rate limits:** 1 request/second, 500 000 tweets/month (Basic tier)
- **Graceful skip:** When `TWITTER_BEARER_TOKEN` is not set, `get_twitter_signals` returns an empty result without raising an error, and `get_trending_topics` simply omits Twitter from the source list.
- **429 handling:** HTTP 429 from Twitter is caught and logged as a warning; the client re-raises so the base class records it as a `rate_limited` status in Prometheus.
- **Field mapping:**

| Twitter API field | `SocialSignal` field |
|---|---|
| `id` | `id` (prefixed `twitter_`) |
| `text[:140]` | `title` |
| `public_metrics.like_count + retweet_count` | `score` |
| `public_metrics.reply_count` | `comment_count` |
| `author_id` (expanded) | `author` (`@username` via `includes.users`) |
| `created_at` | `published_at` |
| `entities.hashtags[].tag` | `tags` |
| `text[:300]` | `summary` |

---

### Dev.to — Forem Public API

- **Auth:** None required; `api-key` header increases rate limits
- **Endpoint:** `GET https://dev.to/api/articles`
- **Key params:** `tag`, `top` (past N days), `per_page`
- **Rate limits:** ~10 requests/second
- **Field mapping:**

| Dev.to JSON field | `SocialSignal` field |
|---|---|
| `id` | `id` (prefixed `devto_`) |
| `title` | `title` |
| `url` | `url` |
| `positive_reactions_count` | `score` |
| `comments_count` | `comment_count` |
| `user.username` | `author` |
| `published_at` | `published_at` |
| `tag_list` | `tags` |
| `description[:300]` | `summary` |

- **Tag selection:** `_tags_for_stacks()` maps each stack to up to 2 Dev.to tags. The Dev.to tag format is lowercase and hyphen-free (e.g., `python`, `machinelearning`, `nextjs`).

---

## 7. Shared Modules

All shared modules are identical to those used by the Job Board and Course Catalogue MCP Servers. See `l4-job-board-mcp-server.md § 7. Shared Modules` for the full reference. A brief recap:

### `shared/error_handler.py`
`JsonRpcErrorCode` enum + `make_success_response()` / `make_error_response()` builders. `JsonRpcError` is raised by tool handlers to produce a well-formed error without triggering the generic 500 handler.

### `shared/auth.py`
`verify_api_key()` compares `X-MCP-API-Key` against `MCP_API_KEY` using `hmac.compare_digest`. Bypassed when `MCP_API_KEY` is empty string.

### `shared/cache.py`
`ResponseCache` wraps `redis.asyncio`. Cache keys:
```
mcp:cache:{tool}:{sha256(json({tool, params}))[:16]}
```
All Redis failures are caught and logged; the caller receives `None` and proceeds without cache.

### `shared/rate_limiter.py`
Sliding-window limiter per `(user_id, tool)`. Fails open when Redis is unavailable.

---

## 8. Client Architecture

### `BaseSocialClient`

All four clients inherit from this abstract class. It provides:

- **Async context manager:** creates and closes `httpx.AsyncClient` with shared timeout and browser-like headers
- **`search(stacks, limit, ...)` public method:** wraps the subclass hook with error handling, OTel spans, and Prometheus recording; returns `[]` on any exception
- **`_get()` HTTP helper:** tenacity-decorated, retries on `TimeoutException` and `TransportError` with exponential back-off (3 attempts, 0.5–4 s window)
- **Fail-safe:** all public methods catch exceptions and return empty lists — a broken source never propagates an error to the dispatcher

```python
async with RedditClient(user_agent="CareerRoadmapAI/1.0") as client:
    signals = await client.search(["Python", "FastAPI"], limit=10, correlation_id=cid)
    # Returns [] if Reddit is down, rate-limits us, or returns bad data
```

### Client Lifecycle

Clients are instantiated once at startup in `_build_clients()` and held in the module-level `_clients` dict. The `httpx.AsyncClient` is created lazily on the first `search()` call via `__aenter__`. HTTP connections are reused across requests within the same process.

### Source Registration Logic

```python
# server.py: _build_clients()

# Always registered — no API key required:
HackerNewsClient(min_score=settings.hn_min_score, ...)
RedditClient(user_agent=settings.reddit_user_agent, ...)
DevToClient(api_key=None if not settings.devto_api_key else key, ...)

# Only registered when credential is set:
if settings.twitter_bearer_token:
    TwitterClient(bearer_token=token, ...)
else:
    logger.info("social_signals.client_skipped", source="Twitter/X",
                hint="Set TWITTER_BEARER_TOKEN to enable")
```

Three sources (HackerNews, Reddit, Dev.to) are always active — there is always a functional minimum even with zero credentials configured.

---

## 9. Observability

### Prometheus Metrics

All metrics are prefixed `mcp_social_signals_`.

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `mcp_social_signals_fetch_total` | Counter | `source`, `status` | Upstream fetch calls by source and outcome |
| `mcp_social_signals_fetch_duration_seconds` | Histogram | `source` | Fetch latency per source |
| `mcp_social_signals_fetch_results_count` | Histogram | `source` | Signals returned per source fetch |
| `mcp_social_signals_cache_hits_total` | Counter | `tool` | Cache hits by tool |
| `mcp_social_signals_cache_misses_total` | Counter | `tool` | Cache misses by tool |
| `mcp_social_signals_rate_limit_hit_total` | Counter | `tool` | Rate-limited requests by tool |
| `mcp_social_signals_tool_call_total` | Counter | `method`, `status` | Tool invocations by method and outcome |
| `mcp_social_signals_tool_call_duration_seconds` | Histogram | `method` | End-to-end tool call latency |
| `mcp_social_signals_score_distribution` | Histogram | `source` | Distribution of signal scores by source |
| `mcp_social_signals_audit_log_total` | Counter | `tool` | Audit log events emitted |

Status labels for `fetch_total`: `success`, `error`, `timeout`, `rate_limited`  
Status labels for `tool_call_total`: `ok`, `cache_hit`, `rpc_error`, `error`, `rate_limited`, `skipped`

> The `skipped` status appears specifically for `get_twitter_signals` when the Twitter client is not configured — it is a normal operational state, not an error.

### OpenTelemetry Spans

| Span Name | Created by | Attributes |
|-----------|------------|------------|
| `tool.get_hackernews_signals` | `get_hackernews_signals.py` | `user_id`, `correlation_id`, `stacks`, `result_count` |
| `tool.get_reddit_signals` | `get_reddit_signals.py` | `user_id`, `correlation_id`, `stacks`, `result_count` |
| `tool.get_twitter_signals` | `get_twitter_signals.py` | `user_id`, `correlation_id`, `stacks`, `result_count` |
| `tool.get_devto_signals` | `get_devto_signals.py` | `user_id`, `correlation_id`, `stacks`, `result_count` |
| `tool.get_trending_topics` | `get_trending_topics.py` | `user_id`, `correlation_id`, `stacks`, `topic_count`, `total_signals` |
| `social_signals.{source}.search` | `base_client.py` | `source`, `stacks`, `result_count`, `latency_ms`, `correlation_id` |

OTLP export is enabled when `OTEL_EXPORTER_OTLP_ENDPOINT` is set. In development, spans are printed to stdout via `ConsoleSpanExporter`.

### Structured Logging

All logs use `structlog` with keyword arguments. Key events:

```python
logger.info("social_signals.clients_registered", sources=["hackernews", "reddit", "devto"])
logger.info("social_signals.client_skipped", source="Twitter/X", hint="Set TWITTER_BEARER_TOKEN")
logger.info("get_hackernews_signals.completed", stacks=..., count=8, user_id=..., correlation_id=...)
logger.info("get_trending_topics.completed", stacks=..., topic_count=5, total_signals=67, ...)
logger.warning("social_signals.search_failed", source="Reddit", stacks=..., error="...")
logger.info("search_jobs.cache_hit", stacks=..., correlation_id=...)
```

Format: JSON in production, coloured console in dev.

### Health Endpoints

```
GET /livez   → 200 {"status": "ok"}
GET /readyz  → 200 {"status": "ok", "server_id": "social_signals", "sources": ["hackernews", "reddit", "devto"]}
GET /metrics → 200 (Prometheus text format)
```

---

## 10. Configuration Reference

All values are loaded from environment variables via `SocialSignalsSettings` (pydantic-settings). A `.env` file is supported in development.

| Variable | Default | Required | Description |
|----------|---------|----------|-------------|
| `ENVIRONMENT` | `development` | No | `development`, `staging`, `production` |
| `LOG_LEVEL` | `INFO` | No | `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| `HOST` | `0.0.0.0` | No | Bind address for uvicorn |
| `PORT` | `3005` | No | Listen port |
| `MCP_API_KEY` | `""` | No | Shared secret for `X-MCP-API-Key` auth (empty = bypass) |
| `REDIS_URL` | `redis://localhost:6379/5` | No | Redis DSN (DB 5 — separate from other MCP servers) |
| `CACHE_TTL_SECONDS` | `600` | No | Default cache TTL (10 minutes — social signals decay fast) |
| `RATE_LIMIT_PER_MINUTE` | `60` | No | Max requests per user per minute |
| `TWITTER_BEARER_TOKEN` | — | No | Twitter API v2 Bearer Token (skips Twitter source if absent) |
| `REDDIT_CLIENT_ID` | — | No | Reddit OAuth app client ID (for higher rate limits) |
| `REDDIT_CLIENT_SECRET` | — | No | Reddit OAuth app client secret |
| `REDDIT_USER_AGENT` | `CareerRoadmapAI/1.0 (by /u/career_roadmap_bot)` | No | Reddit User-Agent string |
| `DEVTO_API_KEY` | — | No | Dev.to API key (optional; increases rate limits) |
| `HN_MIN_SCORE` | `10` | No | Minimum HN points threshold for signal inclusion |
| `HN_BASE_URL` | `https://hn.algolia.com/api/v1` | No | Algolia HN API base URL override |
| `HTTP_TIMEOUT_SECONDS` | `15.0` | No | Per-source request timeout |
| `HTTP_MAX_RETRIES` | `3` | No | Tenacity retry attempts |
| `DEFAULT_RESULTS_PER_SOURCE` | `10` | No | Default limit per source fetch |
| `MAX_TOTAL_RESULTS` | `50` | No | Hard cap on merged results |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | — | No | OTLP gRPC endpoint for trace export |

The Redis DB index is `5` to avoid colliding with other MCP servers on the same Redis instance (job-board = 1, course-catalogue = 2, github-trends = 3, salary-benchmark = 4).

---

## 11. Agent Integration

The agents layer connects via `HttpMCPClient`. Three agents use this server:

### Market Intelligence Agent

Primary consumer. Calls `get_trending_topics` to surface community buzz around the tech stacks relevant to the user's target role. This grounds the market intelligence report in real developer sentiment rather than static training data.

```python
raw = await mcp_client.call(
    "social_signals",
    "get_trending_topics",
    {
        "stacks": ["Python", "FastAPI", "LangChain", "Kubernetes"],
        "limit": 10,
    },
    correlation_id=correlation_id,
)
# raw["topics"] → list of TrendingTopic dicts
```

Also calls `get_hackernews_signals` and `get_reddit_signals` individually when the agent needs source-specific context (e.g., "what is the HN community saying about this tech?").

Configured via `MCP_SOCIAL_SIGNALS_URL` in the agents `.env`.

### Roadmap Generation Agent

Calls `get_trending_topics` to validate that the skills in the generated roadmap are currently in demand in developer communities. Roadmap weeks featuring a trending skill receive a "high community momentum" annotation that explains the recommendation.

### Opportunity Matching Agent

Calls `get_devto_signals` and `get_reddit_signals` to find recent community discussions, blog posts, and job-adjacent conversations around the user's target stack. These are surfaced as "community resources" in the opportunity package alongside job postings.

### Stub fallback

When `MCP_SOCIAL_SIGNALS_URL` is not set, agents use `StubMCPClient` which returns realistic mock signals without any network calls.

---

## 12. Path Resolution

The `social-signals/` directory name contains a dash, making it non-importable as a Python package. Imports within the server use flat module names (e.g., `from models import SocialSignal`, `from clients.base_client import ...`).

`server.py` inserts the parent `mcp-servers/` directory into `sys.path` at the top of the file:

```python
_MCP_SERVERS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _MCP_SERVERS_DIR not in sys.path:
    sys.path.insert(0, _MCP_SERVERS_DIR)
```

The pytest `conftest.py` does the same, adding both `mcp-servers/` and `mcp-servers/social-signals/` to `sys.path`.

---

## 13. Testing

Tests live in `mcp-servers/social-signals/tests/test_server.py`. The test client drives the FastAPI app in-process using `fastapi.testclient.TestClient` — no network calls are made.

**Test doubles (fixtures in `conftest.py`):**

- `mock_clients` — dict of `MagicMock` clients with `AsyncMock` `.search()` returning `[]`; individual tests override `.search` return value for positive-path coverage
- `mock_cache` — `AsyncMock` for `.get()` (returns `None` = cache miss) and `.set()`
- `mock_rate_limiter` — `AsyncMock` for `.check()` (returns `True` = allowed); set to `False` for rate-limit tests
- `test_client` — injects the mocks into the `server` module at the global level and wraps with `TestClient`

**Test coverage by area:**

| Area | Tests |
|------|-------|
| Health endpoints (`/livez`, `/readyz`) | 2 |
| JSON-RPC dispatch (parse error, method-not-found, invalid-params) | 3 |
| `get_hackernews_signals` (empty result, with signals) | 2 |
| `get_reddit_signals` (empty result, with signals) | 2 |
| `get_twitter_signals` (graceful skip when client absent) | 1 |
| `get_devto_signals` (empty result) | 1 |
| `get_trending_topics` (with signals, no-sources error) | 2 |
| Rate-limit enforcement | 1 |
| **Total** | **14** |

**Running tests:**

```bash
cd mcp-servers/social-signals
poetry install
poetry run pytest -v
```

---

## 14. Running Locally

```bash
# 1. Start Redis
docker run -d -p 6379:6379 redis:7-alpine

# 2. Install dependencies
cd mcp-servers/social-signals
poetry install

# 3. Configure environment
cat > .env << 'EOF'
ENVIRONMENT=development
LOG_LEVEL=DEBUG
REDIS_URL=redis://localhost:6379/5

# Optional — Twitter/X (server works without it)
TWITTER_BEARER_TOKEN=AAAAAAAAAAAAAAAAAAAAAxxxxxx

# Optional — Dev.to higher rate limits
DEVTO_API_KEY=your_devto_key

# Optional — leave empty to disable auth in dev
MCP_API_KEY=
EOF

# 4. Run
uvicorn server:app --host 0.0.0.0 --port 3005 --reload
```

**Verify:**
```bash
curl http://localhost:3005/livez
# → {"status":"ok"}

curl -X POST http://localhost:3005/ \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": "1",
    "method": "get_trending_topics",
    "params": {"stacks": ["Python", "FastAPI"], "limit": 5}
  }'
```

**Agents side:** add `MCP_SOCIAL_SIGNALS_URL=http://localhost:3005` to `agents/.env`.

---

## 15. Docker

```dockerfile
FROM python:3.12-slim

WORKDIR /app
COPY mcp-servers/shared /app/mcp-servers/shared
COPY mcp-servers/social-signals /app/mcp-servers/social-signals

WORKDIR /app/mcp-servers/social-signals
RUN pip install poetry && poetry install --no-dev

ENV PYTHONPATH=/app/mcp-servers
EXPOSE 3005
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "3005"]
```

`PYTHONPATH=/app/mcp-servers` makes `from shared.xxx import ...` work without the in-process `sys.path` manipulation.

Docker Compose service entry:
```yaml
mcp-social-signals:
  build:
    context: .
    dockerfile: mcp-servers/social-signals/Dockerfile
  ports: ["3005:3005"]
  environment:
    REDIS_URL: redis://redis:6379/5
    TWITTER_BEARER_TOKEN: ${TWITTER_BEARER_TOKEN:-}
    DEVTO_API_KEY: ${DEVTO_API_KEY:-}
    MCP_API_KEY: ${MCP_API_KEY}
  depends_on: [redis]
```

---

## 16. Architecture Decisions

### HackerNews, Reddit, and Dev.to always registered

Unlike the Job Board server where all sources require paid API keys, social signals from three of four sources require no credentials at all. This means the server provides meaningful output in a fully zero-config local development environment. The design deliberate prioritises always-on availability over completeness of optional sources.

### Twitter/X is gracefully optional, not required

Twitter/X API access has become significantly restricted and expensive. Making the server fail at startup when `TWITTER_BEARER_TOKEN` is absent would block development and staging environments. Instead, the `get_twitter_signals` tool returns an empty `SocialSignalsResult` with `total_count: 0` when Twitter is unconfigured, and `get_trending_topics` simply omits Twitter from `sources_queried`. Callers see a clean, annotated empty result rather than an error.

### 10-minute cache TTL vs. 1-hour (course catalogue) or 5-minute (none)

Social signals occupy the middle ground: they change faster than course catalogues (which update weekly) but not so fast that a 10-minute cache is meaningless. A 10-minute TTL:
- Absorbs repeated agent calls within a single roadmap generation pipeline (~2–3 minutes end-to-end)
- Stays within reasonable "freshness" bounds for trending topic data
- Avoids hitting the Reddit public API's ~60 req/min limit during concurrent agent requests

### Trending topics ranking formula: `signal_count × 0.4 + normalised_score × 0.6`

A pure signal count would favour stacks that appear in every post (e.g., "JavaScript" appears in more posts than "LangChain"). A pure score sum would favour stacks with one viral post but little sustained community interest. The composite formula balances breadth of discussion (signal_count) against depth of engagement (normalised_score), producing rankings that reflect genuine community momentum rather than statistical noise.

### Score normalisation in trending topics

The raw score sums across sources are not directly comparable — a HackerNews post scoring 1000 points is not equivalent to 1000 Dev.to reactions. The trending topic ranker normalises by the maximum `total_score` in the result set (`score / max_score`), reducing all scores to a [0, 1] range before weighting. This prevents a single viral HN post from dominating rankings when Reddit and Dev.to show deeper, sustained interest in a different stack.

### Sources fail independently in `get_trending_topics`

`asyncio.gather(*tasks, return_exceptions=True)` is used rather than `asyncio.gather(*tasks)` (which would cancel all tasks on first exception). A Twitter rate-limit or Reddit outage should not prevent HackerNews and Dev.to from contributing their signals. The aggregated result is always the best available subset of sources, never a hard failure caused by one source's transient issue.

### Per-stack search rather than a single combined query

Each stack is searched individually in HackerNews and Dev.to rather than combining stacks into a single `OR` query. This allows the `tech_stack` field on each signal to precisely record which stack keyword matched, enabling accurate grouping in `get_trending_topics`. A combined query would return mixed results where it is ambiguous whether a signal is relevant to "Python" or "FastAPI" — per-stack search makes the attribution explicit.

### Reddit uses `restrict_sr=true`

Reddit search results without `restrict_sr=true` span the entire site, surfacing posts from unrelated subreddits. Restricting to the target subreddit keeps signal-to-noise high — a post in `r/Python` about Python is far more relevant than a post in `r/news` that happens to mention Python in passing.
