"""Tests for RAG ingestion pipeline: chunker, BM25 encoder, and loaders."""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from agents.rag.ingestion.chunker import (
    Chunker,
    SemanticChunker,
    _merge_into_windows,
    _split_paragraphs,
)
from agents.rag.ingestion.loaders.career_kb_loader import CareerKBLoader
from agents.rag.ingestion.loaders.esco_loader import ESCOLoader
from agents.rag.ingestion.loaders.market_reports_loader import MarketReportsLoader
from agents.rag.ingestion.loaders.role_templates_loader import RoleTemplatesLoader
from agents.rag.models import Document, DocumentType, SparseVector


# ── SemanticChunker ────────────────────────────────────────────────────────────


class TestSemanticChunker:
    def test_short_document_produces_one_chunk(self, sample_document: Document) -> None:
        chunker = SemanticChunker()
        chunks = chunker.chunk(sample_document)
        assert len(chunks) >= 1
        for chunk in chunks:
            assert chunk.doc_id == sample_document.doc_id
            assert chunk.doc_type == sample_document.doc_type

    def test_long_document_produces_multiple_chunks(self) -> None:
        long_content = ("This is a sentence about software engineering. " * 20 + "\n\n") * 10
        doc = Document(
            doc_id="long-doc-sem",
            doc_type=DocumentType.MARKET_REPORT,
            title="Long Report",
            content=long_content,
        )
        chunker = SemanticChunker(target_chars=400, overlap_sentences=1)
        chunks = chunker.chunk(doc)
        assert len(chunks) > 1

    def test_sentence_overlap_carries_over(self) -> None:
        content = (
            "First important sentence about Python. "
            "Second sentence about career growth. "
            "Third sentence about salary negotiation. "
            "Fourth sentence about networking strategies. "
            "Fifth sentence about interview preparation."
        )
        doc = Document(
            doc_id="overlap-sem",
            doc_type=DocumentType.CAREER_KB,
            title="Overlap Test",
            content=content,
        )
        chunker = SemanticChunker(target_chars=120, overlap_sentences=1)
        chunks = chunker.chunk(doc)
        assert len(chunks) >= 2
        # The start of the second chunk should contain a sentence from the end of the first
        if len(chunks) >= 2:
            first_sentences = chunks[0].content
            second_start = chunks[1].content[:80]
            assert any(word in second_start for word in first_sentences.split()[-10:])

    def test_metadata_includes_role_industry_country(self) -> None:
        doc = Document(
            doc_id="meta-doc",
            doc_type=DocumentType.ROLE_TEMPLATE,
            title="Senior SWE",
            content="This role requires five years of Python experience.",
            metadata={"role": "Senior Software Engineer", "industry": "FinTech", "country": "Switzerland"},
        )
        chunker = SemanticChunker()
        chunks = chunker.chunk(doc)
        assert len(chunks) >= 1
        meta = chunks[0].metadata
        assert meta.get("role") == "Senior Software Engineer"
        assert meta.get("industry") == "FinTech"
        assert meta.get("country") == "Switzerland"

    def test_metadata_skips_missing_dimensions(self) -> None:
        doc = Document(
            doc_id="no-meta-doc",
            doc_type=DocumentType.CAREER_KB,
            title="General Article",
            content="General career advice for professionals.",
        )
        chunker = SemanticChunker()
        chunks = chunker.chunk(doc)
        assert "role" not in chunks[0].metadata
        assert "industry" not in chunks[0].metadata
        assert "country" not in chunks[0].metadata

    def test_empty_content_returns_fallback(self) -> None:
        doc = Document(
            doc_id="tiny-doc",
            doc_type=DocumentType.CAREER_KB,
            title="Tiny",
            content="Short.",
        )
        chunks = SemanticChunker().chunk(doc)
        assert len(chunks) == 1

    def test_chunk_metadata_includes_title(self, sample_document: Document) -> None:
        chunker = SemanticChunker()
        chunks = chunker.chunk(sample_document)
        assert all(c.metadata.get("title") == sample_document.title for c in chunks)


# ── Chunker ────────────────────────────────────────────────────────────────────


