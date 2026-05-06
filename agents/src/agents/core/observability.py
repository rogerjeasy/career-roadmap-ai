"""OpenTelemetry tracing and Prometheus metrics for the agents worker.

Call ``configure_observability()`` once at Celery worker startup.
All other modules use ``get_tracer(name)`` for span creation and the
module-level metric objects for counters/histograms.

Prometheus metrics are best-effort: if ``prometheus_client`` cannot bind
a port (e.g. multi-process Celery), the metrics are still recorded in
memory and exported via the default multiprocess collector when configured.
"""
from __future__ import annotations

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from prometheus_client import Counter, Histogram

from agents.config import agent_settings
from agents.core.logging import get_logger

_SERVICE_NAME = "career-agents"
_SERVICE_VERSION = "0.1.0"

logger = get_logger(__name__)

# ── Tracer setup ────────────────────────────────────────────────────────────


def configure_observability() -> None:
    """Initialise OTel TracerProvider for the Celery worker process.

    In production, attaches an OTLP gRPC exporter when
    ``OTEL_EXPORTER_OTLP_ENDPOINT`` is set. In development, logs spans to
    stdout so they are visible without a collector.
    """
    resource = Resource.create(
        {
            "service.name": _SERVICE_NAME,
            "service.version": _SERVICE_VERSION,
            "deployment.environment": agent_settings.environment,
        }
    )
    provider = TracerProvider(resource=resource)

    if agent_settings.environment == "development":
        provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
    else:
        _attach_otlp_exporter(provider)

    trace.set_tracer_provider(provider)
    logger.info(
        "observability.configured",
        environment=agent_settings.environment,
        service=_SERVICE_NAME,
    )


def _attach_otlp_exporter(provider: TracerProvider) -> None:
    """Attach an OTLP span exporter if the endpoint env-var is set."""
    try:
        import os

        endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
        if not endpoint:
            logger.info("observability.otlp_endpoint_not_set")
            return

        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
            OTLPSpanExporter,
        )

        provider.add_span_processor(
            BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint))
        )
        logger.info("observability.otlp_attached", endpoint=endpoint)
    except ImportError:
        logger.warning("observability.otlp_exporter_unavailable")


def get_tracer(name: str) -> trace.Tracer:
    """Return a named tracer from the current provider."""
    return trace.get_tracer(name, tracer_provider=trace.get_tracer_provider())


# ── Prometheus metrics ──────────────────────────────────────────────────────
# Registered at import time; safe to import from multiple modules.

CLARIFICATION_SCORE = Histogram(
    "career_agents_clarification_score",
    "Profile completeness score distribution at each scoring call",
    buckets=[0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.75, 0.8, 0.9, 1.0],
)

CLARIFICATION_QUESTIONS_TOTAL = Counter(
    "career_agents_clarification_questions_total",
    "Total clarification question-generation calls by outcome",
    ["status"],  # generated | fallback | skipped
)

CLARIFICATION_ANSWER_PARSE_TOTAL = Counter(
    "career_agents_clarification_answer_parse_total",
    "Total answer-parsing LLM calls by outcome",
    ["status"],  # success | empty | fallback
)

CLARIFICATION_ANSWER_PARSE_DURATION = Histogram(
    "career_agents_clarification_answer_parse_duration_seconds",
    "Wall-clock time for answer-parsing LLM calls in seconds",
    buckets=[0.1, 0.25, 0.5, 1.0, 2.0, 4.0, 8.0, 16.0],
)

CLARIFICATION_ROUND_TOTAL = Counter(
    "career_agents_clarification_round_total",
    "Total clarification rounds initiated (one per incomplete-profile detection)",
)

CLARIFICATION_RESOLVED_TOTAL = Counter(
    "career_agents_clarification_resolved_total",
    "Clarification rounds where answer parsing lifted the profile above threshold",
)

QUESTION_GENERATION_DURATION = Histogram(
    "career_agents_question_generation_duration_seconds",
    "Wall-clock time for question-generation LLM calls in seconds",
    buckets=[0.1, 0.25, 0.5, 1.0, 2.0, 4.0, 8.0],
)

# ── Agent dispatch metrics ──────────────────────────────────────────────────

AGENT_DISPATCH_DURATION = Histogram(
    "career_agents_agent_dispatch_duration_seconds",
    "Wall-clock time for a single agent invocation including retries",
    ["agent_type", "status"],  # status: completed | failed | timeout | partial
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0, 120.0],
)

AGENT_RETRY_TOTAL = Counter(
    "career_agents_agent_retry_total",
    "Total retry attempts made for agent invocations",
    ["agent_type"],
)

AGENT_SKIP_TOTAL = Counter(
    "career_agents_agent_skip_total",
    "Total optional agents skipped after exhausting all retries",
    ["agent_type"],
)

