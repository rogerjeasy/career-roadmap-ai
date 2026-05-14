"""Tests for RAG retrieval: retriever, reranker, MMR, and context assembler."""
from __future__ import annotations

import math
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agents.contracts.tasks import UserProfileSnapshot
from agents.core.context import RagChunk
from agents.rag.models import KnowledgeNamespace, RetrievedChunk, SparseVector
from agents.rag.retrieval.context_assembler import ContextAssembler, _build_query
from agents.rag.retrieval.mmr import fetch_chunk_vectors, maximal_marginal_relevance
from agents.rag.retrieval.reranker import _replace_score
from agents.rag.retrieval.retriever import _scale_hybrid


# ── Helpers ───────────────────────────────────────────────────────────────────


def _chunk(
    chunk_id: str = "c1",
    doc_id: str = "d1",
    score: float = 0.90,
    content: str = "Some content.",
    namespace: str = "career-kb",
    title: str = "",
    source_url: str | None = None,
) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=chunk_id,
        doc_id=doc_id,
        doc_type="career_kb",
        content=content,
        score=score,
        namespace=namespace,
        title=title,
        source_url=source_url,
    )


def _profile() -> UserProfileSnapshot:
    return UserProfileSnapshot(
        target_role="Senior Software Engineer",
        current_role="Software Engineer",
        skills=["Python", "FastAPI"],
    )


# ── RetrievedChunk citation fields ────────────────────────────────────────────


class TestRetrievedChunkCitationFields:
    def test_title_defaults_to_empty_string(self) -> None:
        c = _chunk()
        assert c.title == ""

    def test_source_url_defaults_to_none(self) -> None:
        c = _chunk()
        assert c.source_url is None

    def test_citation_fields_preserved(self) -> None:
        c = _chunk(title="Senior SWE Guide", source_url="https://example.com/swe")
        assert c.title == "Senior SWE Guide"
        assert c.source_url == "https://example.com/swe"


# ── _replace_score helper ─────────────────────────────────────────────────────


class TestReplaceScore:
    def test_score_is_updated(self) -> None:
        c = _chunk(score=0.80)
        updated = _replace_score(c, 9.5)
        assert updated.score == pytest.approx(9.5)

    def test_all_other_fields_preserved(self) -> None:
        c = _chunk(
            chunk_id="x1",
            doc_id="d9",
            score=0.7,
            content="Hello.",
            namespace="role-templates",
            title="My Title",
            source_url="https://example.com",
        )
        updated = _replace_score(c, 3.2)
        assert updated.chunk_id == "x1"
        assert updated.doc_id == "d9"
        assert updated.content == "Hello."
        assert updated.namespace == "role-templates"
        assert updated.title == "My Title"
        assert updated.source_url == "https://example.com"


# ── MMR pure algorithm ────────────────────────────────────────────────────────


class TestMaximalMarginalRelevance:
    def _unit(self, *components: float) -> list[float]:
        """Return a normalised vector from the given components."""
        magnitude = math.sqrt(sum(x * x for x in components))
        return [x / magnitude for x in components]

    def test_empty_candidates_returns_empty(self) -> None:
        result = maximal_marginal_relevance(
            [1.0, 0.0], {}, [], top_k=5, lambda_mult=0.5
        )
        assert result == []

    def test_top_k_zero_returns_empty(self) -> None:
        chunks = [_chunk("c1")]
        result = maximal_marginal_relevance(
            [1.0, 0.0], {"c1": [1.0, 0.0]}, chunks, top_k=0
        )
        assert result == []

    def test_returns_at_most_top_k(self) -> None:
        chunks = [_chunk(f"c{i}", doc_id=f"d{i}") for i in range(5)]
        vecs = {f"c{i}": [float(i), 0.0] for i in range(5)}
        result = maximal_marginal_relevance(
            [1.0, 0.0], vecs, chunks, top_k=3, lambda_mult=0.5
        )
        assert len(result) <= 3

    def test_lambda_one_preserves_relevance_order(self) -> None:
        """λ=1 is pure relevance — result order must match input score order."""
        query = self._unit(1.0, 0.0)
        # Scores: c0=high, c1=medium, c2=low (all point in same direction)
        chunks = [
            _chunk("c0", doc_id="d0", score=0.95),
            _chunk("c1", doc_id="d1", score=0.80),
            _chunk("c2", doc_id="d2", score=0.60),
        ]
        # Vectors all aligned with query; similarity proportional to score
        vecs = {
            "c0": self._unit(0.95, 0.01),
            "c1": self._unit(0.80, 0.01),
            "c2": self._unit(0.60, 0.01),
        }
        result = maximal_marginal_relevance(
            query, vecs, chunks, top_k=3, lambda_mult=1.0
        )
        ids = [r.chunk_id for r in result]
        assert ids == ["c0", "c1", "c2"]

    def test_lambda_zero_maximises_diversity(self) -> None:
        """λ=0 should avoid selecting two chunks pointing in the same direction."""
        query = self._unit(1.0, 0.0)
        # c0 and c1 are nearly identical; c2 is orthogonal
        chunks = [
            _chunk("c0", doc_id="d0", score=0.95),
            _chunk("c1", doc_id="d1", score=0.93),
            _chunk("c2", doc_id="d2", score=0.70),
        ]
        vecs = {
            "c0": self._unit(1.0, 0.01),   # nearly same as c1
            "c1": self._unit(1.0, 0.02),   # nearly same as c0
            "c2": self._unit(0.01, 1.0),   # orthogonal
        }
        result = maximal_marginal_relevance(
            query, vecs, chunks, top_k=2, lambda_mult=0.0
        )
        ids = {r.chunk_id for r in result}
        # c0 selected first (highest dot with query), then c2 (most diverse)
        assert "c0" in ids
        assert "c2" in ids
        assert "c1" not in ids

    def test_fallback_chunks_appended_when_no_vector(self) -> None:
        chunks = [
            _chunk("c0", doc_id="d0", score=0.95),
            _chunk("c1", doc_id="d1", score=0.70),  # no vector
        ]
        vecs = {"c0": [1.0, 0.0]}
        result = maximal_marginal_relevance(
            [1.0, 0.0], vecs, chunks, top_k=2, lambda_mult=0.5
        )
        ids = [r.chunk_id for r in result]
        assert "c0" in ids
        assert "c1" in ids

    def test_all_fallback_returns_score_order(self) -> None:
        chunks = [_chunk(f"c{i}", doc_id=f"d{i}", score=float(3 - i)) for i in range(3)]
        result = maximal_marginal_relevance(
            [1.0, 0.0], {}, chunks, top_k=3, lambda_mult=0.5
        )
        assert [r.chunk_id for r in result] == ["c0", "c1", "c2"]


