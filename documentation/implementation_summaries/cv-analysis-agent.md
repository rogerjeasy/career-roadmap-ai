# CV Analysis Agent — Implementation Summary

**Date:** 2026-05-05
**Status:** Complete
**Author:** rogerjeasy

---

## Overview

The CV Analysis Agent is the second L3 Specialist Agent to be implemented. Its role is to act as the system's **structured reading layer for career documents**: it accepts a CV or LinkedIn export (PDF bytes or plain text), extracts every piece of structured information from it, normalises the resulting skills into a canonical graph, and produces a quantified role-readiness score relative to the user's target role.

By running in Phase 2 of the multi-agent DAG (in parallel with Market Intelligence), the CV Analysis Agent gives all downstream agents — Gap Analysis, Roadmap Generation, Learning Resources, Opportunity — a rich, machine-readable picture of where the candidate actually stands today.

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
  ┌──────────────────────────────────────────────────────────┐
  │  Node 1: parse_intent                                    │
  │  Node 2: score_completeness  (ClarificationEngine)       │
  │  Node 3: build_dag           (TaskPlanner)               │
  │                                                          │
  │  ┌── Phase 1 ──────────────────────────────────────┐    │
  │  │  IntakeAgent  (NER profile building)            │    │
  │  └─────────────────────────────────────────────────┘    │
  │         │ enriched UserProfile in plan_snapshot          │
  │         ▼                                               │
  │  ┌── Phase 2 (parallel) ───────────────────────────┐    │
  │  │  CVAgent  ◄── THIS IMPLEMENTATION               │    │
  │  │    PDFParser → CVParser → SkillExtractor        │    │
  │  │    → SkillNormaliser → ReadinessScorer          │    │
  │  │                         MARKET_INTELLIGENCE     │    │
  │  └─────────────────────────────────────────────────┘    │
  │         │                                               │
  │  ┌── Phase 3 ──────────────────────────────────────┐    │
  │  │  GAP_ANALYSIS (consumes skill_graph + readiness) │   │
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
      │  AgentResult.output["skill_graph"] + ["readiness"]
      ▼
  Synthesizer Node → OrchestratorResult → SSE → Client
```

---

## Files Introduced

### New files

| Path | Role |
|---|---|
| `agents/src/agents/cv_analysis/models.py` | Pure domain types: `ParsedCV`, `SkillGraph`, `SkillNode`, `ReadinessResult`, `ReadinessBreakdown`, `ExperienceEntry`, `EducationEntry`, `ProjectEntry` |
| `agents/src/agents/cv_analysis/pdf_parser.py` | `PDFParser` — `pypdf`-based text extraction with UTF-8 fallback |
| `agents/src/agents/cv_analysis/cv_parser.py` | `CVParser` — LLM-based structured extraction from raw CV text |
| `agents/src/agents/cv_analysis/skill_extractor.py` | `SkillExtractor` — keyword scan across 3 CV sections; no LLM |
| `agents/src/agents/cv_analysis/skill_normaliser.py` | `SkillNormaliser` — 110-entry alias dict + LLM batch normalisation |
| `agents/src/agents/cv_analysis/readiness_scorer.py` | `ReadinessScorer` — 5-dimension LLM scoring + heuristic fallback |
| `agents/src/agents/cv_analysis/cv_agent.py` | `CVAgent` — extends `BaseAgent`, orchestrates the 5-step pipeline |
| `agents/src/agents/cv_analysis/__init__.py` | Public package surface |
| `agents/src/agents/cv_analysis/tests/__init__.py` | Test package marker |
| `agents/src/agents/cv_analysis/tests/test_cv_agent.py` | 55 unit tests (all LLM calls mocked) |

### Modified files

| Path | Change |
|---|---|
| `agents/src/agents/core/observability.py` | Added 8 CV-analysis-specific Prometheus metrics |
| `agents/pyproject.toml` | Added `pypdf >=5.0.0` dependency |

---

## Pipeline Design

The agent runs five discrete steps in sequence. Each step is wrapped in its own OTel span and emits a `STEP_PROGRESS` SSE event to the client.

```
CV document (PDF bytes or plain text)
        │
        ▼  Step 1
  PDFParser.extract_text()
        │  raw_text: str
        ▼  Step 2
  CVParser.parse()              ← LLM call (claude-sonnet-4-6)
        │  ParsedCV
        ▼  Step 3
  SkillExtractor.extract()      ← no LLM, pure keyword scan
        │  raw_skills: list[str]
        ▼  Step 4
  SkillNormaliser.normalise()   ← alias dict + LLM batch call
        │  SkillGraph
        ▼  Step 5
  ReadinessScorer.score()       ← LLM call + heuristic fallback
        │  ReadinessResult
        ▼
  AgentResult.output
