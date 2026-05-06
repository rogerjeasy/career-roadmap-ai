# Clarification Engine — Implementation Summary

**Date:** 2026-05-04
**Status:** Complete
**Author:** rogerjeasy

---

## Overview

The Clarification Engine is the component responsible for determining whether the Master Orchestrator has enough information about a user to generate a meaningful career roadmap. When the user's profile is incomplete, the engine generates targeted follow-up questions, waits for the user's answers, extracts structured values from their free-text reply, and merges those values back into the profile — all before any specialist agent is dispatched.

The engine is intentionally **stateless**: it holds no mutable data between calls. All state (round counter, questions asked, updated profile) flows through `OrchestratorState` and, across independent Celery invocations, through `OrchestratorTaskInput` passed by the API layer.

---

## Architecture Position

```
Client (Next.js)
      │  user message + profile
      ▼
FastAPI Gateway
      │  OrchestratorTaskInput
      │  (clarification_round, previous_clarification_questions)
      ▼
Celery Worker — MasterOrchestrator
      │
      ▼
  LangGraph Pipeline
  ┌──────────────────────────────────────────────────────────┐
  │  Node 1: parse_intent                                    │
  │  Node 2: score_completeness  ◄── ClarificationEngine    │
  │          │                        score()               │
  │          │                        parse_answers()  (r>0)│
  │          │                        apply_answers()  (r>0)│
  │          │                        generate_questions()  │
  │          ▼                                              │
  │   [score < threshold?] ──► CLARIFY → END (emit event)  │
  │          │                                              │
  │         proceed                                         │
  │          ▼                                              │
  │  Node 3: build_dag                                      │
  │  Node 4: dispatch_and_collect                           │
  │  Node 5: validate                                       │
  │  Node 6: synthesize                                     │
  └──────────────────────────────────────────────────────────┘
      │
      ▼
  Redis pub/sub  ──►  CLARIFICATION_REQUIRED event  ──►  Client SSE
```

---

## Files Changed or Created

| File | Status | Purpose |
|---|---|---|
| `agents/src/agents/core/observability.py` | **Created** | OTel TracerProvider + 7 Prometheus metrics for the Celery worker |
| `agents/src/agents/orchestrator/clarification_engine.py` | **Rewritten** | Full engine: score, generate, parse, apply |
| `agents/src/agents/orchestrator/nodes/completeness_scorer.py` | **Rewritten** | LangGraph node with answer-parsing on re-invocation |
| `agents/src/agents/contracts/tasks.py` | **Updated** | Added multi-turn fields to `OrchestratorTaskInput` |
| `agents/src/agents/orchestrator/orchestrator.py` | **Updated** | Seeds initial state from task input; fixed round comparison |
| `agents/src/agents/orchestrator/tests/test_clarification_engine.py` | **Created** | 36-case pytest suite |
| `agents/pyproject.toml` | **Updated** | Added OTel + Prometheus dependencies |

---

## Component Design

### `ClarificationEngine` class

One instance per `MasterOrchestrator`. Injected into `CompletenessScorerNode` at construction. Never holds user state.

```
ClarificationEngine
│
├── score(profile, *, correlation_id) → (float, list[str])
│       Deterministic slot-weighted check. O(1), no I/O.
│       Emits: OTel span · Prometheus histogram
│
├── generate_questions(profile, missing_slots, user_message, n, ...) → list[ClarificationQuestion]
│       LLM call (claude-sonnet-4-6, temp 0.2).
│       Sorts slots by descending weight so the most blocking question comes first.
│       Retries: tenacity, 3 attempts, exponential back-off (1 s → 8 s).
│       Fallback: canned questions per slot when LLM fails after all retries.
│       Emits: OTel span · questions_generated / fallback counter · duration histogram
│
├── parse_answers(questions, user_response, *, correlation_id) → dict[str, Any]
│       [NEW] LLM call to extract {field_name: value} from free-text reply.
│       Returns {} on empty input or persistent LLM failure.
│       Passes structured questions to the LLM so it can map each answer to a slot.
│       Retries: same tenacity policy as generate_questions.
│       Emits: OTel span · parse counter (success / empty / fallback) · duration histogram
│
└── apply_answers(profile, parsed_answers, *, correlation_id) → (UserProfileSnapshot, list[str])
        [NEW] Immutable profile update via Pydantic model_copy(update=...).
        Merge rules:
          · skills — union with existing list, deduplication, original order preserved.
          · all other slots — overwrite (LLM only returns clearly answered values).
        Fires CLARIFICATION_RESOLVED_TOTAL metric when new score ≥ threshold.
        Emits: OTel span · applied/resolved attributes
```

