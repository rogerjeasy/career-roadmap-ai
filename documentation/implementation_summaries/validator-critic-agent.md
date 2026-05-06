# Validator / Critic Agent — Implementation Summary

**Layer:** L3 Specialist Agent  
**Package:** `agents/src/agents/validator/`  
**Agent type:** `AgentType.VALIDATOR`  
**Date:** 2026-05-06

---

## Purpose

The Validator / Critic Agent is the quality gate in the career roadmap generation pipeline. It sits between the Roadmap Synthesis Agent and the user-facing approval step. Its job is to catch four categories of problems before a draft roadmap reaches the user:

1. **Evidence gaps** — roadmap claims (skills, milestones, market statements) that have no backing in the agent outputs used to generate them.
2. **Unsupported claims** — hallucinated content introduced by the synthesis LLM with no grounding in cv_analysis, gap_analysis, or market_intelligence data.
3. **Realism failures** — timelines or workloads that are structurally infeasible given the user's declared constraints.
4. **Missing fix instructions** — when issues are found, the agent produces structured repair directives that the Roadmap Synthesis Agent can act on in a targeted repair loop.

If all checks pass and no critical fixes are required, the roadmap advances to user approval. If not, the orchestrator triggers a repair cycle using the fix instructions before re-validating.

---

## Architecture Position

```
IntakeAgent → CVAgent → GapAgent → MarketAgent
                                        │
                                  RoadmapAgent (synthesise)
                                        │
                                  ValidatorAgent  ◄── you are here
                                        │
                          passed? ──────┤
                            │           │ failed
                            │     RoadmapAgent (repair with fix_instructions)
                            │           │
                       User Approval ───┘
```

The agent is registered in the `AgentRegistry` at worker startup and invoked by the Master Orchestrator via `registry.get(AgentType.VALIDATOR)`. It reads its inputs from `AgentContext.plan_snapshot` and returns a JSON-serialisable dict as `AgentResult.output`.

---

## File Structure

```
agents/src/agents/validator/
├── __init__.py              # Public surface: exports ValidatorAgent only
├── models.py                # Pure domain dataclasses — no I/O, no LLM
├── evidence_checker.py      # Stage 1: evidence coverage check
├── claim_auditor.py         # Stage 2: hallucination / unsupported claim detection
├── realism_assessor.py      # Stage 3: timeline + workload feasibility
├── fix_instructor.py        # Stage 4: structured repair instructions
├── validator_agent.py       # Main BaseAgent subclass — orchestrates all stages
└── tests/
    ├── __init__.py
    └── test_validator_agent.py   # 30+ tests, no network required
```

---

## Pipeline: Four Stages

### Stage 1 — EvidenceChecker (`evidence_checker.py`)

Extracts all concrete claims from the draft roadmap (skills to acquire, milestone names, market relevance statements, summary) and asks the LLM whether each claim is backed by the available agent outputs.

**Input:**
- `agent_outputs`: merged dict of `cv_analysis`, `gap_analysis`, `market_intelligence`
- `roadmap`: the draft roadmap dict

**Output:** `(list[EvidenceCheck], coverage_score: float)`

Each `EvidenceCheck` carries: `claim`, `is_grounded`, `evidence_ref` (key path in agent outputs or `None`), `confidence`.

Claims are capped at 40 to avoid token overflow. On LLM failure, all claims are marked grounded at `confidence=0.5` (permissive degradation — avoids blocking the pipeline on infra issues).

---

### Stage 2 — ClaimAuditor (`claim_auditor.py`) — concurrent with Stage 3

Sends the full roadmap alongside all agent data to the LLM and asks it to find claims that are not backed by any agent output. Returns a grounding score and a list of `UnsupportedClaim` objects, each with a `roadmap_location` (e.g. `"phases[1].market_relevance"`) and a `severity` (`critical | high | low`).

**Critical severity** is reserved for claims that could actively mislead the user: fabricated salary figures, fake certification values, invented company hiring signals.

On LLM failure, returns an empty list and `score=1.0` (permissive — avoids false positives that would incorrectly block a good roadmap).

---

### Stage 3 — RealismAssessor (`realism_assessor.py`) — concurrent with Stage 2

Two-pass assessment:

**Pass A — Deterministic (no LLM):**
- Compares total roadmap duration (sum of `duration_weeks / 4.33`) against `user_profile.timeline_months`.
  - > 50% over budget → `CRITICAL` issue
  - > 20% over budget → `HIGH` issue
- For each phase, checks whether `phase_weeks × weekly_hours_available ≥ skill_count × 8h`.
  - If not, flags a `HIGH` per-phase issue with a specific suggested extension.

**Pass B — LLM:**
- Evaluates skill complexity, phase ordering logic, and nuanced workload plausibility.
- Returns a `realism_score` and a list of `RealismIssue` objects.

Deterministic issues **cap** the LLM score: a `CRITICAL` deterministic issue limits the final score to ≤ 0.3, preventing the LLM from obscuring a structurally broken timeline with an optimistic score.

On LLM failure, the score is estimated from the deterministic checks alone and the pipeline continues.

---

### Stage 4 — FixInstructor (`fix_instructor.py`)

Only runs if any issues were found in stages 1–3. Sends all issues (evidence gaps, unsupported claims, realism problems) to the LLM and asks for a ranked, de-duplicated list of `FixInstruction` objects.

Each `FixInstruction` carries:

| Field | Description |
|-------|-------------|
| `issue_id` | Unique identifier for tracking |
| `priority` | `critical \| high \| low` |
| `category` | `evidence_gap \| unsupported_claim \| timeline \| workload` |
| `description` | Concise issue description |
| `suggested_action` | Specific, targeted action for the RoadmapAgent |
| `roadmap_location` | Exact location in the roadmap (e.g. `phases[2].skills_to_acquire`) |

On LLM failure, deterministic fallback instructions are generated from the raw issue lists so the orchestrator always has actionable output.

---

## Pass / Fail Logic

The roadmap **passes** only when all four conditions hold:

```python
evidence_score  >= 0.70   # EVIDENCE_THRESHOLD
grounding_score >= 0.65   # GROUNDING_THRESHOLD
realism_score   >= 0.60   # REALISM_THRESHOLD
overall_score   >= 0.70   # OVERALL_THRESHOLD (weighted composite)
no FixInstruction with priority == CRITICAL
```

The overall score is a weighted composite:

```
overall = evidence × 0.35 + grounding × 0.40 + realism × 0.25
```

Grounding carries the highest weight because hallucinated content is the most harmful failure mode for a career planning tool.

Each per-stage score is also translated to a `CheckStatus` label:

| Score | Status |
|-------|--------|
| ≥ threshold | `passed` |
| ≥ threshold × 0.75 | `degraded` |
| < threshold × 0.75 | `failed` |

---

## Agent Output Schema

`AgentResult.output` is a JSON-serialisable dict with these keys:

```json
{
  "passed": true,
  "overall_score": 0.82,
  "evidence_coverage_score": 0.88,
  "grounding_score": 0.79,
  "realism_score": 0.84,
  "evidence_checks": [
    { "claim": "Learn: PyTorch", "is_grounded": true, "evidence_ref": "gap_analysis.gaps[0]", "confidence": 0.91 }
  ],
  "unsupported_claims": [],
  "realism_issues": [],
  "fix_instructions": [],
  "evidence_check_status": "passed",
  "grounding_status": "passed",
  "realism_status": "passed",
  "processing_steps": ["evidence_coverage", "claim_audit", "realism_assess", "fix_instructions"],
  "validation_duration_ms": 3420
}
```

---

## Observability

### OpenTelemetry Spans

| Span name | Attributes |
|-----------|-----------|
| `validator.execute` | `session_id`, `user_id`, `correlation_id`, `passed`, `overall_score`, `evidence_score`, `grounding_score`, `realism_score`, `fix_count`, `critical_fixes` |
| `evidence_checker.check` | `coverage_score`, `claims_count`, `grounded_count` |
| `claim_auditor.audit` | `grounding_score`, `unsupported_count` |
| `realism_assessor.assess` | `realism_score`, `issues_count`, `deterministic_issues` |
| `fix_instructor.generate` | `fix_count`, `critical_count` |

