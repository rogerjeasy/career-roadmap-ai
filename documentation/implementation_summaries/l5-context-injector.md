# L5 — Context Injector

## 1. Context and Purpose

The Context Injector is the final component of the **L5 RAG Pipeline**. It bridges the retrieval layer (which produces ranked `RagChunk` objects) and the agent prompt-construction layer (which calls Claude). Its job is to transform raw retrieved passages into citation-labelled, token-budgeted evidence cards — and to emit a system-prompt fragment that forces every LLM call to ground its claims in those cards.

Without the Context Injector, agents receive `rag_chunks` in `AgentContext` but have no structured mechanism to cite them, no freshness enforcement, no token ceiling, and no instruction to label unsupported claims as assumptions. The Context Injector closes all six anti-hallucination guardrails that the architecture requires.

```
Orchestrator (assemble_rag_context)
  rag_chunks: list[RagChunk] in AgentContext
        │
        ▼
  ContextInjector.inject(chunks, token_budget=N, intent_type=...)
        │
        ├─ Stage 1: Freshness check
        │   └─ market-reports / swiss-eu-market chunks older than
        │      market_data_freshness_days → excluded or [STALE] labelled
        │
        ├─ Stage 2: Token-budget trimming
        │   └─ chunks admitted highest-score-first until
        │      estimated token count reaches ceiling
        │
        └─ Stage 3: Citation ID assignment
            └─ [SRC-1] … [SRC-N] markers, citation_map dict
                    │
                    ▼
             InjectedContext
              ├─ formatted_context     → prepend to human message
              ├─ grounding_instructions → append to system prompt
              ├─ citation_map          → str → RagChunk lookup
              └─ observability counters
```

---

## 2. File Locations

```
agents/src/agents/rag/
├── context_injector.py              ← ContextInjector, InjectedContext, CitedChunk
├── observability.py                 ← 6 new RAG_INJECTION_* Prometheus metrics
└── tests/
    └── test_context_injector.py     ← 32 unit tests (no external deps)
```

**Modified files:**

| File | Change |
|---|---|
| `agents/src/agents/config.py` | 3 new `AgentSettings` fields |
| `agents/src/agents/rag/__init__.py` | exports public API |
| `agents/src/agents/orchestrator/orchestrator.py` | preserve `title` + `source_url` in serialised `rag_chunks` |
| `agents/src/agents/orchestrator/nodes/agent_dispatcher.py` | deserialise `title` + `source_url` into `RagChunk` |

---

## 3. Public API

### `ContextInjector.inject()`

```python
from agents.rag import get_context_injector

injected = get_context_injector().inject(
    ctx.rag_chunks,
    token_budget=4000,          # optional; defaults to config
    intent_type="roadmap_generation",  # optional; for logging only
)

# Build a grounded LLM call:
system  = build_grounded_system_prompt(MY_AGENT_SYSTEM, injected)
human   = build_grounded_human_message(user_goal, injected)
```

### `InjectedContext` fields

| Field | Type | Description |
|---|---|---|
| `formatted_context` | `str` | Formatted evidence-cards block, ready to insert before the user instruction |
| `grounding_instructions` | `str` | System-prompt fragment containing all six guardrail rules |
| `citation_map` | `dict[str, RagChunk]` | `"SRC-1"` → `RagChunk`; validators use this to cross-check citations |
| `token_estimate` | `int` | Estimated token count of the evidence block |
| `chunks_included` | `int` | Chunks that passed freshness + budget filters |
| `chunks_excluded_stale` | `int` | Market chunks dropped by freshness policy |
| `chunks_excluded_budget` | `int` | Chunks dropped because they exceeded the token ceiling |
| `has_context` | `bool` (property) | `True` when at least one chunk was included |

### `CitedChunk` fields

| Field | Type | Description |
|---|---|---|
| `citation_id` | `str` | e.g. `"SRC-1"` |
| `chunk` | `RagChunk` | Original chunk from retrieval |
| `confidence_label` | `str` | `"high"` / `"medium"` / `"low"` |
| `is_stale` | `bool` | True if chunk failed freshness check |
| `staleness_days` | `int \| None` | Age in days; `None` when date metadata is absent |

