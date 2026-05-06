# Learning Resource Agent — Implementation Summary

**Date:** 2026-05-06
**Status:** Complete
**Author:** rogerjeasy

---

## Overview

The Learning Resource Agent is the fifth L3 Specialist Agent to be implemented. Its role is the system's **structured course discovery and embedding layer**: it receives the prioritised skill gaps produced by the Gap Analysis Agent, queries the MCP Course Catalogue for matching learning materials, ranks every resource by a four-factor weighted score (relevance, quality, cost-value, and level fit), and groups the top resources into roadmap phase embeddings so the Roadmap Generation Agent can embed concrete, actionable learning paths directly into each milestone.

By running in Phase 5 of the multi-agent DAG (alongside Networking and Opportunity), the Learning Resource Agent transforms the abstract gap list into a time-budgeted, cost-aware curriculum — meaning users always receive a specific course or book they can open within 24 hours, not a generic instruction to "learn Python".

The entire ranking pipeline is **LLM-free**: relevance scoring uses Jaccard token overlap, ranking uses deterministic weighted arithmetic, and phase assignment uses a simple priority-rank boundary rule. This keeps the agent fast, testable without mocking, and resistant to LLM quota or latency issues.

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
  │  │  LearningResourcesAgent  ◄── THIS IMPLEMENTATION    │    │
  │  │    CourseFetcher → ResourceMatcher                   │    │
  │  │    → ResourceRanker → ResourceEmbedder              │    │
  │  │                                                      │    │
  │  │  NetworkingAgent     OpportunityAgent                │    │
  │  └─────────────────────────────────────────────────────┘    │
  └──────────────────────────────────────────────────────────────┘
      │  AgentResult.output["roadmap_embeddings"]
      │  AgentResult.output["top_resources"]
      ▼
  Synthesizer Node → OrchestratorResult → SSE → Client
```

---

## Files Introduced

### New files

| Path | Role |
|---|---|
| `agents/src/agents/learning_resources/models.py` | Pure domain types: `LearningResource`, `SkillResourceBundle`, `RoadmapPhaseEmbedding`, `LearningResourcesResult`, `ResourceLevel`, `ResourceFormat` |
| `agents/src/agents/learning_resources/mcp_client.py` | `MCPClientProtocol` (Protocol), `HttpMCPClient` (JSON-RPC 2.0 over HTTP), `StubMCPClient` (realistic stub for 12 skills + generic fallback) |
| `agents/src/agents/learning_resources/course_fetcher.py` | `CourseFetcher` — concurrent MCP course catalog queries via `asyncio.gather`; per-gap failure tolerance |
| `agents/src/agents/learning_resources/resource_matcher.py` | `ResourceMatcher` — Jaccard token-overlap relevance scoring; pure computation |
| `agents/src/agents/learning_resources/resource_ranker.py` | `ResourceRanker` — four-factor weighted scoring; global top-k deduplication |
| `agents/src/agents/learning_resources/resource_embedder.py` | `ResourceEmbedder` — phase assignment by gap priority rank; learning-hour estimation |
| `agents/src/agents/learning_resources/learning_agent.py` | `LearningAgent` — extends `BaseAgent`, orchestrates the 4-step pipeline |
| `agents/src/agents/learning_resources/__init__.py` | Public package surface: exports `LearningAgent` |
| `agents/src/agents/learning_resources/prompts/learning_system.txt` | System prompt stub for any future LLM-based summarisation step |
| `agents/src/agents/learning_resources/tests/__init__.py` | Test package marker |
| `agents/src/agents/learning_resources/tests/test_learning_agent.py` | 40+ unit tests (no network, no LLM, no MCP calls) |

### Modified files

| Path | Change |
|---|---|
| `agents/src/agents/core/observability.py` | Added 6 learning-resources-specific Prometheus metrics (`LR_*` prefix) |
| `agents/src/agents/config.py` | Added `mcp_course_catalog_url` and `learning_resources_max_gaps` settings |

---

## Pipeline Design

The agent runs four discrete steps in sequence. Each step emits a `STEP_PROGRESS` SSE event and increments a `STEP_PROGRESS_TOTAL` Prometheus counter. The entire pipeline is wrapped in a single OTel span `learning_resources.execute`.

```
context.plan_snapshot["gap_analysis"]["prioritised_gaps"]   ← primary input
context.user_profile.skills                                 ← fallback when no gap analysis
context.user_profile.target_role
        │
        │  gaps[:max_gaps]   (default 10; configurable via learning_resources_max_gaps)
        ▼  Step 1
  CourseFetcher.fetch()              ← asyncio.gather over MCP course.search calls
        │  dict[skill_name → list[raw_course_dict]]
        │  (tech_skill + certification dimensions only; soft_skill → empty list)
        ▼  Step 2
  ResourceMatcher.match()            ← pure computation, Jaccard relevance scoring
        │  list[SkillResourceBundle]
        │  (per-gap: resources scored by relevance, sorted, trimmed to top_k)
        ▼  Step 3
  ResourceRanker.rank()              ← pure computation, weighted multi-factor scoring
        │  (ranked_bundles, top_resources)
        │  overall_score = 0.35×relevance + 0.30×quality + 0.20×cost_value + 0.15×level_fit
        ▼  Step 4
  ResourceEmbedder.embed()           ← pure computation, phase grouping + hour estimation
        │  list[RoadmapPhaseEmbedding]
        │  Phase 1: critical gaps OR rank ≤ 3
        │  Phase 2: high gaps   OR rank ≤ 7
        │  Phase 3: remaining gaps
        ▼
  AgentResult.output
