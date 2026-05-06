# Roadmap Generation Agent — Implementation Summary

**Date:** 2026-05-06
**Status:** Complete
**Author:** rogerjeasy

---

## Overview

The Roadmap Generation Agent is the fifth L3 Specialist Agent to be implemented and the **synthesis core of the entire pipeline**. It sits at Phase 4 of the multi-agent DAG — after the Gap Analysis Agent and Market Intelligence Agent have both completed — and transforms their structured outputs into a concrete, week-by-week career plan.

Its primary responsibility is to answer the question: *"Given what this candidate already knows, what the target role requires, and what the market is currently demanding, how should this person spend the next N months?"* The agent produces a strict JSON roadmap schema containing phases, milestones, a weekly schedule, recurring habits, and curated learning resources — all grounded in the gap report and real market signals.

Downstream agents (`LearningResourcesAgent`, `NetworkingAgent`, `OpportunityAgent`) consume the roadmap's phases and skills lists to generate complementary, context-aware outputs that further accelerate the candidate's transition.

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
  │  │  CVAgent            (skill_graph, readiness)        │    │
  │  │  MarketAgent        (trending_skills, salary)       │    │
  │  └─────────────────────────────────────────────────────┘    │
  │         │ plan_snapshot["cv_analysis"]                      │
  │         ▼                                                    │
  │  ┌── Phase 3 ──────────────────────────────────────────┐    │
  │  │  GapAgent   (prioritised_gaps, dimension_scores)    │    │
  │  └─────────────────────────────────────────────────────┘    │
  │         │ plan_snapshot["gap_analysis"]                     │
  │         │ plan_snapshot["market_intelligence"]              │
  │         ▼                                                    │
  │  ┌── Phase 4 ──────────────────────────────────────────┐    │
  │  │  RoadmapAgent  ◄── THIS IMPLEMENTATION              │    │
  │  │    PhaseGenerator → MilestoneGenerator              │    │
  │  │    WeeklyPlanner  → ResourceLinker                  │    │
  │  └─────────────────────────────────────────────────────┘    │
  │         │ plan_snapshot["roadmap_generation"]               │
  │         ▼                                                    │
  │  ┌── Phase 5 (parallel) ───────────────────────────────┐    │
  │  │  LEARNING_RESOURCES  NETWORKING  OPPORTUNITY        │    │
  │  └─────────────────────────────────────────────────────┘    │
  └──────────────────────────────────────────────────────────────┘
      │  AgentResult.output["phases"] + ["milestones"] + ["weekly_schedule"]
      ▼
  Synthesizer Node → OrchestratorResult → SSE → Client
