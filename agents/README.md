<div align="center">

# 🧠 Career Roadmap AI — Agent Pipeline

**LangGraph · Celery · Anthropic Claude · Python 3.12**

[![Agents CI](https://img.shields.io/github/actions/workflow/status/rogerjeasy/career-roadmap-ai/ci-agents.yml?branch=main&style=flat-square&label=CI&logo=github)](https://github.com/rogerjeasy/career-roadmap-ai/actions)
[![Python](https://img.shields.io/badge/Python-3.12-3776AB?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![LangGraph](https://img.shields.io/badge/LangGraph-StateGraph-1C3C3C?style=flat-square&logo=langchain&logoColor=white)](https://langchain-ai.github.io/langgraph/)
[![Claude](https://img.shields.io/badge/Claude-Sonnet_4.6_%2F_Haiku_4.5-D4A027?style=flat-square&logo=anthropic&logoColor=white)](https://anthropic.com)

</div>

The standalone Python package that powers Career Roadmap AI's intelligence. A **9-specialist LangGraph agent pipeline** runs on Celery workers, produces structured roadmaps, and streams live progress events back to the browser via Redis pub/sub.

> **System overview:** See the [root README](../README.md) for the full architecture picture.
> **Deep-dive patterns:** See [`.claude/backend-patterns.md`](../.claude/backend-patterns.md) for agent internals, contract layer design, and observability patterns.

---

## Table of Contents

- [Architecture position](#architecture-position)
- [Design philosophy](#design-philosophy)
- [Agent roster](#agent-roster)
- [Directory structure](#directory-structure)
- [The contract layer](#the-contract-layer)
- [Pipeline execution flow](#pipeline-execution-flow)
- [LLM strategy](#llm-strategy)
- [RAG pipeline](#rag-pipeline)
- [Local setup](#local-setup)
- [Running agents in isolation](#running-agents-in-isolation)
- [Environment variables](#environment-variables)
- [Testing](#testing)
- [Adding a new agent](#adding-a-new-agent)

---

## Architecture position

```
FastAPI (apps/api)
    │  POST /api/v1/orchestrator/generate
    │  → dispatches Celery task
    ▼
Celery worker (agents package)
    │
    ▼
LangGraph StateGraph (MasterOrchestrator)
    │  DAG of specialist agent nodes
    │  parallel execution via asyncio.gather
    ▼
9 Specialist Agents
    │  each calls MCP tool servers for external data
    │  each emits AgentEvents via Redis pub/sub
    ▼
Redis channel: agent_events:{uid}:{session_id}
    │
    ▼
SSE bridge (FastAPI /stream/{session_id})
    │
    ▼
Browser (EventSource)
```

**Coupling rule:** `apps/api` imports **only** from `agents.contracts`. The agents package never imports from `apps/api`. This keeps the agent runtime independently testable and deployable.

---

## Design philosophy

| Principle | How it's applied |
|---|---|
| **Narrow specialists** | Each agent owns one domain (CV reading, gap analysis, roadmap generation…). No agent does two things. |
| **Shared plan snapshot** | Agents read/write a mutable `plan_snapshot` dict in Redis. They never call each other directly. |
| **Parallel where possible** | Phase 2 (CV Analysis + Market Intel), Phase 5 (Learning Resources + Opportunities + Networking) run in `asyncio.gather`. |
| **Dependencies enforce ordering** | Gap Analysis runs only after both Phase 2 agents complete. Roadmap Generation runs after Gap Analysis. |
| **Fault-tolerant LLMs** | Claude → OpenAI → DeepSeek cascade. If all fail, the agent raises loudly — no synthetic fallback. |
| **Structured outputs** | Every agent returns a typed Pydantic model. No raw dict passing between layers. |
| **Observability by default** | Every agent emits Prometheus metrics, OTel spans, and structlog events. There are no silent agents. |

---

## Agent roster

| # | Agent | Model | Phase | What it does |
|---|---|---|---|---|
| 0 | **MasterOrchestrator** | Sonnet 4.6 | Coordination | Parses intent, scores completeness, builds DAG, dispatches agents, validates outputs |
| 1 | **IntakeProfileAgent** | Sonnet 4.6 | 1 — Profile | NER slot extraction from user message; enriches structured user profile |
| 2 | **CVAnalysisAgent** | Haiku 4.5 | 2 — Analysis | PDF parsing, skill extraction, normalisation, readiness scoring (5 dimensions) |
| 3 | **MarketIntelligenceAgent** | Haiku 4.5 | 2 — Analysis | Fetches live job postings, salary benchmarks, GitHub trends, social signals |
| 4 | **GapAnalysisAgent** | Sonnet 4.6 | 3 — Gaps | Compares user skills vs. market requirements; ranks gaps by ROI × urgency |
| 5 | **RoadmapGenerationAgent** | Sonnet 4.6 | 4 — Roadmap | Builds 12–24 week plan: phases, milestones, weekly tasks, habits, resource links |
| 6 | **LearningResourcesAgent** | Haiku 4.5 | 5 — Enrichment | Finds and ranks specific courses/books per gap; embeds into roadmap phases |
| 7 | **OpportunityMatchingAgent** | Sonnet 4.6 | 5 — Enrichment | Scores live job postings by fit; generates tailored CV snippets for top matches |
| 8 | **NetworkingOutreachAgent** | Haiku 4.5 | 5 — Enrichment | Finds events and communities; drafts personalised outreach messages |
| 9 | **CoachAgent** | Haiku 4.5 | Always-on | Conversational Q&A grounded in the full plan; interview prep, timeline checks |

### Execution DAG

```
[IntakeProfileAgent]
        │
   ┌────┴────┐
   │         │
[CVAnalysis] [MarketIntel]   ← parallel (asyncio.gather)
   │         │
   └────┬────┘
        │
  [GapAnalysis]
        │
  [RoadmapGeneration]
        │
   ┌────┼────┐
   │    │    │
[Learning] [Opportunities] [Networking]   ← parallel
   │    │    │
   └────┴────┘
        │
  [OutputValidator]
```

---

## Directory structure

```
agents/
├── src/agents/
│   ├── __init__.py              ← Registers all agents with AgentRegistry
│   ├── config.py                ← AgentSettings (pydantic-settings, LLM models, MCP URLs)
│   │
│   ├── contracts/               ← Public API surface — the ONLY thing apps/api imports
│   │   ├── events.py            ← AgentEvent, EventType (STEP_PROGRESS, COMPLETED…)
│   │   ├── messages.py          ← OrchestratorTaskInput, OrchestratorTaskOutput
│   │   ├── results.py           ← Per-agent typed result models
│   │   └── tasks.py             ← AgentType enum, TaskDefinition
│   │
│   ├── core/
│   │   ├── base_agent.py        ← BaseAgent ABC: _execute(), emit_event(), retry logic
│   │   ├── agent_registry.py    ← Singleton registry: registry.register(), registry.get()
│   │   ├── context.py           ← AgentContext: plan_snapshot, user_profile, session state
│   │   ├── message_bus.py       ← Redis pub/sub publisher + subscriber
│   │   ├── observability.py     ← Prometheus metrics (counters, histograms per agent)
│   │   ├── logging.py           ← get_logger() (structlog)
│   │   ├── exceptions.py        ← AgentError, LLMError, MCPToolError
│   │   └── result.py            ← AgentResult wrapper
│   │
│   ├── bus/
│   │   ├── celery_app.py        ← Celery app factory + worker startup hooks
│   │   ├── tasks.py             ← @celery_app.task: run_orchestration()
│   │   ├── publisher.py         ← EventPublisher: publishes to Redis channel
│   │   └── subscriber.py        ← EventSubscriber: consumed by FastAPI SSE bridge
│   │
│   ├── orchestrator/
│   │   ├── master_orchestrator.py  ← LangGraph StateGraph definition
│   │   ├── intent_parser.py        ← Extracts goal, timeline, constraints from message
│   │   ├── completeness_scorer.py  ← Scores info completeness (threshold: 0.75)
│   │   ├── clarification_engine.py ← Generates follow-up questions
│   │   ├── task_planner.py         ← Builds DAG from user intent
│   │   └── nodes/
│   │       └── agent_dispatcher.py ← asyncio.gather for parallel agent phases
│   │
│   ├── intake/                  ← Phase 1: Profile enrichment
│   ├── cv_analysis/             ← Phase 2: CV parsing and skill extraction
│   ├── market_intelligence/     ← Phase 2: Live job market data
│   ├── gap_analysis/            ← Phase 3: Skill gap scoring
│   ├── roadmap_generation/      ← Phase 4: Week-by-week plan builder
│   ├── learning_resources/      ← Phase 5: Course + book discovery
│   ├── opportunity/             ← Phase 5: Job matching + CV tailoring
│   ├── networking/              ← Phase 5: Outreach + event discovery
│   ├── coach/                   ← Always-on: conversational Q&A
│   ├── validator/               ← Output validation + schema checks
│   │
│   └── rag/                     ← RAG pipeline
│       ├── embedding/           ← OpenAI text-embedding-3-large
│       ├── retrieval/           ← Pinecone dense+sparse search, Cohere reranker
│       └── context_injector.py  ← Injects retrieved context into agent prompts
│
├── scripts/                     ← Data scripts: fetch market data, seed knowledge base, eval RAG
├── data/
│   ├── knowledge-base/          ← Career KB, ESCO skills/occupations, O*NET, market reports
│   └── eval/                    ← RAG evaluation datasets and results
├── conftest.py
└── pyproject.toml
```

---

## The contract layer

`agents/src/agents/contracts/` is the only public API surface of this package. `apps/api` imports exclusively from here.

```python
# In apps/api — the ONLY permitted import pattern
from agents.contracts import OrchestratorTaskInput, AgentEvent, AgentType

# agents/contracts/messages.py
class OrchestratorTaskInput(BaseModel):
    session_id: str
    user_id: str
    user_message: str
    plan_snapshot: dict

# agents/contracts/events.py
class AgentEvent(BaseModel):
    event_type: EventType
    agent: AgentType
    payload: dict
    timestamp: datetime
```

This boundary ensures:
- The agent package is independently testable with mocked inputs
- `apps/api` never depends on agent implementation details
- The contract can be versioned separately

---

## Pipeline execution flow

### 1. Celery task dispatch

FastAPI calls `run_orchestration.delay(task_input.model_dump())`. Celery picks it up from the Redis broker.

### 2. Completeness check

The orchestrator parses the user's message, extracts slots (goal, timeline, location, hours/week), and scores completeness. If score < 0.75, it emits a `CLARIFICATION_REQUIRED` event with follow-up questions and stops.

### 3. DAG execution

The orchestrator builds a task DAG from the user's intent and runs it:

```python
# Phase 2: parallel
await asyncio.gather(
    cv_agent.run(context),
    market_agent.run(context),
)

# Phase 3: sequential (depends on Phase 2)
await gap_agent.run(context)

# Phase 4: sequential (depends on Phase 3)
await roadmap_agent.run(context)

# Phase 5: parallel (all depend on Phase 4)
await asyncio.gather(
    learning_agent.run(context),
    opportunity_agent.run(context),
    networking_agent.run(context),
)
```

### 4. Plan snapshot

Each agent reads from and writes to a shared `plan_snapshot` dict in the `AgentContext`. Results accumulate as agents complete:

```python
context.plan_snapshot["cv_analysis"] = cv_result.model_dump()
context.plan_snapshot["market_intel"] = market_result.model_dump()
# ... gap_analysis reads both of the above
```

### 5. Event emission

After each significant step, agents emit events:

```python
await self.emit_event(
    event_type=EventType.STEP_PROGRESS,
    payload={"step": "extracting_skills", "progress": 0.6},
)
```

Events flow: `BaseAgent.emit_event()` → `EventPublisher` → Redis channel `agent_events:{uid}:{session_id}` → FastAPI SSE bridge → browser `EventSource`.

---

## LLM strategy

### Model selection

| Task complexity | Model | Why |
|---|---|---|
| Complex reasoning (roadmap, gap analysis, orchestration) | Claude Sonnet 4.6 | Best reasoning quality for multi-step synthesis |
| Simpler extraction/classification (CV parsing, course ranking) | Claude Haiku 4.5 | 10× cheaper, fast enough for structured extraction |
| Always-on chat (coach agent) | Claude Haiku 4.5 | Low latency for conversational responses |

### Fault-tolerant cascade

If the primary LLM call fails (rate limit, API error, timeout), the agent automatically retries with fallbacks:

```
Claude Sonnet 4.6 → OpenAI GPT-4o → DeepSeek V3 → AgentError (no synthetic data)
```

Configured in `config.py` via `LLM_FALLBACK_ORDER`. Each fallback is tried once before the next. If all fail, the agent raises `LLMError` — the orchestrator marks the task as failed and emits `ORCHESTRATION_FAILED`.

### Prompt caching

System prompts are structured to maximise Anthropic's prompt cache hit rate (5-minute TTL). Long, stable system prompts are placed at the beginning of the message array. Per-request variable content goes at the end.

---

## RAG pipeline

The RAG pipeline provides agents with relevant career knowledge base content grounded in authoritative sources (ESCO, O\*NET, BLS, Coursera).

```
Query (skill gap or job role)
    │
    ▼
Embedding (OpenAI text-embedding-3-large, 3072 dims)
    │
    ▼
Pinecone dense+sparse hybrid search
    │
    ▼
Cohere Rerank v3 (optional — improves precision by ~15%)
    │
    ▼
Top-k retrieved chunks
    │
    ▼
ContextInjector → injected into agent system prompt
```

Data sources in `agents/data/knowledge-base/`:
- `career_kb_real.json` — Curated career paths and progression patterns
- `esco_skills.csv` + `esco_occupations_enriched.csv` — European skills/occupations taxonomy
- `onet_occupations_enriched.csv` — US O\*NET occupations with skill requirements
- `global_market_real.json`, `swiss_eu_market_real.json` — Regional market data
- `market_reports_real.json`, `role_templates_real.json` — Role-specific intelligence

---

## Local setup

The agents package is installed as an editable dependency of `apps/api`:

```bash
# From monorepo root
make install        # installs everything including editable agents package

# Or from apps/api/
poetry install      # pyproject.toml includes agents as local path dependency
```

The package is importable as `agents` in both the API and Celery workers.

---

## Running agents in isolation

For development and debugging, you can run individual agents directly:

```python
import asyncio
from agents.core.context import AgentContext
from agents.cv_analysis.cv_agent import CVAnalysisAgent

async def main():
    agent = CVAnalysisAgent()
    context = AgentContext(
        session_id="test-session",
        user_id="test-user",
        plan_snapshot={},
        user_profile={"goal": "become a ML engineer"},
    )
    result = await agent.run(context)
    print(result)

asyncio.run(main())
```

Or run the full pipeline in a Celery worker:

```bash
make worker   # starts Celery worker that processes orchestration tasks
```

---

## Environment variables

These are read from `apps/api/.env` (shared with the API) via `AgentSettings` in `config.py`.

| Variable | Required | Description |
|---|---|---|
| `ANTHROPIC_API_KEY` | Yes | Primary LLM provider |
| `OPENAI_API_KEY` | No | Fallback LLM + embeddings |
| `DEEPSEEK_API_KEY` | No | Second fallback LLM |
| `REDIS_URL` | Yes | Session + plan snapshot storage |
| `CELERY_BROKER_URL` | Yes | Celery task queue |
| `CELERY_RESULT_BACKEND` | Yes | Celery result storage |
| `PINECONE_API_KEY` | No | Vector database (RAG) |
| `PINECONE_INDEX_NAME` | No | Pinecone index name |
| `COHERE_API_KEY` | No | Reranker (improves RAG quality) |
| `CLOUDINARY_URL` | No | Document storage for uploaded CVs |
| `MCP_JOB_BOARD_URL` | No | `http://localhost:3001` |
| `MCP_COURSE_CATALOGUE_URL` | No | `http://localhost:3002` |
| `MCP_GITHUB_TRENDS_URL` | No | `http://localhost:3003` |
| `MCP_SALARY_BENCHMARK_URL` | No | `http://localhost:3004` |
| `MCP_SOCIAL_SIGNALS_URL` | No | `http://localhost:3005` |
| `MCP_CALENDAR_URL` | No | `http://localhost:3006` |
| `MCP_INDUSTRY_NEWS_URL` | No | `http://localhost:3007` |
| `COMPLETENESS_THRESHOLD` | No | `0.75` — min score before generation |
| `MAX_CLARIFICATION_ROUNDS` | No | `3` — max follow-up question rounds |

---

## Testing

```bash
# From monorepo root
make test-agents

# From agents/
poetry run pytest                           # all agent tests
poetry run pytest src/agents/cv_analysis/  # one agent
poetry run pytest -k "test_gap" -v         # filter by name

# RAG evaluation
python scripts/eval_rag.py --retriever hybrid --reranker cohere
```

Tests use mocked LLM clients — no real API calls are made in unit tests. Integration tests with real LLMs require valid API keys and are tagged `@pytest.mark.integration`.

---

## Adding a new agent

1. **Create the agent class:**

```python
# agents/src/agents/<domain>/agent.py
from agents.core.base_agent import AgentContext, BaseAgent
from agents.contracts.tasks import AgentType

class MyAgent(BaseAgent):
    @property
    def agent_type(self) -> AgentType:
        return AgentType.MY_AGENT

    async def _execute(self, context: AgentContext) -> dict:
        # 1. Read from context.plan_snapshot
        # 2. Call LLM or MCP tools
        # 3. Emit progress events
        # 4. Write result back to plan_snapshot
        return {"result": ...}
```

2. **Add to the `AgentType` enum** in `agents/src/agents/contracts/tasks.py`.

3. **Register with the registry** in `agents/src/agents/__init__.py`:

```python
from agents.core.agent_registry import registry
from agents.my_domain.agent import MyAgent

registry.register(MyAgent())
```

4. **Wire into a DAG phase** in `agents/src/agents/orchestrator/task_planner.py`.

5. **Add observability** — Prometheus counter/histogram in `agents/src/agents/core/observability.py`, OTel span in `_execute()`, structlog events at key steps.

6. **Add tests** in `agents/src/agents/<domain>/tests/`.

> **Implementation summary template:** Copy an existing file from `documentation/implementation_summaries/` as a starting point for your new agent's documentation.
