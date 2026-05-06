# Market Intelligence Agent — Implementation Summary

**Date:** 2026-05-05
**Status:** Complete
**Author:** rogerjeasy

---

## Overview

The Market Intelligence Agent is the fourth L3 Specialist Agent to be implemented. Its role is the system's **real-time data layer**: while the Gap Analysis Agent measures the distance between where a candidate is and where they need to be, the Market Intelligence Agent answers the complementary question — *what does the live job market actually want right now, and what is it paying?*

It runs in **Phase 2 of the multi-agent DAG in parallel with CV Analysis**, polling four MCP tool servers concurrently (job board, salary benchmarks, GitHub trends, and social signals), aggregating the raw data into structured signals through a pure-computation processor, and then producing a human-readable narrative via an LLM summarisation step. The resulting `MarketIntelligenceResult` is placed in `plan_snapshot["market_intelligence"]` and consumed directly by the Roadmap Generation Agent and the Output Validator.

Two design choices distinguish this agent from the others:

1. **Zero hard dependencies on live infrastructure.** All five components are injected via DI. When no MCP server URLs are configured (e.g. in development or CI), the agent automatically falls back to `StubMCPClient`, which returns realistic mock data and exercises the full pipeline without any network calls.

2. **Parallel I/O at steps 1–3.** Job postings, salary benchmarks, and GitHub/social trends are fetched with a single `asyncio.gather`, so three MCP round-trips complete in the time of the slowest one rather than the sum of all three.

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
  ┌──────────────────────────────────────────────────────────────────┐
  │  Node 1: parse_intent                                            │
  │  Node 2: score_completeness  (ClarificationEngine)              │
  │  Node 3: build_dag           (TaskPlanner)                       │
  │                                                                  │
  │  ┌── Phase 1 ──────────────────────────────────────────────┐    │
  │  │  IntakeAgent  (NER profile building)                    │    │
  │  └─────────────────────────────────────────────────────────┘    │
  │         │ enriched UserProfile in plan_snapshot                 │
  │         ▼                                                        │
  │  ┌── Phase 2 (parallel) ───────────────────────────────────┐    │
  │  │  CVAgent         (skill_graph, readiness)               │    │
  │  │  MarketAgent  ◄── THIS IMPLEMENTATION                   │    │
  │  │    ├─ JobBoardFetcher   (MCP: job_board)                │    │
  │  │    ├─ SalaryFetcher     (MCP: salary_benchmark)         │    │
  │  │    ├─ TrendFetcher      (MCP: github_trends             │    │
  │  │    │                        + social_signals)           │    │
  │  │    ├─ SignalProcessor   (pure computation)              │    │
  │  │    └─ TrendSummariser   (LLM: claude-haiku)             │    │
  │  └─────────────────────────────────────────────────────────┘    │
  │         │ plan_snapshot["cv_analysis"]                          │
  │         │ plan_snapshot["market_intelligence"]                  │
  │         ▼                                                        │
  │  ┌── Phase 3 ──────────────────────────────────────────────┐    │
  │  │  GapAgent  (role profiling + skill gap scoring)         │    │
  │  └─────────────────────────────────────────────────────────┘    │
  │         │ plan_snapshot["gap_analysis"]                         │
  │         ▼                                                        │
  │  ┌── Phase 4 ──────────────────────────────────────────────┐    │
  │  │  RoadmapGenerationAgent                                 │    │
  │  │  (consumes trending_skills + salary_benchmark)          │    │
  │  └─────────────────────────────────────────────────────────┘    │
  │         │                                                        │
  │  ┌── Phase 5 (parallel) ───────────────────────────────────┐    │
  │  │  LearningResourcesAgent  NetworkingAgent  OpportunityAgent   │
  │  └─────────────────────────────────────────────────────────┘    │
  └──────────────────────────────────────────────────────────────────┘
      │  AgentResult.output["trending_skills"] + ["salary_benchmark"]
      │                      + ["market_summary"]
      ▼
  Synthesizer Node → OrchestratorResult → SSE → Client
