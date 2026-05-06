# Progress & Adaptation Agent — Implementation Summary

**Layer:** L3 Specialist Agent (WORKERS)  
**Package:** `agents/src/agents/progress/`  
**Agent type:** `AgentType.PROGRESS`  
**Date:** 2026-05-06  
**Status:** Complete

---

## 1. Purpose

The Progress & Adaptation Agent monitors how closely a user is following their active career roadmap and proposes concrete, evidence-based changes when the plan and reality diverge. It replaces the static "roadmap is delivered once" model with a continuous adaptation loop.

It is triggered:

- **Weekly** — by a Celery beat schedule that passes the latest scorecard data through the pipeline.
- **On demand** — by the Master Orchestrator when a user opens the progress dashboard or asks the coach agent about their trajectory.
- **By the market intelligence flow** — when the `MarketIntelligenceAgent` detects a significant shift and the orchestrator decides a plan review is warranted.

---

## 2. Responsibilities

| Responsibility | Where it lives |
|---|---|
| Compute how far the user has drifted from the plan | `DriftDetector` |
| Measure habit consistency and streaks | `HabitStreakAnalyser` |
| Propose targeted plan changes (LLM) | `AdaptationProposer` |
| Orchestrate all three steps and emit SSE events | `ProgressAgent` |
| Emit OTel spans and Prometheus metrics | All components |

---

## 3. Three-Step Pipeline

```
ProgressAgent._execute(context)
│
├─ [Step 1] DriftDetector.detect(scorecards, planned_milestones)
│     Pure computation — no LLM, no I/O
│     Output → DriftAnalysis
│
├─ [Step 2] HabitStreakAnalyser.analyse(scorecards)
│     Pure computation — no LLM, no I/O
│     Output → list[HabitStreak]
│
└─ [Step 3] AdaptationProposer.propose(drift, streaks, plan_snapshot, profile_summary)
      LLM call (claude-sonnet-4-6) → structured JSON
      Heuristic fallback if LLM fails
      Output → list[AdaptationProposal]
```

Each step emits a `STEP_PROGRESS` SSE event so the browser shows live progress.

---

## 4. File Structure

```
agents/src/agents/progress/
├── __init__.py                  # Public surface: from agents.progress import ProgressAgent
├── models.py                    # Domain models — pure data, no I/O
├── drift_detector.py            # Step 1: drift score computation
├── habit_streak_analyser.py     # Step 2: streak and completion-rate statistics
├── adaptation_proposer.py       # Step 3: LLM-based adaptation proposals
├── progress_agent.py            # Orchestrating BaseAgent subclass
└── tests/
    ├── __init__.py
    └── test_progress_agent.py   # 60+ unit tests, zero real API calls
```

`agents/src/agents/core/observability.py` — 7 new Prometheus metrics appended.

---

## 5. Domain Models (`models.py`)

### Enums

```python
class DriftSeverity(str, Enum):
    ON_TRACK = "on_track"   # drift_score < 0.20
    MINOR    = "minor"      # 0.20 – 0.39
    MODERATE = "moderate"   # 0.40 – 0.64
    SEVERE   = "severe"     # ≥ 0.65

class AdaptationType(str, Enum):
    PACE_ADJUSTMENT     # slow / accelerate milestone cadence
    MILESTONE_REORDER   # change ordering based on dependencies
    SCOPE_REDUCTION     # defer or drop lower-priority items
    RESOURCE_SWAP       # replace learning resources
    HABIT_RESET         # reduce habit frequency to rebuild consistency
    FULL_REGENERATION   # re-trigger the full roadmap generation pipeline
```

### Key dataclasses

| Dataclass | Fields |
|---|---|
| `WeeklyScorecard` | `week_start_date`, `milestones_planned`, `milestones_completed`, `habit_completions: dict[str, bool]`, `hours_spent`, `planned_hours`, `notes`, `blockers` |
| `HabitStreak` | `habit_name`, `current_streak_weeks`, `longest_streak_weeks`, `completion_rate`, `total_weeks_tracked`, `weeks_completed` |
| `DriftAnalysis` | `drift_score`, `drift_severity`, `milestone_completion_rate`, `hours_variance`, `stalled_milestones`, `at_risk_milestones`, `weeks_analysed`, `evidence` |
| `AdaptationChange` | `change_type` (pace/remove/swap/defer/reset), `target`, `description`, `rationale`, `priority` |
| `AdaptationProposal` | `adaptation_type`, `trigger_reason`, `changes: list[AdaptationChange]`, `confidence`, `requires_regeneration`, `summary` |

