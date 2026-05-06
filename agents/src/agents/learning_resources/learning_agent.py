"""LearningAgent — L3 Specialist Agent: learning resource discovery and embedding.

Four-step pipeline:
  1. CourseFetcher   (MCP: course_catalog)  — concurrent course catalog queries
  2. ResourceMatcher (pure computation)     — relevance scoring against skill gaps
  3. ResourceRanker  (pure computation)     — weighted quality × cost × level scoring
  4. ResourceEmbedder(pure computation)     — phase grouping for roadmap embedding

Input (via context.plan_snapshot + context.user_profile):
  plan_snapshot["gap_analysis"]["prioritised_gaps"] : list[dict]  — from GapAgent
  user_profile.target_role                           : str
  user_profile.timeline_months                       : int | None
  user_profile.weekly_hours_available                : int | None

Output (AgentResult.output):
  target_role            : str
  skill_recommendations  : list[dict]   — per-gap resource bundles
  top_resources          : list[dict]   — global top-k resources across all gaps
  roadmap_embeddings     : list[dict]   — resources grouped by roadmap phase
  total_resources_found  : int
  total_learning_hours   : float
  data_sources           : list[str]
  fetched_at             : str          — ISO 8601
  processing_steps       : list[str]

Low-coupled: all four components are injected via constructor DI.
Observable:  OTel span wraps the full pipeline; STEP_PROGRESS SSE events
             emitted at each step so the client shows live progress.

Registration (at Celery worker startup):
    from agents.learning_resources import LearningAgent
    from agents.core.agent_registry import registry
    registry.register(LearningAgent(event_publisher=EventPublisher(redis_client)))
"""
from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

from opentelemetry.trace import Status, StatusCode

from agents.config import agent_settings
from agents.contracts.events import AgentEvent, AgentEventType
from agents.contracts.tasks import AgentType
from agents.core.base_agent import BaseAgent
from agents.core.context import AgentContext
from agents.core.logging import get_logger
from agents.core.message_bus import EventPublisherProtocol
from agents.core.observability import (
    LR_COURSE_FETCH_TOTAL,
    LR_PHASE_COUNT,
    LR_RESOURCES_MATCHED,
    LR_TOP_RESOURCE_SCORE,
    LR_TOTAL_LEARNING_HOURS,
    STEP_PROGRESS_TOTAL,
    get_tracer,
)
from agents.learning_resources.course_fetcher import CourseFetcher
from agents.learning_resources.mcp_client import (
    HttpMCPClient,
    MCPClientProtocol,
    StubMCPClient,
)
from agents.learning_resources.models import (
    LearningResource,
    LearningResourcesResult,
    RoadmapPhaseEmbedding,
    SkillResourceBundle,
)
from agents.learning_resources.resource_embedder import ResourceEmbedder
from agents.learning_resources.resource_matcher import ResourceMatcher
from agents.learning_resources.resource_ranker import ResourceRanker

logger = get_logger(__name__)
_tracer = get_tracer("agents.learning_resources.learning_agent")

# Maximum number of prioritised gaps to process (prevents excessive MCP calls)
_MAX_GAPS = 10


