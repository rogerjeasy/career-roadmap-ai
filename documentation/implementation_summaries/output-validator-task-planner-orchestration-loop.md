# Output Validator, Task Planner & Orchestration Loop — Implementation Summary

**Date:** 2026-05-05
**Status:** Complete
**Author:** rogerjeasy

---

## Overview

This implementation completes three interrelated components of the Master Orchestrator pipeline:

1. **Output Validator** — a three-stage LLM pipeline that checks realism, detects hallucinations against agent data, and scores per-step confidence for each roadmap phase.
2. **Task Planner** — extended with per-agent retry policies, required/optional flags, and automatic phase numbering.
3. **Orchestration Loop** — the full 8-step Celery pipeline is now observable end-to-end: every LangGraph node emits a `STEP_PROGRESS` SSE event, agents retry with exponential backoff on failure, and the validation report flows through to synthesis.

---

## Architecture Position

```
Celery Worker — MasterOrchestrator
│
├── Step 1: parse_intent          ──► STEP_PROGRESS event (0/6)
├── Step 2: score_completeness    ──► STEP_PROGRESS event (1/6)
│   │   [score < threshold?] ──► CLARIFICATION_REQUIRED → END
│   └── [complete] ──────────────────────────────────────────┐
├── Step 3: build_dag             ──► STEP_PROGRESS event (2/6)
│   └── TaskPlanner.build()                                  │
│       └── per-agent: phase, is_required, retry_policy     │
├── Step 4: dispatch_and_collect  ──► STEP_PROGRESS event (3/6)
│   └── AgentDispatcherNode                                  │
│       ├── Kahn topological phases → asyncio.gather        │
│       └── per-agent: wait_for timeout + retry backoff     │
├── Step 5: validate              ──► STEP_PROGRESS event (4/6)
│   └── OutputValidatorNode → OutputValidator.validate()    │
│       ├── Stage 1: Realism + Coherence  (LLM, temp=0)    │
│       └── Stage 2+3 concurrent:                          │
│           ├── Stage 2: Grounding check   (LLM, temp=0)  │
│           └── Stage 3: Per-step conf.   (LLM, temp=0)  │
├── Step 6: synthesize            ──► STEP_PROGRESS event (5/6)
│   └── SynthesizerNode (injects step_confidences + unverified_claims)
│
└── ORCHESTRATION_COMPLETED / ORCHESTRATION_FAILED event
```

---

## Files Changed or Created

| File | Status | Description |
|---|---|---|
| `agents/src/agents/orchestrator/output_validator.py` | **Rewritten** | Promoted from 11-line facade to full 3-stage validation module |
| `agents/src/agents/orchestrator/nodes/synthesizer.py` | **Rewritten** | `OutputValidatorNode` now delegates to real module; Synthesizer injects validation context |
| `agents/src/agents/orchestrator/nodes/agent_dispatcher.py` | **Rewritten** | Full retry loop with `asyncio.wait_for` timeout, exponential backoff, OTel per-attempt |
| `agents/src/agents/orchestrator/task_planner.py` | **Rewritten** | `_AGENT_SPECS`, `_compute_phases()`, extended `TaskNode` fields |
| `agents/src/agents/orchestrator/state.py` | **Updated** | `TaskNode` gains `phase`, `is_required`, `retry_policy`; `OrchestratorState` gains `validation_report` |
| `agents/src/agents/orchestrator/orchestrator.py` | **Updated** | `_with_progress` wrapper; `make_output_validator_node`; `validation_report` in initial state |
| `agents/src/agents/core/observability.py` | **Updated** | 7 new Prometheus metrics for dispatch and validation |
| `agents/src/agents/orchestrator/tests/test_output_validator.py` | **Created** | 30-case test suite |
| `agents/src/agents/orchestrator/tests/test_orchestrator.py` | **Created** | 26-case test suite (TaskPlanner + _AGENT_SPECS) |

---

## Output Validator — Three-Stage Pipeline

### Stage 1: Realism + Coherence (sequential gate)
- Single LLM call (`claude-haiku`, temp=0, max_tokens=1024)
- Returns `{realism_passed, coherence_passed, notes[]}`
- **Gate**: if BOTH fail → early exit; Stages 2+3 are skipped (saves ~2 LLM calls on clearly bad roadmaps)
- Fallback on error: permissive (`True, True, []`) so a single LLM outage doesn't block the pipeline

### Stage 2: Grounding Check (concurrent with Stage 3)
- Receives: `agent_data` (completed agent outputs) + `roadmap` (synthesised JSON)
- LLM identifies claims not traceable to any agent output
- Returns `{grounding_score ∈ [0,1], unverified_claims[]}`
- `passed` requires `grounding_score >= 0.5` (configurable: `_GROUNDING_THRESHOLD`)
- Fallback on error: `(1.0, [])` — permissive