```

---

## Files Introduced

### New files

| Path | Role |
|---|---|
| `agents/src/agents/roadmap_generation/models.py` | Pure domain types: `Phase`, `Milestone`, `WeeklyTask`, `Habit`, `Resource`, `RoadmapResult`, `DifficultyLevel`, `ResourceType` |
| `agents/src/agents/roadmap_generation/phase_generator.py` | `PhaseGenerator` — LLM-based learning phase builder with deterministic 3-phase fallback |
| `agents/src/agents/roadmap_generation/milestone_generator.py` | `MilestoneGenerator` — LLM milestone generator with one-per-phase heuristic fallback |
| `agents/src/agents/roadmap_generation/weekly_planner.py` | `WeeklyPlanner` — pure-computation weekly task distributor and habit recommender |
| `agents/src/agents/roadmap_generation/resource_linker.py` | `ResourceLinker` — RAG-first + 25-skill curated catalog resource linker |
| `agents/src/agents/roadmap_generation/roadmap_agent.py` | `RoadmapAgent` — extends `BaseAgent`, orchestrates the 4-step pipeline |
| `agents/src/agents/roadmap_generation/__init__.py` | Public package surface (`RoadmapAgent` only) |
| `agents/src/agents/roadmap_generation/tests/__init__.py` | Test package marker |
| `agents/src/agents/roadmap_generation/tests/test_roadmap_agent.py` | 65+ unit tests across 17 test classes (all LLM calls mocked) |
| `agents/src/agents/roadmap_generation/prompts/roadmap_system.txt` | PhaseGenerator system prompt (editable reference) |
| `agents/src/agents/roadmap_generation/prompts/roadmap_few_shot.txt` | Annotated few-shot example for phase generation |

### Modified files

| Path | Change |
|---|---|
| `agents/src/agents/core/observability.py` | Added 7 roadmap-specific Prometheus metrics |
| `agents/src/agents/config.py` | Added `roadmap_generation_model` (`claude-sonnet-4-6`) and `roadmap_milestone_model` (`claude-haiku-4-5-20251001`) |

---

## Pipeline Design

The agent runs four discrete steps. Steps 1 and 2 are sequential LLM calls; steps 3 and 4 are pure computation that runs after the LLM steps complete. Each step emits a `STEP_PROGRESS` SSE event and is wrapped in an OTel span.

```
context.plan_snapshot["gap_analysis"]["prioritised_gaps"]
context.plan_snapshot["market_intelligence"]["trending_skills"]
context.plan_snapshot["market_intelligence"]["salary_benchmark"]
context.user_profile.target_role
context.user_profile.timeline_months
context.user_profile.weekly_hours_available
context.rag_chunks
        │
        ▼  Step 1
  PhaseGenerator.generate()        ← LLM call (claude-sonnet-4-6)
        │  list[Phase]
        │  (index, title, duration_weeks, goals, skills_to_acquire,
        │   gaps_addressed, market_relevance, difficulty)
        ▼  Step 2
  MilestoneGenerator.generate()    ← LLM call (claude-haiku-4-5-20251001)
        │  list[Milestone]
        │  (name, week_number, success_criteria, deliverable)
        ▼  Step 3
  WeeklyPlanner.plan()             ← pure computation, no LLM
        │  (list[WeeklyTask], list[Habit])
        │  (week_number, focus_area, tasks[], estimated_hours, deliverable)
        ▼  Step 4
  ResourceLinker.link()            ← RAG + catalog lookup, no LLM
        │  list[Resource]
        │  (title, resource_type, provider, difficulty, tags, url, is_free)
        ▼
  AgentResult.output  (strict JSON roadmap schema)
```

**LLM budget per run:** 2 LLM calls (PhaseGenerator + MilestoneGenerator). Steps 3 and 4 are always LLM-free.

---

## Component Design

### `models.py` — Domain types

Eight frozen dataclasses and two enums carrying structured data through the pipeline. All are internal to the `roadmap_generation` package; external code imports only `RoadmapAgent` via `__init__.py`.

```python
class DifficultyLevel(str, Enum):
    BEGINNER     = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED     = "advanced"

class ResourceType(str, Enum):
    COURSE        = "course"
    BOOK          = "book"
    TUTORIAL      = "tutorial"
    DOCUMENTATION = "documentation"
    PROJECT       = "project"
    CERTIFICATION = "certification"
    COMMUNITY     = "community"
    VIDEO         = "video"

@dataclass(frozen=True)
class Phase:
    index:             int                  # 1-based
    title:             str
    description:       str
    duration_weeks:    int
    goals:             list[str]            # action-verb measurable goals
    skills_to_acquire: list[str]
    gaps_addressed:    list[str]            # requirement_name from gap_analysis
    market_relevance:  str                  # cites specific market data
    difficulty:        DifficultyLevel

@dataclass(frozen=True)
class Milestone:
    name:                str
    description:         str
    phase_index:         int                # aligns with Phase.index
    week_number:         int                # cumulative end-week of the phase
    success_criteria:    list[str]          # observable, measurable outcomes
    skills_demonstrated: list[str]
    deliverable:         str                # concrete shareable artifact

@dataclass(frozen=True)
class WeeklyTask:
    week_number:    int
    phase_index:    int
    focus_area:     str                     # skill being worked on this week
    tasks:          list[str]               # 4 specific actionable items
    estimated_hours: float
    deliverable:    str | None              # set only on the last week of each phase

@dataclass(frozen=True)
class Habit:
    name:             str
    frequency:        str                   # "daily" | "weekly"
    duration_minutes: int
    rationale:        str
    phase_start:      int                   # which phase to begin this habit

@dataclass(frozen=True)
class Resource:
    title:           str
    resource_type:   ResourceType
    provider:        str
    difficulty:      DifficultyLevel
    tags:            list[str]
    url:             str | None
    estimated_hours: float | None
    is_free:         bool
    description:     str