class LearningAgent(BaseAgent):
    """Discover, rank, and embed learning resources for identified skill gaps.

    Parameters
    ----------
    course_fetcher:
        MCP-backed course catalog fetcher. Defaults to CourseFetcher with auto MCP.
    resource_matcher:
        Relevance scorer. Defaults to ``ResourceMatcher()``.
    resource_ranker:
        Weighted scorer. Defaults to ``ResourceRanker()``.
    resource_embedder:
        Phase grouper. Defaults to ``ResourceEmbedder()``.
    event_publisher:
        Optional SSE progress publisher. When ``None``, progress events are silently
        skipped (e.g. in unit tests).
    mcp_client:
        Explicit MCP client override shared by the course fetcher.
    max_gaps:
        Maximum number of gaps to search courses for per run.
    """

    def __init__(
        self,
        *,
        course_fetcher: CourseFetcher | None = None,
        resource_matcher: ResourceMatcher | None = None,
        resource_ranker: ResourceRanker | None = None,
        resource_embedder: ResourceEmbedder | None = None,
        event_publisher: EventPublisherProtocol | None = None,
        mcp_client: MCPClientProtocol | None = None,
        max_gaps: int = _MAX_GAPS,
    ) -> None:
        _client = mcp_client or _build_mcp_client()
        self._course_fetcher = course_fetcher or CourseFetcher(_client)
        self._resource_matcher = resource_matcher or ResourceMatcher()
        self._resource_ranker = resource_ranker or ResourceRanker()
        self._resource_embedder = resource_embedder or ResourceEmbedder()
        self._event_publisher = event_publisher
        self._max_gaps = max_gaps

    # ── BaseAgent contract ─────────────────────────────────────────────────

    @property
    def agent_type(self) -> AgentType:
        return AgentType.LEARNING_RESOURCES

    @property
    def display_name(self) -> str:
        return "Learning Resource Agent"

    async def _execute(self, context: AgentContext) -> dict:
        """Run the full learning resource pipeline and return structured output."""
        with _tracer.start_as_current_span("learning_resources.execute") as span:
            span.set_attribute("session_id", context.session_id)
            span.set_attribute("user_id", context.user_id)
            span.set_attribute("correlation_id", context.correlation_id)

            target_role = context.user_profile.target_role or "Software Engineer"
            span.set_attribute("target_role", target_role)

            # Read gap analysis from plan_snapshot; fall back to profile skills
            gap_analysis = context.plan_snapshot.get("gap_analysis", {})
            gaps = _resolve_gaps(gap_analysis, context)
            gaps = gaps[: self._max_gaps]

            span.set_attribute("gap_count", len(gaps))

            # ── Step 1: Course fetching ────────────────────────────────────
            self._emit_progress(
                context,
                "course_fetching",
                f"Querying course catalogue for {len(gaps)} skill gaps…",
            )
            STEP_PROGRESS_TOTAL.labels(step_name="lr.course_fetching").inc()

            raw_courses = await self._course_fetcher.fetch(
                gaps, correlation_id=context.correlation_id
            )

            # ── Step 2: Resource matching ──────────────────────────────────
            self._emit_progress(
                context,
                "resource_matching",
                "Matching courses to skill gaps…",
            )
            STEP_PROGRESS_TOTAL.labels(step_name="lr.resource_matching").inc()

            bundles = self._resource_matcher.match(gaps, raw_courses)
            total_matched = sum(len(b.resources) for b in bundles)
            LR_RESOURCES_MATCHED.observe(total_matched)

            # ── Step 3: Resource ranking ───────────────────────────────────
            self._emit_progress(
                context,
                "resource_ranking",
                "Ranking resources by quality, cost, and level fit…",
            )
            STEP_PROGRESS_TOTAL.labels(step_name="lr.resource_ranking").inc()

            ranked_bundles, top_resources = self._resource_ranker.rank(bundles)

            if top_resources:
                LR_TOP_RESOURCE_SCORE.observe(top_resources[0].overall_score)

            # ── Step 4: Roadmap embedding ──────────────────────────────────
            self._emit_progress(
                context,
                "resource_embedding",
                "Embedding resources into roadmap phases…",
            )
            STEP_PROGRESS_TOTAL.labels(step_name="lr.resource_embedding").inc()

            embeddings = self._resource_embedder.embed(ranked_bundles)
            total_hours = sum(e.estimated_hours for e in embeddings)

            LR_PHASE_COUNT.observe(len(embeddings))
            LR_TOTAL_LEARNING_HOURS.observe(total_hours)

            # ── Observability ──────────────────────────────────────────────
            span.set_attribute("total_matched", total_matched)
            span.set_attribute("top_resource_count", len(top_resources))
            span.set_attribute("phase_count", len(embeddings))
            span.set_attribute("total_learning_hours", total_hours)
            span.set_status(Status(StatusCode.OK))

            data_sources = _collect_data_sources(ranked_bundles)

            logger.info(
                "learning_resources.completed",
                target_role=target_role,
                gap_count=len(gaps),
                total_matched=total_matched,
                top_resource_count=len(top_resources),
                phase_count=len(embeddings),
                total_learning_hours=total_hours,
                correlation_id=context.correlation_id,
            )

            result = LearningResourcesResult(
                target_role=target_role,
                skill_recommendations=ranked_bundles,
                top_resources=top_resources,
                roadmap_embeddings=embeddings,
                total_resources_found=total_matched,
                total_learning_hours=total_hours,
                data_sources=data_sources,
                processing_steps=[
                    "course_fetching",
                    "resource_matching",
                    "resource_ranking",
                    "resource_embedding",
                ],
            )
            return _serialise(result)

    # ── Private helpers ────────────────────────────────────────────────────

    def _emit_progress(self, context: AgentContext, step: str, description: str) -> None:
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
                "learning_resources.progress_emit_failed",
                step=step,
                error=str(exc),
            )