```

**LLM budget per run:** 2–3 LLM calls (CVParser + ReadinessScorer always; SkillNormaliser only for skills not in the alias dictionary).

---

## Component Design

### `models.py` — Domain types

Nine frozen dataclasses that carry structured data through the pipeline. All are **internal to the cv_analysis package**; nothing outside `agents.cv_analysis` imports from here directly (the public surface is via `__init__.py`).

```python
@dataclass(frozen=True)
class ParsedCV:
    raw_text: str
    full_name: str | None
    email: str | None
    location: str | None
    summary: str | None
    total_experience_months: int | None
    experience: list[ExperienceEntry]
    education: list[EducationEntry]
    projects: list[ProjectEntry]
    raw_skills: list[str]
    certifications: list[str]
    languages: list[str]          # spoken languages only

@dataclass(frozen=True, slots=True)
class SkillNode:
    name: str                     # raw string from CV
    canonical_name: str           # normalised form
    category: str                 # programming_language | framework | database |
                                  # platform | tool | soft_skill | domain |
                                  # certification | other
    proficiency: str | None       # beginner | intermediate | advanced | expert
    years_of_experience: float | None
    evidence_sources: list[str]

@dataclass(frozen=True)
class SkillGraph:
    nodes: list[SkillNode]
    # computed properties:
    #   .canonical_names → list[str]
    #   .by_category     → dict[str, list[SkillNode]]

@dataclass(frozen=True, slots=True)
class ReadinessBreakdown:
    required_skills_matched: float    # 0–1
    preferred_skills_matched: float   # 0–1
    experience_level_match: float     # 0–1
    education_match: float            # 0–1
    domain_alignment: float           # 0–1

@dataclass(frozen=True)
class ReadinessResult:
    overall_score: float              # 0–1 weighted composite
    breakdown: ReadinessBreakdown
    matched_skills: list[str]
    missing_required_skills: list[str]
    missing_preferred_skills: list[str]
    recommendations: list[str]        # 3–5 actionable steps
