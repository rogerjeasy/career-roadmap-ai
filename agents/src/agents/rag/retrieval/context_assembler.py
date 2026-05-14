"""ContextAssembler — builds list[RagChunk] for AgentContext injection.

Called by the ``assemble_rag_context`` orchestrator node before agent dispatch.
Composes a compound query from the user profile + user message, retrieves
passages through the full retrieval pipeline (ANN -> optional reranker -> optional
MMR), and converts them into the ``RagChunk`` dataclass expected by
``AgentContext.rag_chunks``.

Pipeline (all stages opt-in via config):
  1. Build compound query from user message + profile + intent type.
  2. Check Redis cache — return immediately on hit (skips HyDE + Pinecone).
  3. HyDE expansion — replace query with a synthetically generated career-domain
     passage to close the embedding-space gap on vague queries.
  4. Pinecone retrieval — ANN fan-out across intent-filtered namespaces,
     optionally followed by reranking and MMR diversity filter.
  5. Convert RetrievedChunk -> RagChunk (promotes title + source_url).
  6. Write results to Redis cache for future identical queries.

Namespace selection is intent- AND location-aware (see ``_select_namespaces``):
  roadmap_generation / gap_analysis
    → role-templates + taxonomy + market-reports + career-kb
    → + swiss-eu-market  if user is in EU/CH
    → + global-market    if user is outside US/EU/CH (or location unknown)
  market_intelligence
    → market-reports
    → + swiss-eu-market  if user is in EU/CH
    → + global-market    if user is outside US/EU/CH (or location unknown)
  default → all namespaces

Covers all job families and industries — not just technology.

Graceful degradation:
- Returns [] immediately if ``rag_enabled=False``.
- Returns [] with a warning if retrieval raises; never propagates exceptions.
  The orchestrator pipeline continues without RAG context in both cases.
"""
from __future__ import annotations

import dataclasses
import time
from typing import TYPE_CHECKING

from agents.config import agent_settings
from agents.contracts.tasks import UserProfileSnapshot
from agents.core.context import RagChunk
from agents.core.logging import get_logger
from agents.core.observability import get_tracer
from agents.rag.models import KnowledgeNamespace
from agents.rag.observability import (
    RAG_CONTEXT_ASSEMBLY_DURATION,
    RAG_CONTEXT_ASSEMBLY_TOTAL,
)
from agents.rag.retrieval.retriever import PineconeRetriever

if TYPE_CHECKING:
    from agents.rag.retrieval.hyde import HyDEQueryExpander
    from agents.rag.retrieval.query_cache import RagQueryCache

logger = get_logger(__name__)
_tracer = get_tracer("agents.rag.retrieval.context_assembler")

# ── Location-aware namespace routing ─────────────────────────────────────────
# Keywords are lowercase; matched against the user's free-text location field.
# "US region" covers North America (US / CA) — both get US market data.
# Order matters: EU is checked before Americas so "Paris, France" hits EU first.

_US_REGION_KEYWORDS = frozenset({
    "united states", "usa", " us ", "u.s.", "canada", "mexico",
    "new york", "san francisco", "seattle", "austin", "chicago",
    "los angeles", "boston", "toronto", "vancouver",
})

_EU_CH_KEYWORDS = frozenset({
    "switzerland", "zurich", "geneva", "bern", "basel",
    "germany", "france", "netherlands", "spain", "italy", "sweden",
    "norway", "denmark", "finland", "belgium", "austria", "poland",
    "portugal", "ireland", "czech", "hungary", "romania", "greece",
    "united kingdom", "uk", "london", "amsterdam", "berlin", "paris",
    "europe", "european union", "eu",
})


def _location_region(location: str | None) -> str:
    """Classify a free-text location into 'us', 'eu_ch', or 'global'.

    Returns:
        'us'     — North America
        'eu_ch'  — EU member states or Switzerland
        'global' — everywhere else (Asia, LATAM, Africa, MENA, Oceania)
                   or when location is None / unrecognised
    """
    if not location:
        return "global"
    loc = location.lower()
    # Pad with spaces so substring " us " doesn't false-match "focus"
    padded = f" {loc} "
    if any(kw in padded for kw in _US_REGION_KEYWORDS):
        return "us"
    if any(kw in loc for kw in _EU_CH_KEYWORDS):
        return "eu_ch"
    return "global"


