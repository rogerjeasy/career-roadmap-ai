# Networking & Outreach Agent — Implementation Summary

**Date:** 2026-05-06
**Status:** Complete
**Author:** rogerjeasy

---

## Overview

The Networking & Outreach Agent is the seventh L3 Specialist Agent to be implemented. Its role is the system's **relationship-building and visibility layer**: it analyses the user's LinkedIn profile, discovers relevant events and communities, drafts personalised outreach messages, and seeds a structured relationship pipeline — all from a single agent invocation triggered by the Master Orchestrator.

The agent operates in Phase 5 of the multi-agent DAG, running in parallel with the Learning Resource Agent and (future) Opportunity Agent. It consumes the prioritised skill gaps from the Gap Analysis Agent and the parsed CV from the CV Analysis Agent, then produces four complementary outputs that turn an abstract career plan into concrete human connections.

Three of the four pipeline steps involve an LLM or external MCP call. To keep the pipeline resilient to API outages, every LLM step has a deterministic fallback:

- `LinkedInReviewer` falls back to a heuristic score derived from the profile's completeness percentage.
- `OutreachDrafter` falls back to three pre-written template drafts with placeholder tokens.
- `EventFinder` falls back to an empty list (never crashes the pipeline).
- `RelationshipTracker` is pure computation with no I/O at all.

A key architecture decision is that steps 1 and 2 run **concurrently** via `asyncio.gather`, cutting wall-clock time by roughly 50% compared to sequential execution.

---

## Architecture Position

```
Client (Next.js)
      │  user message + CV upload
      ▼
FastAPI Gateway
      │  OrchestratorTaskInput
      ▼
Celery Worker — MasterOrchestrator (LangGraph)
      │
      ▼
  LangGraph Pipeline
  ┌──────────────────────────────────────────────────────────────┐
  │  Node 1: parse_intent                                        │
  │  Node 2: score_completeness  (ClarificationEngine)          │
  │  Node 3: build_dag           (TaskPlanner)                   │
  │                                                              │
  │  ┌── Phase 1 ──────────────────────────────────────────┐    │
  │  │  IntakeAgent  (NER profile building)                │    │
  │  └─────────────────────────────────────────────────────┘    │
  │         │ enriched UserProfile in plan_snapshot             │
  │         ▼                                                    │
  │  ┌── Phase 2 (parallel) ───────────────────────────────┐    │
  │  │  CVAgent              MarketIntelligenceAgent        │    │
  │  └─────────────────────────────────────────────────────┘    │
  │         │ plan_snapshot["cv_analysis"]                      │
  │         │ plan_snapshot["market_intelligence"]              │
  │         ▼                                                    │
  │  ┌── Phase 3 ──────────────────────────────────────────┐    │
  │  │  GapAgent                                           │    │
  │  │    RoleProfiler → SkillGapScorer → GapPrioritiser   │    │
  │  └─────────────────────────────────────────────────────┘    │
  │         │ plan_snapshot["gap_analysis"]["prioritised_gaps"] │
  │         ▼                                                    │
  │  ┌── Phase 4 ──────────────────────────────────────────┐    │
  │  │  RoadmapAgent                                       │    │
  │  │    PhaseGenerator → MilestoneGenerator              │    │
  │  │    → WeeklyPlanner → ResourceLinker                 │    │
  │  └─────────────────────────────────────────────────────┘    │
  │         │                                                    │
  │  ┌── Phase 5 (parallel) ───────────────────────────────┐    │
  │  │  LearningResourcesAgent                             │    │
  │  │                                                      │    │
  │  │  NetworkingAgent         ◄── THIS IMPLEMENTATION    │    │
  │  │    LinkedInReviewer ──┐  (asyncio.gather)           │    │
  │  │    EventFinder ────────┤                            │    │
  │  │    OutreachDrafter    ─┘  (sequential after 1+2)    │    │
  │  │    RelationshipTracker                               │    │
  │  │                                                      │    │
  │  │  OpportunityAgent                                    │    │
  │  └─────────────────────────────────────────────────────┘    │
  └──────────────────────────────────────────────────────────────┘
      │  AgentResult.output["outreach_drafts"]
      │  AgentResult.output["relationship_pipeline"]
      ▼
  Synthesizer Node → OrchestratorResult → SSE → Client
```

