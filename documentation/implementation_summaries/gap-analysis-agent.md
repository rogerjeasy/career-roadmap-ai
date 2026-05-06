# Gap Analysis Agent — Implementation Summary

**Date:** 2026-05-05
**Status:** Complete
**Author:** rogerjeasy

---

## Overview

The Gap Analysis Agent is the third L3 Specialist Agent to be implemented. Its role is the system's **structured comparison layer between where a candidate is today and where they need to be**: it receives the `SkillGraph` and structured CV data produced by the CV Analysis Agent, builds a requirements profile for the target role, identifies every gap across five dimensions (tech skills, soft skills, certifications, portfolio, and ATS keywords), and ranks those gaps by ROI and urgency so that the Roadmap Generation Agent can immediately translate them into a prioritised action plan.

By running in Phase 3 of the multi-agent DAG (after CV Analysis has completed), the Gap Analysis Agent provides all downstream agents with a machine-readable, priority-ordered list of what the candidate must still learn or demonstrate.

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
  │  │  CVAgent  (skill_graph, readiness)                  │    │
  │  │  MARKET_INTELLIGENCE                                │    │
  │  └─────────────────────────────────────────────────────┘    │
  │         │ plan_snapshot["cv_analysis"]                      │
  │         ▼                                                    │
  │  ┌── Phase 3 ──────────────────────────────────────────┐    │
  │  │  GapAgent  ◄── THIS IMPLEMENTATION                  │    │
  │  │    RoleProfiler → SkillGapScorer → GapPrioritiser   │    │
  │  └─────────────────────────────────────────────────────┘    │
  │         │ plan_snapshot["gap_analysis"]                     │
  │         ▼                                                    │
  │  ┌── Phase 4 ──────────────────────────────────────────┐    │
  │  │  ROADMAP_GENERATION  (consumes prioritised_gaps)    │    │
  │  └─────────────────────────────────────────────────────┘    │
  │         │                                                    │
  │  ┌── Phase 5 (parallel) ───────────────────────────────┐    │
  │  │  LEARNING_RESOURCES  NETWORKING  OPPORTUNITY        │    │
  │  └─────────────────────────────────────────────────────┘    │
  └──────────────────────────────────────────────────────────────┘
      │  AgentResult.output["prioritised_gaps"] + ["overall_diff_score"]
      ▼
  Synthesizer Node → OrchestratorResult → SSE → Client
```

---

## Files Introduced

### New files

| Path | Role |
|---|---|
| `agents/src/agents/gap_analysis/models.py` | Pure domain types: `RoleRequirement`, `RoleProfile`, `SkillGap`, `DimensionScores`, `GapSeverity`, `GapDimension`, `GapAnalysisResult` |
| `agents/src/agents/gap_analysis/role_profiler.py` | `RoleProfiler` — LLM-based target role requirements builder with heuristic fallback |
| `agents/src/agents/gap_analysis/skill_gap_scorer.py` | `SkillGapScorer` — LLM semantic gap scorer with name-match fallback; computes per-dimension scores |
| `agents/src/agents/gap_analysis/gap_prioritiser.py` | `GapPrioritiser` — pure-computation ROI × urgency ranker; never touches LLM |
| `agents/src/agents/gap_analysis/gap_agent.py` | `GapAgent` — extends `BaseAgent`, orchestrates the 3-step pipeline |
| `agents/src/agents/gap_analysis/__init__.py` | Public package surface |
| `agents/src/agents/gap_analysis/tests/__init__.py` | Test package marker |
| `agents/src/agents/gap_analysis/tests/test_gap_agent.py` | 50+ unit tests (all LLM calls mocked) |

### Modified files

| Path | Change |
|---|---|
| `agents/src/agents/core/observability.py` | Added 6 gap-analysis-specific Prometheus metrics |

---

## Pipeline Design

The agent runs three discrete steps in sequence. Each step emits a `STEP_PROGRESS` SSE event and is wrapped in an OTel span.

```
context.plan_snapshot["cv_analysis"]["skill_graph"]
context.plan_snapshot["cv_analysis"]["parsed_cv"]
context.user_profile.target_role
        │
        ▼  Step 1
  RoleProfiler.profile()            ← LLM call (claude-sonnet-4-6)
        │  RoleProfile
        │  (requirements, keywords, typical_experience_months)
        ▼  Step 2
  SkillGapScorer.score()            ← LLM call + name-match fallback
        │  list[SkillGap]  +  DimensionScores
        │  (diff_score, roi_score, urgency_score per gap)
        ▼  Step 3
  GapPrioritiser.prioritise()       ← pure computation, no LLM
        │  list[SkillGap] (priority_rank assigned, sorted by composite)
        ▼
  AgentResult.output
