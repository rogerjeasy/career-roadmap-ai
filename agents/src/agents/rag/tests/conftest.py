"""Shared fixtures for RAG pipeline tests."""
from __future__ import annotations

import pytest

from agents.rag.models import Chunk, Document, DocumentType, EmbeddedChunk, SparseVector


@pytest.fixture
def sample_document() -> Document:
    return Document(
        doc_id="test-doc-001",
        doc_type=DocumentType.CAREER_KB,
        title="How to Get a Senior Engineering Role",
        content=(
            "To become a senior engineer you need deep expertise in your domain.\n\n"
            "System design skills are essential. You should be able to design "
            "scalable distributed systems.\n\n"
            "Leadership and mentoring junior engineers is also expected at this level."
        ),
        source_url="https://example.com/senior-eng",
        metadata={"tags": ["engineering", "career"], "category": "career_development"},
    )


@pytest.fixture
def sample_chunk(sample_document: Document) -> Chunk:
    return Chunk(
        chunk_id="test-doc-001::abc123",
        doc_id="test-doc-001",
        doc_type=DocumentType.CAREER_KB,
        content="To become a senior engineer you need deep expertise in your domain.",
        char_start=0,
        char_end=65,
        metadata={"title": "How to Get a Senior Engineering Role", "source_url": ""},
    )


@pytest.fixture
def sample_sparse_vector() -> SparseVector:
    return SparseVector(indices=[1, 42, 137, 500], values=[0.8, 0.6, 0.4, 0.2])


@pytest.fixture
def sample_embedded_chunk(sample_chunk: Chunk) -> EmbeddedChunk:
    return EmbeddedChunk(
        chunk_id=sample_chunk.chunk_id,
        doc_id=sample_chunk.doc_id,
        doc_type=sample_chunk.doc_type,
        content=sample_chunk.content,
        embedding=[0.1] * 3072,
        metadata=sample_chunk.metadata,
    )


@pytest.fixture
def sample_hybrid_embedded_chunk(
    sample_chunk: Chunk, sample_sparse_vector: SparseVector
) -> EmbeddedChunk:
    return EmbeddedChunk(
        chunk_id=sample_chunk.chunk_id,
        doc_id=sample_chunk.doc_id,
        doc_type=sample_chunk.doc_type,
        content=sample_chunk.content,
        embedding=[0.1] * 3072,
        sparse_embedding=sample_sparse_vector,
        metadata=sample_chunk.metadata,
    )
