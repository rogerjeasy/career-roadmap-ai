# Opportunity Matching Agent

**Date:** 2026-05-06  
**Phase:** L3 Specialist Agent — Phase 5 (parallel with LearningResourceAgent, NetworkingAgent)  
**Model:** `claude-sonnet-4-6` (overridable via `OPPORTUNITY_MODEL`)  
**Tests:** 39 unit tests, all passing

---

## 1. What It Does

The Opportunity Matching Agent connects the user's career profile to the live job market. It:

1. **Fetches** live job listings from the job-board MCP server for the user's target role.
2. **Scores** every listing against the user profile using a fast deterministic algorithm (no LLM cost per listing).
3. **Enriches** the top 10 listings with Claude-generated match reasons and critical skill gaps.
4. **Alerts** the user on high-match roles (score ≥ 0.65).
5. **Tailors** the user's CV for the top 5 high-match jobs — one summary sentence, 3–5 achievement bullets, and an ATS keyword list per role.
6. **Tracks target companies** — surfaces employers with multiple high-match listings or an exceptionally strong fit.

---

## 2. Architecture Position

```
Phase 5 (parallel)
├── LearningResourceAgent   ← curated courses per skill gap
├── NetworkingAgent         ← events, LinkedIn outreach drafts
└── OpportunityAgent        ← job matching, CV tailoring  ← THIS AGENT
```

The agent reads from `AgentContext.user_profile` and `AgentContext.plan_snapshot` (outputs of prior phases). It does **not** depend on LearningResourceAgent or NetworkingAgent outputs. Its own output (`opportunity` key) is merged into `plan_snapshot` and available to the Validator and Aggregator in Phase 6.

The agent is also reachable **standalone** via its dedicated HTTP endpoint (see §15), which sets `forced_intent="opportunity_search"` to bypass the intent parser and run the OpportunityAgent directly — the same short-circuit mechanism used by the coach endpoint.

---

## 3. Pipeline Steps

```
AgentContext
    │
    ▼
[1] Fetch job listings
    └─ JobBoardMCPClient.search_jobs(role, location, skills, limit=50)
    │
    ▼
[2] Deterministic scoring  (all listings, no LLM)
    └─ JobScorer.score_all() → list[JobMatchScore], sorted desc
    │
    ▼
[3] LLM enrichment         (top 10 listings only)
    └─ JobScorer.enrich_top() → populates match_reasons + refines missing_skills
    │
    ▼
[4] CV tailoring            (top 5 high-match jobs)
    └─ CVTailor.tailor() → list[CVTailoringSnippet]
    │
    ▼
[5] Target company extraction
    └─ _extract_target_companies() → list[TargetCompany]
    │
    ▼
[6] Match alerts
    └─ _build_alerts() → list[str]   (top 5, human-readable)
    │
    ▼
OpportunityOutput.model_dump()  →  AgentResult.output
```

Each step emits a `STEP_PROGRESS` SSE event so the browser can show a live progress indicator.

---

## 4. Scoring Algorithm

### 4.1 Deterministic Score (all listings)

```
match_score = (
    skill_score    × 0.50
  + location_score × 0.20
  + salary_score   × 0.15
  + seniority_score × 0.15
)
```

| Dimension | How calculated |
|---|---|
| **Skill score** | `len(overlap) / max(len(required), 1)` where overlap = required skills the user has (case-insensitive) |
| **Location score** | 1.0 if listing is remote or user location string appears in listing location; 0.3 otherwise |
| **Salary score** | 1.0 if `listing.salary_max ≥ user.salary_goal × 0.85`; 0.5 if below; 1.0 if no salary goal or listing has no salary data |
| **Seniority score** | 1.0 if both listing and user profile are senior/junior aligned; 0.4 if listing is senior but user is junior; 0.5 if listing is junior but user is senior; 0.8 for unknown/mid |

**High-match threshold:** 0.65

### 4.2 LLM Enrichment (top 10)

Claude Sonnet receives the pre-scored top 10 listings plus the user profile. For each listing it returns:
- `match_reasons` — exactly 3 concise reasons (< 25 words each) referencing actual skills, role context, and career progression opportunity.
- `missing_skills` — top 3 highest-leverage skills the user lacks, most critical first.

Enrichment is best-effort. If the LLM call fails, the deterministic scores and empty `match_reasons` are returned. The agent never fails due to enrichment errors.

---

## 5. CV Tailoring

For each of the top 5 high-match jobs, Claude generates:

```json
{
  "summary_bullet": "Seasoned Python engineer delivering scalable FastAPI services for high-traffic platforms.",
  "skill_highlights": [
    "Built REST API serving 10k+ rps with 99.9% uptime using FastAPI + PostgreSQL",
    "Reduced query latency by 40% through query optimisation and Redis caching",
    "Led migration of monolith to microservices architecture across 3-person team"
  ],
  "keywords_to_include": ["FastAPI", "PostgreSQL", "Redis", "Docker", "Microservices"]
}
```