```

**LLM budget per run:** 2 LLM calls (RoleProfiler + SkillGapScorer). GapPrioritiser is always LLM-free.

---

## Component Design

### `models.py` — Domain types

Seven frozen dataclasses and two enums that carry structured data through the pipeline. All are **internal to the gap_analysis package**; external code imports only `GapAgent` via `__init__.py`.

```python
class GapSeverity(str, Enum):
    CRITICAL = "critical"   # Required skill — completely absent
    HIGH     = "high"       # Required skill — partially present or low proficiency
    MEDIUM   = "medium"     # Preferred skill — absent
    LOW      = "low"        # Preferred skill — partially present

class GapDimension(str, Enum):
    TECH_SKILL    = "tech_skill"
    SOFT_SKILL    = "soft_skill"
    CERTIFICATION = "certification"
    PORTFOLIO     = "portfolio"
    KEYWORD       = "keyword"

@dataclass(frozen=True, slots=True)
class RoleRequirement:
    name:          str
    dimension:     GapDimension
    is_required:   bool             # True = must-have, False = nice-to-have
    description:   str
    typical_level: str | None       # beginner | intermediate | advanced | expert

@dataclass(frozen=True)
class RoleProfile:
    role_title:                  str
    requirements:                list[RoleRequirement]
    keywords:                    list[str]   # ATS resume keywords
    typical_experience_months:   int | None
    # computed properties:
    #   .required        → list[RoleRequirement]  (is_required=True)
    #   .preferred       → list[RoleRequirement]  (is_required=False)
    #   .by_dimension    → dict[str, list[RoleRequirement]]

@dataclass(frozen=True, slots=True)
class SkillGap:
    requirement_name: str
    dimension:        GapDimension
    severity:         GapSeverity
    is_required:      bool
    diff_score:       float   # 0=no gap, 1=fully absent
    current_level:    str | None
    required_level:   str | None
    roi_score:        float   # 0-1: expected return from closing this gap
    urgency_score:    float   # 0-1: how urgently the gap needs attention
    priority_rank:    int     # 1-based, assigned by GapPrioritiser
    evidence:         str     # one-line rationale

@dataclass(frozen=True, slots=True)
class DimensionScores:
    tech_skills:    float   # 0=no gap, 1=complete gap
    soft_skills:    float
    certifications: float
    portfolio:      float
    keywords:       float
