# MCP Social Signals Server

JSON-RPC 2.0 tool server for social signal aggregation across tech communities.
Used by the Market Intelligence agent to surface trending topics and developer buzz.

**Port:** `3005`  
**Env var:** `MCP_SOCIAL_SIGNALS_URL=http://mcp-social-signals:3005`

---

## Tools

| Method | Description | Auth required |
|---|---|---|
| `get_hackernews_signals` | Top HN stories / Ask HN / Show HN by tech stack | No |
| `get_reddit_signals` | Top Reddit posts from tech subreddits | No |
| `get_twitter_signals` | Recent tweets by stack keyword | Bearer Token |
| `get_devto_signals` | Top Dev.to articles by tag | No (key optional) |
| `get_trending_topics` | Cross-source aggregated trending topics | Varies |

---

## Sources

| Source | API | Key required | Default |
|---|---|---|---|
| HackerNews | [Algolia HN Search API](https://hn.algolia.com/api) | No | Always on |
| Reddit | [Public JSON API](https://www.reddit.com/dev/api/) | No | Always on |
| Dev.to | [Dev.to API](https://developers.forem.com/api) | No (optional) | Always on |
| Twitter/X | [Twitter API v2](https://developer.twitter.com/en/docs/twitter-api) | Yes | Skipped if absent |

---

## Configuration

```env
# Required
MCP_SOCIAL_SIGNALS_URL=http://mcp-social-signals:3005
REDIS_URL=redis://redis:6379/5

# Optional — enables Twitter/X
TWITTER_BEARER_TOKEN=AAAAAAAAAAAAAAAAAAAAAxxxxxx

# Optional — higher rate limits on Dev.to
DEVTO_API_KEY=your_devto_key

# Optional — Reddit OAuth for higher rate limits
REDDIT_CLIENT_ID=your_reddit_client_id
REDDIT_CLIENT_SECRET=your_reddit_client_secret

# Tuning
CACHE_TTL_SECONDS=600        # 10 min default (signals decay fast)
RATE_LIMIT_PER_MINUTE=60
HN_MIN_SCORE=10              # Minimum HN points filter
```

---

## Running

```bash
# From mcp-servers/social-signals/
poetry install
poetry run start
# → http://localhost:3005
```

Health: `GET /livez`, `GET /readyz`  
Metrics: `GET /metrics` (Prometheus)

---

## Example Request

```json
POST /
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "get_trending_topics",
  "params": {
    "stacks": ["Python", "FastAPI", "LangChain"],
    "limit": 10
  }
}
```

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "topics": [
      {
        "topic": "Python",
        "stack": "Python",
        "signal_count": 23,
        "total_score": 4850,
        "sources": ["HackerNews", "Reddit", "Dev.to"],
        "top_signals": [...]
      }
    ],
    "total_signals_analysed": 45,
    "stacks_queried": ["Python", "FastAPI", "LangChain"],
    "sources_queried": ["HackerNews", "Reddit", "Dev.to"],
    "fetched_at": "2026-05-07T10:30:00+00:00"
  }
}
```