```

**LLM budget per run:** zero. All four steps are deterministic. The `prompts/learning_system.txt` file exists for a future optional LLM-based narrative summarisation step.

---

## Component Design

### `models.py` — Domain types

Six types (two enums, four frozen dataclasses) that carry structured data through the pipeline. All are **internal to the `learning_resources` package**; external code imports only `LearningAgent` via `__init__.py`.

```python
class ResourceLevel(str, Enum):
    BEGINNER     = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED     = "advanced"
    EXPERT       = "expert"

class ResourceFormat(str, Enum):
    COURSE        = "course"
    VIDEO         = "video"
    BOOK          = "book"
    ARTICLE       = "article"
    PROJECT       = "project"
    WORKSHOP      = "workshop"
    CERTIFICATION = "certification"

@dataclass(frozen=True)
class LearningResource:
    resource_id:    str
    title:          str
    provider:       str             # Coursera, Udemy, edX, YouTube, O'Reilly …
    skill_tags:     list[str]       # normalised lowercase keyword tokens
    level:          ResourceLevel
    format:         ResourceFormat
    duration_hours: float | None
    cost_usd:       float           # 0.0 = free
    quality_score:  float           # 0–1 provider reputation × review aggregate
    relevance_score:float           # 0–1 computed by ResourceMatcher
    overall_score:  float           # 0–1 weighted ranking score from ResourceRanker
    is_free:        bool
    url:            str | None
    description:    str
    freshness_year: int | None      # year of last content update
    source:         str             # "mcp_course_catalog" | "stub"

@dataclass(frozen=True)
class SkillResourceBundle:
    skill_gap:         str    # requirement_name from GapAgent
    gap_severity:      str    # critical | high | medium | low
    gap_priority_rank: int    # 1 = highest (passed from GapAgent)
    resources:         list[LearningResource]
    # computed property: .top_resource → resources[0] | None

@dataclass(frozen=True)
class RoadmapPhaseEmbedding:
    phase_number:    int
    phase_title:     str
    skill_gaps:      list[str]
    resources:       list[LearningResource]
    estimated_hours: float

