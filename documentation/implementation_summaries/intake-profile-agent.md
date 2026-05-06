# Intake & Profile Agent — Implementation Summary

**Date:** 2026-05-05
**Status:** Complete
**Author:** rogerjeasy

---

## Overview

The Intake & Profile Agent is the first L3 Specialist Agent to be implemented. Its role is to act as the system's **structured listening layer**: it reads the user's raw natural-language message, applies Named-Entity Recognition (NER) and slot-filling via an LLM call, and produces an enriched `UserProfileSnapshot` for all downstream agents to consume.

By running in Phase 1 of every multi-agent DAG, the Intake agent ensures that later agents (CV Analysis, Gap Analysis, Roadmap Generation, etc.) always operate on the most complete picture of the user that can be extracted from what they have said so far — without requiring a separate data-entry form.

---

## Architecture Position

```
Client (Next.js)
      │  user message
      ▼
FastAPI Gateway
      │  OrchestratorTaskInput
      ▼
Celery Worker — MasterOrchestrator (LangGraph)
      │
      ▼
  LangGraph Pipeline
  ┌──────────────────────────────────────────────────────────┐
  │  Node 1: parse_intent                                    │
  │  Node 2: score_completeness  (ClarificationEngine)       │
  │  Node 3: build_dag           (TaskPlanner)               │
  │                                                          │
  │  ┌── Phase 1 ──────────────────────────────────────┐    │
  │  │  IntakeAgent  ◄── THIS IMPLEMENTATION           │    │
  │  │    SlotExtractor (NER via LLM)                  │    │
  │  │    ProfileBuilder (pure merge)                  │    │
  │  └─────────────────────────────────────────────────┘    │
  │         │ enriched UserProfile in plan_snapshot          │
  │         ▼                                               │
  │  ┌── Phase 2 (parallel) ───────────────────────────┐    │
  │  │  CV_ANALYSIS    MARKET_INTELLIGENCE             │    │
  │  └─────────────────────────────────────────────────┘    │
  │         │                                               │
  │  ┌── Phase 3 ──────────────────────────────────────┐    │
  │  │  GAP_ANALYSIS                                   │    │
  │  └─────────────────────────────────────────────────┘    │
  │         │                                               │
  │  ┌── Phase 4 ──────────────────────────────────────┐    │
  │  │  ROADMAP_GENERATION                             │    │
  │  └─────────────────────────────────────────────────┘    │
  │         │                                               │
  │  ┌── Phase 5 (parallel) ───────────────────────────┐    │
  │  │  LEARNING_RESOURCES  NETWORKING  OPPORTUNITY    │    │
  │  └─────────────────────────────────────────────────┘    │
  └──────────────────────────────────────────────────────────┘
      │  AgentResult.output["user_profile"] (enriched)
      ▼
  Synthesizer Node → OrchestratorResult → SSE → Client
```

---

## Files Introduced

### New files

| Path | Role |
|---|---|
| `agents/src/agents/intake/models.py` | Pure domain types: `ExtractedSlot`, `SlotExtractionResult`, `ProfileDiff` |
| `agents/src/agents/intake/slot_extractor.py` | NER slot-filling component |
| `agents/src/agents/intake/profile_builder.py` | Profile merge component + completeness helpers |
| `agents/src/agents/intake/intake_agent.py` | `IntakeAgent` — extends `BaseAgent`, orchestrates the pipeline |
| `agents/src/agents/intake/__init__.py` | Public package surface |
| `agents/src/agents/intake/tests/test_intake_agent.py` | 35 unit tests (all LLM calls mocked) |

### Modified files

| Path | Change |
|---|---|
| `agents/src/agents/core/context.py` | Added `user_message: str = ""` field to `AgentContext` |
| `agents/src/agents/orchestrator/nodes/agent_dispatcher.py` | `_build_context` now passes `state["user_message"]` into every `AgentContext` |
| `agents/src/agents/bus/tasks.py` | `run_agent` Celery task extracts `user_message` from `AgentTaskInput.payload` |
| `agents/src/agents/core/observability.py` | Added 3 intake-specific Prometheus metrics |
| `agents/src/agents/orchestrator/task_planner.py` | INTAKE added as Phase 1 in `roadmap_generation` and `cv_review` DAG templates |
| `agents/pyproject.toml` | `testpaths` widened from `orchestrator/tests` to `src/agents` |

---

## Component Design

### `models.py` — Domain types

Three frozen dataclasses that carry extraction and diff data through the pipeline. They are **internal to the intake package** — nothing outside `agents.intake` imports from here.