# ── fetch_chunk_vectors ───────────────────────────────────────────────────────


class TestFetchChunkVectors:
    @pytest.mark.asyncio
    async def test_groups_by_namespace_and_maps_ids(self) -> None:
        fetch_result = MagicMock()
        fetch_result.vectors = {
            "c1": MagicMock(values=[0.1, 0.2]),
            "c2": MagicMock(values=[0.3, 0.4]),
        }
        index = MagicMock()
        index.fetch = MagicMock(return_value=fetch_result)

        chunks = [
            _chunk("c1", namespace="career-kb"),
            _chunk("c2", namespace="career-kb"),
        ]
        vectors = await fetch_chunk_vectors(index, chunks)
        assert "c1" in vectors
        assert "c2" in vectors
        assert vectors["c1"] == pytest.approx([0.1, 0.2])

    @pytest.mark.asyncio
    async def test_tolerates_fetch_error(self) -> None:
        index = MagicMock()
        index.fetch = MagicMock(side_effect=RuntimeError("Pinecone unavailable"))

        chunks = [_chunk("c1", namespace="career-kb")]
        vectors = await fetch_chunk_vectors(index, chunks)
        assert vectors == {}

    @pytest.mark.asyncio
    async def test_multi_namespace_fetched_separately(self) -> None:
        def _fake_fetch(ids, namespace):
            if namespace == "career-kb":
                return MagicMock(vectors={"c1": MagicMock(values=[1.0, 0.0])})
            return MagicMock(vectors={"c2": MagicMock(values=[0.0, 1.0])})

        index = MagicMock()
        index.fetch = MagicMock(side_effect=_fake_fetch)

        chunks = [
            _chunk("c1", namespace="career-kb"),
            _chunk("c2", namespace="role-templates"),
        ]
        vectors = await fetch_chunk_vectors(index, chunks)
        assert "c1" in vectors
        assert "c2" in vectors


# ── ContextAssembler ──────────────────────────────────────────────────────────