@dataclass
class LearningResourcesResult:
    target_role:           str
    skill_recommendations: list[SkillResourceBundle]
    top_resources:         list[LearningResource]
    roadmap_embeddings:    list[RoadmapPhaseEmbedding]
    total_resources_found: int
    total_learning_hours:  float
    data_sources:          list[str]
    processing_steps:      list[str]
    fetched_at:            datetime
```

---

### `mcp_client.py` — MCP transport layer

Provides three artefacts that follow the same structural Protocol pattern used by `market_intelligence/mcp_client.py`:

**`MCPClientProtocol`** (runtime-checkable `Protocol`):

```python
async def call(
    self,
    server_id: str,
    tool: str,
    params: dict[str, Any],
    *,
    correlation_id: str = "",
) -> dict[str, Any]: ...
```

Agents depend only on this protocol. `CourseFetcher` receives it via constructor injection and never imports a concrete class.

**`HttpMCPClient`** (production):
- JSON-RPC 2.0 over HTTP using `httpx.AsyncClient`
- Accepts a server registry dict: `{"course_catalog": "http://mcp-course-catalog:3002"}`
- Sets `X-Correlation-ID` header on every request for end-to-end tracing
- Raises `RuntimeError` on JSON-RPC error responses (`"error"` key in response body)
- Logs `mcp_lr.call_ok` with `latency_ms` on success; `mcp_lr.call_failed` on any exception

**`StubMCPClient`** (development / tests):
- Returns realistic course data for 12 skill areas: Python, Kubernetes, Docker, PyTorch, Machine Learning, Deep Learning, AWS, FastAPI, LangChain, MLOps, Terraform, SQL, System Design, Kafka, React
- For unknown skills, generates three generic placeholder courses (beginner / intermediate / advanced)
- All stub courses include realistic `quality_score`, `duration_hours`, `cost_usd`, `url`, and `freshness_year`

**Auto-selection logic in `learning_agent.py`:**

```python
def _build_mcp_client() -> MCPClientProtocol:
    if agent_settings.mcp_course_catalog_url:
        return HttpMCPClient(
            {"course_catalog": agent_settings.mcp_course_catalog_url},
            timeout_seconds=agent_settings.mcp_timeout_seconds,
        )
    return StubMCPClient()
```

No environment variable → `StubMCPClient`. One environment variable → `HttpMCPClient`. The agent works end-to-end in development with no external services.

---

### `course_fetcher.py` — Concurrent MCP queries

`CourseFetcher.fetch()` calls `course_catalog / course.search` for every qualifying gap concurrently using `asyncio.gather`.

**Dimension filter:** only `tech_skill` and `certification` gaps are searched. `soft_skill`, `portfolio`, and `keyword` gaps receive an empty list immediately — there is no meaningful course search for "leadership" or "ATS keywords".

```python
_SKILL_DIMENSIONS = frozenset({"tech_skill", "certification"})
searchable = [g for g in gaps if g.get("dimension") in _SKILL_DIMENSIONS]
```

**Level inference:** the fetcher derives the appropriate course level from the gap's `current_level` and `severity` before calling MCP, so courses returned are immediately relevant:

| Current level | Severity | Search level |
|---|---|---|
| `advanced` or `expert` | any | `advanced` |
| `intermediate` | `medium` or `low` | `advanced` |
| `intermediate` | `high` or `critical` | `intermediate` |
| `beginner` | any | `intermediate` (level up) |
| absent | `critical` | `beginner` (start from scratch) |
| absent | any other | `intermediate` |

**Failure tolerance:** the `asyncio.gather` call returns one result per skill. If a single MCP call raises, that skill's entry in the output dict is an empty list — the pipeline continues with the remaining skills. The failure is logged as `course_fetcher.single_fetch_failed` at `WARNING` level.

**Observability:**
- `LR_COURSE_FETCH_DURATION` histogram (seconds) — one observation per `_fetch_one` call
- `LR_COURSE_FETCH_TOTAL` counter labelled `status=success|error` — incremented in the `finally` block

---

### `resource_matcher.py` — Relevance scoring

`ResourceMatcher.match()` converts raw MCP course dicts into typed `LearningResource` objects and assigns each a `relevance_score` based on how well its `skill_tags` overlap with the gap's keyword tokens.

**Tokenisation (`_tokenise`):**

Splits on any combination of spaces, hyphens, underscores, slashes, plus signs, commas, and periods, lowercases, and drops single-character tokens. This means:

```
"deep-learning"  → {"deep", "learning"}
"PyTorch"        → {"pytorch"}
"CI/CD"          → {"ci", "cd"}
"machine learning" → {"machine", "learning"}
```

**Relevance score (`_compute_relevance`):**

Jaccard similarity between the set of gap keyword tokens and the union of all course skill_tag tokens:

```
relevance = |gap_keywords ∩ tag_keywords| / |gap_keywords ∪ tag_keywords|
```

When either side is empty, a neutral `0.5` is returned rather than `0.0` — this prevents courses with minimal metadata from being systematically penalised before the ranker can evaluate their `quality_score`.

**Output:**
- One `SkillResourceBundle` per gap, resources sorted descending by `relevance_score`
- Trimmed to `top_k` resources (default 5) before being passed to the ranker
- `overall_score` is set to `0.0` at this stage — the ranker fills it in

---

### `resource_ranker.py` — Weighted multi-factor scoring

`ResourceRanker.rank()` applies a four-factor weighted score to every resource in every bundle. Because `LearningResource` is a frozen dataclass, a new instance is created for each scored resource with `overall_score` populated.

**Scoring formula:**

```
overall_score = 0.35 × relevance_score
              + 0.30 × quality_score
              + 0.20 × cost_value_score
              + 0.15 × level_fit_score