```python
@dataclass(frozen=True, slots=True)
class ExtractedSlot:
    field_name: str
    value: Any
    confidence: float      # 0.0 – 1.0
    source_span: str       # exact substring of raw text

@dataclass(frozen=True)
class SlotExtractionResult:
    raw_text: str
    slots: list[ExtractedSlot]
    unresolved_mentions: list[str]
    overall_confidence: float

@dataclass(frozen=True)
class ProfileDiff:
    added_fields: list[str]
    updated_fields: list[str]
    unchanged_fields: list[str]
    old_completeness: float
    new_completeness: float
```

---

### `slot_extractor.py` — NER via LLM

`SlotExtractor` makes a single structured LLM call per user message. The system prompt instructs the model to behave as an NER system, filling 9 pre-defined slots:

| Slot | Type | Weight |
|---|---|---|
| `target_role` | string | highest priority |
| `current_role` | string | — |
| `skills` | array of strings | — |
| `goals` | array of strings | — |
| `constraints` | array of strings | — |
| `location` | string | — |
| `timeline_months` | integer | — |
| `weekly_hours_available` | integer | — |
| `salary_goal` | integer | — |

**Confidence gating:** any slot with `confidence < 0.7` is silently dropped by `_parse_llm_output` before it reaches `ProfileBuilder`. This prevents low-quality guesses from polluting the profile.

**Type coercion (`_coerce`):** raw LLM output is normalised to Python types:
- String fields → stripped; empty string → `None`
- List fields → split comma/semicolon-separated strings into arrays
- Integer fields → strip currency symbols and commas; `0` → `None`

**Resilience:**
- `_call_llm` is decorated with `@retry(stop_after_attempt(3), wait_exponential(...))` via tenacity.
- On any exception after all retries, `extract()` catches the error, logs a warning, and returns an empty `SlotExtractionResult` — the pipeline continues with the current profile rather than crashing.
- Empty text short-circuits immediately (no LLM call).

**Observability:**
- OTel span `intake.slot_extraction` with attributes: `slots_extracted`, `overall_confidence`, `duration_ms`
- `INTAKE_SLOT_EXTRACTION_DURATION` histogram (seconds)
- `INTAKE_SLOTS_EXTRACTED_TOTAL` counter labelled `status=success|fallback`

---

### `profile_builder.py` — Pure profile merge

`ProfileBuilder.build()` is a **pure function**: no I/O, no LLM, deterministic. It merges extracted slots onto the existing `UserProfileSnapshot` using `model_copy(update=...)` (Pydantic v2 — never mutates the original).

**Merge rules:**

| Field type | Rule |
|---|---|
| `skills`, `goals`, `constraints` | Union: new items appended; case-insensitive deduplication |
| All scalar fields | Overwrite only when new value is non-empty and differs from current |
| `additional` dict | Never touched |

The module also exposes two public helpers used by the intake agent and by the clarification engine:

```python
def completeness_score(profile: UserProfileSnapshot) -> float: ...
def missing_slots(profile: UserProfileSnapshot) -> list[str]: ...
```

`missing_slots` returns field names ordered by descending weight, matching the slot priority ordering used by `ClarificationEngine.generate_questions()`. This keeps both systems consistent.

**Observability:**
- OTel span `intake.profile_build` with attributes: `fields_added`, `fields_updated`, `old_completeness`, `new_completeness`
- `INTAKE_PROFILE_COMPLETENESS` histogram records the post-merge completeness score on every call

---

### `intake_agent.py` — Main agent

`IntakeAgent` extends `BaseAgent` and implements `_execute(context)` as a three-step sequential pipeline:

```
Step 1: slot_extraction   → SlotExtractor.extract(context.user_message)
Step 2: profile_build     → ProfileBuilder.build(context.user_profile, extraction)
Step 3: completeness_check → missing_slots(updated_profile)
```

After each step a `STEP_PROGRESS` SSE event is emitted so the browser client can display live progress (e.g., "Analysing your message…", "Building your profile…", "Assessing profile completeness…").

**Output shape** (`AgentResult.output`):

```json
{
  "user_profile": { ... },
  "completeness_score": 0.70,
  "missing_slots": ["location", "salary_goal"],
  "needs_clarification": true,
  "extracted_slots": [
    { "field_name": "target_role", "value": "ML Engineer", "confidence": 0.95, "source_span": "ML Engineer" }
  ],
  "unresolved_mentions": ["startup environment"],
  "diff": {
    "added": ["target_role", "timeline_months"],
    "updated": ["skills"],
    "old_completeness": 0.30,
    "new_completeness": 0.70
  }
}
```

Downstream agents access the enriched profile via `context.plan_snapshot["intake"]["user_profile"]`. The session layer (API side) can also persist it back to Redis via `SessionManager`.