def _select_namespaces(
    intent_type: str | None,
    location: str | None,
) -> list[KnowledgeNamespace]:
    """Return the Pinecone namespaces to query for this intent + location combo.

    The rules ensure every user gets relevant labour-market data for their
    actual geography, across all industries and job families — not just tech.

    roadmap_generation / gap_analysis:
      always:   role-templates, taxonomy, career-kb
      + market-reports (global US-anchored signals)
      + swiss-eu-market  if region is eu_ch
      + global-market    if region is global (non-US, non-EU/CH)
      + both market namespaces if region is unknown (global fallback)

    market_intelligence:
      always:   market-reports
      + swiss-eu-market  if eu_ch
      + global-market    if global

    default (unknown intent):
      all namespaces
    """
    region = _location_region(location)

    if intent_type in ("roadmap_generation", "gap_analysis"):
        ns = [
            KnowledgeNamespace.ROLE_TEMPLATES,
            KnowledgeNamespace.ESCO_ONET,
            KnowledgeNamespace.CAREER_KB,
            KnowledgeNamespace.MARKET_REPORTS,
        ]
        if region == "eu_ch":
            ns.append(KnowledgeNamespace.SWISS_EU_MARKET)
        elif region == "global":
            ns.append(KnowledgeNamespace.GLOBAL_MARKET)
        else:
            # US — market-reports already covers this; no extra namespace needed
            pass
        return ns

    if intent_type == "market_intelligence":
        ns = [KnowledgeNamespace.MARKET_REPORTS]
        if region == "eu_ch":
            ns.append(KnowledgeNamespace.SWISS_EU_MARKET)
        elif region == "global":
            ns.append(KnowledgeNamespace.GLOBAL_MARKET)
        else:
            # For US users requesting market intelligence, include swiss-eu for
            # comparative context since market-reports already has US data.
            ns.append(KnowledgeNamespace.SWISS_EU_MARKET)
            ns.append(KnowledgeNamespace.GLOBAL_MARKET)
        return ns

    # Unknown intent — fan out across all namespaces for maximum recall.
    return list(KnowledgeNamespace)