```

Weight rationale:

| Factor | Weight | Rationale |
|---|---|---|
| `relevance_score` | 0.35 | Most important: resource must match the skill being closed |
| `quality_score` | 0.30 | Provider reputation and review aggregate from MCP metadata |
| `cost_value_score` | 0.20 | Free resources are strongly preferred; cost degrades linearly |
| `level_fit_score` | 0.15 | Level should match the gap's severity to avoid under/over-shooting |

**Cost value score:**

| Cost range | Score |
|---|---|
| Free (0.0) | 1.00 |
| $0.01–$20 | 0.85 |
| $20.01–$50 | 0.70 |
| $50.01–$100 | 0.55 |
| $100.01+ | 0.40 |

**Level fit score (`_LEVEL_FIT` lookup table):**

| Gap severity | Resource level | Score |
|---|---|---|
| `critical` | beginner | 0.95 — start from scratch is correct |
| `critical` | intermediate | 0.80 |
| `critical` | advanced | 0.55 — too advanced for a critical gap |
| `high` | intermediate | 1.00 — best match |
| `high` | advanced | 0.85 |
| `medium` | advanced | 1.00 — best match for refinement |
| `low` | expert | 1.00 |
| unknown severity | any | 0.70 — neutral fallback |

**Global top-k deduplication:**

After scoring all bundles, the ranker collects every resource, sorts by `overall_score` descending, and deduplicates by `resource_id` to produce a global top-10 list. A resource that appears in three different gap bundles (e.g. a Python fundamentals course relevant to Python, Machine Learning, and MLOps gaps) appears only once in `top_resources`.

```python
seen: set[str] = set()
unique: list[LearningResource] = []
for r in sorted(all_resources, key=lambda x: x.overall_score, reverse=True):
    if r.resource_id not in seen:
        seen.add(r.resource_id)
        unique.append(r)
top_resources = unique[:self._top_global]
```

---

### `resource_embedder.py` — Phase grouping

`ResourceEmbedder.embed()` groups the ranked bundles into roadmap phase embeddings using a two-dimensional assignment rule:

**Phase assignment (`_assign_phase`):**

```python
def _assign_phase(priority_rank: int, severity: str) -> int:
    if severity == "critical" or priority_rank <= 3:
        return 1   # Foundation & Critical Gaps
    if severity == "high" or priority_rank <= 7:
        return 2   # Core Skill Development
    return 3       # Enhancement & Specialisation