---

## 4. Three-Stage Build Pipeline

### Stage 1 — Freshness check

Only applies to chunks whose `source` is `"market-reports"` or `"swiss-eu-market"`. All other namespaces (`career-kb`, `role-templates`, `taxonomy`) are considered evergreen and skip this stage.

A market chunk is **stale** when:
- `metadata["retrieved_at"]` or `metadata["source_date"]` is absent, or
- The ISO datetime parses to an age greater than `market_data_freshness_days` (default: 30 days).

Behaviour is controlled by `stale_market_data_excluded` (default: `True`):
- `True` — stale chunks are dropped; `chunks_excluded_stale` incremented.
- `False` — stale chunks are included but rendered with a `[STALE: N days old]` tag. The grounding instructions prohibit using them for high-impact claims without an `[ASSUMPTION]` qualifier.

### Stage 2 — Token budget trimming

Chunks are processed in the order they arrive (retrieval pipeline already sorts by relevance score descending). A simple `len(content) // 4` heuristic estimates token count. Chunks are admitted until the cumulative estimate would exceed `context_injection_token_budget` (default: 4000). Excluded chunks increment `chunks_excluded_budget`.

The heuristic intentionally under-counts for code-heavy or non-English content, providing a conservative safety margin without the overhead of a real tokenizer.

### Stage 3 — Citation ID assignment

Each admitted chunk receives a sequential `[SRC-N]` marker starting from `SRC-1`. A `citation_map: dict[str, RagChunk]` is built at this point so that any downstream validator can look up the original chunk for a given citation ID.

---

## 5. Evidence Cards Format

The `formatted_context` string produced by the injector looks like this:

```
=== Evidence Cards ===

[SRC-1] — Senior Data Scientist Role Template (confidence: high)
Source: role-templates | https://example.com/role-ds | Relevance: 0.921
---
Senior data scientists are expected to own end-to-end ML pipelines,
from data collection and feature engineering to model deployment...

[SRC-2] — Swiss Tech Market Q1 2025 (confidence: medium) [STALE: 45 days old]
Source: market-reports | Relevance: 0.742
Date: 2025-03-15T00:00:00+00:00
---
Demand for MLOps engineers in Switzerland grew 28% year-on-year in 2024,
driven by adoption of LLM-based tooling in FinTech and Insurance sectors...

=== End Evidence Cards ===
```

Each card includes:
- Citation ID and title (if available)
- Confidence label (high / medium / low)
- Stale tag with age in days (when applicable)
- Source namespace, URL (if available), and relevance score
- Retrieval date (for market-sensitive namespaces)
- Full chunk content

---

## 6. Anti-Hallucination Guardrails

The `grounding_instructions` string appended to the system prompt enforces all six guardrails defined in the architecture.

### Guardrail 1 — No source, no claim

Claim types that must be cited or labelled `[ASSUMPTION: …]`:
- Required skills
- Salary ranges
- Market demand
- Trending tools or frameworks
- Certification value
- Visa requirements
- Course availability
- Company hiring
- Local event recommendations

### Guardrail 2 — No evidence tag

When a required data point is absent from all evidence cards, the LLM is instructed to write `[NO_EVIDENCE: topic]`, which is captured by the output validator and flagged for human review.

### Guardrail 3 — Sources array

The LLM is required to include `"sources": ["SRC-1", "SRC-3"]` in its JSON output. The output validator cross-checks every listed citation ID against the `citation_map` to ensure the claim is traceable.

### Guardrail 4 — Confidence labels

Confidence is derived from the retrieval relevance score:

| Label | Threshold | Agent output requirement |
|---|---|---|
| `high` | score ≥ 0.85 | No extra caveat needed |
| `medium` | score ≥ 0.70 | Present as confident but sourced |
| `low` | score < 0.70 | Must include explanation of uncertainty |

### Guardrail 5 — Stale data protection

Evidence cards labelled `[STALE]` must not appear in high-impact recommendations (salary, job availability, skills demand) without an `[ASSUMPTION]` qualifier. This is stated explicitly in the grounding instructions.

### Guardrail 6 — Freshness date in output

