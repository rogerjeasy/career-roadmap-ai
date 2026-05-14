# MCP LinkedIn Profile Server

JSON-RPC 2.0 MCP tool server for Career Roadmap AI — LinkedIn profile enrichment, job title normalisation, and connection suggestions.

**Port:** `3008`

---

## Tools

| Method | Rate limit | Description |
|---|---|---|
| `fetch_profile` | 20/min | Fetch a LinkedIn profile by URL (requires RapidAPI key) |
| `normalize_job_title` | 20/min | Canonical title mapping — in-process, always available, no API key |
| `suggest_connections` | 20/min | People search for relevant connections (requires RapidAPI key) |

---

## Environment variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `LINKEDIN_API_KEY` | For fetch/suggest | — | RapidAPI key for `linkedin-data-api.p.rapidapi.com` |
| `LINKEDIN_API_HOST` | No | `linkedin-data-api.p.rapidapi.com` | RapidAPI host override |
| `MCP_REDIS_URL` | No | `redis://localhost:6379/8` | Redis for rate limiting + cache |
| `MCP_API_KEY` | No | — | HMAC API key (X-MCP-API-Key header) |
| `SENTRY_DSN` | No | — | Sentry error tracking |

---

## Running locally

```bash
# From mcp-servers/linkedin-profile/
poetry install
uvicorn server:app --host 0.0.0.0 --port 3008 --reload
```

`normalize_job_title` is always available even without a LinkedIn API key — useful for testing and environments where the API key is not configured.

Health checks:
- `GET /livez` — liveness (always 200 if process is up)
- `GET /readyz` — readiness (200 if Redis is reachable)
- `GET /metrics` — Prometheus metrics

---

## Example calls

```bash
# Normalize a job title (no API key needed)
curl -s -X POST http://localhost:3008/ \
  -H 'Content-Type: application/json' \
  -d '{
    "jsonrpc": "2.0",
    "method": "normalize_job_title",
    "params": {"raw_title": "sr. swe", "industry": "Technology"},
    "id": 1
  }' | jq .

# Fetch a LinkedIn profile (requires LINKEDIN_API_KEY)
curl -s -X POST http://localhost:3008/ \
  -H 'Content-Type: application/json' \
  -H 'X-MCP-API-Key: <key>' \
  -d '{
    "jsonrpc": "2.0",
    "method": "fetch_profile",
    "params": {
      "user_id": "user-abc",
      "profile_url": "https://www.linkedin.com/in/some-person"
    },
    "id": 2
  }' | jq .
```

---

## Tests

```bash
poetry run pytest tests/ -v
```
