# Backend Patterns — Deep Reference

> Loaded on demand. Referenced from the root `CLAUDE.md`.
> Contains agent pipeline internals, MCP server patterns, domain schemas, and contract definitions.

---

## Agent Pipeline — Full Design

### Pipeline phases (LangGraph StateGraph in `agents/src/agents/orchestrator/orchestrator.py`)

```
Client message → FastAPI POST /orchestrator/generate (202)
     ↓ OrchestratorTaskInput dispatched to Celery
Celery Worker → MasterOrchestrator.run()
     ↓ LangGraph nodes execute in sequence / parallel

Node 1  parse_intent           → IntentParser extracts target role, request type
Node 2  score_completeness     → ClarificationEngine.score() + optional LLM question gen
        [score < 0.75?]        → emit CLARIFICATION_REQUIRED via Redis pub/sub → SSE → END
        [score ≥ 0.75]         → proceed
Node 3  build_dag              → TaskPlanner builds execution phases
Node 4  dispatch_and_collect   → runs agents phase-by-phase; within each phase, parallel
        Phase 1 (sequential):  IntakeAgent
        Phase 2 (parallel):    CVAgent  |  MarketIntelligenceAgent
        Phase 3 (sequential):  GapAnalysisAgent
        Phase 4 (sequential):  RoadmapGenerationAgent
        Phase 5 (parallel):    LearningResourceAgent | NetworkingAgent | OpportunityAgent
Node 5  validate               → OutputValidator + ValidatorAgent (realism + evidence checks)
Node 6  synthesize             → ResultAggregator assembles final roadmap JSON
     ↓ ROADMAP_COMPLETE event via Redis pub/sub → SSE
```

Multi-turn clarification: after a `CLARIFICATION_REQUIRED` event the client re-calls `POST /orchestrator/generate` with the same session; the API passes `clarification_round=N+1` and `previous_clarification_questions=[...]` in the task input. The orchestrator seeds those into state so `CompletenessScorerNode` calls `parse_answers()` and `apply_answers()` before re-scoring.

---

### Specialist Agents — Responsibilities

| Agent | Module path | Phase | Key outputs |
|---|---|---|---|
| IntakeAgent | `agents/cv/intake/intake_agent.py` | 1 | Structured `UserProfile` with NER-extracted slots |
| CVAgent | `agents/cv/cv_agent.py` | 2 | `skill_graph`, `readiness_score`, parsed work history |
| MarketIntelligenceAgent | `agents/market/market_agent.py` | 2 | Trending skills, salary benchmarks, job demand signal |
| GapAnalysisAgent | `agents/gap/gap_agent.py` | 3 | Prioritised skill gaps, dimension scores |
| RoadmapGenerationAgent | `agents/roadmap/roadmap_agent.py` | 4 | Phased roadmap with milestones + weekly schedule |
| LearningResourceAgent | `agents/learning/learning_agent.py` | 5 | Curated courses matched to gap list |
| NetworkingAgent | `agents/networking/networking_agent.py` | 5 | Events, LinkedIn outreach drafts, relationship tracker |
| OpportunityAgent | `agents/opportunity/opportunity_agent.py` | 5 | Scored job listings, tailored CV snippets |
| ProgressAgent | `agents/progress/progress_agent.py` | on-demand | Drift detection, adaptation proposals, habit streaks |
| ValidatorAgent | `agents/validator/validator_agent.py` | post-phase | Claim auditing, realism assessment, fix instructions |

Actual paths are under `agents/src/agents/<name>/`.

---

### BaseAgent Contract (`agents/src/agents/core/base_agent.py`)

All specialist agents extend `BaseAgent`. Implement:
```python
async def run(self, context: AgentContext) -> AgentResult: ...
```

`AgentContext` carries:
- `user_id`, `session_id`, `correlation_id`
- `user_profile: UserProfileSnapshot`
- `plan_snapshot: dict`  ← accumulated outputs from prior phases
- `mcp_clients: dict[str, MCPClient]`  ← pre-wired tool clients

`AgentResult` carries:
- `agent_name: str`
- `output: dict`  ← merged into `plan_snapshot` after the agent completes
- `events: list[AgentEvent]`  ← streamed to SSE
- `success: bool`, `error: str | None`

