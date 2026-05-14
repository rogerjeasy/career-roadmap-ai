"""Loader for global job-market documents (Asia, LATAM, Africa, MENA, Oceania).

Covers ALL job families and industries — not just technology.  Every document
produced here represents real labour-market data for a specific country or
sub-region outside the US and the EU/Swiss coverage in ``swiss_eu_market``.

Required metadata fields (see ``models.GLOBAL_MARKET_METADATA_FIELDS``):
  continent   — "Asia" | "Americas" | "Africa" | "Oceania" | "Middle East"
  country     — ISO 3166-1 alpha-2 code, e.g. "SG", "BR", "NG", "AU"
  market_tier — "mature" | "emerging" | "frontier"
  industries  — list of industries the document covers (all sectors, not tech-only)
  job_families— list of broad job families the document covers

Optional but recommended:
  region      — e.g. "Southeast Asia", "Sub-Saharan Africa"
  sub_region  — e.g. "Greater Jakarta", "Lagos Metropolitan"
  published_at— ISO date string "YYYY-MM-DD"
  source_url  — canonical URL of the original data source
  tags        — free-form search tags

JSON record schema (array of objects):
{
  "id": "sg-mom-wages-2024",
  "title": "Singapore MOM Occupational Wages 2024",
  "content": "...",
  "continent": "Asia",
  "country": "SG",
  "region": "Southeast Asia",
  "sub_region": "Greater Singapore",
  "market_tier": "mature",
  "industries": ["technology", "finance", "logistics", "healthcare"],
  "job_families": ["engineering", "finance", "operations", "healthcare"],
  "published_at": "2024-06-01",
  "source_url": "https://stats.mom.gov.sg/...",
  "tags": ["singapore", "salary", "wages", "2024"]
}
"""
from __future__ import annotations

import json
import uuid
from collections.abc import AsyncGenerator
from pathlib import Path

from agents.core.logging import get_logger
from agents.rag.ingestion.loaders.base_loader import BaseLoader
from agents.rag.models import Document, DocumentType

logger = get_logger(__name__)

_REQUIRED_META = ("continent", "country", "market_tier")


class GlobalMarketLoader(BaseLoader):
    """Loads global job-market intelligence documents.

    Accepts the same source types as other loaders — a ``Path`` to a JSON file
    or raw ``bytes``.  Emits :class:`~agents.rag.models.DocumentType.GLOBAL_MARKET`
    documents so they are indexed into the dedicated ``global-market`` Pinecone
    namespace.

    Documents with missing ``content`` are skipped; documents with missing
    required metadata fields emit a warning but are still ingested (the missing
    fields default to empty strings so downstream filters degrade gracefully).
    """

    def __init__(self, *, source: Path | bytes | None = None) -> None:
        self._source = source

    async def load(self) -> AsyncGenerator[Document, None]:
        if self._source is None:
            logger.warning("rag.global_market_loader.no_source")
            return

        text = (
            self._source.read_text(encoding="utf-8")
            if isinstance(self._source, Path)
            else self._source.decode("utf-8")
        )
        raw: list[dict] = json.loads(text)
        if isinstance(raw, dict):
            raw = [raw]

        count = 0
        skipped = 0
        for item in raw:
            content = str(item.get("content", "")).strip()
            if not content:
                skipped += 1
                continue

            # Support both the legacy flat format ({"id": ..., "continent": ...})
            # and the current nested format ({"doc_id": ..., "metadata": {...}}).
            nested: dict = item.get("metadata") or {}
            doc_id = str(item.get("doc_id") or item.get("id") or uuid.uuid4().hex)

            def _field(key: str, default: object = "") -> object:
                return item.get(key) or nested.get(key) or default

            # Warn on missing required metadata but don't drop the document.
            missing = [f for f in _REQUIRED_META if not _field(f)]
            if missing:
                logger.warning(
                    "rag.global_market_loader.missing_metadata",
                    doc_id=doc_id,
                    missing=missing,
                )

            count += 1
            yield Document(
                doc_id=f"global-market::{doc_id}",
                doc_type=DocumentType.GLOBAL_MARKET,
                title=str(item.get("title", "Global Market Report")),
                content=content,
                source_url=_field("source_url") or None,
                metadata={
                    # Geography
                    "continent": _field("continent"),
                    "country": _field("country"),
                    "region": _field("region"),
                    "sub_region": _field("sub_region"),
                    # Classification
                    "market_tier": _field("market_tier"),
                    "industries": _field("industries", []),
                    "job_families": _field("job_families", []),
                    # Provenance
                    "published_at": _field("published_at"),
                    "tags": _field("tags", []),
                },
            )

        logger.info(
            "rag.global_market_loader.done",
            loaded=count,
            skipped=skipped,
        )