When an agent cites a market card, it must include the card's retrieval date in an `evidence_date` field in its JSON output. This makes the age of the evidence visible to users and downstream processors.

---

## 7. Prompt Builder Helpers

Two module-level functions simplify agent prompt construction:

```python
from agents.rag import build_grounded_system_prompt, build_grounded_human_message

injected = get_context_injector().inject(ctx.rag_chunks)

# Append grounding rules to the agent's base system prompt
system_prompt = build_grounded_system_prompt(
    "You are a senior career coach ...",
    injected,
)

# Prepend evidence cards before the user instruction
human_message = build_grounded_human_message(
    f"Build a 12-week roadmap for {profile.target_role}.",
    injected,
)
```

When `injected.has_context` is `False` (RAG disabled or all chunks filtered), both helpers return the original string unchanged — agents do not need to check `has_context` before calling them.

---

## 8. Configuration

All fields in `AgentSettings` (`agents/src/agents/config.py`):

| Env variable | Config field | Default | Description |
|---|---|---|---|
| `CONTEXT_INJECTION_TOKEN_BUDGET` | `context_injection_token_budget` | `4000` | Max estimated token count for the evidence-cards block per agent call |
| `MARKET_DATA_FRESHNESS_DAYS` | `market_data_freshness_days` | `30` | Market chunk age threshold in days |
| `STALE_MARKET_DATA_EXCLUDED` | `stale_market_data_excluded` | `True` | `True` = exclude stale; `False` = include with `[STALE]` label |

The `token_budget` parameter of `inject()` overrides the config value for that specific call, enabling per-agent budget tuning without changing global settings.

---

## 9. Observability

### Prometheus Metrics

All metrics use the `career_agents_rag_` prefix.

| Metric | Type | Labels | Description |
|---|---|---|---|
| `career_agents_rag_injection_duration_seconds` | Histogram | — | Wall-clock time for one `inject()` call |
| `career_agents_rag_injection_total` | Counter | `status` | Total injection calls by outcome (`success` / `error`) |
| `career_agents_rag_injection_chunks_included` | Histogram | — | Chunks included per call |
| `career_agents_rag_injection_chunks_stale_total` | Counter | — | Cumulative market chunks excluded by freshness policy |
| `career_agents_rag_injection_chunks_budget_trimmed_total` | Counter | — | Cumulative chunks dropped by token budget |
| `career_agents_rag_injection_token_estimate` | Histogram | — | Estimated token count of evidence block per call |

### OpenTelemetry Span

`rag.context_injection` — created for every `inject()` call.

Span attributes:

| Attribute | Description |
|---|---|
| `input_chunks` | Number of chunks passed in |
| `token_budget` | Budget ceiling used |
| `intent_type` | Intent type from the orchestrator |
| `chunks_included` | Admitted chunks after all filters |
| `chunks_stale_excluded` | Chunks removed by freshness policy |
| `chunks_budget_trimmed` | Chunks removed by budget |
| `token_estimate` | Final token estimate |

On exception the span records the exception and increments `injection_total{status="error"}`. The error path returns a gracefully degraded `InjectedContext` with empty `formatted_context` but intact `grounding_instructions`.

### Structured Logging

```python
logger.info("rag.context_injector.done",
    included=5, stale_excluded=2, budget_trimmed=1,
    token_estimate=1820, intent_type="roadmap_generation")

logger.debug("rag.context_injector.chunk_excluded_stale",
    chunk_id="m-001", source="market-reports", staleness_days=45)

logger.debug("rag.context_injector.chunk_budget_trimmed",
    chunk_id="r-007", tokens_needed=350, budget_remaining=200)
```

---

## 10. Singleton

`get_context_injector()` returns a process-level `ContextInjector` singleton. `ContextInjector` is stateless, so sharing the instance across concurrent agent calls is safe.

```python
# Module-level singleton — initialised on first call
injector = get_context_injector()
```

---

## 11. Pipeline Integration

The Context Injector is called **inside each agent** when building its LLM prompt. It is not a LangGraph node — the retrieval node (`assemble_rag_context`) has already run and populated `AgentContext.rag_chunks` by the time `dispatch_and_collect` fires.

Recommended agent usage pattern:

