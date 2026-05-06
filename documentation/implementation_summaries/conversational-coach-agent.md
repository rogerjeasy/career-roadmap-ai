# Conversational Coach Agent — Implementation Summary

**Date:** 2026-05-06
**Status:** Complete
**Author:** rogerjeasy

---

## Overview

The Conversational Coach Agent is the always-on chat companion embedded in the career roadmap platform. Unlike the other specialist agents — which run once per roadmap generation and produce structured plan artefacts — the Coach is designed to be invoked repeatedly throughout a user's journey in response to ad-hoc questions.

Its core capabilities:

- **Ad-hoc career questions** — answers any career question grounded in the user's actual profile, skills, and plan rather than giving generic advice.
- **Interview preparation** — detects interview-prep intent and produces tailored question lists, STAR-method frameworks, and practice prompts matched to the user's target role and skill gaps.
- **Timeline reality checks** — explicitly flags when a user's stated transition timeline is unrealistic, explains why, and proposes an achievable alternative. Never validates an impossible plan to be agreeable.
- **Full plan + history context** — assembles roadmap phases, skill gap data, market intelligence, and the last 12 conversation turns into a single rich prompt. Advice is grounded in the user's actual generated plan, not generic career guidance.
- **Conversation continuity** — reads Redis-persisted conversation history so it builds on prior exchanges and never asks for information the user already provided.

---

## Architecture Position

```
Client (Next.js)
      │  POST /api/v1/coach/chat
      ▼
FastAPI Gateway — CoachController
      │  1. Saves user turn to Redis session
      │  2. Packs conversation history + plan context → UserProfileSnapshot.additional
      │  3. Builds OrchestratorTaskInput(forced_intent="coach_query")
      ▼
Celery Worker — MasterOrchestrator (LangGraph)
      │
      ▼
  LangGraph Pipeline (coach_query intent — single-phase DAG)
  ┌──────────────────────────────────────────────────────────┐
  │  Node 1: parse_intent  ← short-circuits (forced_intent) │
  │  Node 2: score_completeness                              │
  │  Node 3: build_dag   →  [COACH] (phase 1, no deps)      │
  │                                                          │
  │  ┌── Phase 1 ──────────────────────────────────────┐    │
  │  │  CoachAgent  ◄── THIS IMPLEMENTATION            │    │
  │  │    CoachContextAssembler                        │    │
  │  │    ChatAnthropic (claude-haiku-4-5-20251001)    │    │
  │  └─────────────────────────────────────────────────┘    │
  │                                                          │
  │  Node 5: validate                                        │
  │  Node 6: synthesize → OrchestratorResult                │
  └──────────────────────────────────────────────────────────┘
      │  ORCHESTRATION_COMPLETED event → Redis pub/sub
      ▼
  SSE stream → Client (GET /api/v1/stream/{session_id})
```

The Coach also runs as a **post-roadmap advisor** when called after a full roadmap generation. In that case, the agent dispatcher passes `plan_snapshot` populated with live outputs from CV Analysis, Gap Analysis, Market Intelligence, and Roadmap Generation agents, and the coach response is deeply grounded in actual plan data.

---

## Files Introduced

### New files

| Path | Role |
|---|---|
| `agents/src/agents/coach/models.py` | Pure domain types: `CoachResponse`, `CoachContextBundle`, `CoachingType`, `ActionableStep` |
| `agents/src/agents/coach/context_assembler.py` | `CoachContextAssembler` — reads profile, history, and plan data into a `CoachContextBundle` |
| `agents/src/agents/coach/coach_agent.py` | `CoachAgent` — extends `BaseAgent`, orchestrates context assembly + LLM call + fallback |
| `agents/src/agents/coach/prompts/coach_system.txt` | Structured system prompt: 4 coaching modes, behaviour rules, JSON output format |
| `agents/src/agents/coach/prompts/coach_persona.txt` | "Alex" persona — communication style, tone calibration, hard constraints |
| `agents/src/agents/coach/__init__.py` | Public package surface |
| `agents/src/agents/coach/tests/test_coach_agent.py` | 34 unit tests (all LLM calls mocked) |
| `apps/api/src/endpoints/v1/coach_controller.py` | `POST /coach/chat` and `GET /coach/history` HTTP endpoints |