**Constructor — dependency injection:**

```python
IntakeAgent(
    slot_extractor=SlotExtractor(llm=...),   # injectable for tests
    profile_builder=ProfileBuilder(),          # injectable for tests
    event_publisher=EventPublisher(redis),     # None → events silently skipped
    llm=ChatAnthropic(...),                    # forwarded to SlotExtractor default
)
```

**Registration at worker startup:**

```python
from redis import Redis
from agents.bus.publisher import EventPublisher
from agents.intake import IntakeAgent
from agents.core.agent_registry import registry

redis_client = Redis.from_url(settings.redis_url)
registry.register(IntakeAgent(event_publisher=EventPublisher(redis_client)))
```

---

## Infrastructure Changes

### `AgentContext` — `user_message` field

`AgentContext` gained a new optional field:

```python
user_message: str = ""
```

This is backward-compatible (default `""`). The orchestrator's `_build_context` now passes `state["user_message"]` into every context, and the Celery `run_agent` task extracts it from `AgentTaskInput.payload["user_message"]`. All agents now receive the triggering user message — the `CoachAgent` will use this for context assembly in a later sprint.

### DAG templates — INTAKE as Phase 1

`TaskPlanner._DAG_TEMPLATES` was updated so INTAKE gates the two most common flows:

**`roadmap_generation`** (before → after):
```
Before: Phase 1: CV_ANALYSIS ∥ MARKET_INTELLIGENCE → ...
After:  Phase 1: INTAKE → Phase 2: CV_ANALYSIS ∥ MARKET_INTELLIGENCE → ...
```

**`cv_review`** (before → after):
```
Before: Phase 1: CV_ANALYSIS → GAP_ANALYSIS
After:  Phase 1: INTAKE → Phase 2: CV_ANALYSIS → GAP_ANALYSIS
```

INTAKE is marked `is_required: False` in `_AGENT_SPECS`, meaning if it times out or fails after retries the dispatcher produces a `PARTIAL` result and the rest of the pipeline continues with the original profile. This keeps roadmap generation available even when the NER LLM call is degraded.

### Prometheus metrics added

| Metric | Type | Labels |
|---|---|---|
| `career_agents_intake_slot_extraction_duration_seconds` | Histogram | — |
| `career_agents_intake_slots_extracted_total` | Counter | `status` (success \| fallback) |
| `career_agents_intake_profile_completeness` | Histogram | — |

---

## Test Coverage

The test file (`tests/test_intake_agent.py`) contains **35 unit tests** organised into 7 test classes. All LLM calls are replaced with `AsyncMock` — no network required.

| Class | What is tested |
|---|---|
| `TestCoerce` | Type coercion for every slot category: strings, lists, integers, edge cases |
| `TestParseLlmOutput` | JSON→`SlotExtractionResult` conversion; low-confidence filtering; unknown fields; malformed entries |
| `TestSlotExtractorExtract` | Async extraction; empty text; LLM failure fallback; invalid JSON fallback; multi-slot extraction |
| `TestMergeList` | Union logic; case-insensitive dedup; `None` handling |
| `TestCompletenessScore` | Empty profile = 0.0; full profile = 1.0; partial scoring |
| `TestMissingSlots` | Ordering by weight; empty result on full profile |
| `TestProfileBuilderBuild` | Empty profile merge; list field union; scalar overwrite; no-change detection; goals/constraints merge |
| `TestIntakeAgent` | Agent type/display name; output key set; user_message routing; builder call args; clarification flag; progress events; no-publisher path; extracted_slots format; full `run()` wrapper via BaseAgent |

Run the full test suite:

```bash
cd agents
poetry run pytest src/agents/intake/tests/ -v
```

---

## Design Principles Applied

| Principle | How it manifests |
|---|---|
| **Low coupling** | `SlotExtractor` and `ProfileBuilder` are injected into `IntakeAgent`; neither knows about the other or about the agent framework |
| **High cohesion** | All intake logic lives inside `agents.intake`; nothing outside imports from `agents.intake.models` |
| **Statelessness** | `ProfileBuilder` is a pure function; `SlotExtractor` holds only the shared LLM client; all context flows through method arguments |
| **Graceful degradation** | LLM failure → empty extraction → original profile unchanged → downstream agents continue |
| **Observability** | OTel span per component, Prometheus metrics per LLM call outcome, STEP_PROGRESS SSE events per pipeline step |
| **Testability** | Every external dependency (LLM, Redis publisher) is constructor-injectable and has a sensible `None` default |
| **Consistency** | `completeness_score` and `missing_slots` helpers use the same slot weights as `ClarificationEngine` to prevent score drift between L2 and L3 |