```

---

## Files Introduced

### New files

| Path | Role |
|---|---|
| `agents/src/agents/market_intelligence/models.py` | Pure domain types: `JobPosting`, `SalaryBenchmark`, `TrendingSkill`, `IndustrySignal`, `MarketIntelligenceResult`, `TrendDirection`, `SignalType` |
| `agents/src/agents/market_intelligence/mcp_client.py` | `MCPClientProtocol` (structural typing interface) + `HttpMCPClient` (JSON-RPC 2.0 over HTTP) + `StubMCPClient` (realistic mock, auto-used in dev) |
| `agents/src/agents/market_intelligence/job_board_fetcher.py` | `JobBoardFetcher` — MCP `job_board.search_jobs` → `list[JobPosting]`; returns `[]` on failure |
| `agents/src/agents/market_intelligence/salary_fetcher.py` | `SalaryFetcher` — MCP `salary_benchmark.get_salary` → `SalaryBenchmark \| None`; returns `None` on failure |
| `agents/src/agents/market_intelligence/trend_fetcher.py` | `TrendFetcher` — MCP `github_trends` + `social_signals` fetched concurrently; returns `([], [])` on failure |
| `agents/src/agents/market_intelligence/signal_processor.py` | `SignalProcessor` — pure computation: skill counting, GitHub star-velocity weighting, trend direction classification, industry signal normalisation, relevance scoring |
| `agents/src/agents/market_intelligence/trend_summariser.py` | `TrendSummariser` — LLM narrative (claude-haiku) with retry and deterministic text fallback |
| `agents/src/agents/market_intelligence/market_agent.py` | `MarketAgent` — extends `BaseAgent`; orchestrates the 5-step pipeline; country extraction; full output serialisation |
| `agents/src/agents/market_intelligence/__init__.py` | Public package surface: exports `MarketAgent` only |
| `agents/src/agents/market_intelligence/tests/__init__.py` | Test package marker |
| `agents/src/agents/market_intelligence/tests/test_market_agent.py` | 60+ unit tests across 13 test classes (all MCP and LLM calls mocked) |

### Modified files

| Path | Change |
|---|---|
| `agents/src/agents/core/observability.py` | Added 9 market-intelligence-specific Prometheus metrics |
| `agents/src/agents/config.py` | Added `market_intelligence_model` + 5 optional `mcp_*` settings |
| `agents/pyproject.toml` | Added `httpx` dependency for `HttpMCPClient` HTTP transport |

---

## Pipeline Design

Steps 1–3 run as a single `asyncio.gather` call. Steps 4–5 run sequentially after the gather resolves. Each step emits a `STEP_PROGRESS` SSE event and is wrapped in an OTel span.

```
context.user_profile.target_role       → role
context.user_profile.location          → country  (_extract_country)
context.user_profile.skills            → tech_hints  (GitHub topic seeds)
        │
        │  asyncio.gather (steps 1-3 run concurrently)
        ├──────────────────────────────────────────────────────────┐
        │  Step 1                                                  │
        │  JobBoardFetcher.fetch(role, country)                    │
        │       MCP: job_board.search_jobs                         │
        │       → list[JobPosting]                                 │
        │                                                          │
        │  Step 2                                                  │
        │  SalaryFetcher.fetch(role, country)                      │
        │       MCP: salary_benchmark.get_salary                   │
        │       → SalaryBenchmark | None                           │
        │                                                          │
        │  Step 3                                                  │
        │  TrendFetcher.fetch(tech_hints)                          │
        │       MCP: github_trends.get_trending   (concurrent)     │
        │       MCP: social_signals.get_signals   (concurrent)     │
        │       → (list[dict], list[dict])                         │
        └──────────────────────────────────────────────────────────┘
        │  job_postings, salary_benchmark, (github_raw, social_raw)
        ▼  Step 4
  SignalProcessor.extract_trending_skills()   ← pure computation
  SignalProcessor.normalise_industry_signals() ← pure computation
        │  list[TrendingSkill]  +  list[IndustrySignal]
        ▼  Step 5
  TrendSummariser.summarise()                 ← LLM call (claude-haiku)
        │  market_summary: str
        ▼
  MarketIntelligenceResult → serialise() → AgentResult.output