```python
from agents.rag import build_grounded_human_message, build_grounded_system_prompt, get_context_injector

class RoadmapAgent(BaseAgent):
    async def run(self, ctx: AgentContext) -> AgentResult:
        injected = get_context_injector().inject(
            ctx.rag_chunks,
            intent_type="roadmap_generation",
        )
        system = build_grounded_system_prompt(_ROADMAP_SYSTEM, injected)
        human  = build_grounded_human_message(
            _build_instruction(ctx.user_profile),
            injected,
        )
        response = await self._llm.ainvoke([
            SystemMessage(content=system),
            HumanMessage(content=human),
        ])
        # response now contains [SRC-N] citations and "sources" array
```

The `citation_map` in the returned `InjectedContext` can be forwarded to the output validator for citation cross-checking:

```python
# In the output validator or agent result post-processing
for citation_id in roadmap.get("sources", []):
    if citation_id not in injected.citation_map:
        flagged_claims.append(f"Citation {citation_id} not found in evidence set")
```

---

## 12. Orchestrator Fix — Citation Fields Preserved

Prior to this component, the `assemble_rag_context` node serialised `RagChunk` objects into plain dicts for `OrchestratorState` storage but dropped `title` and `source_url`. These are now preserved:

**`orchestrator.py`** (serialisation):
```python
{
    "chunk_id": c.chunk_id,
    "content": c.content,
    "source": c.source,
    "relevance_score": c.relevance_score,
    "title": c.title,           # ← added
    "source_url": c.source_url, # ← added
    "metadata": dict(c.metadata),
}
```

**`agent_dispatcher.py`** (deserialisation):
```python
RagChunk(
    chunk_id=c["chunk_id"],
    content=c["content"],
    source=c["source"],
    relevance_score=c["relevance_score"],
    title=c.get("title", ""),        # ← added
    source_url=c.get("source_url"),  # ← added
    metadata=c.get("metadata", {}),
)
```

This ensures the evidence card header (`[SRC-1] — Title`) and the source URL in the formatted context are populated correctly for chunks retrieved through the full pipeline.

---

## 13. Tests

`agents/src/agents/rag/tests/test_context_injector.py` — **32 tests**, no external dependencies (Pinecone, OpenAI, Redis are not called).

| Area | Tests |
|---|---|
| Confidence label thresholds (high / medium / low) | 3 |
| Token estimation heuristic | 2 |
| Freshness check — non-market chunk (never stale) | 1 |
| Freshness check — fresh market chunk | 1 |
| Freshness check — stale market chunk | 1 |
| Freshness check — no date metadata | 1 |
| Freshness check — invalid date string | 1 |
| Freshness check — `source_date` fallback field | 1 |
| Evidence card formatting — empty input | 1 |
| Evidence card formatting — single chunk with citation | 1 |
| Evidence card formatting — stale tag with days | 1 |
| Evidence card formatting — stale tag, unknown age | 1 |
| Evidence card formatting — source URL in output | 1 |
| Evidence card formatting — multiple sequential IDs | 1 |
| `inject()` — empty chunks | 1 |
| `inject()` — single chunk, citation map entry | 1 |
| `inject()` — citation map keys match formatted text | 1 |
| `inject()` — token budget trims excess | 1 |
| `inject()` — token budget admits all when sufficient | 1 |
| `inject()` — stale market chunk excluded (default) | 1 |
| `inject()` — stale market chunk included when flag off | 1 |
| `inject()` — fresh market chunk not excluded | 1 |
| `inject()` — all stale → empty context | 1 |
| `inject()` — token estimate non-zero | 1 |
| `inject()` — confidence labels in output | 1 |
| `inject()` — intent_type parameter doesn't crash | 1 |
| `inject()` — grounding instructions contain claim types | 1 |
| `build_grounded_system_prompt` — appends rules | 1 |
| `build_grounded_system_prompt` — empty context unchanged | 1 |
| `build_grounded_human_message` — prepends cards | 1 |
| `build_grounded_human_message` — no context unchanged | 1 |
| `get_context_injector()` — returns same instance | 1 |

**Running tests:**

```bash
cd agents
poetry install
poetry run python -m pytest src/agents/rag/tests/test_context_injector.py -v
```