```

---

### `pdf_parser.py` — Text extraction

`PDFParser.extract_text()` accepts three input shapes and always returns a `str`:

| Input type | Behaviour |
|---|---|
| `str` | Pass-through — already plain text; no processing |
| `bytes` | Attempt `pypdf.PdfReader` extraction |
| `BinaryIO` | Attempt `pypdf.PdfReader` extraction |

When `pypdf` fails (corrupt PDF, unsupported encryption, etc.) the fallback decodes the raw bytes as `UTF-8` with `errors="replace"` so the pipeline always receives a string, even if degraded.

Base64-encoded PDF bytes transmitted over JSON (common in API payloads) are decoded by `CVAgent._execute()` before passing them to `PDFParser`, keeping the parser itself format-agnostic.

**Observability:**
- OTel span `cv.pdf_parse` with attributes: `input_type`, `method` (passthrough | pypdf | fallback_utf8), `text_length`
- `CV_PDF_PARSE_DURATION` histogram (seconds)

---

### `cv_parser.py` — Structured LLM extraction

`CVParser.parse()` makes a single structured LLM call against the raw CV text and returns a fully typed `ParsedCV`. The system prompt instructs the model to extract:

| Section | Fields extracted |
|---|---|
| Identity | `full_name`, `email`, `phone`, `location`, `summary` |
| Experience | Per-role: `company`, `title`, `start_date`, `end_date`, `duration_months`, `responsibilities[]`, `impact_statements[]` |
| Education | Per-institution: `institution`, `degree`, `field_of_study`, `graduation_year`, `gpa` |
| Projects | Per-project: `name`, `description`, `technologies[]`, `impact` |
| Skills | `raw_skills[]` — aggregated from all sections |
| Other | `certifications[]`, `languages[]` (spoken only), `total_experience_months` |

**Key rules enforced in the prompt:**
- Extract only information present in the text; never invent values.
- `impact_statements` should focus on quantified results (numbers, percentages, scale).
- `languages` means spoken/written human languages, not programming languages.
- `total_experience_months` is the sum of non-overlapping roles; `null` when unclear.

**Token budget:** CV text is truncated to 12 000 characters before being sent to stay within model token limits while covering any realistic résumé.

**Resilience:**
- `_call_llm` decorated with `@retry(stop_after_attempt(3), wait_exponential(0.5, 1, 8))`.
- On failure after all retries: returns `ParsedCV(raw_text=raw_text)` — a minimal valid result — so the pipeline continues rather than crashing.
- Empty or whitespace-only text short-circuits immediately (no LLM call).

**Observability:**
- OTel span `cv.parse` with attributes: `experience_entries`, `education_entries`, `raw_skills_count`, `duration_ms`
- `CV_PARSE_DURATION` histogram (seconds)
- `CV_PARSE_TOTAL` counter labelled `status=success|fallback`

---

### `skill_extractor.py` — Keyword-based skill collection

`SkillExtractor.extract()` collects skill mentions from three sections of the `ParsedCV` without any LLM call. It is the fastest step in the pipeline.

**Three collection sources:**

| Source | Method |
|---|---|
| `parsed_cv.raw_skills` | Direct copy — skills already listed in the CV's skills section |
| `parsed_cv.experience[*].responsibilities` | Keyword scan against a curated set of ~65 technology names |
| `parsed_cv.projects[*].technologies` | Direct copy — explicit tech stack per project |

**Deduplication:** case-insensitive; first occurrence wins. For example, `"python"` and `"Python"` from different sections produce one entry.

**Keyword catalogue** covers: programming languages (Python, TypeScript, Go, Rust, …), frontend frameworks (React, Next.js, Vue, Angular, …), backend frameworks (FastAPI, Django, Spring Boot, …), databases (PostgreSQL, MongoDB, Redis, Elasticsearch, …), cloud platforms (AWS, GCP, Azure), container/infra tools (Docker, Kubernetes, Terraform, …), data/ML libraries (PyTorch, scikit-learn, Pandas, Airflow, MLflow, LangChain, …), and API protocols (GraphQL, gRPC, REST).

**Observability:**
- OTel span `cv.skill_extraction` with attribute `total_skills`
- `CV_SKILLS_EXTRACTED_TOTAL` counter labelled `source=skills_section|experience|projects`

---

### `skill_normaliser.py` — Two-pass normalisation

`SkillNormaliser.normalise()` converts the raw skill list into a `SkillGraph` via two passes:

**Pass 1 — Dictionary lookup (fast path, zero latency):**

A 110-entry alias map resolves common abbreviations and spelling variants without touching the network. Examples:

| Raw input | Canonical name | Category |
|---|---|---|
| `"js"`, `"reactjs"` | `"JavaScript"`, `"React"` | `programming_language`, `framework` |
| `"k8s"` | `"Kubernetes"` | `tool` |
| `"postgres"` | `"PostgreSQL"` | `database` |
| `"golang"` | `"Go"` | `programming_language` |
| `"sklearn"`, `"scikit learn"` | `"scikit-learn"` | `framework` |
| `"wandb"` | `"Weights & Biases"` | `tool` |

**Pass 2 — LLM batch call (slow path, unknown skills only):**

Skills not found in the alias map are sent to the LLM in a single batch request. The model assigns:
- `canonical` — the display name (e.g. `"Temporal"` stays as-is if it is already canonical)
- `category` — one of: `programming_language | framework | database | platform | tool | soft_skill | domain | certification | other`

Uses `claude-haiku-4-5` (the validator model) for cost efficiency — categorisation does not require a large reasoning model.

**Graceful degradation:** if the LLM call fails after retries, unknown skills are kept as-is with `category="other"`. The pipeline never hard-fails due to a missing skill label.

**Observability:**
- OTel span `cv.skill_normalise` with attributes: `raw_skill_count`, `resolved_count`, `llm_resolved_count`, `duration_ms`
- `CV_NORMALISE_DURATION` histogram (seconds)
- `CV_NORMALISE_TOTAL` counter labelled `status=dict_only|llm|fallback`

---

### `readiness_scorer.py` — Role-readiness scoring

`ReadinessScorer.score()` compares the candidate's `SkillGraph` and `ParsedCV` against the target role and returns a `ReadinessResult` with five scored dimensions.

**Scoring dimensions and weights:**

| Dimension | Weight | What it measures |
|---|---|---|
| `required_skills_matched` | 35% | Fraction of must-have skills for the role covered by the candidate |
| `experience_level_match` | 25% | Whether total experience meets the role's typical requirement |
| `preferred_skills_matched` | 15% | Fraction of nice-to-have skills covered |
| `domain_alignment` | 15% | How closely the candidate's work domain overlaps with the target role |
| `education_match` | 10% | Degree field alignment (1.0 directly relevant; 0.7 adjacent; 0.4 unrelated) |

Weights sum to 1.0. The overall score is computed as:

```
overall = Σ (dimension_score × dimension_weight)
```

The LLM is used for semantic matching — a skill node named `"scikit-learn"` satisfies a requirement for `"ML frameworks"` even though the strings differ.

**Heuristic fallback:** when the LLM is unavailable, a local calculation is performed using only the measurable signals (skill count and total experience months). Education and domain alignment default to `0.0` in the fallback because they cannot be assessed without LLM context; this keeps the fallback score conservative and honest.

```python
exp_score   = min(1.0, total_experience_months / 60)  # 5 years → 1.0
skill_score = min(1.0, skill_count / 15)               # 15 skills → 1.0
overall     = skill_score × 0.50 + exp_score × 0.25
```

**Observability:**
- OTel span `cv.readiness_score` with attributes: `target_role`, `skill_count`, `overall_score`, `duration_ms`
- `CV_READINESS_DURATION` histogram (seconds)
- `CV_READINESS_SCORE` histogram — tracks score distribution across all runs

---

### `cv_agent.py` — Main agent

`CVAgent` extends `BaseAgent` and implements `_execute(context)` as the 5-step sequential pipeline described above.

**Input (from `context.plan_snapshot["cv"]`):**

```json
{
  "cv_document": "<base64-encoded PDF bytes or plain text string>",
  "source_type": "pdf | text | linkedin_export"
}
```

PDF bytes transmitted over JSON must be base64-encoded. `CVAgent._execute()` detects `source_type == "pdf"` and calls `base64.b64decode()` before passing the bytes to `PDFParser`. If decoding fails, the document is treated as plain text.

**Output shape (`AgentResult.output`):**

```json
{
  "cv_text_length": 4821,
  "parsed_cv": {
    "full_name": "Jane Doe",
    "email": "jane@example.com",
    "location": "Berlin, Germany",
    "total_experience_months": 48,
    "raw_skills": ["Python", "FastAPI", "Docker", "PostgreSQL"],
    "certifications": ["AWS SAA 2023"],
    "languages": ["English", "German"],
    "experience": [
      {
        "company": "Acme Corp",
        "title": "Backend Engineer",
        "start_date": "2022-01",
        "end_date": "present",
        "duration_months": 28,
        "responsibilities": ["Built REST APIs using Python and FastAPI"],
        "impact_statements": ["Reduced API latency by 40%"]
      }
    ],
    "education": [
      {
        "institution": "TU Berlin",
        "degree": "MSc",
        "field_of_study": "Computer Science",
        "graduation_year": 2021,
        "gpa": 1.5
      }
    ],
    "projects": [
      {
        "name": "DataPipeline",
        "description": "ETL pipeline for analytics",
        "technologies": ["Python", "Kafka", "PostgreSQL"],
        "impact": "Processed 1M events/day"
      }
    ]
  },
  "skill_graph": {
    "nodes": [
      {
        "name": "Python", "canonical_name": "Python",
        "category": "programming_language",
        "proficiency": null, "years_of_experience": null,
        "evidence_sources": []
      }
    ],
    "by_category": {
      "programming_language": ["Python"],
      "framework": ["FastAPI"],
      "tool": ["Docker"],
      "database": ["PostgreSQL"]
    }
  },
  "readiness": {
    "overall_score": 0.73,
    "breakdown": {
      "required_skills_matched": 0.80,
      "preferred_skills_matched": 0.60,
      "experience_level_match": 0.80,
      "education_match": 1.00,
      "domain_alignment": 0.75
    },
    "matched_skills": ["Python", "FastAPI", "PostgreSQL"],
    "missing_required_skills": ["Kubernetes", "CI/CD pipelines"],
    "missing_preferred_skills": ["Terraform", "Redis"],
    "recommendations": [
      "Earn the Certified Kubernetes Application Developer (CKAD) certificate",
      "Build a personal project using GitHub Actions for CI/CD",
      "Complete the HashiCorp Terraform Associate certification"
    ]
  },
  "processing_steps": [
    "pdf_extraction",
    "cv_parsing",
    "skill_extraction",
    "skill_normalisation",
    "readiness_scoring"
  ]
}
```

Downstream agents access this via `context.plan_snapshot["cv_analysis"]`. `GapAgent` consumes `skill_graph` and `readiness.missing_required_skills`; `RoadmapAgent` consumes `readiness.overall_score` to calibrate phase duration.

**Constructor — dependency injection:**

```python
CVAgent(
    pdf_parser=PDFParser(),             # injectable for tests
    cv_parser=CVParser(llm=...),        # injectable for tests
    skill_extractor=SkillExtractor(),   # injectable for tests
    skill_normaliser=SkillNormaliser(llm=...),  # injectable for tests
    readiness_scorer=ReadinessScorer(llm=...),  # injectable for tests
    event_publisher=EventPublisher(redis),       # None → events silently skipped
    llm=ChatAnthropic(...),             # forwarded to LLM components if not provided
)
```

**Registration at worker startup:**

```python
from agents.cv_analysis import CVAgent
from agents.core.agent_registry import registry