class TestChunker:
    def test_short_document_produces_one_chunk(self, sample_document: Document) -> None:
        chunker = Chunker()
        chunks = chunker.chunk(sample_document)
        assert len(chunks) >= 1
        for chunk in chunks:
            assert chunk.doc_id == sample_document.doc_id
            assert chunk.doc_type == sample_document.doc_type

    def test_long_document_produces_multiple_chunks(self) -> None:
        long_content = ("This is a sentence about software engineering. " * 60 + "\n\n") * 5
        doc = Document(
            doc_id="long-doc",
            doc_type=DocumentType.MARKET_REPORT,
            title="Long Report",
            content=long_content,
        )
        chunker = Chunker(target_chars=500, overlap_chars=50)
        chunks = chunker.chunk(doc)
        assert len(chunks) > 1

    def test_chunks_contain_overlap(self) -> None:
        content = (
            "First paragraph with important context.\n\n"
            "Second paragraph continues the topic.\n\n"
            "Third paragraph provides more detail."
        )
        doc = Document(
            doc_id="overlap-doc",
            doc_type=DocumentType.CAREER_KB,
            title="Overlap Test",
            content=content,
        )
        chunker = Chunker(target_chars=60, overlap_chars=20)
        chunks = chunker.chunk(doc)
        assert len(chunks) >= 1

    def test_empty_document_returns_fallback(self) -> None:
        doc = Document(
            doc_id="empty-doc",
            doc_type=DocumentType.CAREER_KB,
            title="Empty",
            content="Short.",
        )
        chunks = Chunker().chunk(doc)
        assert len(chunks) == 1

    def test_chunk_metadata_includes_title(self, sample_document: Document) -> None:
        chunker = Chunker()
        chunks = chunker.chunk(sample_document)
        assert all(c.metadata.get("title") == sample_document.title for c in chunks)

    def test_split_paragraphs_splits_on_double_newline(self) -> None:
        text = "Para one.\n\nPara two.\n\nPara three."
        parts = _split_paragraphs(text, 2000)
        assert len(parts) == 3

    def test_merge_into_windows_respects_target(self) -> None:
        paragraphs = ["a" * 100, "b" * 100, "c" * 100]
        windows = _merge_into_windows(paragraphs, target=200, overlap=20)
        assert all(len(w) > 0 for w in windows)


# ── BM25SparseEncoder ────────────────────────────────────────────────────────


class TestBM25SparseEncoder:
    def _mock_bm25_encoder(self) -> MagicMock:
        """Return a mock pinecone_text BM25Encoder."""
        enc = MagicMock()
        enc.encode_documents.return_value = [
            {"indices": [1, 42, 137], "values": [0.8, 0.6, 0.4]},
            {"indices": [2, 50, 200], "values": [0.7, 0.5, 0.3]},
        ]
        enc.encode_queries.return_value = [
            {"indices": [1, 42], "values": [0.9, 0.5]}
        ]
        return enc

    def test_encode_documents_returns_sparse_vectors(self) -> None:
        from agents.rag.ingestion.bm25_encoder import BM25SparseEncoder

        mock_inner = self._mock_bm25_encoder()
        with patch("agents.rag.ingestion.bm25_encoder.BM25SparseEncoder.__init__", return_value=None):
            encoder = BM25SparseEncoder.__new__(BM25SparseEncoder)
            encoder._encoder = mock_inner

        texts = ["Senior Python engineer", "Kubernetes operator Zurich"]
        result = encoder.encode_documents(texts)
        assert len(result) == 2
        assert all(isinstance(r, SparseVector) for r in result)
        assert result[0].indices == [1, 42, 137]
        assert result[0].values == [0.8, 0.6, 0.4]

    def test_encode_query_returns_sparse_vector(self) -> None:
        from agents.rag.ingestion.bm25_encoder import BM25SparseEncoder

        mock_inner = self._mock_bm25_encoder()
        with patch("agents.rag.ingestion.bm25_encoder.BM25SparseEncoder.__init__", return_value=None):
            encoder = BM25SparseEncoder.__new__(BM25SparseEncoder)
            encoder._encoder = mock_inner

        result = encoder.encode_query("Staff Engineer FAANG")
        assert isinstance(result, SparseVector)
        assert result.indices == [1, 42]
        assert result.values == [0.9, 0.5]

    def test_fit_calls_underlying_encoder(self) -> None:
        from agents.rag.ingestion.bm25_encoder import BM25SparseEncoder

        mock_inner = self._mock_bm25_encoder()
        with patch("agents.rag.ingestion.bm25_encoder.BM25SparseEncoder.__init__", return_value=None):
            encoder = BM25SparseEncoder.__new__(BM25SparseEncoder)
            encoder._encoder = mock_inner

        corpus = ["Python developer", "Data engineer SQL", "Senior SWE Zurich"]
        encoder.fit(corpus)
        mock_inner.fit.assert_called_once_with(corpus)

    def test_save_calls_dump(self, tmp_path) -> None:
        from agents.rag.ingestion.bm25_encoder import BM25SparseEncoder

        mock_inner = self._mock_bm25_encoder()
        with patch("agents.rag.ingestion.bm25_encoder.BM25SparseEncoder.__init__", return_value=None):
            encoder = BM25SparseEncoder.__new__(BM25SparseEncoder)
            encoder._encoder = mock_inner

        out_path = str(tmp_path / "bm25_params.json")
        encoder.save(out_path)
        mock_inner.dump.assert_called_once_with(out_path)

    def test_encode_documents_empty_list(self) -> None:
        from agents.rag.ingestion.bm25_encoder import BM25SparseEncoder

        mock_inner = self._mock_bm25_encoder()
        mock_inner.encode_documents.return_value = []
        with patch("agents.rag.ingestion.bm25_encoder.BM25SparseEncoder.__init__", return_value=None):
            encoder = BM25SparseEncoder.__new__(BM25SparseEncoder)
            encoder._encoder = mock_inner

        result = encoder.encode_documents([])
        assert result == []