Every agent must:
1. Emit at minimum a `AGENT_STARTED` and `AGENT_COMPLETED` (or `AGENT_FAILED`) event.
2. Wrap the LLM call in a tenacity retry with exponential backoff (3 attempts, 1–8 s).
3. Open an OTel span for the main LLM call and any sub-steps.
4. Increment `agent_invocations_total` counter on completion.
5. Record `agent_duration_seconds` histogram.
6. Log with `structlog` using `user_id`, `session_id`, `correlation_id`.

---

### Clarification Engine (`agents/src/agents/orchestrator/clarification_engine.py`)

Stateless. Slot weights:
```
target_role           0.30
current_role          0.15
skills                0.15
timeline_months       0.15
location              0.10
weekly_hours_available 0.10
salary_goal           0.05
```
Completeness threshold: `0.75` (env `COMPLETENESS_THRESHOLD`).
Max clarification rounds: `3` (env `MAX_CLARIFICATION_ROUNDS`).
Max questions per round: `3`.
LLM: `claude-sonnet-4-6`, temp 0.2.
Fallback: canned questions per slot when LLM fails all retries.

---

## MCP Servers

All servers live in `mcp-servers/<name>/`. Each has:
```
server.py          ← FastMCP server entrypoint
tools/             ← one file per tool
clients/           ← async Python client for that server
shared/
  auth.py          ← Bearer token validation
  base_server.py   ← shared FastMCP base
  cache.py         ← Redis TTL cache
  error_handler.py ← structured error responses
  rate_limiter.py  ← per-server rate limiting
```

Servers:

| Server | Purpose |
|---|---|
| `job-board` | Job listings from external APIs |
| `salary-benchmark` | Salary data by role + location |
| `course-catalogue` | Udemy/Coursera/edX course search |
| `github-trends` | GitHub trending repos and skill signals |
| `industry-news` | Recent industry news articles |
| `social-signals` | LinkedIn / Twitter professional signals |
| `calendar` | Google/Outlook calendar read + write |

Each MCP tool call from an agent goes through:
1. Agent calls `mcp_client.<tool>(...)` from `agents/src/agents/<name>/mcp_client.py`
2. Client sends gRPC/HTTP to the MCP server
3. Server validates the Bearer token (`shared/auth.py`) and rate-limits
4. Tool handler fetches + caches + returns structured data
5. Agent emits a `mcp_tool_calls_total` Prometheus counter increment

---

## Message Bus (`agents/src/agents/bus/`)

```
celery_app.py    ← Celery app instance; broker and result backend from env
publisher.py     ← TaskPublisher.dispatch_orchestration(OrchestratorTaskInput) → str (task_id)
subscriber.py    ← Redis pub/sub subscriber used by SSE controller
channel.py       ← channel_for_session(user_id, session_id) → str (channel name)
```

Flow:
1. API calls `TaskPublisher.dispatch_orchestration(task_input)` → returns Celery task ID.
2. Client subscribes to `GET /stream/{session_id}` (SSE).
3. SSE controller subscribes to Redis channel `channel_for_session(...)`.
4. Agent pipeline publishes events to that channel as the pipeline progresses.
5. `ROADMAP_COMPLETE` event contains the full serialised roadmap JSON.

---

## Agent Contracts (`agents/src/agents/contracts/`)

Shared Pydantic models used by both the API layer and agent workers:

```
tasks.py    ← OrchestratorTaskInput, UserProfileSnapshot
events.py   ← AgentEvent, EventType enum (AGENT_STARTED, AGENT_COMPLETED, CLARIFICATION_REQUIRED, ROADMAP_COMPLETE, ...)
results.py  ← OrchestratorResult, AgentResult
messages.py ← inter-agent message types
```

The boundary between `apps/api` and `agents` is **one function**: `_to_profile_snapshot()` in `orchestrator_controller.py`. No other import crosses that boundary in the API→agents direction.

---

## Session Data Schema (`apps/api/src/session/models.py`)

Redis key: `session:{user_id}`, JSON, 24h sliding TTL.

```python
SessionData:
  user_id: str
  email: str | None
  created_at: datetime
  last_active_at: datetime
  conversation_state: list[ConversationTurn]   # capped at MAX_CONVERSATION_TURNS
  follow_up_queue: list[ClarificationQuestion] # ≤3 questions
  clarification_flags: ClarificationFlags      # round_number, completeness_score, missing_slots
  user_profile_context: UserProfileContext | None
  plan_context: PlanContext | None
```