---

## 6. Step 1 — Drift Detector (`drift_detector.py`)

Pure computation — no LLM calls, safe to test with no mocks.

### Algorithm

```
completed_set  = union of milestones_completed across all scorecards
milestone_rate = len(planned ∩ completed) / len(planned)   # 0–1
hours_variance = sum(hours_spent) − sum(planned_hours)

# Only penalise under-delivery; over-delivery is not drift
hours_score = max(0, −hours_variance) / max(total_planned, 1)  # 0–1

drift_score = milestone_shortfall × 0.65 + hours_score × 0.35   # bounded 0–1
```

**Severity bands:**

| Band | Range |
|---|---|
| `on_track` | drift_score < 0.20 |
| `minor` | 0.20 – 0.39 |
| `moderate` | 0.40 – 0.64 |
| `severe` | ≥ 0.65 |

**Outputs per run:**
- `stalled_milestones` — planned but never completed across any scorecard.
- `at_risk_milestones` — planned in the most recent scorecard but still open.
- `evidence` — one-sentence human-readable summary (used by the LLM in Step 3).

---

## 7. Step 2 — Habit Streak Analyser (`habit_streak_analyser.py`)

Pure computation — no LLM calls.

### Algorithm

For each habit name seen across all scorecards:

1. Build a boolean completion vector, one entry per scorecard (oldest → newest). If a habit is absent in a given week, it counts as `False`.
2. **Current streak** — count backwards from the most recent entry while `True`.
3. **Longest streak** — forward scan tracking the longest unbroken run of `True`.
4. **Completion rate** — `weeks_completed / total_weeks_tracked`.

Results are sorted alphabetically by habit name for deterministic output.

---

## 8. Step 3 — Adaptation Proposer (`adaptation_proposer.py`)

LLM-based. Falls back to rule-based heuristics on any LLM failure (network error, invalid JSON, timeout).

### LLM contract

**Model:** `claude-sonnet-4-6` (via `agent_settings.clarification_model`)  
**Temperature:** 0.2 (low — proposals must be concrete and predictable)  
**Max tokens:** 2048  
**Retries:** 3 attempts with exponential backoff (tenacity)

**System prompt guidance:**

| Drift severity | LLM instruction |
|---|---|
| `on_track` | 0–1 minor optimisations |
| `minor` | 1–2 pace adjustments or habit resets |
| `moderate` | 2–3 changes including possible scope reduction |
| `severe` | scope reduction and/or full regeneration |

`requires_regeneration = true` only when `drift_score > 0.70` or `stalled_milestones > 3`.

### Context message sent to the LLM

```
User profile: Target: ML Engineer, Current: Software Engineer, Timeline: 12 months, Weekly capacity: 10h

Drift analysis:
  drift_score: 0.52 (moderate)
  milestone_completion_rate: 38%
  hours_variance: -8.0h
  weeks_analysed: 4
  stalled_milestones: ML Fundamentals Course, Portfolio Project
  at_risk_milestones: System Design Study
  evidence: Analysed 4 week(s): 3 milestone(s) completed, 2 stalled. Hours variance: -8.0h.

Habits with <50% completion rate: Daily coding, Reading technical papers

Propose the minimum set of adaptations to bring the plan back on track.
```

### Heuristic fallback rules

| Condition | Proposal generated |
|---|---|
| `minor` or `moderate` drift | `PACE_ADJUSTMENT` — defer the top stalled milestone |
| Any habit with `completion_rate < 0.4` | `HABIT_RESET` — up to 2 habits reset |
| `severe` drift or `stalled_milestones > 3` | `FULL_REGENERATION` with `requires_regeneration = True` |

---

## 9. Agent Output Schema

`AgentResult.output` dict returned by `ProgressAgent._execute()`:

```json
{
  "drift_analysis": {
    "drift_score": 0.52,
    "drift_severity": "moderate",
    "milestone_completion_rate": 0.38,
    "hours_variance": -8.0,
    "stalled_milestones": ["ML Fundamentals Course", "Portfolio Project"],
    "at_risk_milestones": ["System Design Study"],
    "weeks_analysed": 4,
    "evidence": "Analysed 4 week(s): 3 milestone(s) completed, 2 stalled. Hours variance: -8.0h."
  },
  "habit_streaks": [
    {
      "habit_name": "Daily coding",
      "current_streak_weeks": 1,
      "longest_streak_weeks": 3,
      "completion_rate": 0.375,
      "total_weeks_tracked": 8,
      "weeks_completed": 3
    }
  ],
  "adaptations": [
    {
      "adaptation_type": "pace_adjustment",
      "trigger_reason": "User is completing only 38% of planned milestones over 4 weeks.",
      "confidence": 0.82,
      "requires_regeneration": false,
      "summary": "Reduce weekly milestone target to 1 per week until capacity recovers.",
      "changes": [
        {
          "change_type": "defer",
          "target": "ML Fundamentals Course",
          "description": "Move completion target from Week 4 to Week 6.",
          "rationale": "Consistent under-delivery on this milestone suggests the timeline was too aggressive.",
          "priority": 1
        }
      ]
    }
  ],
  "requires_regeneration": false,
  "analysis_summary": "Drift: moderate (score=0.52, 4 week(s) analysed). 2 stalled milestone(s): ML Fundamentals Course, Portfolio Project. 1 habit(s) below 50% completion: Daily coding. Proposed 1 adaptation(s): pace_adjustment.",
  "processing_steps": ["drift_detection", "habit_analysis", "adaptation_proposals"]
}
```

---

## 10. Context Input Contract

The agent reads from `AgentContext.plan_snapshot`. The orchestrator must populate these keys before dispatch:

| Key | Type | Description |
|---|---|---|
| `scorecards` | `list[dict]` | Weekly scorecard history — see schema below |
| `planned_milestones` | `list[str]` | Milestone names expected to be complete by now |
| `target_role` | `str` | Forwarded to the LLM for context |
| `active_plan` | `dict` | Full plan snapshot (phases, milestones) for richer LLM context |

### Scorecard dict schema

```json
{
  "week_start_date": "2026-04-07",
  "milestones_planned": ["ML Fundamentals Course"],
  "milestones_completed": [],
  "habit_completions": {
    "Daily coding": true,
    "Reading": false
  },
  "hours_spent": 4.5,
  "planned_hours": 10.0,
  "notes": "Busy week at work",
  "blockers": ["Work deadline"]
}
```

Invalid or missing `week_start_date` strings default to `date.today()`. Scorecards are sorted by `week_start_date` before processing.

---

## 11. `requires_regeneration` Flag

When any `AdaptationProposal` sets `requires_regeneration = True`, the flag is hoisted to the top-level output key `requires_regeneration: true`. The orchestrator checks this flag and can re-trigger the full roadmap generation pipeline (`AgentType.ROADMAP_GENERATION`) with the latest user profile and market signals.

Conditions that produce `requires_regeneration = True`:

- `drift_score > 0.70` (configured in `AdaptationProposer` system prompt)
- `len(stalled_milestones) > 3` (heuristic fallback)
- The LLM itself decides the situation warrants a full re-plan

---

## 12. Observability

### OTel spans

| Span | Attributes |
|---|---|
| `progress.execute` | `session_id`, `user_id`, `correlation_id`, `scorecard_count`, `planned_milestone_count`, `drift_score`, `drift_severity`, `habit_count`, `adaptation_count`, `requires_regeneration` |
| `progress.propose_adaptations` | `correlation_id`, `drift_score`, `drift_severity`, `proposal_count`, `duration_ms` |

### Prometheus metrics

| Metric | Type | Description |
|---|---|---|
| `career_agents_progress_drift_score` | Histogram | Drift score distribution (0–1) |
| `career_agents_progress_drift_detection_duration_seconds` | Histogram | Wall-clock time — pure computation |
| `career_agents_progress_habit_analysis_duration_seconds` | Histogram | Wall-clock time — pure computation |
| `career_agents_progress_adapt_duration_seconds` | Histogram | Wall-clock time — LLM adaptation call |
| `career_agents_progress_adapt_total` | Counter | LLM calls by method (`llm` / `fallback`) |
| `career_agents_progress_adapt_count` | Histogram | Proposals generated per run (0–5) |
| `career_agents_progress_regen_total` | Counter | Runs where full regeneration was recommended |