---

## Files Introduced

### New files

| Path | Role |
|---|---|
| `agents/src/agents/networking/models.py` | Pure domain types: `LinkedInProfileScore`, `CommunityEvent`, `OutreachDraft`, `RelationshipContact`, `RelationshipPipeline`, `NetworkingResult`, and four enums (`EventType`, `RecipientType`, `OutreachTone`, `ConnectionStatus`) |
| `agents/src/agents/networking/mcp_client.py` | `MCPClientProtocol` (Protocol), `HttpMCPClient` (JSON-RPC 2.0 over HTTP), `StubMCPClient` (realistic stubs for `linkedin_profile.profile.fetch` + `industry_news.events.search` across 6 topic areas) |
| `agents/src/agents/networking/linkedin_reviewer.py` | `LinkedInReviewer` — LLM-based profile scorer: 5 dimension scores + ATS score + strengths + improvements + keyword recommendations; heuristic fallback from `profile_completeness` |
| `agents/src/agents/networking/event_finder.py` | `EventFinder` — concurrent MCP fan-out across topics via `asyncio.gather`; deduplication by event_id; relevance ranking by skill-tag overlap |
| `agents/src/agents/networking/outreach_drafter.py` | `OutreachDrafter` — LLM (temperature=0.3) drafts 3 messages (mentor / peer / community_leader); pre-written template fallback with `[NAME]`, `[THEIR_PROJECT]`, `[YOUR_NAME]` placeholders |
| `agents/src/agents/networking/relationship_tracker.py` | `RelationshipTracker` — pure computation: seeds `RelationshipPipeline` from outreach drafts + uncovered high-priority gaps; generates prioritised next actions |
| `agents/src/agents/networking/networking_agent.py` | `NetworkingAgent` — extends `BaseAgent`, orchestrates the 4-step pipeline with concurrent steps 1+2 |
| `agents/src/agents/networking/__init__.py` | Public package surface: exports `NetworkingAgent` |
| `agents/src/agents/networking/tests/__init__.py` | Test package marker |
| `agents/src/agents/networking/tests/test_networking_agent.py` | 68 unit tests across all 5 components (no network, no LLM, no MCP calls) |

### Modified files

| Path | Change |
|---|---|
| `agents/src/agents/core/observability.py` | Added 8 networking-specific Prometheus metrics (`NET_*` prefix) |
| `agents/src/agents/config.py` | Added `mcp_linkedin_profile_url`, `mcp_industry_news_url`, `networking_model`, `networking_max_outreach_drafts`, `networking_max_events` |

---

## Pipeline Design

The agent runs four discrete steps. Steps 1 and 2 execute concurrently. Steps 3 and 4 are sequential. Every step emits a `STEP_PROGRESS` SSE event and increments `STEP_PROGRESS_TOTAL`. The entire pipeline is wrapped in a single OTel span `networking.execute`.

```
context.plan_snapshot["gap_analysis"]["prioritised_gaps"]   ← primary gap input
context.plan_snapshot["cv_analysis"]["parsed_cv"]           ← profile data for LinkedIn review
context.user_profile.target_role / current_role / location / skills
context.plan_snapshot["payload"]["linkedin_profile_url"]    ← optional LinkedIn URL
        │
        │  ┌─────────────────────────────────┐  ┌──────────────────────────────────┐
        │  │  Step 1 (async)                 │  │  Step 2 (async)                  │
        │  │  LinkedInReviewer.review()      │  │  EventFinder.find()              │
        │  │  MCP: linkedin_profile          │  │  MCP: industry_news              │
        │  │  + LLM (claude-haiku)           │  │  asyncio.gather over topics      │
        │  │  → LinkedInProfileScore | None  │  │  → list[CommunityEvent]          │
        │  └─────────────────────────────────┘  └──────────────────────────────────┘
        │               └────────── asyncio.gather ──────────┘
        │
        ▼  Step 3
  OutreachDrafter.draft()            ← LLM (claude-haiku, temperature=0.3)
        │  context: target_role, current_role, top_skill_gap, background_summary
        │  → list[OutreachDraft]     (3 drafts: mentor / peer / community_leader)
        │
        ▼  Step 4
  RelationshipTracker.build_pipeline()   ← pure computation
        │  inputs: prioritised_gaps, outreach_drafts, target_role
        │  → RelationshipPipeline
        │       .contacts          (one per draft + extra for uncovered critical gaps)
        │       .by_status         (all start as IDENTIFIED)
        │       .next_actions      (prioritised list of concrete steps)
        │       .outreach_priority_skills
        │
        ▼
  Serialise → AgentResult.output
```