@dataclass(frozen=True)
class RoadmapResult:
    role:              str
    timeline_months:   int
    phases:            list[Phase]
    milestones:        list[Milestone]
    weekly_schedule:   list[WeeklyTask]
    habits:            list[Habit]
    resources:         list[Resource]
    summary:           str
    market_grounding:  dict
    processing_steps:  list[str]
    roadmap_id:        str      # UUID, auto-generated
    generated_at:      datetime # UTC, auto-generated
```

---

### `phase_generator.py` — Learning phase builder

`PhaseGenerator.generate()` sends a single LLM call (using `claude-sonnet-4-6`) that designs the full phase structure from the gap report and market signals. The model returns a strictly-typed JSON array of phases whose `duration_weeks` values sum exactly to `timeline_months × 4`.

**Prompt strategy:**

The system prompt enforces 10 hard rules:

| Rule | Constraint |
|---|---|
| Phase count | Exactly 3–5 phases |
| Duration sum | Must equal `total_weeks` (provided in prompt) |
| Difficulty progression | `beginner → intermediate → advanced` |
| Gap coverage | Every CRITICAL and HIGH severity gap must appear in `gaps_addressed` of the earliest suitable phase |
| Market grounding | `market_relevance` must cite specific numbers from the input (job count, salary, signal count) |
| Goal verbs | All goals must start with an action verb and be deliverable within the phase |
| Gap name fidelity | `gaps_addressed` values must exactly match requirement names from `prioritised_gaps` input |
| No hallucination | Do not invent facts not present in the input |

**User prompt structure:**

```
Target role: Backend Python Engineer
Timeline: 6 months (24 total_weeks — phases must sum to this)
Study hours per week: 10h
Active job postings: 18
Salary benchmark: median 95,000 CHF/yr

CRITICAL/HIGH priority gaps (must address first):
  - FastAPI (severity: critical, diff_score: 0.90)
  - PostgreSQL (severity: high, diff_score: 0.70)

Top trending market skills:
  - Python (12 signals, rising)
  - FastAPI (8 signals, rising)
```

**Deterministic fallback:** if the LLM call fails after 3 retries, `_fallback_phases()` generates three phases (Foundation Building → Applied Skills Development → Advanced Specialisation) with durations from `_split_weeks(total, 3)` and gaps distributed by severity tier. The pipeline never stalls.

**Observability:**
- OTel span `roadmap.phase_generation` with `target_role`, `timeline_months`
- `ROADMAP_PHASE_GEN_DURATION` histogram (seconds)
- `ROADMAP_PHASE_GEN_TOTAL` counter labelled `status=llm|fallback`

---

### `milestone_generator.py` — Measurable checkpoint generator

`MilestoneGenerator.generate()` sends a single LLM call (using `claude-haiku-4-5-20251001`) that produces exactly one milestone per phase. Milestones mark the successful completion of a phase with observable, deliverable-backed success criteria.

**Prompt strategy:**

| Rule | Constraint |
|---|---|
| Count | Exactly one milestone per phase |
| `week_number` | Must be the cumulative end-week of the phase |
| `success_criteria` | At least 3 items, all observable ("build X that does Y" not "understand X") |
| `deliverable` | A concrete shareable artifact (GitHub repo, live URL, certificate) |
| `skills_demonstrated` | Must come from the phase's `skills_to_acquire` |

**User prompt structure:**

```
Phase 1: Python & API Fundamentals
  Duration: 8 weeks (ends at week 8)
  Difficulty: beginner
  Goals: Build a fully-typed FastAPI service; Write unit tests; Document the API
  Skills: Python, FastAPI, pytest
  Gaps closed: FastAPI