```

Severity always takes precedence over rank. A `critical` gap at rank 8 still lands in Phase 1 — it must be addressed first regardless of how many other gaps precede it.

**Phase titles:**

| Phase | Title |
|---|---|
| 1 | Foundation & Critical Gaps |
| 2 | Core Skill Development |
| 3 | Enhancement & Specialisation |

**Resource collection per phase:** resources from all bundles in the same phase are merged, deduplicated by `resource_id`, sorted by `overall_score` descending, and trimmed to `resources_per_phase` (default 5). This means the user sees the best 5 resources across all critical gaps in Phase 1 — not 5 resources per gap, which would be overwhelming.

**Hour estimation:**

```python
estimated_hours = sum(
    r.duration_hours if r.duration_hours is not None else 20.0
    for r in phase_resources
)
```

The 20-hour fallback for resources without a stated duration is a conservative estimate based on the median course length in the stub catalog. This ensures `total_learning_hours` is always a positive, meaningful number even when MCP returns sparse metadata.

**Empty phase skipping:** phases with no bundles are omitted from the output list entirely. If all gaps are critical, the output contains only one `RoadmapPhaseEmbedding` (Phase 1).

---

### `learning_agent.py` — Main agent

`LearningAgent` extends `BaseAgent` and implements `_execute(context)` as the 4-step sequential pipeline.

**Input resolution:**

```python
gap_analysis = context.plan_snapshot.get("gap_analysis", {})
gaps = gap_analysis.get("prioritised_gaps", [])

# Fallback when agent is run standalone (no prior gap_analysis in plan_snapshot)
if not gaps:
    gaps = [
        {
            "requirement_name": skill,
            "dimension": "tech_skill",
            "severity": "medium",
            "priority_rank": i + 1,
            "current_level": None,
            "required_level": "intermediate",
            "is_required": True,
            "diff_score": 0.5,
        }
        for i, skill in enumerate(context.user_profile.skills)
    ]

gaps = gaps[:self._max_gaps]  # default 10
```

**Constructor — dependency injection:**

```python
LearningAgent(
    course_fetcher=CourseFetcher(mcp_client),      # injectable for tests
    resource_matcher=ResourceMatcher(),             # injectable for tests
    resource_ranker=ResourceRanker(),               # injectable for tests
    resource_embedder=ResourceEmbedder(),           # injectable for tests
    event_publisher=EventPublisher(redis),          # None → events silently skipped
    mcp_client=StubMCPClient(),                    # overrides auto-build when set
    max_gaps=10,                                    # configurable cap
)
```

**Output shape (`AgentResult.output`):**

```json
{
  "target_role": "ML Engineer",
  "skill_recommendations": [
    {
      "skill_gap": "Python",
      "gap_severity": "high",
      "gap_priority_rank": 1,
      "resources": [
        {
          "resource_id": "py-001",
          "title": "Python for Everybody Specialisation",
          "provider": "Coursera / UMich",
          "skill_tags": ["python", "programming", "data"],
          "level": "beginner",
          "format": "course",
          "duration_hours": 35.0,
          "cost_usd": 0.0,
          "is_free": true,
          "quality_score": 0.93,
          "relevance_score": 1.0,
          "overall_score": 0.836,
          "url": "https://coursera.org/specializations/python",
          "description": "Foundational Python programming from scratch.",
          "freshness_year": 2024,
          "source": "stub"
        }
      ],
      "top_resource": { "..." : "..." }
    }
  ],
  "top_resources": [
    { "resource_id": "py-001", "overall_score": 0.836, "..." : "..." }
  ],
  "roadmap_embeddings": [
    {
      "phase_number": 1,
      "phase_title": "Foundation & Critical Gaps",
      "skill_gaps": ["Machine Learning"],
      "resources": [ { "..." : "..." } ],
      "estimated_hours": 60.0
    },
    {
      "phase_number": 2,
      "phase_title": "Core Skill Development",
      "skill_gaps": ["Python"],
      "resources": [ { "..." : "..." } ],
      "estimated_hours": 35.0
    },
    {
      "phase_number": 3,
      "phase_title": "Enhancement & Specialisation",
      "skill_gaps": ["Docker"],
      "resources": [ { "..." : "..." } ],
      "estimated_hours": 29.0
    }
  ],
  "total_resources_found": 9,
  "total_learning_hours": 124.0,
  "data_sources": ["Coursera / UMich", "KodeKloud", "Udemy"],
  "fetched_at": "2026-05-06T08:50:00Z",
  "processing_steps": [
    "course_fetching",
    "resource_matching",
    "resource_ranking",
    "resource_embedding"
  ]
}
```

**Registration at worker startup:**

```python
from agents.learning_resources import LearningAgent
from agents.core.agent_registry import registry

