"""Loader for Swiss and EU job-market documents.

Same JSON schema as MarketReportsLoader but tags documents as
``SWISS_EU_MARKET`` so they land in the dedicated Pinecone namespace
and are prioritised for Swiss/EU-located users.

Record schema:
{
  "id": "zurich-tech-2024",
  "title": "Zurich Tech Ecosystem Overview 2024",
  "content": "...",
  "region": "Switzerland",
  "sub_region": "Zurich",
  "published_at": "2024-11-01",
  "source_url": "https://...",
  "tags": ["zurich", "tech", "switzerland", "salary"]
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


class SwissEUMarketLoader(BaseLoader):
    """Loads Swiss and EU market intelligence documents."""

    def __init__(self, *, source: Path | bytes | None = None) -> None:
        self._source = source

    async def load(self) -> AsyncGenerator[Document, None]:
        if self._source is None:
            logger.warning("rag.swiss_eu_market_loader.no_source")
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
        for item in raw:
            content = str(item.get("content", "")).strip()
            if not content:
                continue
            doc_id = str(item.get("id") or uuid.uuid4().hex)
            count += 1
            yield Document(
                doc_id=f"swiss-eu-market::{doc_id}",
                doc_type=DocumentType.SWISS_EU_MARKET,
                title=str(item.get("title", "Swiss/EU Market Report")),
                content=content,
                source_url=item.get("source_url"),
                metadata={
                    "region": item.get("region", ""),
                    "sub_region": item.get("sub_region", ""),
                    "published_at": item.get("published_at", ""),
                    "tags": item.get("tags", []),
                },
            )

        logger.info("rag.swiss_eu_market_loader.done", count=count)