# ── Output validation metrics ───────────────────────────────────────────────

VALIDATION_STAGE_DURATION = Histogram(
    "career_agents_validation_stage_duration_seconds",
    "Wall-clock time for each validation stage LLM call",
    ["stage"],  # stage: realism_coherence | grounding | confidence
    buckets=[0.1, 0.25, 0.5, 1.0, 2.0, 4.0, 8.0],
)

VALIDATION_GROUNDING_SCORE = Histogram(
    "career_agents_validation_grounding_score",
    "Grounding score distribution from Stage 2 validation",
    buckets=[0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0],
)

VALIDATION_PASSED_TOTAL = Counter(
    "career_agents_validation_passed_total",
    "Total validation outcomes by result",
    ["result"],  # result: passed | failed
)

# ── Orchestration step-progress metrics ────────────────────────────────────

STEP_PROGRESS_TOTAL = Counter(
    "career_agents_step_progress_total",
    "Total STEP_PROGRESS events emitted, by step name",
    ["step_name"],
)

# ── Intake agent metrics ────────────────────────────────────────────────────

INTAKE_SLOT_EXTRACTION_DURATION = Histogram(
    "career_agents_intake_slot_extraction_duration_seconds",
    "Wall-clock time for NER slot-extraction LLM calls",
    buckets=[0.1, 0.25, 0.5, 1.0, 2.0, 4.0, 8.0, 16.0],
)

INTAKE_SLOTS_EXTRACTED_TOTAL = Counter(
    "career_agents_intake_slots_extracted_total",
    "Total slot-extraction LLM calls by outcome",
    ["status"],  # success | fallback
)

INTAKE_PROFILE_COMPLETENESS = Histogram(
    "career_agents_intake_profile_completeness",
    "Profile completeness score distribution after intake processing",
    buckets=[0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.75, 0.8, 0.9, 1.0],
)

# ── CV Analysis agent metrics ───────────────────────────────────────────────

CV_PDF_PARSE_DURATION = Histogram(
    "career_agents_cv_pdf_parse_duration_seconds",
    "Wall-clock time for PDF text extraction",
    buckets=[0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0],
)

CV_PARSE_DURATION = Histogram(
    "career_agents_cv_parse_duration_seconds",
    "Wall-clock time for LLM-based CV structure extraction",
    buckets=[0.5, 1.0, 2.0, 4.0, 8.0, 16.0, 30.0],
)

CV_PARSE_TOTAL = Counter(
    "career_agents_cv_parse_total",
    "Total CV structure-extraction LLM calls by outcome",
    ["status"],  # success | fallback
)

CV_SKILLS_EXTRACTED_TOTAL = Counter(
    "career_agents_cv_skills_extracted_total",
    "Total skill mentions collected from CV sections by source",
    ["source"],  # skills_section | experience | projects
)

CV_NORMALISE_DURATION = Histogram(
    "career_agents_cv_normalise_duration_seconds",
    "Wall-clock time for skill normalisation (dict + LLM)",
    buckets=[0.1, 0.25, 0.5, 1.0, 2.0, 4.0, 8.0],
)

CV_NORMALISE_TOTAL = Counter(
    "career_agents_cv_normalise_total",
    "Total skill normalisation calls by resolution method",
    ["status"],  # dict_only | llm | fallback
)

CV_READINESS_DURATION = Histogram(
    "career_agents_cv_readiness_duration_seconds",
    "Wall-clock time for readiness scoring LLM calls",
    buckets=[0.5, 1.0, 2.0, 4.0, 8.0, 16.0, 30.0],
)

CV_READINESS_SCORE = Histogram(
    "career_agents_cv_readiness_score",
    "Readiness score distribution across CV analysis runs",
    buckets=[0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0],
)

# ── Gap Analysis agent metrics ──────────────────────────────────────────────

GAP_ROLE_PROFILE_DURATION = Histogram(
    "career_agents_gap_role_profile_duration_seconds",
    "Wall-clock time for role profiling LLM calls",
    buckets=[0.5, 1.0, 2.0, 4.0, 8.0, 16.0, 30.0],
)

GAP_ROLE_PROFILE_TOTAL = Counter(
    "career_agents_gap_role_profile_total",
    "Total role-profiling calls by resolution method",
    ["status"],  # llm | fallback
)

GAP_SKILL_SCORE_DURATION = Histogram(
    "career_agents_gap_skill_score_duration_seconds",
    "Wall-clock time for skill gap-scoring LLM calls",
    buckets=[0.5, 1.0, 2.0, 4.0, 8.0, 16.0, 30.0],
)

GAP_SKILL_SCORE_TOTAL = Counter(
    "career_agents_gap_skill_score_total",
    "Total skill gap-scoring calls by resolution method",
    ["status"],  # llm | fallback
)