---

## RAG Pipeline (`agents/rag/`)

Used by agents that need semantic search over career documents.

```
rag/
  config.py         ← RAG settings (embedding model, chunk size, vector store params)
  embedding/        ← text embedding wrappers
  ingestion/        ← document chunking and ingestion pipeline
  retrieval/        ← query + rerank
  vector_store/     ← vector DB client (pgvector or external)
  tests/
```

---

## Adding a New Specialist Agent — Checklist

1. Create `agents/src/agents/<name>/` directory.
2. `<name>_agent.py` — extend `BaseAgent`; implement `async def run(context) -> AgentResult`.
3. `models.py` — Pydantic input/output models specific to this agent.
4. `<helper>.py` files for sub-steps (parser, scorer, fetcher, etc.).
5. `<name>_system.txt` — system prompt.
6. `mcp_client.py` — if this agent uses an MCP server.
7. `tests/test_<name>_agent.py` — unit tests with mocked LLM, no network.
8. Register in `agents/src/agents/core/agent_registry.py`.
9. Add `AgentType.<NAME>` entry to `agents/src/agents/contracts/tasks.py` enum.
10. Wire into `TaskPlanner` phase plan (`agents/src/agents/orchestrator/task_planner.py`).
11. Add Prometheus counter label for agent name to `agent_invocations_total` usage.
12. Write implementation summary to `documentation/implementation_summaries/<name>-agent.md`.

---

## Adding a New API Domain — Checklist

1. `apps/api/src/domains/<name>/model.py` — SQLAlchemy model, `Base` from `src/db/base.py`.
2. Alembic migration: `poetry run alembic revision --autogenerate -m "add <name> table"`.
3. `repository.py` — `class <Name>Repository(session: AsyncSession)`.
4. `schemas.py` — Pydantic v2 request/response models.
5. `service.py` — `class <Name>Service`; expose `get_<name>_service` FastAPI dep.
6. `apps/api/src/endpoints/v1/<name>_controller.py` — `router = APIRouter(prefix="/<name>")`.
7. Register router in `apps/api/src/endpoints/v1/__init__.py`.
8. Tests in `domains/<name>/tests/`.
9. Update `GET /livez` or `GET /readyz` if the domain has a health dependency.

---

## Observability Checklist for New Features

For every significant new feature (agent, service method, or endpoint), verify:

- [ ] Structlog event on entry and exit with all relevant IDs
- [ ] OTel span wrapping the main I/O or LLM call
- [ ] Prometheus counter incremented on success and error paths (with outcome label)
- [ ] Prometheus histogram recording duration for LLM calls and external API calls
- [ ] Sentry will capture unhandled exceptions automatically (no extra code needed)
- [ ] Rate limiting applied to any new public endpoint
- [ ] Audit log emitted for any MCP tool write action or sensitive data access

---

## Security Checklist for New Features

- [ ] Every new endpoint depends on `get_current_user()` unless explicitly public
- [ ] All DB queries filter by `user_id` / `uid` — never return another user's data
- [ ] No secrets in code; all from `Settings` / env
- [ ] File uploads validated for MIME type and size before storage (`MAX_UPLOAD_SIZE_MB`)
- [ ] MCP write actions (calendar, outreach) gated behind user confirmation
- [ ] Responsible AI: no protected attribute inference, expose uncertainty, provide explanations
- [ ] New external account connections require explicit consent
- [ ] Tool-call audit log written for every MCP action

---

## Common Pitfalls

- **Don't cross the `apps/api` ↔ `agents` boundary** except via `OrchestratorTaskInput` contracts and the `_to_profile_snapshot()` converter in `orchestrator_controller.py`.
- **Don't use sync DB calls** inside `async def` endpoints. Use `await session.execute(...)`.
- **Don't store tokens or secrets in session state.** Session Redis keys are unencrypted. Store only non-sensitive derived data.
- **Don't call Firebase Admin SDK in tests** without mocking. It makes network calls.
- **Don't hard-code model names** — read from `Settings.default_llm_model` or agent-specific config.
- **Don't skip the completeness threshold** — even if a user profile looks full, always run `ClarificationEngine.score()` and respect the threshold before dispatching agents.
- **LangGraph state is serialised between nodes.** All values in `OrchestratorState` must be JSON-serialisable. Use dicts, not dataclass instances, for values stored in state.
