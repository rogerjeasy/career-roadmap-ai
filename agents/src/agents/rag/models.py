"""Domain models for the L5 RAG pipeline.

Plain dataclasses — no I/O, no external library imports.
Ingestion, retrieval, and storage layers depend on these;
nothing imports them except the layers above.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class DocumentType(str, Enum):
    """Source category for a knowledge-base document."""

    CAREER_KB = "career_kb"
    ESCO_ONET = "esco_onet"
    MARKET_REPORT = "market_report"
    ROLE_TEMPLATE = "role_template"
    SWISS_EU_MARKET = "swiss_eu_market"
    GLOBAL_MARKET = "global_market"
    USER_CV = "user_cv"


class KnowledgeNamespace(str, Enum):
    """Pinecone namespace per document category."""

    CAREER_KB = "career-kb"
    ESCO_ONET = "taxonomy"
    MARKET_REPORTS = "market-reports"
    ROLE_TEMPLATES = "role-templates"
    SWISS_EU_MARKET = "swiss-eu-market"
    GLOBAL_MARKET = "global-market"


NAMESPACE_FOR_DOC_TYPE: dict[DocumentType, KnowledgeNamespace] = {
    DocumentType.CAREER_KB: KnowledgeNamespace.CAREER_KB,
    DocumentType.ESCO_ONET: KnowledgeNamespace.ESCO_ONET,
    DocumentType.MARKET_REPORT: KnowledgeNamespace.MARKET_REPORTS,
    DocumentType.ROLE_TEMPLATE: KnowledgeNamespace.ROLE_TEMPLATES,
    DocumentType.SWISS_EU_MARKET: KnowledgeNamespace.SWISS_EU_MARKET,
    DocumentType.GLOBAL_MARKET: KnowledgeNamespace.GLOBAL_MARKET,
    DocumentType.USER_CV: KnowledgeNamespace.CAREER_KB,
}


# ── Global market document metadata convention ────────────────────────────────
# Every GLOBAL_MARKET document MUST include these metadata fields.
# Used by the ContextAssembler for region-aware namespace routing and by
# retrieval filters to narrow results to the user's location.
#
# continent   : "Asia" | "Americas" | "Africa" | "Oceania" | "Middle East"
# country     : ISO 3166-1 alpha-2 code (e.g. "SG", "BR", "NG", "AU")
# market_tier : "mature" | "emerging" | "frontier"
# industries  : list of industries covered (never tech-only — include all sectors)
#               e.g. ["technology", "finance", "healthcare", "education",
#                     "manufacturing", "retail", "agriculture", "public_sector"]
# job_families: broad job families covered
#               e.g. ["engineering", "finance", "operations", "sales",
#                     "healthcare", "education", "legal", "creative", "trades"]
#
# Example:
# {
#   "continent": "Asia",
#   "country": "SG",
#   "region": "Southeast Asia",
#   "sub_region": "Greater Singapore",
#   "market_tier": "mature",
#   "industries": ["technology", "finance", "logistics", "healthcare"],
#   "job_families": ["engineering", "finance", "operations", "healthcare"],
#   "published_at": "2024-06-01",
#   "source_url": "https://mom.gov.sg/...",
#   "tags": ["singapore", "salary", "2024"]
# }
GLOBAL_MARKET_METADATA_FIELDS = frozenset({
    "continent", "country", "region", "sub_region", "market_tier",
    "industries", "job_families", "published_at", "source_url", "tags",
})


@dataclass(frozen=True, slots=True)
class Document:
    """A single knowledge-base document before chunking."""

    doc_id: str
    doc_type: DocumentType
    title: str
    content: str
    source_url: str | None = None
    language: str = "en"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Chunk:
    """A text passage produced by splitting a Document."""

    chunk_id: str
    doc_id: str
    doc_type: DocumentType
    content: str
    char_start: int
    char_end: int
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class SparseVector:
    """BM25 sparse representation of a text chunk."""

    indices: list[int]
    values: list[float]


@dataclass(frozen=True, slots=True)
class EmbeddedChunk:
    """A Chunk paired with its dense (and optional sparse) vector representation."""

    chunk_id: str
    doc_id: str
    doc_type: DocumentType
    content: str
    embedding: list[float]
    sparse_embedding: SparseVector | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class IndexedChunk:
    """An EmbeddedChunk confirmed as upserted to Pinecone."""

    chunk_id: str
    doc_id: str
    doc_type: DocumentType
    namespace: str
    vector_id: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class RetrievedChunk:
    """A chunk returned by a Pinecone similarity query."""

    chunk_id: str
    doc_id: str
    doc_type: str
    content: str
    score: float
    namespace: str
    # Citation fields — sourced from Pinecone metadata at retrieval time.
    title: str = ""
    source_url: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