### `ClarificationQuestion` dataclass

Frozen dataclass replacing the raw `dict` previously threaded through state.

```python
@dataclass(frozen=True)
class ClarificationQuestion:
    question: str
    field_name: str
    priority: int = 1
    id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def to_dict(self) -> dict[str, Any]: ...
    @classmethod
    def from_dict(cls, d) -> ClarificationQuestion: ...
```

Stored as dicts in `OrchestratorState` (JSON-serialisable) and converted to/from the dataclass at the node boundary.

---

## Slot Weights

```
target_role           0.30   (most blocking — defines the entire roadmap shape)
current_role          0.15
skills                0.15
timeline_months       0.15
location              0.10
weekly_hours_available 0.10
salary_goal           0.05
                      ────
Total                 1.00
```

The completeness threshold is `0.75` (configurable via `COMPLETENESS_THRESHOLD` env var). Questions are generated in descending weight order so the user is never asked about salary before role and timeline.

---

## Multi-Turn Clarification Flow

Previously, `OrchestratorTaskInput` had no way to carry round state across independent Celery invocations. Every run started with `clarification_round=0`, making the round cap unreachable.

Two fields were added to `OrchestratorTaskInput`:

```python
clarification_round: int = 0
previous_clarification_questions: list[dict[str, Any]] = []
```

The API layer is responsible for:
1. Storing the `clarification_questions` returned in `OrchestratorResult` after a `CLARIFICATION_REQUIRED` event.
2. On re-invocation: passing `clarification_round=N+1` and the stored questions as `previous_clarification_questions`.

The orchestrator seeds those into `OrchestratorState` so `CompletenessScorerNode` can parse the user's answers without any additional API calls.

### Round lifecycle

```
Round 0  →  score < threshold  →  generate questions  →  emit CLARIFICATION_REQUIRED
                                                               │
                                      user answers ←──────────┘
                                              │
Round 1  →  parse_answers()                  │
         →  apply_answers()      ←───────────┘
         →  re-score
         →  if still < threshold AND round ≤ max: generate new questions
         →  if ≥ threshold OR round > max: proceed to build_dag
```

The round counter is **pre-incremented by the scorer node** before writing back to state, so `_should_clarify` compares `round ≤ max_clarification_rounds` (not `< max`).

---

## Observability

### OpenTelemetry Spans

Every public method on `ClarificationEngine` and `CompletenessScorerNode` opens a named span:

| Span name | Key attributes |
|---|---|
| `clarification.score` | `score`, `missing_count`, `missing_slots`, `correlation_id` |
| `clarification.generate_questions` | `missing_count`, `intent_type`, `questions_generated`, `duration_ms` |
| `clarification.parse_answers` | `questions_count`, `fields_extracted`, `fields`, `duration_ms` |
| `clarification.apply_answers` | `candidates`, `applied_count`, `applied_fields`, `old_score`, `new_score`, `resolved` |
| `node.completeness_scorer` | `clarification_round`, `score`, `questions_count`, `fields_applied` |

Failed LLM calls record the exception on the span (`span.record_exception`) and set `StatusCode.ERROR`. Fallback paths set `StatusCode.OK` so dashboards do not alert on expected degraded-mode operation.

### Prometheus Metrics

| Metric | Type | Labels | Description |
|---|---|---|---|
| `career_agents_clarification_score` | Histogram | — | Score distribution at every scoring call |
| `career_agents_clarification_questions_total` | Counter | `status` (generated\|fallback\|skipped) | Question-generation outcomes |
| `career_agents_clarification_answer_parse_total` | Counter | `status` (success\|empty\|fallback) | Answer-parsing outcomes |
| `career_agents_clarification_answer_parse_duration_seconds` | Histogram | — | LLM latency for answer parsing |
| `career_agents_question_generation_duration_seconds` | Histogram | — | LLM latency for question generation |
| `career_agents_clarification_round_total` | Counter | — | Clarification rounds initiated |
| `career_agents_clarification_resolved_total` | Counter | — | Rounds that lifted the profile above threshold |