GAP_DIFF_SCORE = Histogram(
    "career_agents_gap_diff_score",
    "Overall diff-score distribution across gap analysis runs",
    buckets=[0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0],
)

GAP_GAP_COUNT = Histogram(
    "career_agents_gap_gap_count",
    "Number of identified gaps per gap analysis run",
    buckets=[0, 1, 2, 3, 5, 8, 12, 16, 20],
)

# ── Market Intelligence agent metrics ───────────────────────────────────────

MARKET_JOB_FETCH_DURATION = Histogram(
    "career_agents_market_job_fetch_duration_seconds",
    "Wall-clock time for MCP job board fetch calls",
    buckets=[0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0],
)

MARKET_JOB_FETCH_TOTAL = Counter(
    "career_agents_market_job_fetch_total",
    "Total MCP job board fetch calls by outcome",
    ["status"],  # success | error
)

MARKET_SALARY_FETCH_DURATION = Histogram(
    "career_agents_market_salary_fetch_duration_seconds",
    "Wall-clock time for MCP salary benchmark fetch calls",
    buckets=[0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0],
)

MARKET_SALARY_FETCH_TOTAL = Counter(
    "career_agents_market_salary_fetch_total",
    "Total MCP salary benchmark fetch calls by outcome",
    ["status"],  # success | error
)

MARKET_TREND_FETCH_DURATION = Histogram(
    "career_agents_market_trend_fetch_duration_seconds",
    "Wall-clock time for concurrent GitHub + social trend fetch",
    buckets=[0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0],
)

MARKET_TREND_FETCH_TOTAL = Counter(
    "career_agents_market_trend_fetch_total",
    "Total MCP trend fetch calls by outcome and source",
    ["status", "source"],  # status: success|error  source: github_trends|social_signals
)

MARKET_SUMMARISE_DURATION = Histogram(
    "career_agents_market_summarise_duration_seconds",
    "Wall-clock time for LLM trend summarisation calls",
    buckets=[0.5, 1.0, 2.0, 4.0, 8.0, 16.0, 30.0],
)

MARKET_SUMMARISE_TOTAL = Counter(
    "career_agents_market_summarise_total",
    "Total trend summarisation calls by method",
    ["status"],  # llm | fallback
)

MARKET_TRENDING_SKILLS_COUNT = Histogram(
    "career_agents_market_trending_skills_count",
    "Number of trending skills identified per market intelligence run",
    buckets=[0, 1, 2, 3, 5, 8, 12, 16, 20],
)

MARKET_JOB_POSTINGS_COUNT = Histogram(
    "career_agents_market_job_postings_count",
    "Number of job postings retrieved per market intelligence run",
    buckets=[0, 1, 2, 3, 5, 10, 20, 50, 100],
)

# ── Roadmap Generation agent metrics ────────────────────────────────────────

ROADMAP_PHASE_GEN_DURATION = Histogram(
    "career_agents_roadmap_phase_gen_duration_seconds",
    "Wall-clock time for LLM phase-generation calls",
    buckets=[0.5, 1.0, 2.0, 4.0, 8.0, 16.0, 30.0],
)

ROADMAP_PHASE_GEN_TOTAL = Counter(
    "career_agents_roadmap_phase_gen_total",
    "Total phase-generation calls by method",
    ["status"],  # llm | fallback
)

ROADMAP_MILESTONE_GEN_DURATION = Histogram(
    "career_agents_roadmap_milestone_gen_duration_seconds",
    "Wall-clock time for LLM milestone-generation calls",
    buckets=[0.5, 1.0, 2.0, 4.0, 8.0, 16.0, 30.0],
)

ROADMAP_MILESTONE_GEN_TOTAL = Counter(
    "career_agents_roadmap_milestone_gen_total",
    "Total milestone-generation calls by method",
    ["status"],  # llm | fallback
)

ROADMAP_PHASE_COUNT = Histogram(
    "career_agents_roadmap_phase_count",
    "Number of phases generated per roadmap run",
    buckets=[1, 2, 3, 4, 5, 6, 8],
)

ROADMAP_MILESTONE_COUNT = Histogram(
    "career_agents_roadmap_milestone_count",
    "Number of milestones generated per roadmap run",
    buckets=[1, 2, 3, 4, 5, 6, 8],
)

ROADMAP_RESOURCE_LINK_TOTAL = Counter(
    "career_agents_roadmap_resource_link_total",
    "Total resources linked per source",
    ["source"],  # rag | catalog
)

# ── Validator / Critic Agent metrics ────────────────────────────────────────

VALIDATOR_EVIDENCE_COVERAGE = Histogram(
    "career_agents_validator_evidence_coverage",
    "Evidence coverage score distribution per validation run",
    buckets=[0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0],
)