```

**Heuristic fallback:** one milestone per phase with three standard success criteria (build project, push to GitHub, write README). The fallback produces valid output no matter what.

**Observability:**
- OTel span `roadmap.milestone_generation` with `phase_count`, `target_role`
- `ROADMAP_MILESTONE_GEN_DURATION` histogram (seconds)
- `ROADMAP_MILESTONE_GEN_TOTAL` counter labelled `status=llm|fallback`

---

### `weekly_planner.py` — Pure-computation weekly scheduler

`WeeklyPlanner.plan()` converts phases and milestones into a week-by-week task list and a set of recurring habits. It performs **no LLM call** and never fails.

**Phase scaling algorithm:**

If the LLM-generated phase durations don't sum exactly to `timeline_months × 4` weeks (due to rounding), `_scale_phases()` proportionally rescales them using `dataclasses.replace()` on frozen instances, adjusting the last phase to absorb any rounding remainder.

**Weekly task generation algorithm:**

For each phase, tasks rotate across `skills_to_acquire` week-by-week. The task template is selected by position within the phase:

| Position in phase | Template | Focus |
|---|---|---|
| First 35% of weeks | `intro` | Setup, official tutorial, beginner exercises |
| Middle 35–65% of weeks | `build` | Small projects, advanced features, code review |
| Last week of phase | `consolidate` | Milestone project, README, GitHub push, gap reflection |

The `deliverable` field on the last week is populated from the phase's corresponding `Milestone.deliverable`.

**Habit recommendations:**

Four core habits are always emitted for all learners (from phase 1):

| Habit | Frequency | Duration |
|---|---|---|
| Daily coding practice | daily | 30 min |
| Review learning notes | daily | 15 min |
| Weekly project review | weekly | 60 min |
| Read tech articles or release notes | daily | 15 min |

Plus one role-specific bonus habit (from phase 2) matched by keyword in `target_role`:

| Role keyword | Bonus habit |
|---|---|
| `data` | Kaggle notebook practice (90 min/week) |
| `machine learning` | Kaggle notebook practice (90 min/week) |
| `cloud` | Cloud console exploration (45 min/week) |
| `devops` | Infrastructure lab exercises (60 min/week) |
| `frontend` | UI component study and cloning (60 min/week) |

**Observability:**
- Structured log `roadmap_generation.completed` with `weekly_task_count`

---

### `resource_linker.py` — RAG-first resource matcher

`ResourceLinker.link()` attaches curated learning resources to the roadmap. It performs **no LLM call** and never fails. Matching happens in two passes per phase, capped at `max_per_phase=3` by default.

**Pass 1 — RAG chunks (personalised, highest priority):**

For each `RagChunk` in `context.rag_chunks`, `_chunk_to_resource()` attempts to convert it to a `Resource` by reading `metadata` fields (`title`, `provider`, `resource_type`, `difficulty`, `url`, `is_free`, `estimated_hours`). If `title` or `provider` are missing, the chunk is skipped. Invalid `resource_type` or `difficulty` enum values default to `tutorial` and `intermediate` respectively.

**Pass 2 — Curated catalog (25 skills covered):**

A module-level `_CATALOG` dict maps lowercase skill names to pre-built `Resource` objects. Coverage:

| Category | Skills covered |
|---|---|
| Languages | Python, TypeScript, JavaScript, Go, Rust |
| Frameworks | FastAPI, React, Next.js, LangChain |
| Platforms | Docker, Kubernetes, AWS, GCP |
| Tools | Terraform, PostgreSQL, Git |
| AI/ML | Machine Learning, LLM, RAG |
| Architecture | System Design |

An `_ALIASES` dict normalises common variations (e.g. `golang → go`, `nextjs → next.js`, `k8s → kubernetes`, `llms → llm`) before catalog lookup.

**Deduplication:** a `seen: set[tuple[str, str]]` keyed on `(title.lower(), provider.lower())` prevents the same resource appearing twice across phases.

**Observability:**
- `ROADMAP_RESOURCE_LINK_TOTAL` counter labelled `source=rag|catalog`
- Structured log `roadmap.resources_linked` with `resource_count`

---

### `roadmap_agent.py` — Main agent

`RoadmapAgent` extends `BaseAgent` and implements `_execute(context)` as the 4-step pipeline.

**Input — resolved from context:**

```python
target_role      = context.user_profile.target_role or "Software Engineer"
timeline_months  = context.user_profile.timeline_months or 6
weekly_hours     = context.user_profile.weekly_hours_available or 10