### Modified files

| Path | Change |
|---|---|
| `agents/src/agents/contracts/tasks.py` | Added `forced_intent: str \| None = None` to `OrchestratorTaskInput` |
| `agents/src/agents/orchestrator/state.py` | Added `forced_intent: str \| None` to `OrchestratorState` |
| `agents/src/agents/orchestrator/orchestrator.py` | Threads `task_input.forced_intent` into `initial_state` |
| `agents/src/agents/orchestrator/nodes/intent_parser.py` | Short-circuits LLM detection when `forced_intent` is set |
| `agents/src/agents/core/observability.py` | Added 4 coach-specific Prometheus metrics |
| `apps/api/src/endpoints/v1/__init__.py` | Registered `coach_router` |

---

## Component Design

### `models.py` — Domain types

Four Pydantic models internal to the coach package:

```python
class CoachingType(str, Enum):
    AD_HOC = "ad_hoc"
    INTERVIEW_PREP = "interview_prep"
    TIMELINE_CHECK = "timeline_check"
    PROGRESS_NUDGE = "progress_nudge"
    GOAL_CLARIFICATION = "goal_clarification"
    SKILL_GUIDANCE = "skill_guidance"

class ActionableStep(BaseModel):
    step: str
    timeframe: str    # e.g. "this week", "next 2 weeks", "month 1"
    priority: str     # high | medium | low

class CoachResponse(BaseModel):
    response: str                           # main narrative (markdown)
    coaching_type: CoachingType
    confidence: float                       # 0.0 – 1.0
    follow_up_suggestions: list[str]        # 2-3 proactive next questions
    timeline_concern: bool
    timeline_note: str | None               # constructive pushback when True
    actionable_steps: list[ActionableStep]  # 1-4 concrete next actions
    assumptions: list[str]                  # named assumptions made

class CoachContextBundle(BaseModel):
    user_message: str
    current_role: str | None
    target_role: str | None
    skills: list[str]
    goals: list[str]
    constraints: list[str]
    timeline_months: int | None
    weekly_hours: int | None
    conversation_history: list[dict[str, Any]]
    roadmap_summary: str | None
    gap_summary: str | None
    market_summary: str | None
    progress_summary: str | None
    has_plan: bool
```

`CoachResponse` is returned as `AgentResult.output` (plain dict) and consumed by the synthesizer and directly by the SSE client.

---

### `context_assembler.py` — Rich context assembly

`CoachContextAssembler.assemble()` reads from three sources and produces a `CoachContextBundle`:

**Source 1 — `context.user_profile`** (always present):
- `current_role`, `target_role`, `skills`, `goals`, `constraints`, `timeline_months`, `weekly_hours_available`

**Source 2 — `context.user_profile.additional`** (packed by the coach controller at dispatch time):
- `additional["conversation_history"]` — list of `{role, content}` dicts, capped at 12 turns in the assembler
- `additional["plan_context"]` — lightweight roadmap snapshot from the Redis session (`roadmap_id`, `snapshot` dict)

**Source 3 — `context.plan_snapshot`** (populated by the agent dispatcher from prior agents in the same run):
- `plan_snapshot["roadmap_generation"]` — phases, milestones, total duration
- `plan_snapshot["gap_analysis"]` — diff score, critical gaps, priority order
- `plan_snapshot["market_intelligence"]` — market narrative (first 600 chars)
- `plan_snapshot["progress"]` — drift detection, habit summary

The assembler gives priority to live `plan_snapshot` data over the cached session plan context, since the live data is more current. When the agent runs standalone (coach_query intent), `plan_snapshot` is empty and the assembler falls back to the session plan context.

---

### `coach_agent.py` — Main agent

`CoachAgent` extends `BaseAgent` and implements `_execute()` as a two-step pipeline:

```
Step 1: context_assembly  → CoachContextAssembler.assemble(context)
Step 2: llm_inference     → ChatAnthropic(claude-haiku-4-5-20251001)
```

After each step a `STEP_PROGRESS` SSE event is emitted ("Reading your profile and history…", "Preparing your personalised coaching response…").

**LLM call** (`_call_llm` + `_call_llm_with_retry`):
- Uses `langchain_anthropic.ChatAnthropic` with `temperature=0.3` and `max_tokens=2048`.
- Split into two methods so tenacity retry and the fallback path compose correctly:
  - `_call_llm_with_retry` — decorated with `@retry(stop_after_attempt(3), wait_exponential(0.5, min=1, max=8))`; raises on any failure so tenacity can retry it up to 3 times.
  - `_call_llm` — outer wrapper; calls `_call_llm_with_retry` and catches the final exception after all retries are exhausted, returning `_fallback_response()` instead of propagating.
- Strips markdown code fences from the response before JSON parsing (some models wrap JSON in ` ```json ` blocks).
- On any failure after all retries, returns a `_fallback_response()` — a structured message containing the user's original question and a service recovery notice. Confidence is set to `0.1`. The pipeline **never returns a 500**.

**Model selection:**
The model is resolved at construction time via `os.getenv("COACH_MODEL", "claude-haiku-4-5-20251001")`. Using Haiku by default keeps latency low for Q&A interactions while allowing an operator to swap in Sonnet or Opus for higher-stakes coaching via environment variable.

**Output shape** (`AgentResult.output`):

```json
{
  "response": "## Interview Prep for ML Engineer Roles\n\nGiven your Python background...",
  "coaching_type": "interview_prep",
  "confidence": 0.88,
  "follow_up_suggestions": [
    "What system design concepts should I know?",
    "How long should I spend on LeetCode prep?"
  ],
  "timeline_concern": false,
  "timeline_note": null,
  "actionable_steps": [
    { "step": "Complete 3 LeetCode mediums daily", "timeframe": "this week", "priority": "high" },
    { "step": "Mock interview with peer for ML system design", "timeframe": "next 2 weeks", "priority": "high" }
  ],
  "assumptions": ["User is targeting senior/staff level roles"]
}
```

**Constructor — dependency injection:**

```python
CoachAgent(
    event_publisher=EventPublisher(redis),   # None → progress events silently skipped
    llm=ChatAnthropic(...),                  # injectable for tests
    context_assembler=CoachContextAssembler(),  # injectable for tests
)
```

**Registration at worker startup:**

```python
from redis import Redis
from agents.bus.publisher import EventPublisher
from agents.coach import CoachAgent
from agents.core.agent_registry import registry

redis_client = Redis.from_url(settings.redis_url)
registry.register(CoachAgent(event_publisher=EventPublisher(redis_client)))
```

---

### `prompts/coach_system.txt` — System prompt

The system prompt instructs the LLM across four dimensions:

**Core responsibilities:**
1. Ad-hoc career questions — grounded, specific, profile-aware
2. Interview preparation — tailored question lists, STAR frameworks, pitfalls by skill gap
3. Timeline reality check — explicit flag + constructive alternative when timeline is unrealistic
4. Plan & progress awareness — reference actual roadmap phases, not generic guidance

**Behaviour rules:**
- *Honesty over comfort* — politely challenge unrealistic expectations; state confidence level
- *Specificity* — use numbers, timelines, skill names from the user's profile
- *Uncertainty disclosure* — name assumptions in the `assumptions` field
- *Responsible AI* — never infer protected attributes; never adjust ambition based on them; for write-type actions, instruct the user to take the final step

**Output format:** The prompt enforces a strict JSON envelope with `response`, `coaching_type`, `confidence`, `follow_up_suggestions`, `timeline_concern`, `timeline_note`, `actionable_steps`, and `assumptions`. This makes the output machine-readable for the synthesizer and client without post-processing.

### `prompts/coach_persona.txt` — Persona

Defines the "Alex" persona: direct, warm, never generic. Specifies tone per situation (roadmap questions, gap questions, timeline pushback, interview prep, encouragement), and enumerates what the coach never does (pretends certainty, gives generic advice, asks for info already in the profile).

---

### `coach_controller.py` — HTTP endpoints

**`POST /api/v1/coach/chat`** (202 Accepted)

```
Request body: { "message": "<career question>" }

Response:
{
  "request_id": "<celery task id>",
  "session_id": "<user session id>",
  "stream_channel": "<redis pub/sub channel>",
  "message": "Coaching response starting. Subscribe to the stream for live output."
}
```

The controller:
1. Calls `mgr.get_or_create()` to load/create the user's session.
2. Calls `mgr.add_turn(role=user, content=body.message)` to persist the turn in Redis.
3. Serialises the last 20 conversation turns and the session's `plan_context` into `UserProfileSnapshot.additional`.
4. Builds `OrchestratorTaskInput` with `forced_intent="coach_query"`.
5. Dispatches via `TaskPublisher.dispatch_orchestration()` — fire and forget.
6. Returns `request_id` and `stream_channel` so the client can subscribe to SSE.

**`GET /api/v1/coach/history?limit=20`** (200 OK)

Returns the last `limit` conversation turns with role, content, and ISO timestamp. Used by the client to hydrate the chat UI on page load without waiting for a Celery task.

---

## Infrastructure Changes

### `forced_intent` — Bypassing LLM intent detection

**Problem:** The standard orchestration pipeline begins with an LLM call in `IntentParserNode` to classify the user's message. For the coach chat endpoint, this classification is unnecessary — the intent is always `coach_query`. Adding an extra LLM hop degrades latency for what should feel like real-time Q&A.

**Solution:** `OrchestratorTaskInput` gained a `forced_intent: str | None = None` field. When non-null, `IntentParserNode` short-circuits:

```python
# intent_parser.py
if forced := state.get("forced_intent"):
    return {
        "parsed_intent": state["user_message"],
        "intent_type": forced,
        "messages": [HumanMessage(content=state["user_message"])],
    }
```

This bypasses the LLM entirely and proceeds directly to completeness scoring. The field is threaded through `OrchestratorState` (adding `forced_intent: str | None`) and initialised from `task_input.forced_intent` in `MasterOrchestrator.run()`.

**Scope:** `forced_intent` is only honoured when set by a trusted internal caller (the coach controller). No API endpoint exposes it to clients.

### Conversation history — Context packing strategy

**Problem:** `AgentContext` does not carry conversation history; `plan_snapshot` contains only outputs from agents in the same run. For a `coach_query` (standalone run), `plan_snapshot` is empty and the coach would have no conversational context.

**Solution:** The coach controller packs history and plan context into `UserProfileSnapshot.additional` before dispatch:

```python
additional["conversation_history"] = [
    {"role": t.role.value, "content": t.content}
    for t in session.conversation_state[-20:]
]
additional["plan_context"] = {
    "roadmap_id": session.plan_context.roadmap_id,
    "snapshot": session.plan_context.snapshot,
}
```

`CoachContextAssembler` reads these keys and merges them with any live `plan_snapshot` data. This approach requires no new fields in `AgentContext` or the orchestrator state — the existing `additional: dict[str, Any]` on `UserProfileSnapshot` acts as a pass-through channel for caller-supplied context.

**Trade-off:** `UserProfileSnapshot` is semantically a profile type, not a context container. However, the `additional` field is already an escape hatch for untyped data, and modifying the full contract stack (tasks → state → context → dispatcher) for a single field would have been a disproportionate change. This can be refactored to a proper `session_context: dict` field on `OrchestratorTaskInput` when a second agent needs the same pattern.

### Prometheus metrics added

| Metric | Type | Labels | Meaning |
|---|---|---|---|
| `career_agents_coach_llm_duration_seconds` | Histogram | — | Wall-clock time for coach LLM calls |
| `career_agents_coach_llm_total` | Counter | `status` (llm \| fallback) | LLM call outcome |
| `career_agents_coach_timeline_concerns_total` | Counter | — | Responses where unrealistic timeline was flagged |
| `career_agents_coach_confidence_score` | Histogram | — | Distribution of coach confidence scores |

---

## Test Coverage

The test file (`tests/test_coach_agent.py`) contains **34 unit tests** in 5 test classes. All LLM calls are replaced with `AsyncMock` — no network or Anthropic API required.

| Class | What is tested |
|---|---|
| `TestCoachContextAssembler` | Profile field extraction; conversation history from `additional`; invalid history entries ignored; plan context → roadmap summary; live plan_snapshot roadmap/gap extraction; `has_plan` flag; history capped at max turns |
| `TestBuildUserPrompt` | User message present; profile fields present; roadmap section when `has_plan=True`; no roadmap section when `has_plan=False`; conversation history rendered |
| `TestValidateLlmOutput` | Full valid payload; invalid coaching_type → AD_HOC fallback; missing response key; timeline_concern + timeline_note; malformed actionable steps skipped; assumptions extracted |
| `TestFallbackResponse` | User message in fallback text; confidence ≤ 0.2; assumption about service unavailability present |
| `TestCoachAgent` | Agent type/display name; output key set; user message passed to LLM; LLM failure → fallback response; timeline concern surfaced; progress events with publisher; no progress events without publisher; markdown code fence stripped; full `run()` via BaseAgent; rich plan_snapshot context; coaching_type classified correctly |

Run the test suite:

```bash
cd agents
poetry run pytest src/agents/coach/tests/ -v
```

---

## Client Integration

### Typical chat interaction

```
1. Client: POST /api/v1/coach/chat { "message": "How do I prepare for ML engineer interviews?" }
   ← 202: { request_id, session_id, stream_channel }

2. Client: GET /api/v1/stream/{session_id}   [SSE connection]
   → event: agent_event  data: { "event_type": "orchestration_started", ... }
   → event: agent_event  data: { "event_type": "step_progress", "payload": { "step_name": "parse_intent", ... } }
   → event: agent_event  data: { "event_type": "step_progress", "payload": { "agent": "coach", "step": "context_assembly", ... } }
   → event: agent_event  data: { "event_type": "step_progress", "payload": { "agent": "coach", "step": "llm_inference", ... } }
   → event: agent_event  data: { "event_type": "orchestration_completed", "payload": { "roadmap": { ...CoachResponse... } } }

3. Client: (optional) GET /api/v1/coach/history?limit=20
   ← 200: { turns: [...], total: N }
```

### Saving the assistant turn

The coach controller saves the **user** turn to session history before dispatch. The **assistant** turn (the coach's response) should be saved by the client or a post-processing hook after the `ORCHESTRATION_COMPLETED` event is received — the coach response is in `event.payload.roadmap.response`.

---

## Design Principles Applied

| Principle | How it manifests |
|---|---|
| **Low coupling** | `CoachContextAssembler` and `CoachAgent` are independently injectable; neither imports from the API layer |
| **High cohesion** | All coach logic lives in `agents.coach`; nothing outside imports from `agents.coach.models` |
| **Graceful degradation** | LLM failure after 3 retries → deterministic fallback with low confidence; pipeline never crashes |
| **Honesty by design** | System prompt explicitly prohibits validating unrealistic timelines; `timeline_concern` field forces structured disclosure |
| **Uncertainty disclosure** | `assumptions` field in every response; `confidence` float exposed to the client |
| **Responsible AI** | System prompt forbids protected-attribute inference and adjustments; write-type actions always require human action |
| **Observability** | OTel spans per step, Prometheus metrics per call outcome, STEP_PROGRESS SSE events at each pipeline step |
| **Testability** | Every external dependency (LLM, Redis publisher, context assembler) is constructor-injectable with sensible defaults |
| **Performance** | `forced_intent` eliminates one LLM hop for every coach query; Haiku model default keeps P50 latency low |