### Stage 3: Per-step Confidence (concurrent with Stage 2)
- LLM scores each roadmap phase 0.0–1.0 for achievability
- Returns `list[StepConfidence]` — one per phase, same order as roadmap
- `mean_step_confidence` is computed as arithmetic mean
- Fallback on error: all phases get `confidence=0.5`

### ValidationReport schema

```python
@dataclass
class ValidationReport:
    realism_passed: bool
    coherence_passed: bool
    stage1_notes: list[str]       # ≤ 3 items

    grounding_score: float        # 0.0–1.0
    unverified_claims: list[str]  # claims flagged by Stage 2

    step_confidences: list[StepConfidence]   # per-phase from Stage 3
    mean_step_confidence: float

    passed: bool    # True iff realism AND coherence AND grounding >= 0.5
    notes: list[str]             # aggregated from all stages
    validation_duration_ms: int

    def to_dict(self) -> dict:  # JSON-serialisable for OrchestratorState
```

```python
@dataclass
class StepConfidence:
    phase_index: int
    phase_title: str
    confidence: float  # 0.0–1.0
    reasoning: str     # ≤ 1 sentence
```

### Synthesiser integration
The `SynthesizerNode` now receives `step_confidences` and `unverified_claims` from the validation report in its context. Its system prompt instructs it to:
- Embed the confidence score on each phase object in the output JSON
- Add a low-confidence warning milestone for phases scoring below 0.5

---

## Task Planner — Retry Policies & Phase Assignment

### Per-agent specs (`_AGENT_SPECS`)

Every `AgentType` has an entry with:
- `is_required: bool` — if `True`, agent failure makes `OrchestratorResult.status = FAILED`
- `retry_policy: dict` — `{max_attempts, timeout_seconds, backoff_seconds}`

| Agent | Required | Max Attempts | Timeout (s) | Backoff (s) |
|---|---|---|---|---|
| CV_ANALYSIS | Yes | 3 | 60 | 2.0 |
| GAP_ANALYSIS | Yes | 3 | 60 | 2.0 |
| ROADMAP_GENERATION | Yes | 3 | 120 | 4.0 |
| COACH | Yes | 3 | 90 | 3.0 |
| MARKET_INTELLIGENCE | No | 2 | 90 | 3.0 |
| LEARNING_RESOURCES | No | 2 | 60 | 2.0 |
| NETWORKING | No | 2 | 45 | 2.0 |
| OPPORTUNITY | No | 2 | 60 | 2.0 |
| PROGRESS | No | 2 | 45 | 2.0 |
| INTAKE | No | 2 | 30 | 1.0 |

### Automatic phase assignment (`_compute_phases`)
BFS over the dependency graph. All agents with no dependencies = Phase 1. Agents whose dependencies are all in Phase N = Phase N+1. For `roadmap_generation`:

```
Phase 1 (parallel): CV_ANALYSIS, MARKET_INTELLIGENCE
Phase 2 (serial):   GAP_ANALYSIS
Phase 3 (serial):   ROADMAP_GENERATION
Phase 4 (parallel): LEARNING_RESOURCES, NETWORKING, OPPORTUNITY
```

Phase numbers are written into each `TaskNode` so the dispatcher and monitoring tools can group events by phase without re-computing the graph.

---

## Agent Dispatcher — Retry + Timeout

### Retry loop per agent

```
for attempt in 1..max_attempts:
    with OTel span "agent.dispatch" (agent_type, attempt):
        try:
            result = await asyncio.wait_for(agent.run(ctx), timeout=timeout_sec)
            break  ← success
        except TimeoutError:
            AGENT_DISPATCH_DURATION(agent, "timeout")
            AGENT_RETRY_TOTAL(agent)
        except Exception:
            AGENT_DISPATCH_DURATION(agent, "failed")
            AGENT_RETRY_TOTAL(agent)
    
    if attempt < max_attempts:
        await asyncio.sleep(min(backoff_sec × 2^(attempt-1), 30))

if result is None:
    if is_required → FAILED result
    else           → PARTIAL result + AGENT_SKIP_TOTAL.inc()
```

Key points:
- `asyncio.wait_for` wraps a **single attempt** — each attempt gets a fresh timeout budget
- Backoff: `backoff_seconds × 2^(attempt-1)`, capped at 30 s
- Non-required agents that fail all retries → `PARTIAL` with `{"stub": True, "skipped": True}`
- Synthesis proceeds regardless (ResultAggregator handles partial results)
- Each attempt is its own OTel span so trace shows per-attempt latency

---

## Step Progress Events (STEP_PROGRESS)

Every LangGraph node is wrapped by `_with_progress()` at graph construction time. The wrapper emits a `STEP_PROGRESS` event before delegating to the node:

```json
{
  "event_type": "step_progress",
  "payload": {
    "step_name": "dispatch_and_collect",
    "step_index": 3,
    "total_steps": 6,
    "pct": 50
  }
}
```

The API layer forwards these via SSE so the frontend can display a progress bar. Wrapping is done in `orchestrator._build_graph()` — individual node classes remain clean and unaware of the event bus.