```

---

### `role_profiler.py` — Role requirements builder

`RoleProfiler.profile()` sends a single LLM call to enumerate what the target role actually requires. The model returns:

| Section | What is extracted |
|---|---|
| `requirements[]` | Each item: `name`, `dimension`, `is_required`, `description`, `typical_level` |
| `keywords[]` | 5–10 ATS/resume keywords the CV should contain for this role |
| `typical_experience_months` | Median months of professional experience the role expects |

**Prompt strategy:** the system prompt instructs the model to produce 8–15 requirements covering `tech_skill` (required and preferred), `soft_skill` (2–4 key ones), `certification` (if standard for the role), and `portfolio` (2–3 project types). The model is asked to set `is_required=true` only for genuine must-haves.

**Resilience:**
- `_profile_with_llm` decorated with `@retry(stop_after_attempt(3), wait_exponential(0.5, 1, 8))`.
- On failure: returns `_heuristic_profile(role_title)` — a minimal but valid `RoleProfile` containing generic soft skills, Git, and a portfolio entry — so the pipeline never halts.

**Observability:**
- OTel span `gap.role_profile` with attributes: `target_role`, `requirement_count`, `duration_ms`
- `GAP_ROLE_PROFILE_DURATION` histogram (seconds)
- `GAP_ROLE_PROFILE_TOTAL` counter labelled `status=llm|fallback`

---

### `skill_gap_scorer.py` — Semantic gap scoring

`SkillGapScorer.score()` compares the candidate's skills, certifications, and experience against every requirement in the `RoleProfile` and returns one `SkillGap` per unmet requirement plus aggregated `DimensionScores`.

**Key design decisions:**

**Semantic matching via LLM:** the LLM can recognise that `"TypeScript"` partially satisfies a `"JavaScript"` requirement, or that `"PyTorch"` satisfies an `"ML frameworks"` requirement. Simple string matching would produce far too many false-positive gaps.

**Gap threshold:** requirements with `diff_score ≤ 0.05` are considered fully met and are silently excluded from the output. Only genuine gaps are returned.

**Per-gap scores:**

| Score | Range | Meaning |
|---|---|---|
| `diff_score` | 0–1 | Magnitude of the gap (0 = fully met, 1 = completely absent, 0.5 = partially met) |
| `roi_score` | 0–1 | How much closing this gap improves hiring chances for the target role |
| `urgency_score` | 0–1 | How soon this gap needs to be addressed, given the role requirements |

**Dimension score aggregation:** `DimensionScores` is computed from the list of `SkillGap` objects after the LLM (or fallback) returns. Required gaps are weighted 1.5× higher than preferred gaps within each dimension:

```python
dim_score = sum(gap.diff_score × weight) / sum(weight)
# where weight = 1.5 if gap.is_required else 1.0
```

**Severity mapping:**

| Condition | Severity |
|---|---|
| Required + diff ≥ 0.7 | `CRITICAL` |
| Required + diff ≥ 0.3 | `HIGH` |
| Preferred + diff ≥ 0.5 | `MEDIUM` |
| All others | `LOW` |

**Heuristic fallback (name-match):** if the LLM call fails after retries, the scorer compares candidate skill names case-insensitively against requirement names. Missing required skills get `diff_score=1.0`; missing preferred get `diff_score=0.6`. No semantic matching is possible, but the pipeline never crashes.

**Observability:**
- OTel span `gap.skill_score` with attributes: `candidate_skill_count`, `requirement_count`, `gap_count`, `duration_ms`
- `GAP_SKILL_SCORE_DURATION` histogram (seconds)
- `GAP_SKILL_SCORE_TOTAL` counter labelled `status=llm|fallback`

---

### `gap_prioritiser.py` — ROI × urgency ranker

`GapPrioritiser.prioritise()` assigns a `priority_rank` (1 = highest) to every gap using a composite score. It performs **no LLM call** and never fails.

**Composite formula:**

```
composite = ROI_WEIGHT(0.45) × roi_score
          + URGENCY_WEIGHT(0.35) × urgency_score × urgency_multiplier
          + SEVERITY_BONUS[severity]
```

**Severity bonuses:**

| Severity | Bonus |
|---|---|
| `CRITICAL` | +0.20 |
| `HIGH` | +0.12 |
| `MEDIUM` | +0.05 |
| `LOW` | +0.00 |

**Urgency multiplier:** adjusted by user context injected from `context.user_profile`:

| Condition | Multiplier boost |
|---|---|
| `timeline_months ≤ 6` | +0.15 (tight deadline amplifies urgency) |
| `weekly_hours_available ≥ 20` | +0.10 (high capacity means gaps can be closed urgently) |
| Maximum multiplier | 1.30 |

The method produces a **new list of `SkillGap` objects** with `priority_rank` set — the original objects are immutable (frozen dataclass), so each ranked gap is reconstructed from its predecessor's fields with only `priority_rank` changed. The input list is never mutated.

**Observability:**
- Structured log `gap.prioritised` with `gap_count`, `top_gap`, `urgency_multiplier`, `correlation_id`

---

### `gap_agent.py` — Main agent

`GapAgent` extends `BaseAgent` and implements `_execute(context)` as the 3-step sequential pipeline described above.

**Input — resolved from context:**

```python
# Primary source: CV analysis output from the previous pipeline phase
skill_graph_nodes = context.plan_snapshot["cv_analysis"]["skill_graph"]["nodes"]
parsed_cv_dict    = context.plan_snapshot["cv_analysis"]["parsed_cv"]
target_role       = context.user_profile.target_role