registry.register(LearningAgent(event_publisher=EventPublisher(redis_client)))
```

---

## Config Keys Added

| Key | Type | Default | Description |
|---|---|---|---|
| `mcp_course_catalog_url` | `str \| None` | `None` | URL of the MCP Course Catalogue server. When absent, `StubMCPClient` is used automatically. |
| `learning_resources_max_gaps` | `int` | `10` | Maximum number of prioritised gaps to fetch courses for per run. Prevents excessive MCP calls when gap lists are long. |

---

## Prometheus Metrics Added

| Metric name | Type | Labels | What it tracks |
|---|---|---|---|
| `career_agents_lr_course_fetch_duration_seconds` | Histogram | — | Wall-clock time for a single MCP course catalog fetch call |
| `career_agents_lr_course_fetch_total` | Counter | `status` (success \| error) | Total MCP fetch call outcomes per skill gap |
| `career_agents_lr_resources_matched` | Histogram | — | Total resources matched across all gaps per run |
| `career_agents_lr_top_resource_score` | Histogram | — | `overall_score` of the highest-ranked resource per run |
| `career_agents_lr_phase_count` | Histogram | — | Number of roadmap phase embeddings produced per run |
| `career_agents_lr_total_learning_hours` | Histogram | — | Aggregate estimated learning hours per run |

---

## Test Coverage

The test file (`tests/test_learning_agent.py`) contains **40+ unit tests** organised into 10 test classes. No network calls, no Anthropic API, no MCP server, no pytest-asyncio fixtures beyond `@pytest.mark.asyncio`.

| Class | What is tested |
|---|---|
| `TestTokenise` | Splits on spaces, hyphens, underscores; filters single chars; normalises case |
| `TestComputeRelevance` | Exact match → 1.0; partial match; no overlap → 0.0; empty gap keywords → neutral 0.5; empty tags → neutral 0.5 |
| `TestResourceMatcher` | One bundle per gap; bundles sorted by priority rank; empty courses → empty bundle; `top_k` respected; `overall_score` is 0.0 at this stage |
| `TestCostValueScore` | Free → 1.0; cheap → 0.85; mid-range → 0.70; expensive → 0.40 |
| `TestLevelFitScore` | Critical + beginner → 0.95; high + intermediate → 1.00; medium + advanced → 1.00; unknown severity → 0.70 fallback |
| `TestResourceRanker` | Scoring increases overall_score; free > paid when quality is equal; resources sorted descending; deduplication by resource_id; `top_global` respected |
| `TestAssignPhase` | Critical → phase 1; rank ≤ 3 → phase 1; rank 4 + high → phase 2; rank 8 + medium → phase 3 |
| `TestEstimateHours` | Sum of known durations; fallback 20h for None; mixed |
| `TestResourceEmbedder` | Produces ≤ 3 phases; empty phases skipped; phase skill_gaps correct; `resources_per_phase` respected; intra-phase deduplication by resource_id |
| `TestCourseFetcher` | Returns courses for known skill; `soft_skill` dimension → empty list without MCP call; single fetch failure → empty list, other skills continue; `asyncio.gather` concurrency verified |
| `TestLearningAgentRun` | COMPLETED status; all required output keys present; all 4 processing steps present; agent type is `LEARNING_RESOURCES`; 4+ progress events emitted; progress emit failure does not propagate; `max_gaps` respected; fallback to `user_profile.skills` when no gap_analysis; `overall_score` values in `[0, 1]`; phase embeddings have non-empty titles and valid phase numbers; total MCP failure → COMPLETED with 0 resources |
| `TestSerialisers` | `_serialise_resource` has all expected keys; level field is string not enum; bundle has `top_resource`; empty bundle gives `null` top_resource |
| `TestHelpers` | `_resolve_gaps` returns gap_analysis when present; fallback uses profile skills with `severity=medium`; `_collect_data_sources` deduplicates providers |

Run the full test suite:

```bash
cd agents
poetry run pytest src/agents/learning_resources/tests/ -v
```

---

## Data Flow to Downstream Agents

| Downstream agent | Fields consumed from `plan_snapshot["learning_resources"]` |
|---|---|
| `RoadmapAgent` | `roadmap_embeddings[*].resources` (embedded into milestone resource links), `roadmap_embeddings[*].estimated_hours` (calibrates phase duration) |
| `CoachAgent` | `top_resources` (surfaces recommended courses in coaching conversation), `skill_recommendations[*]` (answers "what should I study next?") |
| `ProgressAgent` | `total_learning_hours` (tracks curriculum completion percentage against plan), `roadmap_embeddings[*].skill_gaps` (monitors which curriculum areas are on-track) |

All downstream agents access this data via `context.plan_snapshot["learning_resources"]`.

---

## Design Principles Applied

| Principle | How it manifests |
|---|---|
| **Low coupling** | All 4 pipeline components (`CourseFetcher`, `ResourceMatcher`, `ResourceRanker`, `ResourceEmbedder`) are constructor-injected into `LearningAgent`; no component knows about any other or about the agent framework |
| **High cohesion** | All learning-resource logic lives inside `agents.learning_resources`; the public interface is `LearningAgent` only |
| **LLM-free pipeline** | Every step is pure computation or an MCP call — no LLM tokens consumed per run; ranking is deterministic, reproducible, and observable |
| **MCP graceful degradation** | Individual skill fetch failures downgrade to empty lists via `asyncio.gather(return_exceptions=True)`; the pipeline always produces a result even if every MCP call fails |
| **Dimension-aware filtering** | Only `tech_skill` and `certification` gaps trigger MCP queries; soft skills and portfolio gaps are skipped at the fetcher level — no wasted calls, no irrelevant courses returned |
| **Separation of concerns** | `CourseFetcher` only fetches; `ResourceMatcher` only scores relevance; `ResourceRanker` only weighs and ranks; `ResourceEmbedder` only groups — none overlap in responsibility |
| **Input independence** | Reads from `plan_snapshot["gap_analysis"]["prioritised_gaps"]` not from `agents.gap_analysis` — zero compile-time coupling to the Gap Analysis Agent's internals |
| **Fallback for standalone runs** | When `gap_analysis` is absent from `plan_snapshot`, the agent synthesises gaps from `user_profile.skills` — making it usable in isolation for curriculum queries without requiring the full DAG to have run |
| **Deterministic test surface** | All four components are testable without mocking because they are pure computation; only `CourseFetcher` requires a mock, and `StubMCPClient` covers that without needing `AsyncMock` for most test cases |
| **Observability** | OTel span per pipeline run, 6 Prometheus metrics covering MCP latency, match counts, score distribution, phase count, and learning hours; `STEP_PROGRESS` SSE events at each of the 4 steps so the client UI shows live progress |
| **Cost transparency** | `cost_usd` and `is_free` are first-class fields on every resource; the `cost_value_score` in the ranking formula strongly favours free resources — the system is biased toward democratically accessible learning by design |