class TestContextAssembler:
    def _make_assembler(self, chunks: list[RetrievedChunk]) -> ContextAssembler:
        retriever = MagicMock()
        retriever.retrieve = AsyncMock(return_value=chunks)
        return ContextAssembler(retriever=retriever)

    @pytest.mark.asyncio
    async def test_returns_rag_chunks_when_enabled(self) -> None:
        chunks = [
            RetrievedChunk(
                chunk_id="c1",
                doc_id="d1",
                doc_type="career_kb",
                content="Senior engineers design scalable systems.",
                score=0.92,
                namespace="career-kb",
            )
        ]
        assembler = self._make_assembler(chunks)
        with patch("agents.rag.retrieval.context_assembler.agent_settings") as mock_settings:
            mock_settings.rag_enabled = True
            mock_settings.rag_top_k = 10
            result = await assembler.assemble(
                user_message="I want to become a senior engineer",
                user_profile=_profile(),
                intent_type="roadmap_generation",
            )
        assert len(result) == 1
        assert isinstance(result[0], RagChunk)
        assert result[0].relevance_score == 0.92

    @pytest.mark.asyncio
    async def test_citation_fields_surfaced_on_rag_chunk(self) -> None:
        chunks = [
            RetrievedChunk(
                chunk_id="c1",
                doc_id="d1",
                doc_type="career_kb",
                content="Content.",
                score=0.88,
                namespace="career-kb",
                title="Career Guide 2024",
                source_url="https://example.com/guide",
            )
        ]
        assembler = self._make_assembler(chunks)
        with patch("agents.rag.retrieval.context_assembler.agent_settings") as ms:
            ms.rag_enabled = True
            ms.rag_top_k = 10
            result = await assembler.assemble(
                user_message="test", user_profile=_profile()
            )
        assert result[0].title == "Career Guide 2024"
        assert result[0].source_url == "https://example.com/guide"

    @pytest.mark.asyncio
    async def test_returns_empty_when_rag_disabled(self) -> None:
        assembler = self._make_assembler([])
        with patch("agents.rag.retrieval.context_assembler.agent_settings") as mock_settings:
            mock_settings.rag_enabled = False
            result = await assembler.assemble(
                user_message="test",
                user_profile=_profile(),
            )
        assert result == []

    @pytest.mark.asyncio
    async def test_returns_empty_on_retrieval_error(self) -> None:
        retriever = MagicMock()
        retriever.retrieve = AsyncMock(side_effect=RuntimeError("Pinecone down"))
        assembler = ContextAssembler(retriever=retriever)
        with patch("agents.rag.retrieval.context_assembler.agent_settings") as mock_settings:
            mock_settings.rag_enabled = True
            mock_settings.rag_top_k = 10
            result = await assembler.assemble(
                user_message="test",
                user_profile=_profile(),
            )
        assert result == []

    @pytest.mark.asyncio
    async def test_metadata_preserved_in_rag_chunk(self) -> None:
        chunks = [
            RetrievedChunk(
                chunk_id="c1",
                doc_id="d1",
                doc_type="role_template",
                content="Role content.",
                score=0.85,
                namespace="role-templates",
                metadata={"title": "SWE Requirements", "region": "Switzerland"},
            )
        ]
        assembler = self._make_assembler(chunks)
        with patch("agents.rag.retrieval.context_assembler.agent_settings") as mock_settings:
            mock_settings.rag_enabled = True
            mock_settings.rag_top_k = 10
            result = await assembler.assemble(
                user_message="test",
                user_profile=_profile(),
            )
        assert result[0].metadata["region"] == "Switzerland"


# ── Hybrid scaling helper ─────────────────────────────────────────────────────


class TestScaleHybrid:
    def test_dense_scaled_by_alpha(self) -> None:
        dense = [1.0, 0.5, 0.25]
        sparse = SparseVector(indices=[0, 1], values=[0.8, 0.4])
        scaled_dense, _ = _scale_hybrid(dense, sparse, alpha=0.75)
        assert scaled_dense == pytest.approx([0.75, 0.375, 0.1875])

    def test_sparse_scaled_by_one_minus_alpha(self) -> None:
        dense = [1.0]
        sparse = SparseVector(indices=[5, 10], values=[1.0, 0.5])
        _, scaled_sparse = _scale_hybrid(dense, sparse, alpha=0.75)
        assert scaled_sparse["indices"] == [5, 10]
        assert scaled_sparse["values"] == pytest.approx([0.25, 0.125])

    def test_alpha_one_zeroes_sparse(self) -> None:
        dense = [1.0]
        sparse = SparseVector(indices=[1], values=[0.9])
        _, scaled_sparse = _scale_hybrid(dense, sparse, alpha=1.0)
        assert scaled_sparse["values"] == pytest.approx([0.0])

    def test_alpha_zero_zeroes_dense(self) -> None:
        dense = [1.0, 0.5]
        sparse = SparseVector(indices=[1], values=[0.9])
        scaled_dense, _ = _scale_hybrid(dense, sparse, alpha=0.0)
        assert scaled_dense == pytest.approx([0.0, 0.0])

    def test_indices_preserved(self) -> None:
        dense = [0.5]
        sparse = SparseVector(indices=[3, 7, 99], values=[0.1, 0.2, 0.3])
        _, scaled_sparse = _scale_hybrid(dense, sparse, alpha=0.6)
        assert scaled_sparse["indices"] == [3, 7, 99]


# ── Query builder ─────────────────────────────────────────────────────────────


class TestBuildQuery:
    def _profile(self, **kwargs) -> UserProfileSnapshot:
        defaults = dict(
            target_role="Data Engineer",
            current_role="Data Analyst",
            skills=["SQL", "Python"],
        )
        defaults.update(kwargs)
        return UserProfileSnapshot(**defaults)

    def test_includes_user_message(self) -> None:
        query = _build_query("Help me transition to ML", self._profile(), None)
        assert "Help me transition to ML" in query

    def test_includes_target_role(self) -> None:
        query = _build_query("", self._profile(), None)
        assert "Data Engineer" in query

    def test_includes_intent_type(self) -> None:
        query = _build_query("", self._profile(), "roadmap_generation")
        assert "roadmap_generation" in query

    def test_query_capped_at_1000_chars(self) -> None:
        long_msg = "a" * 2000
        query = _build_query(long_msg, self._profile(), None)
        assert len(query) <= 1000
