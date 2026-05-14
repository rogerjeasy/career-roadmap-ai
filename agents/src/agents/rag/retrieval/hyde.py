"""HyDE — Hypothetical Document Embeddings for improved RAG retrieval.

Instead of embedding the user's raw query (which uses colloquial language and
may lack career-domain vocabulary), HyDE first asks an LLM to write a short
passage that *would* answer the query if found in the knowledge base.  That
hypothetical passage is then embedded and used for ANN retrieval.

The embedding space gap between vague natural-language queries and precise
domain documents is the main source of retrieval recall loss.  HyDE closes
it by generating a domain-vocabulary proxy before the embedding step.

Falls back to the original query string on any LLM error so retrieval is
never blocked by a HyDE failure.
"""
from __future__ import annotations

import time

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage
from opentelemetry.trace import StatusCode

from agents.config import agent_settings
from agents.core.logging import get_logger
from agents.core.observability import get_tracer
from agents.rag.observability import RAG_HYDE_DURATION, RAG_HYDE_TOTAL

logger = get_logger(__name__)
_tracer = get_tracer("agents.rag.retrieval.hyde")

_SYSTEM = """\
You are a career knowledge base expert. Given a career-related question or context,
write 2-3 sentences as if excerpted from a relevant knowledge-base article that
directly addresses the topic. Use specific, domain-appropriate terminology: exact
job titles, tool/framework names, certification names, and skill keywords.
Prioritise precision and terminology over breadth.

Output ONLY the excerpt text — no preamble, no "This article covers...", no caveats.\
"""

# Per-intent hint appended to the user message to steer domain focus.
_INTENT_HINTS: dict[str, str] = {
    "roadmap_generation": (
        "Focus on career progression steps, required skills, certifications, "
        "and realistic timeline expectations for the target role."
    ),
    "gap_analysis": (
        "Focus on skill gaps, required competencies for the target role, "
        "learning priorities, and recommended resources."
    ),
    "market_intelligence": (
        "Focus on market demand trends, salary ranges, top-hiring companies, "
        "in-demand tools, and Swiss/EU job-market specifics."
    ),
}


class HyDEQueryExpander:
    """Generates a hypothetical document for a career retrieval query.

    One instance per process (use ``get_hyde_expander()``).  The underlying
    LLM call is async; the class is stateless after construction.
    """

    def __init__(self, llm: ChatAnthropic | None = None) -> None:
        self._llm = llm or ChatAnthropic(
            model=agent_settings.hyde_model,
            api_key=agent_settings.anthropic_api_key.get_secret_value(),
            max_tokens=256,
            temperature=0.2,
        )

    async def expand(self, query: str, *, intent_type: str | None = None) -> str:
        """Return a hypothetical knowledge-base excerpt for ``query``.

        Returns the original ``query`` string unchanged when:
        - ``hyde_enabled`` is False in config
        - The LLM call fails for any reason (graceful fallback)
        """
        if not agent_settings.hyde_enabled:
            return query

        t0 = time.monotonic()
        with _tracer.start_as_current_span("rag.hyde.expand") as span:
            span.set_attribute("query_length", len(query))
            span.set_attribute("intent_type", intent_type or "")
            try:
                hint = _INTENT_HINTS.get(intent_type or "", "")
                user_content = f"Query: {query}"
                if hint:
                    user_content += f"\nHint: {hint}"

                response = await self._llm.ainvoke(
                    [
                        SystemMessage(content=_SYSTEM),
                        HumanMessage(content=user_content),
                    ]
                )
                expanded = str(response.content).strip()
                if not expanded:
                    raise ValueError("LLM returned empty HyDE expansion")

                span.set_attribute("expanded_length", len(expanded))
                span.set_status(StatusCode.OK)
                RAG_HYDE_DURATION.observe(time.monotonic() - t0)
                RAG_HYDE_TOTAL.labels(status="success").inc()
                logger.info(
                    "rag.hyde.expanded",
                    original_length=len(query),
                    expanded_length=len(expanded),
                    intent_type=intent_type or "unknown",
                )
                return expanded

            except Exception as exc:
                span.record_exception(exc)
                span.set_status(StatusCode.ERROR, str(exc))
                RAG_HYDE_DURATION.observe(time.monotonic() - t0)
                RAG_HYDE_TOTAL.labels(status="error").inc()
                logger.warning(
                    "rag.hyde.failed_using_original_query",
                    error=str(exc),
                    intent_type=intent_type or "unknown",
                )
                return query


# ── Module-level singleton ────────────────────────────────────────────────────

_EXPANDER: HyDEQueryExpander | None = None


def get_hyde_expander() -> HyDEQueryExpander:
    """Return the process-level HyDEQueryExpander singleton."""
    global _EXPANDER
    if _EXPANDER is None:
        _EXPANDER = HyDEQueryExpander()
    return _EXPANDER