Rules enforced in `cv_tailor_system.txt`:
- `summary_bullet` begins with a strong adjective or role noun; 20–30 words.
- Each highlight starts with an action verb (Built, Delivered, Scaled, Led, Reduced…).
- Quantified outcomes where the user's background suggests them.
- Placeholder template notation `[quantify X]` when data is insufficient.
- ATS keywords extracted verbatim from the job description.

**Fallback:** When LLM is unavailable, deterministic snippets are generated from `skill_overlap` so the output is always populated.

---

## 6. Target Company Tracker

A company is surfaced as a tracked target if either condition is met:
- It appears in **≥ 2** high-match listings, OR
- Its average match score across high-match listings is **≥ 0.75**

Output per company:

```python
TargetCompany(
    name="TechCorp",
    reason="3 matching role(s) with avg 82% fit.",
    job_count=3,
    top_roles=["Senior Python Developer", "Lead Backend Engineer"],
    avg_match_score=0.82,
)
```

Companies are sorted by `job_count` descending, then `avg_match_score` descending. Maximum 10 companies returned.

---

## 7. Match Alerts

Up to 5 human-readable alerts are generated for the highest-scoring roles:

```
Strong match (87%): Senior Python Developer at TechCorp — Berlin
Strong match (81%): Backend Engineer at StartupXYZ — Remote
```

These are surfaced in the ROADMAP_COMPLETE SSE event payload and displayed as notification banners in the frontend.

---

## 8. Data Models

### `JobListing`
Raw listing from the MCP server. Key fields: `id`, `title`, `company`, `location`, `description`, `required_skills`, `salary_min`, `salary_max`, `remote`, `seniority_level`.

### `JobMatchScore`
Scored listing. Adds: `match_score`, `skill_overlap`, `missing_skills`, `match_reasons`, `salary_fit`, `location_fit`, `is_high_match`.

### `CVTailoringSnippet`
Per-job CV content. Fields: `job_id`, `job_title`, `company`, `summary_bullet`, `skill_highlights`, `keywords_to_include`.

### `TargetCompany`
Aggregated company entry. Fields: `name`, `reason`, `job_count`, `top_roles`, `avg_match_score`.

### `OpportunityOutput`
Full agent output. Returned as a plain `dict` via `AgentResult.output`:

```python
{
    "total_listings_fetched": 47,
    "scored_jobs": [...],          # top 20 scored listings
    "high_match_jobs": [...],      # all listings with score ≥ 0.65
    "cv_tailoring": [...],         # snippets for top 5 high-match jobs
    "target_companies": [...],     # tracked companies
    "match_alerts": [...],         # top 5 human-readable alerts
    "search_query": "Senior Python Developer",
    "timestamp": "2026-05-06T14:32:00+00:00"
}
```

---

## 9. MCP Client

`JobBoardMCPClient` is an async HTTP client that calls `GET /tools/search_jobs` on the job-board MCP server.

```python
listings = await client.search_jobs(
    role="Senior Python Developer",
    location="Berlin",
    skills=["Python", "FastAPI", "PostgreSQL"],
    limit=50,
)
```

Authentication: `Authorization: Bearer <MCP_API_TOKEN>` header (empty if not set).

`JobBoardClientProtocol` is a `@runtime_checkable` Protocol — any object with a matching `search_jobs` async method satisfies it. This makes injection and mocking in tests straightforward without needing `unittest.mock.patch`.

---

## 10. Observability

### Prometheus Metrics

| Metric | Type | Labels | What it measures |
|---|---|---|---|
| `career_agents_opp_job_fetch_duration_seconds` | Histogram | — | MCP fetch wall-clock time |
| `career_agents_opp_job_fetch_total` | Counter | `status` (success/error) | MCP fetch call outcomes |
| `career_agents_opp_score_duration_seconds` | Histogram | — | LLM enrichment wall-clock time |
| `career_agents_opp_score_total` | Counter | `status` (llm/fallback) | Enrichment call outcomes |
| `career_agents_opp_tailor_duration_seconds` | Histogram | — | CV tailoring wall-clock time |
| `career_agents_opp_tailor_total` | Counter | `status` (llm/fallback) | Tailoring call outcomes |
| `career_agents_opp_match_score` | Histogram | — | Score distribution across all listings |
| `career_agents_opp_high_match_count` | Histogram | — | High-match job count per run |

### OTel Spans

The main span `opportunity.execute` covers the full agent run. Key attributes:
- `session_id`, `user_id`, `correlation_id`
- `listings_fetched` — count returned by MCP
- `high_match_count` — listings with score ≥ 0.65

### Structured Log Events

| Event | When | Key fields |
|---|---|---|
| `opportunity.no_listings` | MCP returns empty | `target_role` |
| `opportunity.fetch_failed` | MCP HTTP error | `error` |
| `opportunity.scorer.enrich_failed` | LLM enrichment error | `error` |
| `opportunity.tailor.failed` | CV tailoring LLM error | `error` |
| `opportunity.mcp.job_fetch_failed` | Client-level MCP failure | `role`, `error` |
| `opportunity.completed` | Agent completes | `listings_fetched`, `high_match`, `cv_snippets`, `target_companies` |