### Structured log events

| Event | Level | Key fields |
|---|---|---|
| `progress.analysis_completed` | INFO | `drift_score`, `drift_severity`, `habit_count`, `adaptation_count`, `requires_regeneration`, `scorecard_count` |
| `drift_detector.completed` | INFO | `drift_score`, `drift_severity`, `milestone_completion_rate`, `stalled_count`, `weeks_analysed` |
| `habit_streak_analyser.completed` | INFO | `habit_count`, `scorecard_count` |
| `progress.adaptations_proposed` | INFO | `proposal_count`, `drift_severity`, `requires_regeneration`, `duration_ms` |
| `progress.adapt_llm_failed` | WARNING | `error`, `drift_score`, `fallback="heuristic"` |
| `progress.progress_emit_failed` | WARNING | `step`, `error` |

---

## 13. Design Decisions

### Low coupling via constructor DI

All three sub-components are injected through the constructor. This means:

- Each component can be unit-tested in complete isolation with no mocks beyond its own dependencies.
- A different drift algorithm or a different LLM client can be swapped in without touching `ProgressAgent`.
- The orchestrator only sees `BaseAgent` — it has no knowledge of the internal pipeline.

### Pure computation first

`DriftDetector` and `HabitStreakAnalyser` are deterministic, synchronous functions with no external calls. This makes them:

- **Fast** — milliseconds, not seconds.
- **Testable** — zero mocks needed.
- **Reliable** — no LLM quota, no network dependency.

The LLM is only introduced at Step 3 where natural language reasoning genuinely adds value (understanding context, weighing trade-offs, writing human-readable change descriptions).

### Heuristic fallback is not a degraded path

The heuristic fallback covers all four severity bands and produces structured `AdaptationProposal` objects identical in shape to the LLM output. A frontend consuming the agent output cannot distinguish LLM proposals from heuristic ones — reliability is preserved end-to-end.

### Drift score weighting

`drift_score = completion_shortfall × 0.65 + hours_score × 0.35`

Milestone completion is weighted higher than hours because hours under-delivery is often a reporting artefact (people forget to log time), while stalled milestones are a concrete, objective signal. Over-delivery on hours does not reduce the drift score.

---

## 14. Registration (Celery worker startup)

```python
from agents.progress import ProgressAgent
from agents.core.agent_registry import registry
from agents.bus.publisher import EventPublisher

registry.register(
    ProgressAgent(event_publisher=EventPublisher(redis_client))
)
```

Once registered, the generic `run_agent` Celery task dispatches to it automatically via `registry.get(AgentType.PROGRESS)`.

---

## 15. Test Coverage

**File:** `agents/src/agents/progress/tests/test_progress_agent.py`  
**Test count:** 60+  
**LLM calls:** 0 (all mocked)

| Test class | What it covers |
|---|---|
| `TestParseScorecards` | Date parsing, sorting, type coercion, non-dict skipping |
| `TestClassifySeverity` | All four severity band boundaries |
| `TestDriftDetector` | Empty input, full/partial completion, hours variance sign, stalled vs at-risk, blocker evidence, drift score bounds |
| `TestComputeStreak` | All-completed, all-empty, mid-break, single entry, edge cases |
| `TestHabitStreakAnalyser` | Empty, single habit, multiple habits, absent-week treated as false, alphabetical sort |
| `TestBuildProposals` | Valid parse, unknown type fallback, confidence clamping, missing target skip |
| `TestHeuristicProposals` | All severity bands, broken vs healthy habits, many stalled milestones, `requires_regeneration` flag |
| `TestAdaptationProposerAsync` | LLM success, LLM failure fallback, invalid JSON fallback, severe drift heuristic |
| `TestSerialiseDrift` | All keys present, enum serialised as string |
| `TestSerialiseHabitStreak` | All keys present |
| `TestSerialiseAdaptation` | All keys present including nested changes |
| `TestBuildSummary` | On-track, stalled milestones, regeneration mention, low habit mention |
| `TestProgressAgent` | Full pipeline, 3 steps, event emission, `requires_regeneration` propagation, `BaseAgent.run()` contract, failure path |