### Structured Logging

All log events use `structlog` with `correlation_id` and `session_id` bound at the call site:

```
clarification.scored          score=0.45  missing=[skills, location, ...]
clarification.questions_generated  count=3  slots=[...]  duration_ms=812
clarification.answers_parsed  fields=[target_role, skills]  duration_ms=634
clarification.profile_updated  applied=[target_role]  old_score=0.30  new_score=0.60  resolved=false
```

---

## Resilience

### LLM retry policy (both `generate_questions` and `parse_answers`)

```python
@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=0.5, min=1, max=8),
    retry=retry_if_exception_type(Exception),
    reraise=True,
)
```

Total worst-case wait before giving up: ~1 s + ~2 s + ~4 s = **~7 seconds** of back-off plus three LLM round-trips. After all retries are exhausted, both methods fall back gracefully:

- `generate_questions` → returns canned questions from `_fallback_question()`.
- `parse_answers` → returns `{}`, leaving the profile unchanged for this round.

### Type coercion (`_coerce_parsed_values`)

The LLM output is normalised before being handed to `apply_answers`:

| Field type | Normalisation |
|---|---|
| `target_role`, `current_role`, `location` | `.strip()`, reject empty strings |
| `skills` | Split on `,` / `;` if string; filter empty items |
| `timeline_months`, `weekly_hours_available`, `salary_goal` | Coerce `float → int`; strip currency symbols from strings |

Invalid or unparseable values are silently skipped rather than raising, so a partial LLM response still contributes useful data.

---

## Test Coverage

`agents/src/agents/orchestrator/tests/test_clarification_engine.py` — **36 test cases**, all unit tests with mocked LLM. No network required.

| Class | What it covers |
|---|---|
| `TestClarificationQuestion` | `to_dict` / `from_dict` round-trip, unique ID generation |
| `TestScore` | Full/empty/partial profiles, empty-list skills, determinism |
| `TestGenerateQuestions` | LLM path, fallback path, `n` cap, weight-based slot priority |
| `TestParseAnswers` | Structured extraction, empty inputs, LLM failure, int coercion |
| `TestApplyAnswers` | Empty profile, immutability, skill union, unknown fields, `None` values, overwrite |
| `TestCoerceParsedValues` | Whitespace strip, comma/semicolon split, float→int, salary string, None/unknown |
| `TestFastScore` | Agreement with `score()`, zero for empty profile |
| `TestFallbackQuestion` | Known and unknown slot names |
| `TestClarificationRoundTrip` | Full score → generate → parse → apply cycle verifying score improvement |

---

## Configuration

All tunable values come from `AgentSettings` (read from `.env`):

| Variable | Default | Description |
|---|---|---|
| `COMPLETENESS_THRESHOLD` | `0.75` | Minimum score to proceed without clarification |
| `MAX_CLARIFICATION_ROUNDS` | `3` | Maximum times the engine can ask for more information |
| `MAX_CLARIFICATION_QUESTIONS` | `3` | Maximum questions per round |
| `CLARIFICATION_MODEL` | `claude-sonnet-4-6` | Model used for question generation and answer parsing |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | _(unset)_ | gRPC endpoint for OTel export in non-dev environments |

---

## Design Decisions

**Stateless engine over stateful service.** All state flows through `OrchestratorState` and `OrchestratorTaskInput`. This makes the engine independently testable, trivially horizontally scalable across Celery workers, and free of race conditions.

**Separate `parse_answers` / `apply_answers` methods.** Keeping extraction and merging separate allows callers (API intake, tests) to use either step independently, and makes it easy to inject custom coercion logic without touching the LLM path.

**Pre-increment the round counter in the node.** The scorer node increments `clarification_round` before writing it back to state. This means `_should_clarify` always sees the post-round value and the comparison `round ≤ max_clarification_rounds` is unambiguous regardless of whether the graph loops internally or the API re-invokes the orchestrator externally.

**Fallback to canned questions rather than failing.** Clarification is on the critical path for every new user. A failed LLM call that produces no questions would permanently block roadmap generation. Canned fallback questions keep the user experience intact even during LLM outages.

**Skills use union merge, scalars use overwrite.** A user who answered "Python" in round 1 and "TensorFlow" in round 2 should have both in their profile. All other fields are scalar so overwrite is the correct semantic.