```

**LLM budget per run:** 1 LLM call (TrendSummariser). All four MCP calls are non-LLM tool calls. The `SignalProcessor` is always LLM-free.

**Partial failure handling:** every fetcher catches its own exception and returns an empty result. The pipeline always reaches the summariser. The `TrendSummariser` itself has its own fallback to structured text if the LLM fails. The agent therefore **never returns `FAILED` due to infrastructure unavailability** — it returns `PARTIAL` at worst, with a fallback summary describing what data was available.

---

## Component Design

### `models.py` — Domain types

Six frozen dataclasses and two enums that carry structured data through the pipeline. All are **internal to the `market_intelligence` package**; external code imports only `MarketAgent`.

```python
class TrendDirection(str, Enum):
    RISING   = "rising"    # signal_count >= 3 across sources
    STABLE   = "stable"    # signal_count < 3
    DECLINING = "declining" # reserved for future temporal comparison

class SignalType(str, Enum):
    JOB_POSTING   = "job_posting"
    GITHUB_TREND  = "github_trend"
    SOCIAL_SIGNAL = "social_signal"
    SALARY_DATA   = "salary_data"
    INDUSTRY_NEWS = "industry_news"

@dataclass(frozen=True)
class JobPosting:
    title:           str
    company:         str
    location:        str
    required_skills: list[str]   # extracted from posting
    source:          str         # LinkedIn | Indeed | Glassdoor | ...
    posted_date:     date | None
    salary_min:      int | None
    salary_max:      int | None
    currency:        str         # CHF | EUR | USD | GBP | ...
    url:             str | None

@dataclass(frozen=True)
class SalaryBenchmark:
    role:           str
    country:        str          # ISO 2-letter code
    median_annual:  int | None
    p25_annual:     int | None
    p75_annual:     int | None
    currency:       str
    source:         str
    freshness_date: date | None

@dataclass(frozen=True)
class TrendingSkill:
    name:            str         # canonical (FastAPI, not "fastapi")
    category:        str         # language | framework | platform | tool | ai_ml | tech
    trend_direction: TrendDirection
    signal_count:    int         # weighted total across all sources
    sources:         list[str]   # job_board | github_trends | hackernews | ...
    evidence:        str         # one-line rationale, e.g. "Mentioned in 7 market signals"

@dataclass(frozen=True)
class IndustrySignal:
    topic:           str
    signal_type:     SignalType
    summary:         str         # human-readable one-liner
    source:          str         # GitHub Trends | Hacker News | Reddit | ...
    relevance_score: float       # 0-1: keyword overlap with target role
    url:             str | None
    freshness_date:  date | None

@dataclass(frozen=True)
class MarketIntelligenceResult:
    role:              str
    country:           str
    job_postings:      list[JobPosting]
    salary_benchmark:  SalaryBenchmark | None
    trending_skills:   list[TrendingSkill]
    industry_signals:  list[IndustrySignal]
    market_summary:    str
    fetched_at:        datetime
    data_sources:      list[str]   # deduplicated, sorted
    processing_steps:  list[str]   # ["market_data_fetching", "signal_processing", ...]
```

---

### `mcp_client.py` — MCP transport abstraction

Three classes provide the transport layer. Agents and fetchers depend **only** on `MCPClientProtocol`; no concrete class is imported by the agent itself.

**`MCPClientProtocol`** (structural `Protocol`, `@runtime_checkable`):

```python
class MCPClientProtocol(Protocol):
    async def call(
        self,
        server_id: str,
        tool: str,
        params: dict[str, Any],
        *,
        correlation_id: str = "",
    ) -> dict[str, Any]: ...