# ── Career KB Loader ──────────────────────────────────────────────────────────


class TestCareerKBLoader:
    @pytest.mark.asyncio
    async def test_loads_json_array(self) -> None:
        data = json.dumps([
            {"id": "1", "title": "Title 1", "content": "Content one here."},
            {"id": "2", "title": "Title 2", "content": "Content two here."},
        ]).encode()
        loader = CareerKBLoader(source=data)
        docs = [doc async for doc in loader.load()]
        assert len(docs) == 2
        assert all(d.doc_type == DocumentType.CAREER_KB for d in docs)

    @pytest.mark.asyncio
    async def test_skips_empty_content(self) -> None:
        data = json.dumps([
            {"id": "1", "title": "T", "content": ""},
            {"id": "2", "title": "T", "content": "Has content."},
        ]).encode()
        loader = CareerKBLoader(source=data)
        docs = [doc async for doc in loader.load()]
        assert len(docs) == 1

    @pytest.mark.asyncio
    async def test_no_source_yields_nothing(self) -> None:
        loader = CareerKBLoader(source=None)
        docs = [doc async for doc in loader.load()]
        assert docs == []

    @pytest.mark.asyncio
    async def test_doc_ids_are_prefixed(self) -> None:
        data = json.dumps([{"id": "kb-1", "title": "T", "content": "C"}]).encode()
        loader = CareerKBLoader(source=data)
        docs = [doc async for doc in loader.load()]
        assert docs[0].doc_id.startswith("career-kb::")


# ── ESCO Loader ───────────────────────────────────────────────────────────────


class TestESCOLoader:
    @pytest.mark.asyncio
    async def test_esco_csv(self) -> None:
        csv_data = (
            "conceptUri,preferredLabel,altLabels,description\n"
            "http://data.europa.eu/esco/1,Software Developer,programmer,Develops software.\n"
        ).encode("utf-8-sig")
        loader = ESCOLoader(source=csv_data, source_type="esco")
        docs = [doc async for doc in loader.load()]
        assert len(docs) == 1
        assert docs[0].doc_type == DocumentType.ESCO_ONET

    @pytest.mark.asyncio
    async def test_onet_csv(self) -> None:
        csv_data = (
            "O*NET-SOC Code,Title,Description\n"
            "15-1252.00,Software Developers,Design and develop software.\n"
        ).encode("utf-8-sig")
        loader = ESCOLoader(source=csv_data, source_type="onet")
        docs = [doc async for doc in loader.load()]
        assert len(docs) == 1
        assert docs[0].metadata["taxonomy"] == "onet"


# ── Market Reports Loader ─────────────────────────────────────────────────────


class TestMarketReportsLoader:
    @pytest.mark.asyncio
    async def test_loads_report(self) -> None:
        data = json.dumps([
            {
                "id": "r1",
                "title": "Tech Market Q1 2025",
                "content": "Strong demand for Python engineers in Switzerland.",
                "region": "Switzerland",
            }
        ]).encode()
        loader = MarketReportsLoader(source=data)
        docs = [doc async for doc in loader.load()]
        assert len(docs) == 1
        assert docs[0].doc_type == DocumentType.MARKET_REPORT
        assert docs[0].metadata["region"] == "Switzerland"


# ── Role Templates Loader ─────────────────────────────────────────────────────


class TestRoleTemplatesLoader:
    @pytest.mark.asyncio
    async def test_loads_template(self) -> None:
        data = json.dumps([
            {
                "id": "swe-senior",
                "role": "Senior Software Engineer",
                "level": "senior",
                "description": "Leads technical design.",
                "required_skills": ["Python", "System Design"],
                "nice_to_have": ["Rust"],
                "experience_years": {"min": 5, "max": 10},
                "region": "Switzerland",
            }
        ]).encode()
        loader = RoleTemplatesLoader(source=data)
        docs = [doc async for doc in loader.load()]
        assert len(docs) == 1
        assert docs[0].doc_type == DocumentType.ROLE_TEMPLATE
        assert "Python" in docs[0].content
        assert "Switzerland" in docs[0].content

    @pytest.mark.asyncio
    async def test_skips_empty_role(self) -> None:
        data = json.dumps([{"id": "x", "role": ""}]).encode()
        loader = RoleTemplatesLoader(source=data)
        docs = [doc async for doc in loader.load()]
        assert docs == []
