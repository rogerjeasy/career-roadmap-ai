"""ContextInjector — builds grounded, citation-aware prompt context from RAG chunks.

Responsibilities
----------------
- **Token budget management**: trims candidates to fit a configurable ceiling,
  prioritising chunks by relevance score (highest first).
- **Citation labelling**: assigns ``[SRC-N]`` markers and builds a citation map
  keyed by citation ID so downstream validators can verify claims.
- **Freshness enforcement**: market-sensitive namespaces (``market-reports``,
  ``swiss-eu-market``) must carry ``retrieved_at`` or ``source_date`` metadata.
  Chunks older than ``market_data_freshness_days`` are either excluded or
  labelled ``[STALE]`` depending on ``stale_market_data_excluded`` config.
- **Confidence classification**: high (≥0.85), medium (≥0.70), low (<0.70).
- **Anti-hallucination instructions**: produces a system-prompt fragment that
  requires the LLM to cite every factual claim with a ``[SRC-N]`` marker
  or label it ``[ASSUMPTION: …]``.
- **Uncertainty display**: confidence labels flow through to the evidence cards
  so the LLM can surface them in its output.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from agents.config import agent_settings
from agents.core.context import RagChunk
from agents.core.logging import get_logger
from agents.core.observability import get_tracer
from agents.rag.observability import (
    RAG_INJECTION_CHUNKS_BUDGET_TRIMMED,
    RAG_INJECTION_CHUNKS_INCLUDED,
    RAG_INJECTION_CHUNKS_STALE,
    RAG_INJECTION_DURATION,
    RAG_INJECTION_TOKEN_ESTIMATE,
    RAG_INJECTION_TOTAL,
)

logger = get_logger(__name__)
_tracer = get_tracer("agents.rag.context_injector")

# Namespaces whose data is time-sensitive and subject to the freshness policy.
_MARKET_NAMESPACES: frozenset[str] = frozenset({"market-reports", "swiss-eu-market"})

# Confidence thresholds
_HIGH_THRESHOLD: float = 0.85
_MEDIUM_THRESHOLD: float = 0.70

# ~4 characters per token (English prose average) — cheap heuristic, no tokenizer needed.
_CHARS_PER_TOKEN: int = 4

# Claim types that MUST be cited or labelled [ASSUMPTION].
_MUST_CITE_TYPES: tuple[str, ...] = (
    "required skills",
    "salary ranges",
    "market demand",
    "trending tools or frameworks",
    "certification value",
    "visa requirements",
    "course availability",
    "company hiring",
    "local event recommendations",
)

# System-prompt fragment injected before every LLM call that uses RAG context.
_GROUNDING_INSTRUCTIONS_TEMPLATE = """\
=== GROUNDING AND CITATION RULES ===
Evidence cards are provided above, each labelled [SRC-N].

MANDATORY RULES — output that violates these will be rejected and repaired:

1. CITE OR LABEL: Every claim about {claim_types} MUST be supported by at
   least one [SRC-N] citation.  If no evidence card covers a claim, write it
   as [ASSUMPTION: <claim>] — never state it as fact.

2. NO EVIDENCE TAG: If a required data point is absent from all cards, write
   [NO_EVIDENCE: <topic>] so it can be flagged for human review.

3. SOURCES ARRAY: Include a "sources" key in your JSON output listing every
   [SRC-N] citation you used (e.g. ["SRC-1", "SRC-3"]).

4. CONFIDENCE LABELS: Report the evidence strength alongside each recommendation:
     "high"   — chunk relevance ≥ 0.85
     "medium" — chunk relevance ≥ 0.70
     "low"    — chunk relevance < 0.70  (add a caveat for low-confidence items)

5. STALE DATA: Evidence cards labelled [STALE] MUST NOT be used for
   high-impact recommendations without an explicit [ASSUMPTION] qualifier.

6. FRESHNESS: Market claims must include the evidence card's retrieval date in
   the "evidence_date" field of your output if you cite a market card.