registry.register(CVAgent(event_publisher=EventPublisher(redis_client)))
```

---

## Prometheus Metrics Added

| Metric name | Type | Labels | What it tracks |
|---|---|---|---|
| `career_agents_cv_pdf_parse_duration_seconds` | Histogram | — | Wall-clock time for PDF text extraction |
| `career_agents_cv_parse_duration_seconds` | Histogram | — | Wall-clock time for LLM CV structure extraction |
| `career_agents_cv_parse_total` | Counter | `status` (success \| fallback) | LLM CV parse call outcomes |
| `career_agents_cv_skills_extracted_total` | Counter | `source` (skills_section \| experience \| projects) | Skill mentions per CV section |
| `career_agents_cv_normalise_duration_seconds` | Histogram | — | Wall-clock time for skill normalisation |
| `career_agents_cv_normalise_total` | Counter | `status` (dict_only \| llm \| fallback) | Normalisation path taken |
| `career_agents_cv_readiness_duration_seconds` | Histogram | — | Wall-clock time for readiness scoring |
| `career_agents_cv_readiness_score` | Histogram | — | Overall score distribution across all runs |

---

## Test Coverage

The test file (`tests/test_cv_agent.py`) contains **55 unit tests** organised into 13 test classes. All LLM calls are replaced with `AsyncMock` — no network, no Anthropic API key required.

| Class | What is tested |
|---|---|
| `TestPDFParser` | String passthrough; invalid-PDF fallback; UTF-8 byte decoding; pypdf delegation |
| `TestSafeInt` | Integer coercion from int, float, string; `None` handling; invalid string |
| `TestSafeFloat` | Float coercion; `None`; invalid string |
| `TestBuildParsedCV` | Full LLM response parsing; company-less experience skipped; institution-less education skipped; empty raw dict |
| `TestCVParserParse` | Empty text short-circuit; successful LLM parse; LLM failure fallback; invalid JSON fallback |
| `TestScanKeywords` | Known keyword detection; case-insensitive match; no-match empty result |
| `TestSkillExtractor` | Raw skills collected; project technologies collected; case-insensitive dedup; experience keyword extraction; empty CV |
| `TestSkillNormaliserDictPath` | Known aliases resolved without LLM; correct categories assigned; empty input |
| `TestSkillNormaliserLLMPath` | Unknown skills sent to LLM; LLM failure falls back to `"other"`; mixed known/unknown |
| `TestSkillGraph` | `by_category` grouping; `canonical_names` property |
| `TestBuildReadinessResult` | Score clamping above 1.0; clamping below 0.0; all-ones → 1.0; all-zeros → 0.0 |
| `TestHeuristicScore` | Experienced candidate > 0.0; zero input → 0.0; always in [0, 1]; fallback recommendation present |
| `TestReadinessScorerAsync` | Successful LLM scoring; LLM failure falls back to heuristic |
| `TestCVAgent` | Agent type/display name; required output keys; 5 processing steps; PDF parser call args; CV parser call args; target role routing; empty target role; readiness in output; skill graph in output; 5 progress events; no events without publisher; full `run()` via BaseAgent |
| `TestSerialiseParsedCV` | All top-level fields; experience entry structure; minimal CV |
| `TestSerialiseSkillGraph` | nodes + by_category present; node required fields; category grouping |

Run the full test suite:

```bash
cd agents
poetry run pytest src/agents/cv_analysis/tests/ -v
```

---

## Design Principles Applied

| Principle | How it manifests |
|---|---|
| **Low coupling** | All 5 pipeline components are injected into `CVAgent`; no component knows about another or about the agent framework |
| **High cohesion** | All CV-analysis logic lives inside `agents.cv_analysis`; the public interface is through `__init__.py` only |
| **Statelessness** | Every component holds only its LLM client; all input/output flows through method arguments |
| **Two-speed normalisation** | Alias dictionary (zero latency) handles ~90% of common skills; LLM fallback handles the long tail — avoids unnecessary API calls |
| **Graceful degradation** | Every LLM component has an explicit fallback: CVParser → empty ParsedCV; SkillNormaliser → category `"other"`; ReadinessScorer → heuristic score. The pipeline never hard-fails. |
| **Conservative heuristics** | The heuristic readiness score intentionally excludes education and domain dimensions (sets them to 0) because they cannot be assessed without LLM context — avoids false confidence in the fallback path |
| **Observability** | OTel span per component step, 8 Prometheus metrics covering duration + outcome for every LLM call, `STEP_PROGRESS` SSE events per pipeline step |
| **Testability** | Every external dependency (LLM, Redis publisher, pypdf) is constructor-injectable with a sensible `None` default; 55 tests require no network |