class ContextAssembler:
    """Retrieves and serialises RAG chunks for one orchestration request.

    Parameters
    ----------
    retriever:
        Configured PineconeRetriever instance.
    hyde_expander:
        Optional HyDEQueryExpander. Used only when ``hyde_enabled=True``.
    cache:
        Optional RagQueryCache. Used only when ``rag_cache_enabled=True``.
    """

    def __init__(
        self,
        *,
        retriever: PineconeRetriever,
        hyde_expander: "HyDEQueryExpander | None" = None,
        cache: "RagQueryCache | None" = None,
    ) -> None:
        self._retriever = retriever
        self._hyde = hyde_expander
        self._cache = cache

    async def assemble(
        self,
        *,
        user_message: str,
        user_profile: UserProfileSnapshot,
        intent_type: str | None = None,
    ) -> list[RagChunk]:
        """Return RAG chunks for injection into AgentContext. Never raises."""
        if not agent_settings.rag_enabled:
            RAG_CONTEXT_ASSEMBLY_TOTAL.labels(status="disabled").inc()
            return []

        t0 = time.monotonic()
        with _tracer.start_as_current_span("rag.context_assembly") as span:
            span.set_attribute("intent_type", intent_type or "")
            span.set_attribute("hyde_enabled", agent_settings.hyde_enabled)
            span.set_attribute("cache_enabled", agent_settings.rag_cache_enabled)
            try:
                query = _build_query(user_message, user_profile, intent_type)
                namespaces = _select_namespaces(intent_type, user_profile.location)
                top_k = agent_settings.rag_top_k

                # ── Stage 1: Cache lookup ─────────────────────────────────
                if self._cache and agent_settings.rag_cache_enabled:
                    ns_values = [ns.value for ns in namespaces]
                    from agents.rag.retrieval.query_cache import RagQueryCache  # noqa: PLC0415
                    cache_key = RagQueryCache.make_key(query, ns_values, top_k)
                    cached = await self._cache.get(cache_key)
                    if cached is not None:
                        span.set_attribute("cache_hit", True)
                        span.set_attribute("chunks", len(cached))
                        RAG_CONTEXT_ASSEMBLY_DURATION.observe(time.monotonic() - t0)
                        RAG_CONTEXT_ASSEMBLY_TOTAL.labels(status="cache_hit").inc()
                        logger.info(
                            "rag.context_assembly.cache_hit",
                            chunks=len(cached),
                            intent_type=intent_type or "unknown",
                        )
                        return [RagChunk(**d) for d in cached]
                else:
                    cache_key = ""

                span.set_attribute("cache_hit", False)

                # ── Stage 2: HyDE expansion ───────────────────────────────
                retrieval_query = query
                if self._hyde and agent_settings.hyde_enabled:
                    retrieval_query = await self._hyde.expand(
                        query, intent_type=intent_type
                    )
                    span.set_attribute("hyde_applied", retrieval_query != query)

                # ── Stage 3: Pinecone retrieval ───────────────────────────
                retrieved = await self._retriever.retrieve(
                    retrieval_query,
                    namespaces=namespaces,
                    top_k=top_k,
                )

                # ── Stage 4: Convert to RagChunk ──────────────────────────
                rag_chunks = [
                    RagChunk(
                        chunk_id=chunk.chunk_id,
                        content=chunk.content,
                        source=chunk.namespace,
                        relevance_score=chunk.score,
                        title=chunk.title,
                        source_url=chunk.source_url,
                        metadata=dict(chunk.metadata),
                    )
                    for chunk in retrieved
                ]

                # ── Stage 5: Populate cache ───────────────────────────────
                if self._cache and agent_settings.rag_cache_enabled and cache_key:
                    await self._cache.set(
                        cache_key,
                        [dataclasses.asdict(c) for c in rag_chunks],
                    )

                RAG_CONTEXT_ASSEMBLY_DURATION.observe(time.monotonic() - t0)
                RAG_CONTEXT_ASSEMBLY_TOTAL.labels(status="success").inc()
                span.set_attribute("chunks", len(rag_chunks))
                logger.info(
                    "rag.context_assembly.done",
                    chunks=len(rag_chunks),
                    intent_type=intent_type or "unknown",
                )
                return rag_chunks

            except Exception as exc:
                RAG_CONTEXT_ASSEMBLY_DURATION.observe(time.monotonic() - t0)
                RAG_CONTEXT_ASSEMBLY_TOTAL.labels(status="error").inc()
                span.record_exception(exc)
                logger.warning(
                    "rag.context_assembly.failed",
                    error=str(exc),
                    intent_type=intent_type or "unknown",
                )
                return []


def _build_query(
    user_message: str,
    profile: UserProfileSnapshot,
    intent_type: str | None,
) -> str:
    """Compose a retrieval query from available context signals.

    Includes industry and job-family hints so the embedding captures the
    user's sector (healthcare, finance, education, etc.) — not just role title.
    This ensures global-market and swiss-eu-market chunks for non-tech users
    are retrieved with high relevance.
    """
    parts: list[str] = []
    if user_message:
        parts.append(user_message)
    if profile.target_role:
        parts.append(f"Target role: {profile.target_role}")
    if profile.current_role:
        parts.append(f"Current role: {profile.current_role}")
    if profile.skills:
        parts.append(f"Skills: {', '.join(profile.skills[:10])}")
    if profile.location:
        parts.append(f"Location: {profile.location}")

    # Industry / job-family hints from the profile's additional fields.
    # These are set by the intake agent when the user specifies their sector.
    additional = profile.additional or {}
    if industry := additional.get("industry"):
        parts.append(f"Industry: {industry}")
    if job_family := additional.get("job_family"):
        parts.append(f"Job family: {job_family}")
    if sector := additional.get("sector"):
        parts.append(f"Sector: {sector}")

    if intent_type:
        parts.append(f"Intent: {intent_type}")
    return " | ".join(parts)[:1200]