VALIDATOR_GROUNDING_SCORE = Histogram(
    "career_agents_validator_grounding_score",
    "Grounding score distribution from claim auditor",
    buckets=[0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0],
)

VALIDATOR_REALISM_SCORE = Histogram(
    "career_agents_validator_realism_score",
    "Realism score distribution from realism assessor",
    buckets=[0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0],
)

VALIDATOR_STAGE_DURATION = Histogram(
    "career_agents_validator_stage_duration_seconds",
    "Wall-clock time per validation stage",
    ["stage"],  # evidence_check | claim_audit | realism | fix_instructions
    buckets=[0.1, 0.25, 0.5, 1.0, 2.0, 4.0, 8.0, 16.0],
)

VALIDATOR_PASSED_TOTAL = Counter(
    "career_agents_validator_passed_total",
    "Total validation outcomes by result",
    ["result"],  # passed | failed
)

VALIDATOR_FIX_COUNT = Histogram(
    "career_agents_validator_fix_count",
    "Number of fix instructions generated per validation run",
    buckets=[0, 1, 2, 3, 5, 8, 12, 20],
)

VALIDATOR_FIX_INSTRUCTIONS_TOTAL = Counter(
    "career_agents_validator_fix_instructions_total",
    "Total fix instructions generated across all runs, by priority",
    ["priority"],  # critical | high | low
)

VALIDATOR_UNSUPPORTED_CLAIMS_TOTAL = Counter(
    "career_agents_validator_unsupported_claims_total",
    "Total unsupported claims flagged across all validation runs",
)

# ── Learning Resources agent metrics ────────────────────────────────────────

LR_COURSE_FETCH_DURATION = Histogram(
    "career_agents_lr_course_fetch_duration_seconds",
    "Wall-clock time for a single MCP course catalog fetch call",
    buckets=[0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0],
)

LR_COURSE_FETCH_TOTAL = Counter(
    "career_agents_lr_course_fetch_total",
    "Total MCP course catalog fetch calls by outcome",
    ["status"],  # success | error
)

LR_RESOURCES_MATCHED = Histogram(
    "career_agents_lr_resources_matched",
    "Number of resources matched per learning resources run",
    buckets=[0, 1, 2, 3, 5, 10, 20, 30, 50],
)

LR_TOP_RESOURCE_SCORE = Histogram(
    "career_agents_lr_top_resource_score",
    "Overall score of the top-ranked resource per run",
    buckets=[0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0],
)

LR_PHASE_COUNT = Histogram(
    "career_agents_lr_phase_count",
    "Number of roadmap phases produced per learning resources run",
    buckets=[1, 2, 3, 4, 5],
)

LR_TOTAL_LEARNING_HOURS = Histogram(
    "career_agents_lr_total_learning_hours",
    "Total estimated learning hours per learning resources run",
    buckets=[0, 10, 20, 30, 50, 80, 120, 200, 300],
)

# ── Networking & Outreach agent metrics ─────────────────────────────────────

NET_LINKEDIN_REVIEW_DURATION = Histogram(
    "career_agents_net_linkedin_review_duration_seconds",
    "Wall-clock time for LinkedIn profile review LLM calls",
    buckets=[0.5, 1.0, 2.0, 4.0, 8.0, 16.0, 30.0],
)

NET_LINKEDIN_REVIEW_TOTAL = Counter(
    "career_agents_net_linkedin_review_total",
    "Total LinkedIn profile review calls by resolution method",
    ["status"],  # llm | fallback
)

NET_EVENT_FETCH_DURATION = Histogram(
    "career_agents_net_event_fetch_duration_seconds",
    "Wall-clock time for concurrent MCP event discovery",
    buckets=[0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0],
)

NET_EVENT_FETCH_TOTAL = Counter(
    "career_agents_net_event_fetch_total",
    "Total MCP event discovery calls by outcome",
    ["status"],  # success | error
)

NET_OUTREACH_DRAFT_DURATION = Histogram(
    "career_agents_net_outreach_draft_duration_seconds",
    "Wall-clock time for outreach message drafting LLM calls",
    buckets=[0.5, 1.0, 2.0, 4.0, 8.0, 16.0, 30.0],
)

NET_OUTREACH_DRAFT_TOTAL = Counter(
    "career_agents_net_outreach_draft_total",
    "Total outreach drafting calls by resolution method",
    ["status"],  # llm | fallback
)

NET_EVENTS_FOUND = Histogram(
    "career_agents_net_events_found",
    "Number of relevant events/communities found per networking run",
    buckets=[0, 1, 2, 3, 5, 8, 12, 16, 20],
)

NET_CONTACTS_TRACKED = Histogram(
    "career_agents_net_contacts_tracked",
    "Number of contacts seeded into the relationship pipeline per run",
    buckets=[0, 1, 2, 3, 5, 8, 12, 16, 20],
)