---

## Component Details

### 1. LinkedInReviewer

Uses `claude-haiku` with `temperature=0.0` to produce a structured assessment:

```json
{
  "headline_score":    0.72,
  "summary_score":     0.65,
  "experience_score":  0.70,
  "skills_score":      0.60,
  "overall_score":     0.68,
  "ats_score":         0.55,
  "strengths":         ["Good technical headline", "Consistent career narrative"],
  "improvements":      ["Add target role to headline", "Quantify achievements with numbers"],
  "recommended_keywords": ["MLOps", "LLM", "RAG", "LangChain"]
}
```

**Score computation:**
- `overall_score = headline×0.20 + summary×0.25 + experience×0.30 + skills×0.15 + ats×0.10`
- All scores clamped to `[0.0, 1.0]`; LLM can provide `overall_score` directly or it is derived

**Fallback:** `_heuristic_review()` computes all scores from `profile_completeness` (a 0–1 field from the MCP LinkedIn server). Produces generic improvement suggestions containing the target role name.

**Input priority:**
1. LinkedIn profile data fetched from MCP `linkedin_profile.profile.fetch`
2. Parsed CV data from `plan_snapshot["cv_analysis"]["parsed_cv"]` (same shape)
3. `None` result if both are empty (pipeline continues without a review)

---

### 2. EventFinder

Builds a topic list from the target role + top 3 skills, then fans out concurrently:

```
topics = ["ml engineer", "python", "pytorch", "docker"]
         │
         └── asyncio.gather([
               mcp.call("industry_news", "events.search", {"topic": "ml engineer", "limit": 4}),
               mcp.call("industry_news", "events.search", {"topic": "python",      "limit": 4}),
               mcp.call("industry_news", "events.search", {"topic": "pytorch",     "limit": 4}),
               mcp.call("industry_news", "events.search", {"topic": "docker",      "limit": 4}),
             ])
```

After gathering, results are:
1. **Deduplicated** by `event_id`
2. **Relevance-scored**: `score += 0.4` if tag matches role, `+0.3` if tag matches a skill; capped at 1.0
3. **Sorted** descending by relevance
4. **Trimmed** to `networking_max_events` (default 10)

A single failing topic fetch does not abort the others — `asyncio.gather(..., return_exceptions=True)` is used, with failures logged as warnings.

**Event types supported:** `conference`, `meetup`, `online_community`, `webinar`, `newsletter`, `forum`, `hackathon`

**StubMCPClient catalog:** Covers `machine learning`, `python`, `ai`, `software engineering`, `mlops`, `data engineering`. Unknown topics receive two generic stubs (meetup + Slack community).

---

### 3. OutreachDrafter

Uses `claude-haiku` with `temperature=0.3` (slight creativity for authentic voice) to generate 3 message drafts targeting the user's top skill gap:

```json
[
  {
    "recipient_type": "mentor",
    "subject": "Building MLOps skills — 20 min of your insight?",
    "body": "Hi [NAME], your work on [THEIR_PROJECT] caught my attention...",
    "tone": "friendly",
    "platform": "LinkedIn",
    "target_skill": "MLOps",
    "call_to_action": "20-minute call to share your learning path",
    "estimated_response_rate": "medium"
  },
  { "recipient_type": "peer", ... },
  { "recipient_type": "community_leader", ... }
]
```