```

**`HttpMCPClient`** — production JSON-RPC 2.0 client:
- Accepts a `server_registry: dict[str, str]` (server ID → base URL)
- Sends `{"jsonrpc": "2.0", "id": uuid, "method": tool, "params": params}` via `httpx.AsyncClient`
- Forwards `X-Correlation-ID` header for distributed tracing
- Raises `RuntimeError` on JSON-RPC error objects
- Logs call outcome at `DEBUG` level with latency

**`StubMCPClient`** — development/test mock:
- Satisfies `MCPClientProtocol` without subclassing (structural typing)
- Dispatches on `server_id` to private helpers that return country-aware mock data
- `job_board` responses use country-specific salary ranges and currencies (CHF for CH, EUR for DE/FR, USD for US, GBP for UK)
- `salary_benchmark` base salaries: CH 115k, US 135k, DE 78k, FR 67k, UK 92k
- `github_trends` returns 5 realistic trending repos + 6 topic strings
- `social_signals` returns 2 HN items + 2 Reddit posts + 4 trending topics

**Auto-selection** (`_build_mcp_client()` in `market_agent.py`):
```python
def _build_mcp_client() -> MCPClientProtocol:
    registry = {k: v for k, v in {
        "job_board":        agent_settings.mcp_job_board_url,
        "salary_benchmark": agent_settings.mcp_salary_benchmark_url,
        "github_trends":    agent_settings.mcp_github_trends_url,
        "social_signals":   agent_settings.mcp_social_signals_url,
    }.items() if v}

    if registry:
        return HttpMCPClient(registry, timeout_seconds=agent_settings.mcp_timeout_seconds)
    return StubMCPClient()   # ← used automatically in dev when no URLs configured
```

---

### `job_board_fetcher.py` — Job board MCP calls

`JobBoardFetcher.fetch(role, country, limit=20)` calls `job_board.search_jobs` and parses the response into `list[JobPosting]`.

**Parsing strategy (`_parse_postings`):**
- Skips any entry without a `title`
- Parses `posted_date` from ISO string, ignores parse failures
- Accepts `salary_min` / `salary_max` as int, float, or string
- Defaults `currency` to `"USD"` when absent

**Resilience:**
- The entire MCP call + parse is wrapped in `try/except`; exceptions produce an empty list with a `WARNING` log
- Callers always receive a `list[JobPosting]` (possibly empty) — never an exception

**Observability:**
- OTel span `market.job_board_fetch` with attributes: `role`, `country`, `limit`, `posting_count`, `latency_ms`
- `MARKET_JOB_FETCH_DURATION` histogram
- `MARKET_JOB_FETCH_TOTAL` counter labelled `status=success|error`
- Structured log `market.job_board_fetched` with `posting_count` and `latency_ms`

---

### `salary_fetcher.py` — Salary benchmark MCP calls

`SalaryFetcher.fetch(role, country)` calls `salary_benchmark.get_salary` and parses the response into `SalaryBenchmark | None`.

**Parsing strategy (`_parse_salary`):**
- Returns `None` for an empty raw dict (server returned no data for this role/country)
- Falls back to the `role` and `country` method parameters when the response omits them
- `freshness_date` parsed from ISO string; `None` if absent or unparseable

**Resilience:** exception → `None` return, `WARNING` log. Downstream code treats `None` as "salary data unavailable" and continues.

**Observability:**
- OTel span `market.salary_fetch` with attributes: `role`, `country`, `has_data`, `latency_ms`
- `MARKET_SALARY_FETCH_DURATION` histogram
- `MARKET_SALARY_FETCH_TOTAL` counter labelled `status=success|error`

---

### `trend_fetcher.py` — GitHub and social signal MCP calls

`TrendFetcher.fetch(tech_stack_hints)` fetches GitHub trends and social signals **concurrently** and returns `(github_items, social_items)`.

**Concurrency design:**
```python
github_raw, social_raw = await asyncio.gather(
    self._fetch_github(hints, correlation_id),
    self._fetch_social(hints, correlation_id),
)
```

**GitHub normalisation:** flattens `trending_repos` into individual dicts, then synthesises additional entries from `trending_topics` (string array → `{"name": topic, "topic": topic, "stars_this_week": 0}`), giving the `SignalProcessor` a single uniform list.

**Social normalisation:** collects HackerNews items and Reddit posts into a flat list, tagging each with `_source: "hackernews"|"reddit"`. Trending topics become synthetic entries tagged `_source: "social_aggregate"`.

**Resilience:** each `_fetch_*` method has its own `try/except`; a failing GitHub call does not affect the social call outcome. The outer `asyncio.gather` uses the default `return_exceptions=False` — individual failures are caught inside the helper methods before they propagate.

**Observability:**
- OTel span `market.trend_fetch` with `github_item_count`, `social_item_count`, `latency_ms`
- `MARKET_TREND_FETCH_DURATION` histogram (total concurrent latency)
- `MARKET_TREND_FETCH_TOTAL` counter labelled `status` × `source` (github_trends | social_signals)

---

### `signal_processor.py` — Pure computation aggregation

`SignalProcessor` contains no I/O and no LLM calls. It is stateless and infinitely re-usable.

#### `extract_trending_skills` algorithm

**Step 1 — Count job posting skills:**
```
for each posting in job_postings:
    for each skill in posting.required_skills:
        skill_counts[skill.lower()] += 1
        skill_sources[skill.lower()].add("job_board")
