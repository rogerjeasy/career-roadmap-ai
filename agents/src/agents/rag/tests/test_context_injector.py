"""Tests for ContextInjector — token budget, freshness, citations, confidence."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import patch, MagicMock

import pytest

from agents.core.context import RagChunk
from agents.rag.context_injector import (
    CitedChunk,
    ContextInjector,
    InjectedContext,
    _check_staleness,
    _confidence_label,
    _estimate_tokens,
    _format_evidence_cards,
    build_grounded_human_message,
    build_grounded_system_prompt,
    get_context_injector,
)


# ── Fixtures ───────────────────────────────────────────────────────────────


def _chunk(
    *,
    chunk_id: str = "c1",
    content: str = "Sample content about Python skills.",
    source: str = "career-kb",
    score: float = 0.90,
    title: str = "Test Title",
    source_url: str | None = None,
    metadata: dict | None = None,
) -> RagChunk:
    return RagChunk(
        chunk_id=chunk_id,
        content=content,
        source=source,
        relevance_score=score,
        title=title,
        source_url=source_url,
        metadata=metadata or {},
    )


def _market_chunk(
    *,
    chunk_id: str = "m1",
    content: str = "Demand for data engineers is rising in Switzerland.",
    score: float = 0.80,
    days_old: int | None = 10,
) -> RagChunk:
    if days_old is not None:
        date = (datetime.now(timezone.utc) - timedelta(days=days_old)).isoformat()
        meta = {"retrieved_at": date}
    else:
        meta = {}
    return RagChunk(
        chunk_id=chunk_id,
        content=content,
        source="market-reports",
        relevance_score=score,
        title="Swiss Market 2025",
        source_url=None,
        metadata=meta,
    )


# Mock agent_settings to avoid requiring env vars
_MOCK_SETTINGS = MagicMock()
_MOCK_SETTINGS.context_injection_token_budget = 4000
_MOCK_SETTINGS.market_data_freshness_days = 30
_MOCK_SETTINGS.stale_market_data_excluded = True


@pytest.fixture(autouse=True)
def _patch_settings(monkeypatch):
    """Patch agent_settings for every test in this module."""
    monkeypatch.setattr(
        "agents.rag.context_injector.agent_settings", _MOCK_SETTINGS
    )
    _MOCK_SETTINGS.context_injection_token_budget = 4000
    _MOCK_SETTINGS.market_data_freshness_days = 30
    _MOCK_SETTINGS.stale_market_data_excluded = True


# ── Confidence label ───────────────────────────────────────────────────────


def test_confidence_label_high():
    assert _confidence_label(0.95) == "high"
    assert _confidence_label(0.85) == "high"


def test_confidence_label_medium():
    assert _confidence_label(0.84) == "medium"
    assert _confidence_label(0.70) == "medium"


def test_confidence_label_low():
    assert _confidence_label(0.69) == "low"
    assert _confidence_label(0.00) == "low"


# ── Token estimation ───────────────────────────────────────────────────────


def test_estimate_tokens_basic():
    text = "a" * 400  # 400 chars → 100 tokens
    assert _estimate_tokens(text) == 100


def test_estimate_tokens_minimum():
    assert _estimate_tokens("") == 1
    assert _estimate_tokens("x") == 1


# ── Freshness check ────────────────────────────────────────────────────────


def test_freshness_non_market_chunk_never_stale():
    chunk = _chunk(source="career-kb", metadata={})
    is_stale, days = _check_staleness(chunk, datetime.now(timezone.utc))
    assert is_stale is False
    assert days is None


def test_freshness_market_chunk_fresh():
    chunk = _market_chunk(days_old=10)
    is_stale, days = _check_staleness(chunk, datetime.now(timezone.utc))
    assert is_stale is False
    assert days == 10


def test_freshness_market_chunk_stale():
    chunk = _market_chunk(days_old=45)
    is_stale, days = _check_staleness(chunk, datetime.now(timezone.utc))
    assert is_stale is True
    assert days == 45


def test_freshness_market_chunk_no_date():
    chunk = _market_chunk(days_old=None)
    is_stale, days = _check_staleness(chunk, datetime.now(timezone.utc))
    assert is_stale is True
    assert days is None


def test_freshness_market_chunk_invalid_date():
    chunk = RagChunk(
        chunk_id="x",
        content="...",
        source="market-reports",
        relevance_score=0.75,
        metadata={"retrieved_at": "not-a-date"},
    )
    is_stale, days = _check_staleness(chunk, datetime.now(timezone.utc))
    assert is_stale is True


def test_freshness_source_date_field():
    date = (datetime.now(timezone.utc) - timedelta(days=5)).isoformat()
    chunk = RagChunk(
        chunk_id="x",
        content="...",
        source="swiss-eu-market",
        relevance_score=0.75,
        metadata={"source_date": date},
    )
    is_stale, days = _check_staleness(chunk, datetime.now(timezone.utc))
    assert is_stale is False
    assert days == 5


# ── Evidence card formatting ───────────────────────────────────────────────


def test_format_empty_returns_empty_string():
    assert _format_evidence_cards([]) == ""


def test_format_single_chunk_contains_citation():
    chunk = _chunk()
    cited = [CitedChunk(
        citation_id="SRC-1",
        chunk=chunk,
        confidence_label="high",
        is_stale=False,
        staleness_days=None,
    )]
    output = _format_evidence_cards(cited)
    assert "[SRC-1]" in output
    assert "confidence: high" in output
    assert chunk.content in output
    assert "=== Evidence Cards ===" in output
    assert "=== End Evidence Cards ===" in output


def test_format_stale_chunk_shows_stale_tag():
    chunk = _chunk(source="market-reports")
    cited = [CitedChunk(
        citation_id="SRC-1",
        chunk=chunk,
        confidence_label="medium",
        is_stale=True,
        staleness_days=45,
    )]
    output = _format_evidence_cards(cited)
    assert "[STALE: 45 days old]" in output


def test_format_stale_chunk_unknown_age():
    chunk = _chunk(source="market-reports")
    cited = [CitedChunk(
        citation_id="SRC-1",
        chunk=chunk,
        confidence_label="low",
        is_stale=True,
        staleness_days=None,
    )]
    output = _format_evidence_cards(cited)
    assert "[STALE: age unknown]" in output


def test_format_source_url_included():
    chunk = _chunk(source_url="https://example.com/report")
    cited = [CitedChunk(
        citation_id="SRC-1",
        chunk=chunk,
        confidence_label="high",
        is_stale=False,
        staleness_days=None,
    )]
    output = _format_evidence_cards(cited)
    assert "https://example.com/report" in output


def test_format_multiple_chunks_sequential_ids():
    chunks = [
        CitedChunk(citation_id="SRC-1", chunk=_chunk(chunk_id="c1"), confidence_label="high", is_stale=False, staleness_days=None),
        CitedChunk(citation_id="SRC-2", chunk=_chunk(chunk_id="c2"), confidence_label="medium", is_stale=False, staleness_days=None),
    ]
    output = _format_evidence_cards(chunks)
    assert "[SRC-1]" in output
    assert "[SRC-2]" in output


# ── ContextInjector.inject() ───────────────────────────────────────────────


@pytest.fixture
def injector() -> ContextInjector:
    return ContextInjector()


def test_inject_empty_chunks(injector):
    result = injector.inject([])
    assert result.chunks_included == 0
    assert result.formatted_context == ""
    assert result.has_context is False
    assert "GROUNDING" in result.grounding_instructions


def test_inject_single_chunk(injector):
    result = injector.inject([_chunk()])
    assert result.chunks_included == 1
    assert result.has_context is True
    assert "SRC-1" in result.citation_map
    assert "[SRC-1]" in result.formatted_context


def test_inject_citation_map_keys_match_formatted(injector):
    chunks = [_chunk(chunk_id=f"c{i}") for i in range(3)]
    result = injector.inject(chunks)
    for key in result.citation_map:
        assert f"[{key}]" in result.formatted_context


def test_inject_token_budget_trims_excess(injector):
    # Each chunk ~200 tokens (800 chars); budget 300 → only 1 fits
    _MOCK_SETTINGS.context_injection_token_budget = 300
    long_content = "word " * 160  # ~800 chars → ~200 tokens
    chunks = [_chunk(chunk_id=f"c{i}", content=long_content) for i in range(5)]
    result = injector.inject(chunks, token_budget=300)
    assert result.chunks_included == 1
    assert result.chunks_excluded_budget == 4


def test_inject_token_budget_includes_all_when_sufficient(injector):
    short = "short " * 5  # ~30 chars → ~7 tokens each
    chunks = [_chunk(chunk_id=f"c{i}", content=short) for i in range(5)]
    result = injector.inject(chunks, token_budget=1000)
    assert result.chunks_included == 5
    assert result.chunks_excluded_budget == 0


def test_inject_stale_market_chunk_excluded_by_default(injector):
    _MOCK_SETTINGS.stale_market_data_excluded = True
    stale = _market_chunk(days_old=60)
    fresh = _chunk()
    result = injector.inject([stale, fresh])
    assert result.chunks_excluded_stale == 1
    assert result.chunks_included == 1  # only the fresh career-kb chunk


def test_inject_stale_market_chunk_included_when_flag_off(injector):
    _MOCK_SETTINGS.stale_market_data_excluded = False
    stale = _market_chunk(days_old=60)
    result = injector.inject([stale])
    # Included but labelled stale
    assert result.chunks_excluded_stale == 0
    assert result.chunks_included == 1
    assert "[STALE:" in result.formatted_context


def test_inject_fresh_market_chunk_not_excluded(injector):
    _MOCK_SETTINGS.stale_market_data_excluded = True
    fresh_market = _market_chunk(days_old=5)
    result = injector.inject([fresh_market])
    assert result.chunks_excluded_stale == 0
    assert result.chunks_included == 1


def test_inject_all_stale_returns_empty_context(injector):
    _MOCK_SETTINGS.stale_market_data_excluded = True
    stale1 = _market_chunk(chunk_id="m1", days_old=60)
    stale2 = _market_chunk(chunk_id="m2", days_old=90)
    result = injector.inject([stale1, stale2])
    assert result.chunks_included == 0
    assert result.formatted_context == ""
    assert result.has_context is False
    # Grounding instructions still present
    assert "GROUNDING" in result.grounding_instructions


def test_inject_token_estimate_matches_included_content(injector):
    content = "token " * 100  # 600 chars → ~150 tokens
    chunk = _chunk(content=content)
    result = injector.inject([chunk])
    # Estimate should be non-zero and roughly 150 ± rounding
    assert result.token_estimate >= 100


def test_inject_confidence_labels_in_output(injector):
    high = _chunk(chunk_id="h1", score=0.92)
    medium = _chunk(chunk_id="m1", score=0.75)
    low = _chunk(chunk_id="l1", score=0.50)
    result = injector.inject([high, medium, low])
    assert "confidence: high" in result.formatted_context
    assert "confidence: medium" in result.formatted_context
    assert "confidence: low" in result.formatted_context


def test_inject_intent_type_does_not_crash(injector):
    result = injector.inject([_chunk()], intent_type="roadmap_generation")
    assert result.chunks_included == 1


def test_inject_grounding_instructions_contain_required_claim_types(injector):
    result = injector.inject([_chunk()])
    instructions = result.grounding_instructions
    assert "salary ranges" in instructions
    assert "ASSUMPTION" in instructions
    assert "sources" in instructions


# ── Prompt-builder helpers ─────────────────────────────────────────────────


def test_build_grounded_system_prompt_appends_rules(injector):
    context = injector.inject([_chunk()])
    augmented = build_grounded_system_prompt("You are a career coach.", context)
    assert "You are a career coach." in augmented
    assert "GROUNDING" in augmented


def test_build_grounded_system_prompt_empty_context_unchanged(injector):
    context = injector.inject([])
    context.grounding_instructions = ""
    augmented = build_grounded_system_prompt("Base prompt.", context)
    assert augmented == "Base prompt."


def test_build_grounded_human_message_prepends_cards(injector):
    context = injector.inject([_chunk()])
    message = build_grounded_human_message("Help me transition to ML.", context)
    assert "Evidence Cards" in message
    assert "Help me transition to ML." in message


def test_build_grounded_human_message_no_context_unchanged(injector):
    context = injector.inject([])
    message = build_grounded_human_message("Help me.", context)
    assert message == "Help me."


# ── Singleton ──────────────────────────────────────────────────────────────


def test_get_context_injector_returns_same_instance():
    i1 = get_context_injector()
    i2 = get_context_injector()
    assert i1 is i2