**Design decisions:**
- Body capped at 3–5 sentences by the system prompt — brevity increases response rates
- Uses `[NAME]`, `[THEIR_PROJECT]`, `[THEIR_ARTICLE]`, `[YOUR_NAME]` placeholder tokens — the agent never impersonates the user
- `estimated_response_rate` field gives the user a quick quality signal: `"high"` means brief + specific, `"low"` means cold + generic
- Three draft types are non-negotiable in the prompt: changing one draft's type doesn't remove the others

**Fallback:** `_template_drafts()` provides three pre-written drafts with the same placeholder convention. Subject lines include the target skill and role to remain specific.

---

### 4. RelationshipTracker

Pure computation — no async, no LLM, no MCP.

**Contact seeding logic:**

```python
# 1. One contact per outreach draft (draft already exists → reach out now)
for draft in outreach_drafts:
    contacts.append(RelationshipContact(
        role    = _infer_contact_role(draft.recipient_type, draft.target_skill, target_role),
        source  = {"mentor": "linkedin", "community_leader": "community", ...}[draft.recipient_type],
        status  = ConnectionStatus.IDENTIFIED,
        notes   = f"Draft ready — subject: '{draft.subject}'",
    ))

# 2. Extra contacts for high-severity gaps not covered by a draft
for gap in prioritised_gaps[:5]:
    if gap["requirement_name"] not in covered_skills:
        count = {"critical": 3, "high": 2, "medium": 1, "low": 1}[gap["severity"]]
        for _ in range(count):
            contacts.append(RelationshipContact(recipient_type=RecipientType.MENTOR, ...))
```

**Next actions** are generated in priority order:
1. Send outreach to all `IDENTIFIED` contacts using prepared drafts
2. Search LinkedIn for practitioners in the top skill area
3. Update LinkedIn profile before launching outreach
4. Join 1–2 online communities from the events list
5. Set a weekly networking block in the calendar

**Pipeline lifecycle:** All contacts start at `IDENTIFIED`. The API layer (not the agent) is responsible for advancing status to `REACHED_OUT → REPLIED → CONNECTED → MENTOR` as the user records activity.

---

## Agent Inputs

| Source | Field | Used by |
|---|---|---|
| `user_profile` | `target_role` | All steps |
| `user_profile` | `current_role` | OutreachDrafter context |
| `user_profile` | `skills` | EventFinder topics, background summary |
| `user_profile` | `location` | EventFinder MCP params |
| `plan_snapshot["gap_analysis"]` | `prioritised_gaps` | Top gap name, extra contacts |
| `plan_snapshot["cv_analysis"]` | `parsed_cv` | LinkedIn profile data, background summary |
| `plan_snapshot["payload"]` | `linkedin_profile_url` | LinkedInReviewer MCP fetch |

Up to `_MAX_TARGET_GAPS = 3` gaps are consumed from `prioritised_gaps` to keep MCP calls bounded.

---

## Agent Output