Step sequence:

| Index | Name | % |
|---|---|---|
| 0 | parse_intent | 0% |
| 1 | score_completeness | 17% |
| 2 | build_dag | 33% |
| 3 | dispatch_and_collect | 50% |
| 4 | validate | 67% |
| 5 | synthesize | 83% |
| — | ORCHESTRATION_COMPLETED | 100% |

---

## Observability

### New Prometheus Metrics

| Metric | Type | Labels | Description |
|---|---|---|---|
| `career_agents_agent_dispatch_duration_seconds` | Histogram | `agent_type`, `status` | Per-agent wall-clock time including retries |
| `career_agents_agent_retry_total` | Counter | `agent_type` | Total retry attempts across all agents |
| `career_agents_agent_skip_total` | Counter | `agent_type` | Optional agents skipped after all retries |
| `career_agents_validation_stage_duration_seconds` | Histogram | `stage` | LLM latency per validation stage |
| `career_agents_validation_grounding_score` | Histogram | — | Distribution of grounding scores |
| `career_agents_validation_passed_total` | Counter | `result` (passed\|failed) | Validation outcomes |
| `career_agents_step_progress_total` | Counter | `step_name` | Pipeline step executions |

### OTel Spans

| Span | Key Attributes |
|---|---|
| `output_validator.validate` | `session_id`, `passed`, `grounding_score`, `duration_ms` |
| `output_validator.stage1` | `realism_passed`, `coherence_passed` |
| `output_validator.stage2` | `grounding_score`, `unverified_count` |
| `output_validator.stage3` | `phases_scored` |
| `agent.dispatch` | `agent_type`, `attempt`, `timeout_seconds`, `duration_ms` |
| `task_planner.build` | `intent_type`, `dag_size`, `phases`, `required_agents` |
| `node.output_validator` | `session_id`, `passed` |
| `node.synthesizer` | `session_id`, `has_phases` |

---

## Test Coverage

### `test_output_validator.py` — 30 test cases

| Class | What it covers |
|---|---|
| `TestValidationReport` | `to_dict()` JSON safety, step_confidences serialisation |
| `TestFailedReport` | Early-exit report fields |
| `TestStage1` | Passed/failed realism, fallback permissiveness, notes cap at 3 |
| `TestStage2` | Score extraction, clamp high/low, fallback on error |
| `TestStage3` | Per-phase confidences, empty phases, fallback default 0.5, confidence clamp |
| `TestValidate` | Full pass, early exit (1 LLM call only), grounding fail, notes warnings, serialisability |
| `TestFactory` | `make_output_validator` returns correct type |

### `test_orchestrator.py` — 26 test cases

| Class | What it covers |
|---|---|
| `TestComputePhases` | No-dep → phase 1, dep chain → phase 2, full roadmap phase structure |
| `TestTaskPlannerBuild` | All 6 intent types, unknown intent fallback, retry policies, required flags, phase numbers, task ID uniqueness, PROGRESS skip/include, dependency wiring, phase ordering invariant, max phase = 4 |
| `TestAgentSpecs` | All AgentTypes have spec, required keys present, boolean types, sensible values |

---

## Design Decisions

**Why `asyncio.wait_for` per attempt rather than per retry loop?**
Each attempt gets an independent timeout budget. A slow first attempt that times out at 60 s should not prevent the second attempt from also getting a full 60 s. If the timeout wrapped the whole loop, a single slow attempt would consume the budget for all retries.

**Why skip Stages 2+3 when Stage 1 fails both checks?**
Stage 1 failing both realism AND coherence means the roadmap is fundamentally unusable — grounding check and per-step scoring would be nonsensical on an unrealistic, incoherent roadmap. Skipping saves ~2 LLM calls and keeps latency low in the worst-case path.

**Why store `validation_report` as `dict` in `OrchestratorState`?**
LangGraph serialises state to JSON between checkpoints. A `dataclass` or Pydantic model instance would survive in-memory but fail across checkpoint boundaries. `ValidationReport.to_dict()` makes the serialisation boundary explicit.

**Why wrap nodes in `_with_progress` rather than putting event emission inside each node?**
Nodes are independently testable units with no knowledge of the event bus. The wrapping approach keeps nodes clean and ensures STEP_PROGRESS is emitted for every node uniformly, with no risk of individual nodes forgetting to emit.

**Why `_compute_phases` instead of hardcoding phase numbers?**
Phase numbers are derived from the dependency graph — they're not an independent property of each agent. Hardcoding them would mean any template change requires updating two places. `_compute_phases` is O(n²) on a 7-node graph (negligible) and keeps phase numbers consistent with execution order by construction.

**Non-required agents return PARTIAL, not FAILED.**
`ResultAggregator` already handles `PARTIAL` results by including them with a `_partial: True` flag. The synthesiser can generate a useful roadmap without market intelligence or networking data. Returning `FAILED` for optional agents would degrade the overall `OrchestratorResult.status` unnecessarily.
