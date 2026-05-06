"""CVAgent — L3 Specialist Agent: CV parsing, skill extraction, and readiness scoring.

Five-step pipeline:
  1. PDF/text extraction   (PDFParser)         — no LLM
  2. Structured CV parsing (CVParser)          — LLM
  3. Skill collection      (SkillExtractor)    — no LLM, keyword scan
  4. Skill normalisation   (SkillNormaliser)   — dict + LLM fallback
  5. Readiness scoring     (ReadinessScorer)   — LLM + heuristic fallback

Input (via context.plan_snapshot["cv"]):
  cv_document : bytes | str
      Raw PDF bytes (base64-encoded when transported over JSON) or plain text.
  source_type : "pdf" | "text" | "linkedin_export"  (default "text")
      Drives how the document is pre-processed.

Output (AgentResult.output):
  cv_text_length   : int
  parsed_cv        : dict  — structured CV fields
  skill_graph      : dict  — nodes + by_category index
  readiness        : dict  — overall_score, breakdown, matched/missing skills,
                             recommendations
  processing_steps : list[str]

Low-coupled: all five components are injected via constructor DI.
Observable:  OTel span wraps the full pipeline; STEP_PROGRESS SSE events
             emitted at each step so the client shows live progress.

Registration (at Celery worker startup):
    from agents.cv_analysis import CVAgent
    from agents.core.agent_registry import registry
    registry.register(CVAgent(event_publisher=EventPublisher(redis_client)))
"""
from __future__ import annotations

import base64

from langchain_anthropic import ChatAnthropic
from opentelemetry.trace import Status, StatusCode

from agents.contracts.events import AgentEvent, AgentEventType
from agents.contracts.tasks import AgentType
from agents.core.base_agent import BaseAgent
from agents.core.context import AgentContext
from agents.core.logging import get_logger
from agents.core.message_bus import EventPublisherProtocol
from agents.core.observability import STEP_PROGRESS_TOTAL, get_tracer
from agents.cv_analysis.cv_parser import CVParser
from agents.cv_analysis.models import ParsedCV, ReadinessResult, SkillGraph
from agents.cv_analysis.pdf_parser import PDFParser
from agents.cv_analysis.readiness_scorer import ReadinessScorer
from agents.cv_analysis.skill_extractor import SkillExtractor
from agents.cv_analysis.skill_normaliser import SkillNormaliser

logger = get_logger(__name__)
_tracer = get_tracer("agents.cv_analysis.cv_agent")