```json
{
  "target_role": "ML Engineer",
  "linkedin_review": {
    "headline_score": 0.72,
    "summary_score": 0.65,
    "experience_score": 0.70,
    "skills_score": 0.60,
    "overall_score": 0.68,
    "ats_score": 0.55,
    "strengths": ["Good technical headline"],
    "improvements": ["Add target role to headline", "Quantify achievements"],
    "recommended_keywords": ["MLOps", "LangChain", "RAG"]
  },
  "events_and_communities": [
    {
      "event_id": "evt-ml-001",
      "title": "ML Summit Zurich 2026",
      "event_type": "conference",
      "platform": "Eventbrite",
      "skill_tags": ["machine learning", "deep learning", "mlops"],
      "relevance_score": 0.8,
      "description": "Annual ML conference...",
      "url": "https://mlsummit.ch",
      "date": "2026-09-15",
      "location": "Zurich, Switzerland",
      "is_online": false,
      "source": "mcp_industry_news"
    }
  ],
  "outreach_drafts": [
    {
      "draft_id": "uuid-...",
      "recipient_type": "mentor",
      "subject": "Building MLOps skills — 20 min of your insight?",
      "body": "Hi [NAME], your work on [THEIR_PROJECT]...",
      "tone": "friendly",
      "platform": "LinkedIn",
      "target_skill": "MLOps",
      "call_to_action": "20-minute call to share your learning path",
      "estimated_response_rate": "medium"
    }
  ],
  "relationship_pipeline": {
    "total_contacts": 6,
    "by_status": { "identified": 6 },
    "contacts": [
      {
        "contact_id": "uuid-...",
        "role": "Senior ML Engineer — MLOps practitioner",
        "recipient_type": "mentor",
        "connection_status": "identified",
        "target_skill": "MLOps",
        "source": "linkedin",
        "name": null,
        "company": null,
        "notes": "Draft ready — subject: 'Building MLOps skills...'"
      }
    ],
    "next_actions": [
      "Send personalised outreach to 6 identified contact(s) using the prepared drafts...",
      "Search LinkedIn for 'MLOps' practitioners in your target companies...",
      "Update your LinkedIn profile based on the review suggestions...",
      "Join 1-2 relevant online communities from the events list...",
      "Set a weekly 30-minute networking block in your calendar..."
    ],
    "outreach_priority_skills": ["MLOps", "PyTorch", "System Design"]
  },
  "data_sources": ["llm_linkedin_reviewer", "llm_outreach_drafter", "mcp_industry_news", "mcp_linkedin_profile"],
  "generated_at": "2026-05-06T14:23:11.042Z",
  "processing_steps": ["linkedin_review", "event_finding", "outreach_drafting", "pipeline_building"]
}
```

`linkedin_review` is `null` when no CV or LinkedIn data is available. The pipeline never aborts because of a missing profile.

---

## Observability

### OTel Spans

| Span name | Attributes |
|---|---|
| `networking.execute` | `session_id`, `user_id`, `correlation_id`, `target_role`, `top_gap`, `gap_count`, `events_found`, `outreach_draft_count`, `contacts_tracked`, `linkedin_overall_score` |
| `networking.linkedin_review` | `correlation_id`, `target_role`, `overall_score`, `ats_score`, `duration_ms` |
| `networking.event_find` | `correlation_id`, `target_role`, `skill_count`, `topic_count`, `events_found`, `duration_ms` |
| `networking.outreach_draft` | `correlation_id`, `target_role`, `top_skill_gap`, `draft_count`, `duration_ms` |

### Prometheus Metrics

| Metric | Type | Purpose |
|---|---|---|
| `career_agents_net_linkedin_review_duration_seconds` | Histogram | Wall-clock time for LinkedIn review LLM calls |
| `career_agents_net_linkedin_review_total` | Counter | LLM vs fallback split (`status: llm\|fallback`) |
| `career_agents_net_event_fetch_duration_seconds` | Histogram | Wall-clock time for concurrent event discovery |
| `career_agents_net_event_fetch_total` | Counter | Success vs error split (`status: success\|error`) |
| `career_agents_net_outreach_draft_duration_seconds` | Histogram | Wall-clock time for outreach drafting LLM calls |
| `career_agents_net_outreach_draft_total` | Counter | LLM vs fallback split (`status: llm\|fallback`) |
| `career_agents_net_events_found` | Histogram | Events/communities discovered per run |
| `career_agents_net_contacts_tracked` | Histogram | Contacts seeded into pipeline per run |

### Structured Log Events

| Event key | When |
|---|---|
| `networking.linkedin_reviewed` | After each LinkedIn review (success or fallback) |
| `networking.linkedin_review_llm_failed` | When all LLM retries fail (fallback triggered) |
| `networking.linkedin_review_skipped` | When profile data is completely unavailable |
| `networking.events_found` | After event discovery (includes topic list and count) |
| `networking.event_fetch_failed` | When MCP call fails entirely |
| `networking.topic_fetch_failed` | When a single topic fetch fails within a fan-out |
| `networking.outreach_drafted` | After draft generation (success or fallback) |
| `networking.outreach_draft_llm_failed` | When all LLM retries fail (template fallback) |
| `networking.pipeline_built` | After relationship pipeline construction |
| `networking.completed` | End of full pipeline (scores, counts, correlation_id) |
| `networking.progress_emit_failed` | When SSE event publish fails (best-effort, never raises) |