```

**Step 2 — Weight GitHub trending items by star velocity:**
```
weight = max(1, min(4, 1 + stars_this_week // 1_000))
# A repo with 4,200 stars this week → weight = 1 + 4 = 5 (capped at 4 in practice)
skill_counts[topic.lower()] += weight
skill_sources[topic.lower()].add("github_trends")
```

**Step 3 — Add social signals (weight 1 each):**
```
skill_counts[title.lower()] += 1
skill_sources[title.lower()].add(_source)
```

**Step 4 — Build TrendingSkill objects:**
- Returns `Counter.most_common(top_n)` (default `top_n=15`)
- `TrendDirection.RISING` if `signal_count >= 3`, else `STABLE`
- Canonical name: looked up in `_CANONICAL_NAME` dict, falls back to `.title()`
- Category: looked up in `_SKILL_CATEGORY` dict (covering 50+ known skills), falls back to `"tech"`

**Skill categories:**

| Category | Examples |
|---|---|
| `language` | Python, TypeScript, Go, Rust, Java, Kotlin, Scala, Ruby |
| `framework` | FastAPI, Django, React, LangChain, PyTorch, TensorFlow, Next.js |
| `platform` | Docker, Kubernetes, AWS, GCP, Azure |
| `tool` | Terraform, Ansible, Kafka, Spark, Redis, PostgreSQL, CI/CD |
| `ai_ml` | LLM, AI agents, RAG, prompt engineering, machine learning |
| `tech` | anything not in the above (safe default) |

#### `normalise_industry_signals` algorithm

- GitHub trend entries → `SignalType.GITHUB_TREND`, source = "GitHub Trends"
  - Summary: `"Trending on GitHub: {topic} (+{stars:,} stars this week) · {language}"`
- HackerNews items → `SignalType.SOCIAL_SIGNAL`, source = "Hacker News"
  - Summary: `"{title} ({points:,} points)"`
- Reddit items → `SignalType.SOCIAL_SIGNAL`, source = "Reddit"
  - Summary: `"{title} ({upvotes:,} upvotes)"`

**Relevance scoring:** simple keyword-overlap between the signal topic and the target role name:
```
relevance = min(1.0, |tokenise(topic) ∩ tokenise(target_role)| / |tokenise(target_role)|)
```

A signal whose topic contains both "ml" and "engineer" for target role "ML Engineer" → relevance = 1.0. A signal about "CSS art" → relevance = 0.0. Results are sorted descending by relevance before return.

---

### `trend_summariser.py` — LLM narrative generation

`TrendSummariser.summarise()` produces a 2–3 paragraph market intelligence narrative using `claude-haiku-4-5-20251001` (fast, cost-efficient for summarisation tasks).

**Prompt strategy:**

The system prompt instructs the model to:
1. Address demand context and salary numbers specifically
2. Name the top 3–5 trending skills
3. Reference concrete industry signals from the input data
4. Close with a freshness statement

The user prompt is built by `_build_user_prompt()` from the actual data:

```
Role: Senior ML Engineer
Country: CH
Active job postings found: 42
Salary benchmark: median 115,000 CHF/yr (p25: 92,000, p75: 143,750)
Top trending skills: Python (8 signals), Kubernetes (5 signals), FastAPI (4 signals), ...
Key industry signals:
  - Trending on GitHub: LangChain (+4,200 stars this week) · Python
  - Ask HN: What skills matter most for AI engineers? (450 points)
  ...
```

The model returns `{"summary": "<narrative>"}` — the wrapper JSON prevents accidental prose leaking and gives a reliable parse target.

**Resilience:**
- `@retry(stop_after_attempt(3), wait_exponential(0.5, 1, 8))` on `_summarise_with_llm`
- Fallback to `_fallback_summary()`: deterministic structured text built directly from the input data, e.g.:
  ```
  Market intelligence for Senior ML Engineer in CH: 42 active job postings found.
  Median salary is 115,000 CHF/yr (range: 92,000–143,750).
  Top trending skills: Python, Kubernetes, FastAPI, LangChain, AWS.
  Data freshness: real-time as of retrieval.
  ```

**Observability:**
- OTel span `market.summarise` with `role`, `country`, `correlation_id`
- `MARKET_SUMMARISE_DURATION` histogram
- `MARKET_SUMMARISE_TOTAL` counter labelled `status=llm|fallback`
- Structured log `market.summarised` with `summary_length`

---

### `market_agent.py` — Main agent

`MarketAgent` extends `BaseAgent` and implements `_execute(context)`.

**Country extraction (`_extract_country`):**

Extracts an ISO 2-letter country code from `context.user_profile.location`:

| Input | Rule | Output |
|---|---|---|
| `"Zurich, CH"` | Last comma token is 2-letter non-state | `"CH"` |
| `"Berlin, DE"` | Last comma token is 2-letter non-state | `"DE"` |
| `"San Francisco, CA"` | CA is a US state abbreviation | `"US"` |
| `"New York, NY, US"` | Last token is "US", not a US state | `"US"` |
| `"Berlin, Germany"` | Country name in `_COUNTRY_ALIASES` | `"DE"` |
| `None` or `""` | Default | `"CH"` |

`_COUNTRY_ALIASES` covers 20 countries in multiple languages (e.g. "deutschland" → "DE", "schweiz" → "CH", "suisse" → "CH").

**Constructor — dependency injection:**

```python
MarketAgent(
    job_board_fetcher=JobBoardFetcher(mcp_client),   # injectable for tests
    salary_fetcher=SalaryFetcher(mcp_client),         # injectable for tests
    trend_fetcher=TrendFetcher(mcp_client),            # injectable for tests
    signal_processor=SignalProcessor(),                # injectable for tests
    trend_summariser=TrendSummariser(llm=...),         # injectable for tests
    event_publisher=EventPublisher(redis),             # None → events silently skipped
    mcp_client=StubMCPClient(),                        # overrides all fetcher defaults
    llm=ChatAnthropic(...),                            # forwarded to TrendSummariser
)
```

**Output shape (`AgentResult.output`):**

```json
{
  "role": "Senior ML Engineer",
  "country": "CH",
  "job_postings": [
    {
      "title": "Senior ML Engineer",
      "company": "TechCorp AG",
      "location": "Zurich, CH",
      "required_skills": ["Python", "Docker", "Kubernetes", "AWS", "FastAPI"],
      "source": "LinkedIn",
      "posted_date": "2026-05-05",
      "salary_min": 97750,
      "salary_max": 132250,
      "currency": "CHF",
      "url": "https://linkedin.com/jobs/stub-1"
    }
  ],
  "salary_benchmark": {
    "role": "Senior ML Engineer",
    "country": "CH",
    "median_annual": 115000,
    "p25_annual": 92000,
    "p75_annual": 143750,
    "currency": "CHF",
    "source": "Levels.fyi + Glassdoor",
    "freshness_date": "2026-05-05"
  },
  "trending_skills": [
    {
      "name": "Python",
      "category": "language",
      "trend_direction": "rising",
      "signal_count": 8,
      "sources": ["github_trends", "job_board"],
      "evidence": "Mentioned in 8 market signals"
    },
    {
      "name": "Kubernetes",
      "category": "platform",
      "trend_direction": "rising",
      "signal_count": 5,
      "sources": ["github_trends", "job_board"],
      "evidence": "Mentioned in 5 market signals"
    }
  ],
  "industry_signals": [
    {
      "topic": "LangChain",
      "signal_type": "github_trend",
      "summary": "Trending on GitHub: LangChain (+4,200 stars this week) · Python",
      "source": "GitHub Trends",
      "relevance_score": 0.5,
      "url": null,
      "freshness_date": "2026-05-05"
    }
  ],
  "market_summary": "The Swiss market for Senior ML Engineers shows strong and growing demand...",
  "fetched_at": "2026-05-05T14:32:17.482Z",
  "data_sources": ["Glassdoor", "Indeed", "Levels.fyi + Glassdoor", "LinkedIn"],
  "processing_steps": [
    "market_data_fetching",
    "signal_processing",
    "trend_summarisation"
  ]
}
```

**Registration at worker startup:**

```python
from agents.market_intelligence import MarketAgent
from agents.core.agent_registry import registry

registry.register(MarketAgent(event_publisher=EventPublisher(redis_client)))
```

---

## Configuration

Five new optional settings in `AgentSettings` (all default to `None`/safe values):

```ini
# .env — all optional; StubMCPClient is used automatically when not set
MARKET_INTELLIGENCE_MODEL=claude-haiku-4-5-20251001

MCP_JOB_BOARD_URL=http://mcp-job-board:3001
MCP_SALARY_BENCHMARK_URL=http://mcp-salary-benchmark:3002
MCP_GITHUB_TRENDS_URL=http://mcp-github-trends:3003
MCP_SOCIAL_SIGNALS_URL=http://mcp-social-signals:3004
MCP_TIMEOUT_SECONDS=30.0
```

---

## Prometheus Metrics Added

| Metric name | Type | Labels | What it tracks |
|---|---|---|---|
| `career_agents_market_job_fetch_duration_seconds` | Histogram | — | Wall-clock time per MCP job board call |
| `career_agents_market_job_fetch_total` | Counter | `status` (success\|error) | Job board call outcomes |
| `career_agents_market_salary_fetch_duration_seconds` | Histogram | — | Wall-clock time per MCP salary call |
| `career_agents_market_salary_fetch_total` | Counter | `status` (success\|error) | Salary call outcomes |
| `career_agents_market_trend_fetch_duration_seconds` | Histogram | — | Total wall-clock time for concurrent trend fetch |
| `career_agents_market_trend_fetch_total` | Counter | `status` × `source` (github_trends\|social_signals) | Per-source trend call outcomes |
| `career_agents_market_summarise_duration_seconds` | Histogram | — | Wall-clock time for LLM summarisation |
| `career_agents_market_summarise_total` | Counter | `status` (llm\|fallback) | Summarisation method used |
| `career_agents_market_trending_skills_count` | Histogram | — | Number of trending skills per run |
| `career_agents_market_job_postings_count` | Histogram | — | Number of job postings retrieved per run |

---

## Test Coverage

The test file (`tests/test_market_agent.py`) contains **60+ unit tests** organised into 13 test classes. All MCP calls use `AsyncMock` or `StubMCPClient`. All LLM calls use `AsyncMock`. No network or Anthropic API key is required.

| Class | What is tested |
|---|---|
| `TestParsePostings` | Full posting parsed; entry without title skipped; missing optional fields produce `None`; invalid date → `None`; empty list; empty dict; non-dict item skipped |
| `TestToInt` | `None` → `None`; int value; string int; invalid string → `None` |
| `TestParseSalary` | Full salary parsed; empty raw → `None`; missing freshness → `None`; role/country fallback to params |
| `TestSignalProcessorExtractSkills` | Job posting skill counts; Python has highest count (3×); GitHub adds weighted signal; `RISING` when count ≥ 3; `STABLE` when count < 3; sources populated for multi-source skills; `top_n` respected; empty inputs return empty; social signals contribute count; evidence string includes count |
| `TestSignalProcessorIndustrySignals` | GitHub → `GITHUB_TREND` type, correct source and summary; social → `SOCIAL_SIGNAL`; Reddit source label; sorted by relevance descending; empty topic skipped; freshness date set |
| `TestSignalProcessorHelpers` | Canonical name lookups (fastapi → FastAPI, kubernetes → Kubernetes, aws → AWS); unknown → title case; language category; platform category; ai_ml category; unknown → tech; relevance zero for empty; exact match → 1.0; partial overlap between 0 and 1; no overlap → 0.0 |
| `TestBuildUserPrompt` | Role and country present; salary figures present; "not available" when no salary; trending skill names present; empty skills → "none identified" |
| `TestFallbackSummary` | Role and country; salary when present; top skills included; freshness note present; no salary → still returns string |
| `TestTrendSummariserAsync` | Successful LLM summarise; LLM failure → fallback text; invalid JSON → fallback; missing `summary` key → fallback; empty data → returns summary |
| `TestExtractCountry` | 2-letter code last part (CH, DE, FR); standalone code; country name in string; `None` → default; empty string → default; US city + state → "US"; US city + state + US → "US"; unknown → default |
| `TestSerialisers` | All posting keys present; date isoformat; `None` date; salary `None` → `None`; salary keys present; skill enum is string; signal enum is string; data sources deduplicated |
| `TestMarketAgent` | Agent type; display name; required output keys; 3 processing steps; role from profile; country extracted; country default on `None`; no role → "Software Engineer"; market summary present; salary `None` when fetcher returns `None`; salary serialised when present; job postings serialised; trending skills aggregated (Python tops 3× postings); 3 progress events; no events without publisher; `fetched_at` is ISO 8601; summariser receives correct args; full `run()` via `BaseAgent`; `FAILED` on unexpected error; partial failure (empty postings + salary still returned); industry signals present |
| *(integration test)* | `test_full_stub_client_pipeline`: end-to-end with real `StubMCPClient`, mocked LLM only — verifies ≥3 postings, salary not None, trending skills populated |

Run the full test suite:

```bash
cd agents
poetry run pytest src/agents/market_intelligence/tests/ -v
```

---

## Data Flow to Downstream Agents

| Downstream agent | Fields consumed |
|---|---|
| `RoadmapGenerationAgent` | `trending_skills` (top skills to embed in phase objectives), `salary_benchmark` (for realistic milestone framing), `market_summary` (for narrative context), `job_postings[*].required_skills` (cross-validates gap analysis) |
| `GapAnalysisAgent` | `trending_skills[*].name` (can supplement role requirements with market-confirmed skills), `job_postings[*].required_skills` (alternate signal for role requirements) |
| `LearningResourcesAgent` | `trending_skills` (prioritises courses on rising skills), `industry_signals` (surfaces relevant GitHub repos as learning projects) |
| `OpportunityAgent` | `job_postings` (live listings to evaluate), `salary_benchmark` (calibrates salary target filtering) |
| `OutputValidator` | `salary_benchmark` (grounds salary claims in validated data), `trending_skills` (verifies roadmap skills align with market demand) |

All downstream agents access this data via `context.plan_snapshot["market_intelligence"]`.

---

## Design Principles Applied

| Principle | How it manifests |
|---|---|
| **Low coupling** | All 5 pipeline components injected into `MarketAgent`; fetchers depend on `MCPClientProtocol` only; `SignalProcessor` has zero dependencies; `TrendSummariser` depends only on `ChatAnthropic` |
| **High cohesion** | All market intelligence logic lives inside `agents.market_intelligence`; the public interface is `MarketAgent` only |
| **Protocol-based abstraction** | `MCPClientProtocol` is a structural `Protocol`; `StubMCPClient` satisfies it without subclassing; agents cannot tell the difference at runtime |
| **Zero coupling to transport** | `HttpMCPClient` is only instantiated in `_build_mcp_client()`; fetchers never import `httpx` |
| **Automatic dev fallback** | `StubMCPClient` activates automatically when no MCP URLs are configured — the full pipeline runs end-to-end in development without any infrastructure |
| **Parallel I/O** | Steps 1–3 run with `asyncio.gather`; three MCP round-trips complete in the time of the slowest one |
| **Partial failure tolerance** | Each fetcher catches its own exception and returns an empty result; the pipeline always reaches the summariser; the summariser itself falls back to structured text |
| **LLM-free hot path** | `SignalProcessor` (step 4) is pure computation: no network, no LLM, always fast |
| **Freshness metadata** | Every signal, posting, and benchmark carries a `freshness_date`; the `MarketIntelligenceResult.fetched_at` is UTC-stamped at collection time |
| **Country awareness** | Country is a first-class parameter throughout the pipeline; salary stubs, currency mapping, and location extraction all handle CH / DE / FR / US / UK natively |
| **Observability** | OTel span per step, 10 Prometheus metrics covering duration and outcome for every I/O call, `STEP_PROGRESS` SSE events per pipeline step |
| **Testability** | Every external dependency (MCP client, LLM, event publisher) is constructor-injectable; 60+ tests run offline with no API key |