# Fallback if CV analysis has not run (e.g. direct gap query)
candidate_skills  = context.user_profile.skills
```

**Output shape (`AgentResult.output`):**

```json
{
  "role_profile": {
    "role_title": "Senior Backend Engineer",
    "typical_experience_months": 60,
    "keywords": ["Python", "microservices", "Kubernetes", "REST API", "CI/CD"],
    "requirements": [
      {
        "name": "Python",
        "dimension": "tech_skill",
        "is_required": true,
        "description": "Primary backend language",
        "typical_level": "advanced"
      },
      {
        "name": "Kubernetes",
        "dimension": "tech_skill",
        "is_required": true,
        "description": "Container orchestration for production deployments",
        "typical_level": "intermediate"
      },
      {
        "name": "AWS Certified Developer",
        "dimension": "certification",
        "is_required": false,
        "description": "Preferred cloud certification",
        "typical_level": null
      }
    ]
  },
  "skill_gaps": [
    {
      "requirement_name": "Kubernetes",
      "dimension": "tech_skill",
      "severity": "critical",
      "is_required": true,
      "diff_score": 0.9,
      "current_level": null,
      "required_level": "intermediate",
      "roi_score": 0.88,
      "urgency_score": 0.92,
      "priority_rank": 0,
      "evidence": "Not found in candidate skill graph"
    }
  ],
  "dimension_scores": {
    "tech_skills": 0.62,
    "soft_skills": 0.10,
    "certifications": 0.80,
    "portfolio": 0.40,
    "keywords": 0.30
  },
  "overall_diff_score": 0.487,
  "prioritised_gaps": [
    {
      "requirement_name": "Kubernetes",
      "dimension": "tech_skill",
      "severity": "critical",
      "is_required": true,
      "diff_score": 0.9,
      "current_level": null,
      "required_level": "intermediate",
      "roi_score": 0.88,
      "urgency_score": 0.92,
      "priority_rank": 1,
      "evidence": "Not found in candidate skill graph"
    }
  ],
  "processing_steps": [
    "role_profiling",
    "skill_gap_scoring",
    "gap_prioritisation"
  ]
}
```

**Overall diff score formula:**

```
overall_diff_score = tech_skills × 0.45
                   + soft_skills × 0.20
                   + certifications × 0.15
                   + portfolio × 0.10
                   + keywords × 0.10
```

A score of `0.0` means no gaps exist. A score of `1.0` means the candidate has none of the role's requirements. Downstream agents use this value to calibrate roadmap duration and phase intensity.

**Constructor — dependency injection:**

```python
GapAgent(
    role_profiler=RoleProfiler(llm=...),          # injectable for tests
    skill_gap_scorer=SkillGapScorer(llm=...),      # injectable for tests
    gap_prioritiser=GapPrioritiser(),              # injectable for tests
    event_publisher=EventPublisher(redis),          # None → events silently skipped
    llm=ChatAnthropic(...),                        # forwarded to LLM components if not provided
)
```

**Registration at worker startup:**

```python
from agents.gap_analysis import GapAgent
from agents.core.agent_registry import registry