---

## Configuration

All settings read from the environment (`.env` file) via `AgentSettings`:

| Setting | Default | Description |
|---|---|---|
| `MCP_LINKEDIN_PROFILE_URL` | `None` | HTTP endpoint for LinkedIn Profile MCP server. When unset, `StubMCPClient` is used automatically |
| `MCP_INDUSTRY_NEWS_URL` | `None` | HTTP endpoint for Industry News MCP server. When unset, `StubMCPClient` is used |
| `NETWORKING_MODEL` | `claude-haiku-4-5-20251001` | Claude model for LinkedIn review and outreach drafting |
| `NETWORKING_MAX_OUTREACH_DRAFTS` | `3` | Maximum drafts generated per run (1–10) |
| `NETWORKING_MAX_EVENTS` | `10` | Maximum events/communities returned per run (1–50) |

When both MCP URLs are absent the agent runs entirely without network calls (useful for development and CI). When only one URL is set, the other server falls back to `StubMCPClient` transparently.

---

## MCP Server Contracts

### `linkedin_profile` — `profile.fetch`

**Request params:**
```json
{ "linkedin_url": "https://linkedin.com/in/username" }
```

**Expected response:**
```json
{
  "headline": "Software Engineer | Python | FastAPI",
  "summary": "Backend engineer with 4 years...",
  "experience": [
    { "title": "Backend Engineer", "company": "TechCorp", "duration_months": 36, "description": "..." }
  ],
  "skills": ["Python", "FastAPI", "Docker"],
  "education": [{ "degree": "BSc Computer Science", "institution": "EPFL" }],
  "connections": 342,
  "profile_completeness": 0.72,
  "fetched_at": "2026-05-06T14:00:00Z"
}
```

### `industry_news` — `events.search`

**Request params:**
```json
{ "topic": "machine learning", "limit": 4, "location": "Zurich, Switzerland" }
```

**Expected response:**
```json
{
  "events": [
    {
      "id": "evt-ml-001",
      "title": "ML Summit Zurich 2026",
      "type": "conference",
      "platform": "Eventbrite",
      "skill_tags": ["machine learning", "deep learning"],
      "description": "Annual ML conference...",
      "url": "https://mlsummit.ch",
      "date": "2026-09-15",
      "location": "Zurich, Switzerland",
      "is_online": false
    }
  ],
  "total_count": 4,
  "fetched_at": "2026-05-06T14:00:00Z"
}
```

---

## Design Decisions

### Why concurrency for steps 1 and 2?

LinkedIn profile review and event discovery are completely independent — neither result feeds the other. Running them concurrently via `asyncio.gather` saves the full wall-clock time of whichever finishes first. In a typical scenario where each takes 1–3 seconds, this reduces step 1+2 latency from ~5 seconds to ~3 seconds.

### Why placeholder tokens instead of personalised content?

Generating fully personalised messages would require knowing the specific recipient's name, their recent projects, and their publications. The agent does not have access to this data at generation time. Using `[THEIR_PROJECT]` and `[NAME]` tokens is honest with the user: it makes clear that the draft is a starting point requiring personal research and customisation before sending. This aligns with the architecture principle: *human-approved actions* — outreach drafts require user review and explicit send action.

### Why heuristic LinkedIn review fallback rather than skipping?

Returning a score of `null` when the LLM fails creates a useless output and a confusing UX gap in the frontend. A heuristic review derived from `profile_completeness` still provides genuine value: it gives a baseline score, surfaces generic but real improvements, and adds the target role as a recommended keyword. Falling back to nothing would penalise users who happen to invoke the agent during an LLM outage.

### Why are all contacts seeded at `IDENTIFIED` status?

The relationship pipeline is designed to be **mutable over time** — it is not a one-shot list. Setting all contacts to `IDENTIFIED` at generation time means the API layer can let the user advance status incrementally (REACHED_OUT → REPLIED → CONNECTED → MENTOR) as they actually send messages and receive responses. This tracks real-world relationship progress rather than making optimistic assumptions about which outreach will succeed.

### Why `_MAX_TARGET_GAPS = 3`?