---

## 11. Environment Variables

| Variable | Purpose | Default |
|---|---|---|
| `OPPORTUNITY_MODEL` | LLM model for scoring enrichment and CV tailoring | `claude-sonnet-4-6` |
| `JOB_BOARD_MCP_URL` | Base URL of the job-board MCP server | `http://localhost:8010` |
| `MCP_API_TOKEN` | Bearer token sent in `Authorization` header to MCP server | _(empty)_ |

---

## 12. Registration

Add to Celery worker startup after Redis and the event publisher are initialised:

```python
from agents.bus.publisher import EventPublisher
from agents.opportunity import OpportunityAgent
from agents.core.agent_registry import registry

registry.register(
    OpportunityAgent(event_publisher=EventPublisher(redis_client))
)
```

---

## 13. Test Coverage

`agents/src/agents/opportunity/tests/test_opportunity_agent.py` — **39 tests, all passing**.

| Category | Tests |
|---|---|
| `_parse_listing` — MCP response parsing | 3 |
| `_deterministic_score` — scoring dimensions | 7 |
| `_seniority_match` — seniority alignment | 5 |
| `JobScorer` — sorting, enrichment, fallback, markdown fencing | 6 |
| `CVTailor` — LLM success, fallback, empty list, cap at 5 | 6 |
| Target companies — grouping, inclusion thresholds | 3 |
| Match alerts — count cap, content | 2 |
| `OpportunityAgent` integration — full run, empty, MCP failure, events, CV trigger | 6 |
| Metadata — agent type and display name | 1 |

Run with:

```bash
# From agents/
poetry run pytest src/agents/opportunity/tests/ -v
```

---

## 14. Key Design Decisions

**Two-phase scoring instead of pure LLM scoring.** Scoring 50 job listings with an LLM per pipeline run would be expensive and slow. The deterministic phase provides instant, reproducible scores for all listings, and the LLM only adds narrative value for the top 10.

**Protocol-based MCP client.** Using `@runtime_checkable Protocol` instead of a concrete base class means test code can inject a plain `AsyncMock` without any patching boilerplate.

**Silent fallbacks at every LLM boundary.** Enrichment and tailoring both degrade gracefully — the agent never fails due to an LLM error. The user always receives scored jobs and at least placeholder CV snippets.

**Limit output payload size.** `scored_jobs` is capped at 20 entries in the output dict. The full list may contain 50+ listings; serialising all of them into the Celery result backend on every run wastes storage. High-match jobs are returned in full because the frontend needs them all for the alerts and CV tailoring UI.

**`agents/conftest.py` for test isolation.** `agents.config.agent_settings` validates required env vars at module import time via pydantic-settings. The root conftest sets dummy values before any test module is imported, so `pytest` collection works without a real `.env`. This also fixed the pre-existing coach test collection failure.

---

## 15. HTTP Endpoint

### `opportunity_controller.py` — API surface

| Path | Method | Status | Purpose |
|---|---|---|---|
| `/api/v1/opportunity/search` | POST | 202 | Dispatch a standalone opportunity search |
| `/api/v1/opportunity/alerts` | GET | 200 | Return cached match alerts from the session |

**`POST /api/v1/opportunity/search`** (202 Accepted)

```
Request body: { "role": "<optional override>", "location": "<optional override>" }

Response:
{
  "request_id": "<celery task id>",
  "session_id": "<user session id>",
  "stream_channel": "<redis pub/sub channel>",
  "search_query": "Senior Python Developer",
  "message": "Opportunity search started. Subscribe to the stream for live output."
}
```

The controller:
1. Loads/creates the user session via `mgr.get_or_create()`.
2. Builds a `UserProfileSnapshot` from the session profile, applying optional `role` and `location` overrides for this request only (the session profile is not mutated).
3. Constructs `OrchestratorTaskInput` with `forced_intent="opportunity_search"` to bypass LLM intent classification.
4. Dispatches via `TaskPublisher.dispatch_orchestration()` — fire and forget.
5. Returns `request_id` and `stream_channel` for SSE subscription.

**`GET /api/v1/opportunity/alerts`** (200 OK)

Returns cached match alerts and target companies from the session's plan context. Two lookup paths are tried in priority order:
1. `plan_context.snapshot["opportunity"]` — direct key for standalone search runs.
2. `plan_context.snapshot["agent_outputs"]["opportunity"]` — raw aggregated form used when the synthesiser falls back to unprocessed agent data.

Always returns 200 with empty lists when no cached data exists.

### Modified files

| Path | Change |
|---|---|
| `apps/api/src/endpoints/v1/opportunity_controller.py` | New controller (POST /search, GET /alerts) |
| `apps/api/src/endpoints/v1/__init__.py` | Registered `opportunity_router` |