# from previous pipeline stages
prioritised_gaps = context.plan_snapshot["gap_analysis"]["prioritised_gaps"]
trending_skills  = context.plan_snapshot["market_intelligence"]["trending_skills"]
salary_benchmark = context.plan_snapshot["market_intelligence"]["salary_benchmark"]
job_postings     = context.plan_snapshot["market_intelligence"]["job_postings"]

# from L5 RAG layer (future) or empty list
rag_chunks       = context.rag_chunks
```

**Output shape (`AgentResult.output`):**

```json
{
  "roadmap_id": "550e8400-e29b-41d4-a716-446655440000",
  "role": "Backend Python Engineer",
  "timeline_months": 6,
  "generated_at": "2026-05-06T14:23:01.456789+00:00",
  "phases": [
    {
      "index": 1,
      "title": "Python & API Fundamentals",
      "description": "Build foundational Python and FastAPI skills...",
      "duration_weeks": 8,
      "goals": ["Build a fully-typed FastAPI service with authentication"],
      "skills_to_acquire": ["Python", "FastAPI", "pytest"],
      "gaps_addressed": ["FastAPI"],
      "market_relevance": "FastAPI appears in 8/18 active job postings...",
      "difficulty": "beginner"
    }
  ],
  "milestones": [
    {
      "name": "Python & API Proficiency Checkpoint",
      "description": "Demonstrate production-ready Python and FastAPI skills",
      "phase_index": 1,
      "week_number": 8,
      "success_criteria": [
        "Build a FastAPI service with JWT authentication and 80%+ test coverage",
        "Deploy the service via Docker Compose with a documented README",
        "Receive and incorporate at least one peer code review"
      ],
      "skills_demonstrated": ["Python", "FastAPI", "pytest"],
      "deliverable": "GitHub repository: python-api-portfolio"
    }
  ],
  "weekly_schedule": [
    {
      "week_number": 1,
      "phase_index": 1,
      "focus_area": "Python",
      "tasks": [
        "Set up development environment for Python",
        "Complete the official Python getting-started guide",
        "Study core concepts and reference documentation",
        "Complete 2–3 beginner exercises to validate understanding"
      ],
      "estimated_hours": 10.0,
      "deliverable": null
    }
  ],
  "habits": [
    {
      "name": "Daily coding practice",
      "frequency": "daily",
      "duration_minutes": 30,
      "rationale": "Consistent daily coding builds muscle memory faster than any other single habit.",
      "phase_start": 1
    }
  ],
  "resources": [
    {
      "title": "FastAPI Official Tutorial",
      "resource_type": "documentation",
      "provider": "Sebastián Ramírez",
      "difficulty": "beginner",
      "tags": ["fastapi", "python", "api"],
      "url": "https://fastapi.tiangolo.com/tutorial/",
      "estimated_hours": 6.0,
      "is_free": true,
      "description": ""
    }
  ],
  "summary": "Your personalised roadmap to Backend Python Engineer spans 6 months across 3 structured learning phases. The phases progress through: Python & API Fundamentals → Database & Data Modelling → Containerisation & Deployment. Market-priority skills incorporated: Python, FastAPI, Docker. You will hit 3 measurable milestones, each producing a concrete portfolio deliverable.",
  "market_grounding": {
    "market_summary": "Strong demand for Python backend engineers in Switzerland.",
    "top_trending_skills": ["Python", "FastAPI", "Docker"],
    "job_posting_count": 18,
    "salary_median": 95000,
    "salary_currency": "CHF",
    "country": "CH"
  },
  "processing_steps": [
    "phase_generation",
    "milestone_generation",
    "weekly_planning",
    "resource_linking"
  ]
}
```

**Constructor — dependency injection:**

```python
RoadmapAgent(
    phase_generator=PhaseGenerator(llm=...),        # injectable for tests
    milestone_generator=MilestoneGenerator(llm=...), # injectable for tests
    weekly_planner=WeeklyPlanner(),                  # injectable for tests
    resource_linker=ResourceLinker(),                # injectable for tests
    event_publisher=EventPublisher(redis),           # None → events silently skipped
    llm=ChatAnthropic(...),                          # forwarded to LLM components if not provided
)
```

**Registration at worker startup:**

```python
from agents.roadmap_generation import RoadmapAgent
from agents.core.agent_registry import registry