Each gap triggers at least one contact in the pipeline and influences the top_skill_gap passed to the outreach drafter. Consuming all gaps (which can be 8–15) would:
- Produce redundant drafts that the user cannot reasonably personalise
- Generate an overwhelming pipeline of contacts
- Increase LLM token usage without proportional benefit

Three gaps maps to the 3-draft structure of the outreach drafter and produces a focused, actionable output.

---

## Testing

### Test coverage: 68 tests across 5 test classes

```
tests/test_networking_agent.py
├── TestBuildScore              (5 tests)   — _build_score helper: clamping, defaults, computation
├── TestHeuristicReview         (4 tests)   — _heuristic_review: target role, completeness scaling
├── TestLinkedInReviewerAsync   (3 tests)   — LLM success, LLM failure fallback, non-dict JSON
├── TestBuildTopics             (4 tests)   — topic deduplication, role-first order, skill limit
├── TestComputeRelevance        (4 tests)   — exact match, skill match, no match, bounded score
├── TestDeduplicateAndRank      (4 tests)   — dedup, sort order, missing id skip, invalid type
├── TestEventFinderAsync        (5 tests)   — results, max_events, MCP failure, dedup, location param
├── TestBuildDraft              (5 tests)   — valid types, fallback enum, missing fields, UUID id
├── TestTemplateDrafts          (5 tests)   — count, recipient types, skill in subject, unique ids
├── TestOutreachDrafterAsync    (4 tests)   — LLM success, LLM failure, max_drafts, non-list JSON
├── TestInferContactRole        (3 tests)   — mentor/peer/community descriptions
├── TestCountByStatus           (2 tests)   — correct counts, empty input
├── TestExtractPrioritySkills   (3 tests)   — ordered extraction, empty, missing name skip
├── TestGenerateNextActions     (2 tests)   — non-empty list, identified count in action text
├── TestRelationshipTracker     (6 tests)   — draft seeding, all IDENTIFIED, status sum, priority skills, empty input, uncovered gaps
├── TestResolveTopGap           (3 tests)   — gap name, skill fallback, role fallback
├── TestBuildBackgroundSummary  (4 tests)   — current role, skills, experience, empty defaults
├── TestCollectDataSources      (5 tests)   — linkedin present/absent, llm sources, events, sorted
├── TestSerialisers             (4 tests)   — all keys for each output type, enum serialisation
└── TestNetworkingAgent        (13 tests)   — type, display_name, output keys, 4 steps, progress events,
                                             linkedin None, gap snapshot, BaseAgent.run() happy path + failure
```

All tests run without network access, Anthropic API keys, or Redis. LLM calls are replaced by `AsyncMock`; MCP calls are served by `StubMCPClient` or explicit `AsyncMock`.

---

## Registration

Register the agent at Celery worker startup alongside the other L3 agents:

```python
from agents.networking import NetworkingAgent
from agents.core.agent_registry import registry
from agents.core.message_bus import EventPublisher

registry.register(
    NetworkingAgent(event_publisher=EventPublisher(redis_client))
)
```

With MCP servers configured:

```python
from agents.networking.mcp_client import HttpMCPClient

mcp = HttpMCPClient({
    "linkedin_profile": "http://mcp-linkedin-profile:3004",
    "industry_news":    "http://mcp-industry-news:3007",
}, timeout_seconds=30.0)

registry.register(
    NetworkingAgent(
        mcp_client=mcp,
        event_publisher=EventPublisher(redis_client),
        max_events=agent_settings.networking_max_events,
    )
)
```

---

## What Comes Next

The following L3 agents remain to be implemented in DAG order:

| Agent | Phase | Key inputs | Key outputs |
|---|---|---|---|
| `OpportunityAgent` | 5 (parallel) | `prioritised_gaps`, `parsed_cv`, `market_intelligence` | job match scores, CV tailoring suggestions, target company list |
| `CoachAgent` | Always-on | Full plan context + conversation history | ad-hoc career Q&A, interview prep, timeline challenge |
| `ProgressAgent` | Periodic | Weekly scorecard, roadmap, market signals | drift detection, plan adaptations, habit streak analysis |