# ── Module-level helpers ──────────────────────────────────────────────────────


def _build_mcp_client() -> MCPClientProtocol:
    """Auto-configure MCP client from environment settings.

    Uses HttpMCPClient when a course catalog URL is configured;
    StubMCPClient otherwise (works end-to-end in dev without real MCP servers).
    """
    registry: dict[str, str] = {}
    if agent_settings.mcp_course_catalog_url:
        registry["course_catalog"] = agent_settings.mcp_course_catalog_url
    if registry:
        return HttpMCPClient(registry, timeout_seconds=agent_settings.mcp_timeout_seconds)
    return StubMCPClient()


def _resolve_gaps(
    gap_analysis: dict[str, Any], context: AgentContext
) -> list[dict[str, Any]]:
    """Return prioritised gaps from gap_analysis, or synthetic gaps from user profile."""
    prioritised = gap_analysis.get("prioritised_gaps", [])
    if prioritised:
        return prioritised

    # Fallback: create synthetic gaps from user profile skills (useful for standalone runs)
    return [
        {
            "requirement_name": skill,
            "dimension": "tech_skill",
            "severity": "medium",
            "priority_rank": i + 1,
            "current_level": None,
            "required_level": "intermediate",
            "is_required": True,
            "diff_score": 0.5,
        }
        for i, skill in enumerate(context.user_profile.skills)
    ]


def _collect_data_sources(bundles: list[SkillResourceBundle]) -> list[str]:
    sources: set[str] = set()
    for bundle in bundles:
        for resource in bundle.resources:
            sources.add(resource.provider)
    return sorted(sources)


# ── Output serialisers ────────────────────────────────────────────────────────


def _serialise(result: LearningResourcesResult) -> dict:
    return {
        "target_role": result.target_role,
        "skill_recommendations": [_serialise_bundle(b) for b in result.skill_recommendations],
        "top_resources": [_serialise_resource(r) for r in result.top_resources],
        "roadmap_embeddings": [_serialise_embedding(e) for e in result.roadmap_embeddings],
        "total_resources_found": result.total_resources_found,
        "total_learning_hours": result.total_learning_hours,
        "data_sources": result.data_sources,
        "fetched_at": result.fetched_at.isoformat(),
        "processing_steps": result.processing_steps,
    }


def _serialise_bundle(bundle: SkillResourceBundle) -> dict:
    return {
        "skill_gap": bundle.skill_gap,
        "gap_severity": bundle.gap_severity,
        "gap_priority_rank": bundle.gap_priority_rank,
        "resources": [_serialise_resource(r) for r in bundle.resources],
        "top_resource": _serialise_resource(bundle.top_resource) if bundle.top_resource else None,
    }


def _serialise_resource(resource: LearningResource) -> dict:
    return {
        "resource_id": resource.resource_id,
        "title": resource.title,
        "provider": resource.provider,
        "skill_tags": resource.skill_tags,
        "level": resource.level.value,
        "format": resource.format.value,
        "duration_hours": resource.duration_hours,
        "cost_usd": resource.cost_usd,
        "is_free": resource.is_free,
        "quality_score": resource.quality_score,
        "relevance_score": resource.relevance_score,
        "overall_score": resource.overall_score,
        "url": resource.url,
        "description": resource.description,
        "freshness_year": resource.freshness_year,
        "source": resource.source,
    }


def _serialise_embedding(embedding: RoadmapPhaseEmbedding) -> dict:
    return {
        "phase_number": embedding.phase_number,
        "phase_title": embedding.phase_title,
        "skill_gaps": embedding.skill_gaps,
        "resources": [_serialise_resource(r) for r in embedding.resources],
        "estimated_hours": embedding.estimated_hours,
    }