registry.register(GapAgent(event_publisher=EventPublisher(redis_client)))
```

---

## Prometheus Metrics Added

| Metric name | Type | Labels | What it tracks |
|---|---|---|---|
| `career_agents_gap_role_profile_duration_seconds` | Histogram | — | Wall-clock time for role profiling LLM calls |
| `career_agents_gap_role_profile_total` | Counter | `status` (llm \| fallback) | Role profiling call outcomes |
| `career_agents_gap_skill_score_duration_seconds` | Histogram | — | Wall-clock time for skill gap-scoring LLM calls |
| `career_agents_gap_skill_score_total` | Counter | `status` (llm \| fallback) | Skill gap-scoring call outcomes |
| `career_agents_gap_diff_score` | Histogram | — | Overall diff-score distribution across all runs |
| `career_agents_gap_gap_count` | Histogram | — | Number of identified gaps per run |

---

## Test Coverage

The test file (`tests/test_gap_agent.py`) contains **50+ unit tests** organised into 11 test classes. All LLM calls are replaced with `AsyncMock` — no network, no Anthropic API key required.

| Class | What is tested |
|---|---|
| `TestBuildRoleProfile` | Full LLM response parsing; unknown dimension defaults to `tech_skill`; item without name skipped; experience months coercion; invalid months → `None`; empty raw dict |
| `TestHeuristicProfile` | Returns non-empty profile; all requirements have name and dimension; keywords include role title |
| `TestRoleProfilerAsync` | Successful LLM profile; LLM failure returns heuristic fallback; invalid JSON returns fallback |
| `TestSeverity` | All severity boundary conditions: critical/high/low for required; medium/low for optional |
| `TestBuildGaps` | Gaps below threshold excluded; gap above threshold included; item without name skipped; unknown dimension defaults; score clamping above 1.0 and below 0.0 |
| `TestHeuristicGaps` | Present skill excluded; missing required gets `diff_score=1.0`; missing optional gets `diff_score=0.6`; case-insensitive match |
| `TestComputeDimensionScores` | No gaps → all zeros; single required tech gap; required weighted higher than optional; all scores bounded `[0, 1]` |
| `TestSkillGapScorerAsync` | Successful LLM scoring; LLM failure falls back to heuristic; empty skills generates gaps for all requirements |
| `TestUrgencyMultiplier` | No context → 1.0; tight timeline boosts; high hours boosts; capped at 1.30 |
| `TestComposite` | Higher ROI scores higher; critical severity bonus applied |
| `TestGapPrioritiser` | Empty list returns empty; ranks 1-based; rank 1 is highest priority; critical/high ranks first; tight timeline does not change count; output gaps are new objects with rank set |
| `TestComputeOverallDiff` | All zeros → 0.0; all ones → 1.0; result in `[0, 1]` |
| `TestSerialiseGap` | All keys present; enum values are strings |
| `TestGapAgent` | Agent type/display name; required output keys; 3 processing steps; target role passed to profiler; candidate skills from skill graph nodes; fallback to profile skills when no CV analysis; overall diff in range; dimension scores structure; 3 progress events; no events without publisher; timeline/weekly hours passed to prioritiser; full `run()` via `BaseAgent` |

Run the full test suite:

```bash
cd agents
poetry run pytest src/agents/gap_analysis/tests/ -v
```

---

## Data Flow to Downstream Agents

| Downstream agent | Fields consumed |
|---|---|
| `RoadmapGenerationAgent` | `prioritised_gaps` (full list, rank 1 first), `overall_diff_score` (calibrates roadmap duration), `dimension_scores` (drives phase emphasis) |
| `LearningResourcesAgent` | `prioritised_gaps[*].requirement_name`, `prioritised_gaps[*].dimension`, `prioritised_gaps[*].required_level` |
| `NetworkingAgent` | `role_profile.keywords` (for outreach messaging), `role_profile.role_title` |
| `OpportunityAgent` | `role_profile.keywords` (for job search queries), `overall_diff_score` (filters role seniority) |

All downstream agents access this data via `context.plan_snapshot["gap_analysis"]`.

---

## Design Principles Applied

| Principle | How it manifests |
|---|---|
| **Low coupling** | All 3 pipeline components are injected into `GapAgent`; no component knows about another or about the agent framework |
| **High cohesion** | All gap-analysis logic lives inside `agents.gap_analysis`; the public interface is `GapAgent` only |
| **Statelessness** | Every component holds only its LLM client reference; all state flows through method arguments and return values |
| **Separation of concerns** | `RoleProfiler` knows only about role requirements; `SkillGapScorer` knows only about comparison; `GapPrioritiser` knows only about ranking — none overlap |
| **LLM-free hot path** | `GapPrioritiser` is pure computation, ensuring ranking is always fast and never network-dependent |
| **Graceful degradation** | `RoleProfiler` falls back to a heuristic profile; `SkillGapScorer` falls back to name matching — the pipeline never hard-fails regardless of LLM availability |
| **Conservative heuristics** | The name-match fallback uses `diff_score=1.0` for required skills (worst case) rather than guessing — avoids false confidence in the fallback path |
| **Input independence** | Reads from `plan_snapshot["cv_analysis"]` rather than importing from `agents.cv_analysis` — zero coupling to the CV agent's internals |
| **Observability** | OTel span per component, 6 Prometheus metrics covering duration and outcome for every LLM call, `STEP_PROGRESS` SSE events per pipeline step |
| **Testability** | Every external dependency (LLM, event publisher) is constructor-injectable with a `None` default; 50+ tests require no network |