### Prometheus Metrics

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `career_agents_validator_evidence_coverage` | Histogram | — | Evidence coverage score distribution |
| `career_agents_validator_grounding_score` | Histogram | — | Grounding score distribution |
| `career_agents_validator_realism_score` | Histogram | — | Realism score distribution |
| `career_agents_validator_stage_duration_seconds` | Histogram | `stage` | Wall-clock time per stage |
| `career_agents_validator_passed_total` | Counter | `result` (passed/failed) | Validation outcomes |
| `career_agents_validator_fix_count` | Histogram | — | Fix instructions per run |
| `career_agents_validator_fix_instructions_total` | Counter | `priority` | Total fixes by priority |
| `career_agents_validator_unsupported_claims_total` | Counter | — | Total unsupported claims flagged |

SSE progress events (`AgentEventType.STEP_PROGRESS`) are emitted at three checkpoints: `evidence_coverage`, `claim_audit_and_realism`, and `fix_instructions`.

---

## Design Decisions

### Low coupling via constructor DI

All four stages are injected into `ValidatorAgent.__init__` as optional parameters. Each defaults to its own instance but can be replaced independently — for testing, for A/B experimentation with different models, or for future extension (e.g. swapping the ClaimAuditor for a RAG-aware version).

```python
ValidatorAgent(
    evidence_checker=EvidenceChecker(llm=my_llm),
    claim_auditor=ClaimAuditor(llm=my_llm),
    realism_assessor=RealismAssessor(llm=my_llm),
    fix_instructor=FixInstructor(llm=my_llm),
    event_publisher=EventPublisher(redis_client),
)
```

### Concurrent execution of Stages 2 and 3

The ClaimAuditor and RealismAssessor are independent — neither needs the other's output. They run concurrently with `asyncio.gather`, reducing total latency by roughly one LLM round-trip.

### Deterministic realism check as a safety net

The deterministic pass in `RealismAssessor` catches structurally impossible plans (e.g. a 26-week roadmap declared against a 3-month timeline) without any LLM call. It caps the LLM realism score on failure, preventing an overly optimistic LLM from hiding a broken plan.

### Permissive fallback strategy

Each stage has a different fallback philosophy matching its failure mode:
- **EvidenceChecker**: mark all claims grounded — avoids blocking on infra issues.
- **ClaimAuditor**: return no unsupported claims — avoids false positives.
- **RealismAssessor**: use deterministic score estimate — always has something.
- **FixInstructor**: generate basic instructions from raw issue data — always actionable.

This means the pipeline always produces a result; the orchestrator can inspect individual stage statuses if it needs finer-grained failure information.

### LLM model selection

All four stages reuse `agent_settings.validator_model` (defaults to `claude-haiku-4-5-20251001`) — a fast, low-cost model appropriate for structured JSON extraction tasks at `temperature=0.0`. The Haiku model is sufficient here because each prompt is tightly scoped and asks for a specific JSON schema, not open-ended reasoning.

---

## Registration

Add to the Celery worker startup module alongside the other L3 agents:

```python
from agents.validator import ValidatorAgent
from agents.core.agent_registry import registry
from agents.bus.publisher import EventPublisher

registry.register(
    ValidatorAgent(event_publisher=EventPublisher(redis_client))
)
```

---

## Modified Files

| File | Change |
|------|--------|
| `agents/src/agents/contracts/tasks.py` | Added `VALIDATOR = "validator"` to `AgentType` enum |
| `agents/src/agents/core/observability.py` | Added 8 Prometheus metrics for the validator agent |

---

## Test Coverage

`tests/test_validator_agent.py` contains 30+ tests grouped by component:

- `TestValidationResult` — serialisation and `to_dict()`
- `TestScoreToStatus` — pass/degraded/failed boundary logic
- `TestExtractClaims` — claim extraction from roadmap structure
- `TestEvidenceChecker` — coverage score, clamping, fallback, empty roadmap
- `TestClaimAuditor` — grounding score, severity parsing, fallback
- `TestDeterministicCheck` — timeline overshoot (critical/high), per-phase overload, no-constraint skip
- `TestRealismAssessor` — LLM assessment, deterministic cap, LLM fallback
- `TestFixInstructor` — instruction generation, empty-issue short-circuit, LLM fallback, deterministic fallback
- `TestValidatorAgentFull` — end-to-end pass/fail logic, concurrent stage output, overall score weighting, SSE events, broken publisher resilience, processing steps

Integration tests mock the stage methods (`.check`, `.audit`, `.assess`, `.generate`) rather than the underlying LLM, which avoids coupling tests to tenacity retry counts and `asyncio.gather` scheduling order.