class CVAgent(BaseAgent):
    """Parse a CV, build a SkillGraph, and compute a role-readiness score.

    Parameters
    ----------
    pdf_parser:
        Text-extraction component. Defaults to ``PDFParser()``.
    cv_parser:
        LLM-based structured CV parser. Defaults to ``CVParser()``.
    skill_extractor:
        Keyword-scan collector. Defaults to ``SkillExtractor()``.
    skill_normaliser:
        Dict + LLM normaliser. Defaults to ``SkillNormaliser()``.
    readiness_scorer:
        LLM-based readiness scorer. Defaults to ``ReadinessScorer()``.
    event_publisher:
        Optional publisher for STEP_PROGRESS SSE events. When ``None``
        progress events are silently skipped (e.g. in unit tests).
    llm:
        Override the LangChain LLM forwarded to the three LLM components
        when they are not explicitly provided.
    """

    def __init__(
        self,
        *,
        pdf_parser: PDFParser | None = None,
        cv_parser: CVParser | None = None,
        skill_extractor: SkillExtractor | None = None,
        skill_normaliser: SkillNormaliser | None = None,
        readiness_scorer: ReadinessScorer | None = None,
        event_publisher: EventPublisherProtocol | None = None,
        llm: ChatAnthropic | None = None,
    ) -> None:
        self._pdf_parser = pdf_parser or PDFParser()
        self._cv_parser = cv_parser or CVParser(llm=llm)
        self._skill_extractor = skill_extractor or SkillExtractor()
        self._skill_normaliser = skill_normaliser or SkillNormaliser(llm=llm)
        self._readiness_scorer = readiness_scorer or ReadinessScorer(llm=llm)
        self._event_publisher = event_publisher

    # ── BaseAgent contract ─────────────────────────────────────────────────

    @property
    def agent_type(self) -> AgentType:
        return AgentType.CV_ANALYSIS

    @property
    def display_name(self) -> str:
        return "CV Analysis Agent"

    async def _execute(self, context: AgentContext) -> dict:
        """Run the full CV analysis pipeline and return structured output."""
        with _tracer.start_as_current_span("cv_analysis.execute") as span:
            span.set_attribute("session_id", context.session_id)
            span.set_attribute("user_id", context.user_id)
            span.set_attribute("correlation_id", context.correlation_id)

            cv_payload = context.plan_snapshot.get("cv", {})
            cv_document = cv_payload.get("cv_document", "")
            source_type: str = cv_payload.get("source_type", "text")
            target_role: str = context.user_profile.target_role or ""

            # Base64-encoded PDF bytes are transported as strings over JSON.
            if isinstance(cv_document, str) and source_type == "pdf":
                try:
                    cv_document = base64.b64decode(cv_document)
                except Exception:
                    pass  # not base64 — treat as plain text

            # ── Step 1: PDF / text extraction ───────────────────────────
            self._emit_progress(context, "pdf_extraction", "Extracting CV text…")
            STEP_PROGRESS_TOTAL.labels(step_name="cv.pdf_extraction").inc()

            raw_text: str = self._pdf_parser.extract_text(
                cv_document, correlation_id=context.correlation_id
            )
            span.set_attribute("cv_text_length", len(raw_text))

            # ── Step 2: Structured CV parsing ───────────────────────────
            self._emit_progress(context, "cv_parsing", "Parsing CV structure…")
            STEP_PROGRESS_TOTAL.labels(step_name="cv.cv_parsing").inc()

            parsed_cv: ParsedCV = await self._cv_parser.parse(
                raw_text, correlation_id=context.correlation_id
            )

            # ── Step 3: Skill collection ────────────────────────────────
            self._emit_progress(context, "skill_extraction", "Extracting skills…")
            STEP_PROGRESS_TOTAL.labels(step_name="cv.skill_extraction").inc()

            raw_skills = self._skill_extractor.extract(
                parsed_cv, correlation_id=context.correlation_id
            )

            # ── Step 4: Skill normalisation ─────────────────────────────
            self._emit_progress(context, "skill_normalisation", "Normalising skill graph…")
            STEP_PROGRESS_TOTAL.labels(step_name="cv.skill_normalisation").inc()

            skill_graph: SkillGraph = await self._skill_normaliser.normalise(
                raw_skills, correlation_id=context.correlation_id
            )

            # ── Step 5: Readiness scoring ───────────────────────────────
            self._emit_progress(context, "readiness_scoring", "Computing readiness score…")
            STEP_PROGRESS_TOTAL.labels(step_name="cv.readiness_scoring").inc()

            readiness: ReadinessResult = await self._readiness_scorer.score(
                parsed_cv,
                skill_graph,
                target_role,
                correlation_id=context.correlation_id,
            )

            span.set_attribute("skill_count", len(skill_graph.nodes))
            span.set_attribute("readiness_score", readiness.overall_score)
            span.set_status(Status(StatusCode.OK))

            logger.info(
                "cv_analysis.completed",
                skill_count=len(skill_graph.nodes),
                readiness_score=readiness.overall_score,
                experience_entries=len(parsed_cv.experience),
                target_role=target_role,
                correlation_id=context.correlation_id,
            )

            return {
                "cv_text_length": len(raw_text),
                "parsed_cv": _serialise_parsed_cv(parsed_cv),
                "skill_graph": _serialise_skill_graph(skill_graph),
                "readiness": _serialise_readiness(readiness),
                "processing_steps": [
                    "pdf_extraction",
                    "cv_parsing",
                    "skill_extraction",
                    "skill_normalisation",
                    "readiness_scoring",
                ],
            }

    # ── Private helpers ────────────────────────────────────────────────────

    def _emit_progress(
        self, context: AgentContext, step: str, description: str
    ) -> None:
        """Best-effort STEP_PROGRESS event emission. Never raises."""
        if self._event_publisher is None:
            return
        try:
            self._event_publisher.emit(
                AgentEvent(
                    event_type=AgentEventType.STEP_PROGRESS,
                    session_id=context.session_id,
                    user_id=context.user_id,
                    correlation_id=context.correlation_id,
                    payload={
                        "agent": self.agent_type.value,
                        "step": step,
                        "description": description,
                    },
                )
            )
        except Exception as exc:
            logger.warning(
                "cv_analysis.progress_emit_failed",
                step=step,
                error=str(exc),
            )


# ── Output serialisers ──────────────────────────────────────────────────────


def _serialise_parsed_cv(cv: ParsedCV) -> dict:
    return {
        "full_name": cv.full_name,
        "email": cv.email,
        "phone": cv.phone,
        "location": cv.location,
        "summary": cv.summary,
        "total_experience_months": cv.total_experience_months,
        "raw_skills": cv.raw_skills,
        "certifications": cv.certifications,
        "languages": cv.languages,
        "experience": [
            {
                "company": e.company,
                "title": e.title,
                "start_date": e.start_date,
                "end_date": e.end_date,
                "duration_months": e.duration_months,
                "responsibilities": e.responsibilities,
                "impact_statements": e.impact_statements,
            }
            for e in cv.experience
        ],
        "education": [
            {
                "institution": e.institution,
                "degree": e.degree,
                "field_of_study": e.field_of_study,
                "graduation_year": e.graduation_year,
                "gpa": e.gpa,
            }
            for e in cv.education
        ],
        "projects": [
            {
                "name": p.name,
                "description": p.description,
                "technologies": p.technologies,
                "impact": p.impact,
            }
            for p in cv.projects
        ],
    }


def _serialise_skill_graph(graph: SkillGraph) -> dict:
    return {
        "nodes": [
            {
                "name": n.name,
                "canonical_name": n.canonical_name,
                "category": n.category,
                "proficiency": n.proficiency,
                "years_of_experience": n.years_of_experience,
                "evidence_sources": n.evidence_sources,
            }
            for n in graph.nodes
        ],
        "by_category": {
            cat: [n.canonical_name for n in nodes]
            for cat, nodes in graph.by_category.items()
        },
    }


def _serialise_readiness(r: ReadinessResult) -> dict:
    return {
        "overall_score": r.overall_score,
        "breakdown": {
            "required_skills_matched": r.breakdown.required_skills_matched,
            "preferred_skills_matched": r.breakdown.preferred_skills_matched,
            "experience_level_match": r.breakdown.experience_level_match,
            "education_match": r.breakdown.education_match,
            "domain_alignment": r.breakdown.domain_alignment,
        },
        "matched_skills": r.matched_skills,
        "missing_required_skills": r.missing_required_skills,
        "missing_preferred_skills": r.missing_preferred_skills,
        "recommendations": r.recommendations,
    }