=== END GROUNDING RULES ==="""


# ── Public data types ──────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class CitedChunk:
    """A RAG chunk decorated with citation metadata, ready for prompt injection."""

    citation_id: str        # e.g. "SRC-1"
    chunk: RagChunk
    confidence_label: str   # "high" | "medium" | "low"
    is_stale: bool
    staleness_days: int | None  # None when date metadata is absent


@dataclass
class InjectedContext:
    """Result of ``ContextInjector.inject()``.

    ``formatted_context`` is inserted into the human/user message;
    ``grounding_instructions`` is appended to the agent system prompt.
    """

    # Evidence cards block — append to human message after user instruction.
    formatted_context: str
    # Anti-hallucination system fragment — append to agent base system prompt.
    grounding_instructions: str
    # [SRC-N] → RagChunk; used by validators to cross-check citations.
    citation_map: dict[str, RagChunk] = field(default_factory=dict)

    # Observability
    token_estimate: int = 0
    chunks_included: int = 0
    chunks_excluded_stale: int = 0
    chunks_excluded_budget: int = 0

    @property
    def has_context(self) -> bool:
        return self.chunks_included > 0

    def cited_chunks(self) -> list[CitedChunk]:
        """Convenience: not stored directly, but reconstructible via citation_map."""
        return []  # callers use citation_map directly


# ── ContextInjector ────────────────────────────────────────────────────────


class ContextInjector:
    """Builds citation-aware, token-budgeted prompt context from RAG chunks.

    Stateless — all inputs are passed to ``inject()``.  Suitable for use as
    a module-level singleton (``get_context_injector()``).
    """

    def inject(
        self,
        chunks: list[RagChunk],
        *,
        token_budget: int | None = None,
        intent_type: str | None = None,
    ) -> InjectedContext:
        """Build an ``InjectedContext`` from a ranked list of RAG chunks.

        Parameters
        ----------
        chunks:
            Chunks from ``AgentContext.rag_chunks``, ranked by relevance score
            (highest first) by the retrieval pipeline.
        token_budget:
            Maximum *estimated* token count for the formatted evidence block.
            Defaults to ``agent_settings.context_injection_token_budget``.
        intent_type:
            Passed through for structured logging only.
        """
        budget = token_budget if token_budget is not None else agent_settings.context_injection_token_budget
        t0 = time.monotonic()

        with _tracer.start_as_current_span("rag.context_injection") as span:
            span.set_attribute("input_chunks", len(chunks))
            span.set_attribute("token_budget", budget)
            span.set_attribute("intent_type", intent_type or "")

            try:
                result = self._build(chunks, budget)

                elapsed = time.monotonic() - t0
                RAG_INJECTION_DURATION.observe(elapsed)
                RAG_INJECTION_TOTAL.labels(status="success").inc()
                RAG_INJECTION_CHUNKS_INCLUDED.observe(result.chunks_included)
                RAG_INJECTION_TOKEN_ESTIMATE.observe(result.token_estimate)
                if result.chunks_excluded_stale:
                    RAG_INJECTION_CHUNKS_STALE.inc(result.chunks_excluded_stale)
                if result.chunks_excluded_budget:
                    RAG_INJECTION_CHUNKS_BUDGET_TRIMMED.inc(result.chunks_excluded_budget)

                span.set_attribute("chunks_included", result.chunks_included)
                span.set_attribute("chunks_stale_excluded", result.chunks_excluded_stale)
                span.set_attribute("chunks_budget_trimmed", result.chunks_excluded_budget)
                span.set_attribute("token_estimate", result.token_estimate)

                logger.info(
                    "rag.context_injector.done",
                    included=result.chunks_included,
                    stale_excluded=result.chunks_excluded_stale,
                    budget_trimmed=result.chunks_excluded_budget,
                    token_estimate=result.token_estimate,
                    intent_type=intent_type or "unknown",
                )
                return result

            except Exception as exc:
                elapsed = time.monotonic() - t0
                RAG_INJECTION_DURATION.observe(elapsed)
                RAG_INJECTION_TOTAL.labels(status="error").inc()
                span.record_exception(exc)
                logger.warning(
                    "rag.context_injector.failed",
                    error=str(exc),
                    intent_type=intent_type or "unknown",
                )
                # Graceful degradation — return empty context, grounding rules still apply.
                return InjectedContext(
                    formatted_context="",
                    grounding_instructions=_grounding_instructions(),
                )

    # ── Internal build pipeline ────────────────────────────────────────────

    def _build(self, chunks: list[RagChunk], budget: int) -> InjectedContext:
        now = datetime.now(timezone.utc)

        # ── Stage 1: classify freshness + confidence ──────────────────────
        staged: list[_StagedEntry] = []
        excluded_stale = 0

        for chunk in chunks:
            is_stale, staleness_days = _check_staleness(chunk, now)

            if is_stale and chunk.source in _MARKET_NAMESPACES and agent_settings.stale_market_data_excluded:
                excluded_stale += 1
                logger.debug(
                    "rag.context_injector.chunk_excluded_stale",
                    chunk_id=chunk.chunk_id,
                    source=chunk.source,
                    staleness_days=staleness_days,
                )
                continue

            staged.append(_StagedEntry(
                chunk=chunk,
                confidence_label=_confidence_label(chunk.relevance_score),
                is_stale=is_stale,
                staleness_days=staleness_days,
            ))

        # ── Stage 2: trim to token budget ────────────────────────────────
        included: list[_StagedEntry] = []
        excluded_budget = 0
        tokens_used = 0

        for entry in staged:
            chunk_tokens = _estimate_tokens(entry.chunk.content)
            if tokens_used + chunk_tokens > budget:
                excluded_budget += 1
                logger.debug(
                    "rag.context_injector.chunk_budget_trimmed",
                    chunk_id=entry.chunk.chunk_id,
                    tokens_needed=chunk_tokens,
                    budget_remaining=budget - tokens_used,
                )
            else:
                tokens_used += chunk_tokens
                included.append(entry)

        # ── Stage 3: assign citation IDs and build final output ───────────
        cited: list[CitedChunk] = [
            CitedChunk(
                citation_id=f"SRC-{i + 1}",
                chunk=entry.chunk,
                confidence_label=entry.confidence_label,
                is_stale=entry.is_stale,
                staleness_days=entry.staleness_days,
            )
            for i, entry in enumerate(included)
        ]
        citation_map: dict[str, RagChunk] = {c.citation_id: c.chunk for c in cited}

        return InjectedContext(
            formatted_context=_format_evidence_cards(cited),
            grounding_instructions=_grounding_instructions(),
            citation_map=citation_map,
            token_estimate=tokens_used,
            chunks_included=len(cited),
            chunks_excluded_stale=excluded_stale,
            chunks_excluded_budget=excluded_budget,
        )


# ── Internal helpers ───────────────────────────────────────────────────────


@dataclass
class _StagedEntry:
    """Intermediate holder during the two-pass build pipeline."""

    chunk: RagChunk
    confidence_label: str
    is_stale: bool
    staleness_days: int | None


def _confidence_label(score: float) -> str:
    if score >= _HIGH_THRESHOLD:
        return "high"
    if score >= _MEDIUM_THRESHOLD:
        return "medium"
    return "low"


def _estimate_tokens(text: str) -> int:
    """Cheap heuristic token estimate: chars / 4."""
    return max(1, len(text) // _CHARS_PER_TOKEN)


def _check_staleness(
    chunk: RagChunk,
    now: datetime,
) -> tuple[bool, int | None]:
    """Return (is_stale, staleness_days).

    Only market-namespace chunks are subject to the freshness policy.
    Returns (False, None) for non-market namespaces unconditionally.
    """
    if chunk.source not in _MARKET_NAMESPACES:
        return False, None

    limit_days: int = agent_settings.market_data_freshness_days
    date_str: str | None = (
        chunk.metadata.get("retrieved_at") or chunk.metadata.get("source_date")
    )
    if not date_str:
        # No date on a market chunk → conservatively treat as stale.
        return True, None

    try:
        ts = datetime.fromisoformat(str(date_str).rstrip("Z"))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        staleness_days = (now - ts).days
        return staleness_days > limit_days, staleness_days
    except (ValueError, TypeError):
        return True, None


def _format_evidence_cards(chunks: list[CitedChunk]) -> str:
    """Render evidence cards as a readable, structured text block."""
    if not chunks:
        return ""

    lines: list[str] = ["=== Evidence Cards ===", ""]

    for entry in chunks:
        c = entry.chunk

        # Staleness tag
        if entry.is_stale:
            days_str = f"{entry.staleness_days} days old" if entry.staleness_days is not None else "age unknown"
            stale_tag = f" [STALE: {days_str}]"
        else:
            stale_tag = ""

        title_part = f" — {c.title}" if c.title else ""
        header = f"[{entry.citation_id}]{title_part} (confidence: {entry.confidence_label}){stale_tag}"
        lines.append(header)

        # Source line
        source_line = f"Source: {c.source}"
        if c.source_url:
            source_line += f" | {c.source_url}"
        source_line += f" | Relevance: {c.relevance_score:.3f}"
        lines.append(source_line)

        # Freshness date (market data only)
        date_val = c.metadata.get("retrieved_at") or c.metadata.get("source_date")
        if date_val:
            lines.append(f"Date: {date_val}")

        lines.append("---")
        lines.append(c.content.strip())
        lines.append("")

    lines.append("=== End Evidence Cards ===")
    return "\n".join(lines)


def _grounding_instructions() -> str:
    return _GROUNDING_INSTRUCTIONS_TEMPLATE.format(
        claim_types=", ".join(_MUST_CITE_TYPES)
    )


# ── Convenience helpers for agent prompt construction ─────────────────────


def build_grounded_system_prompt(base_system: str, context: InjectedContext) -> str:
    """Append grounding rules to a base system prompt.

    Usage::

        injected = get_context_injector().inject(ctx.rag_chunks)
        system = build_grounded_system_prompt(MY_AGENT_SYSTEM, injected)
    """
    if not context.grounding_instructions:
        return base_system
    return f"{base_system}\n\n{context.grounding_instructions}"


def build_grounded_human_message(user_instruction: str, context: InjectedContext) -> str:
    """Prepend evidence cards to a human/user message.

    Usage::

        injected = get_context_injector().inject(ctx.rag_chunks)
        msg = build_grounded_human_message(user_goal, injected)
    """
    if not context.formatted_context:
        return user_instruction
    return f"{context.formatted_context}\n\n{user_instruction}"


# ── Module-level singleton ─────────────────────────────────────────────────

_INJECTOR: ContextInjector | None = None


def get_context_injector() -> ContextInjector:
    """Return the process-level ContextInjector singleton."""
    global _INJECTOR
    if _INJECTOR is None:
        _INJECTOR = ContextInjector()
    return _INJECTOR