registry.register(RoadmapAgent(event_publisher=EventPublisher(redis_client)))
```

---

## Configuration

Two new settings added to `AgentSettings` in `agents/src/agents/config.py`:

| Setting | Default | Purpose |
|---|---|---|
| `roadmap_generation_model` | `claude-sonnet-4-6` | LLM used by `PhaseGenerator` — complex structured reasoning requires the full Sonnet model |
| `roadmap_milestone_model` | `claude-haiku-4-5-20251001` | LLM used by `MilestoneGenerator` — structured but simpler task, Haiku is sufficient and faster |

Set via environment variables: `ROADMAP_GENERATION_MODEL`, `ROADMAP_MILESTONE_MODEL`.

---

## Prometheus Metrics Added

| Metric name | Type | Labels | What it tracks |
|---|---|---|---|
| `career_agents_roadmap_phase_gen_duration_seconds` | Histogram | — | Wall-clock time for LLM phase-generation calls |
| `career_agents_roadmap_phase_gen_total` | Counter | `status` (llm \| fallback) | Phase-generation call outcomes |
| `career_agents_roadmap_milestone_gen_duration_seconds` | Histogram | — | Wall-clock time for LLM milestone-generation calls |
| `career_agents_roadmap_milestone_gen_total` | Counter | `status` (llm \| fallback) | Milestone-generation call outcomes |
| `career_agents_roadmap_phase_count` | Histogram | — | Number of phases generated per roadmap run |
| `career_agents_roadmap_milestone_count` | Histogram | — | Number of milestones generated per roadmap run |
| `career_agents_roadmap_resource_link_total` | Counter | `source` (rag \| catalog) | Resources linked per source type |

---

## Test Coverage

The test file (`tests/test_roadmap_agent.py`) contains **65+ unit tests** organised into 17 test classes. All LLM calls are replaced with `AsyncMock` — no network, no Anthropic API key required. Pure-computation components (`WeeklyPlanner`, `ResourceLinker`) are tested with real instances.

| Class | What is tested |
|---|---|
| `TestSplitWeeks` | Exact divisibility; remainder distributed to first phases; single phase; minimum 1 week per phase; zero total handled |
| `TestScalePhases` | No scaling needed; scales up; scales down; empty phases; preserves non-duration attributes; minimum 1 week enforced per phase |
| `TestPlanPhase` | Correct week count; sequential week numbers; estimated hours from input; last week has deliverable when milestone set; no deliverable without milestone; skill rotation across weeks; single-week phase edge case |
| `TestWeeklyPlanner` | Total weeks matches timeline; core habits always present; data role adds Kaggle habit; cloud role adds cloud console habit; unknown role returns only 4 core habits; empty phases returns empty schedule |
| `TestFallbackPhases` | Always produces 3 phases; durations sum to timeline weeks; difficulty progression beginner→intermediate→advanced; critical gaps placed in phase 1; indexes are sequential 1/2/3; short timeline handled |
| `TestParsePhase` | Valid dict parsed correctly; invalid difficulty defaults to beginner; missing optional fields use defaults; `duration_weeks` minimum 1 |
| `TestFallbackMilestones` | One milestone per phase; cumulative week numbers correct; phase_index matches; 3+ success criteria; non-empty deliverable; empty phases → empty list |
| `TestParseMilestone` | Valid dict parsed; missing fields use defaults |
| `TestBuildUserPromptPhase` | Contains role and timeline; contains critical gaps; contains trending skills; salary included when available |
| `TestBuildUserPromptMilestone` | Contains phase titles; contains cumulative week numbers |
| `TestResourceLinker` | Catalog lookup for Python; alias normalisation (golang → go); deduplication across phases; RAG chunks take priority over catalog; `max_per_phase` respected; unknown skill returns empty list gracefully |
| `TestChunkToResource` | Valid chunk converts to Resource; missing title falls back to content prefix; missing title and provider returns None; invalid `resource_type` defaults to tutorial; invalid `difficulty` defaults to intermediate |
| `TestSerialisers` | All keys present in `_serialise_phase`; enum values are strings in phase output; all keys in milestone, weekly_task, habit, resource serialisers; `resource_type` and `difficulty` serialised as strings |
| `TestBuildSummary` | Contains role and timeline; includes phase titles; includes trending skills; mentions milestone count |
| `TestBuildMarketGrounding` | All keys present; job_posting_count correct; salary fields populated; no salary benchmark → None values |
| `TestPhaseGeneratorAsync` | LLM success returns parsed phases; LLM failure returns 3-phase fallback; bad JSON returns fallback; missing `phases` key returns fallback |
| `TestMilestoneGeneratorAsync` | LLM success returns parsed milestones; LLM failure returns one-per-phase fallback |
| `TestRoadmapAgent` | Completed status; all output schema keys present; role from user profile; timeline_months from profile; phases serialised with difficulty string; milestones with success_criteria; processing_steps in order; market_grounding populated; default role when profile empty; 4 progress events emitted; event publisher failure doesn't abort pipeline; roadmap_id is valid UUID; generated_at is ISO string; phase_generator called with correct role; full end-to-end with real WeeklyPlanner + ResourceLinker |

Run the full test suite:

```bash
cd agents
poetry run pytest src/agents/roadmap_generation/tests/ -v
```

---

## Data Flow to Downstream Agents

| Downstream agent | Fields consumed |
|---|---|
| `LearningResourcesAgent` | `phases[*].skills_to_acquire`, `phases[*].difficulty`, `milestones[*].deliverable` |
| `NetworkingAgent` | `phases[*].title`, `phases[*].gaps_addressed`, `market_grounding.top_trending_skills` |
| `OpportunityAgent` | `phases[*].skills_to_acquire`, `milestones[*].deliverable` (portfolio evidence for job applications) |
| `CoachAgent` | `summary`, `phases`, `weekly_schedule` (context for conversational coaching) |
| `ProgressAgent` | `roadmap_id`, `milestones[*].week_number`, `milestones[*].success_criteria` (re-generation baseline) |

All downstream agents access this data via `context.plan_snapshot["roadmap_generation"]`.

---

## Design Principles Applied

| Principle | How it manifests |
|---|---|
| **Low coupling** | All 4 pipeline components are injected into `RoadmapAgent`; no component imports from another; `ResourceLinker` imports `RagChunk` from `agents.core.context` (the shared contract layer), never from `agents.cv_analysis` or any other agent |
| **High cohesion** | All roadmap logic lives inside `agents.roadmap_generation`; the public interface is `RoadmapAgent` only |
| **Statelessness** | Every component holds only its LLM client reference; all state flows through method arguments and return values |
| **Separation of concerns** | `PhaseGenerator` knows only about phases; `MilestoneGenerator` only about milestones; `WeeklyPlanner` only about scheduling; `ResourceLinker` only about matching — none overlap |
| **LLM-free hot path** | `WeeklyPlanner` and `ResourceLinker` are pure computation, ensuring 50% of the pipeline steps are always fast and network-independent |
| **Graceful degradation** | `PhaseGenerator` falls back to deterministic 3-phase plan; `MilestoneGenerator` falls back to one generic milestone per phase — the pipeline always produces a complete, valid roadmap regardless of LLM availability |
| **Market grounding** | Phase titles, `market_relevance` strings, and resource tags all incorporate live signals from `market_intelligence` output — the roadmap reflects what is actually in demand today, not a static template |
| **RAG-readiness** | `ResourceLinker` is designed to prefer `context.rag_chunks` over the static catalog — when the L5 RAG layer is integrated, personalised course recommendations will automatically surface ahead of catalog defaults with zero code changes |
| **Timeline awareness** | `WeeklyPlanner._scale_phases()` ensures phases always sum exactly to `timeline_months × 4` weeks regardless of what the LLM returns, making the schedule mathematically consistent |
| **Input independence** | Reads from `plan_snapshot["gap_analysis"]` and `plan_snapshot["market_intelligence"]` rather than importing from sibling agent packages — zero coupling to agent internals |
| **Observability** | OTel span per step, 7 Prometheus metrics covering duration and outcome for every LLM call and every resource link source, `STEP_PROGRESS` SSE events at each of 4 stages |
| **Testability** | Every external dependency (LLM, event publisher) is constructor-injectable with a `None` default; 65+ tests require no network; pure-computation steps tested with real instances |
