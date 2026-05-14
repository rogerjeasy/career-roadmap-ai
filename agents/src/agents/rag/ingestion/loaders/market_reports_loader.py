"""Loader for job market reports and salary data.

Accepts a JSON array (or single object) of market report records.
Suitable for hand-curated exports from LinkedIn Job Market Reports,
Glassdoor Economy Research, levels.fyi, and Swiss market surveys.

Record schema:
{
  "id": "report-2024-q4",
  "title": "LinkedIn Job Market Report Q4 2024",
  "content": "Full text content...",
  "region": "Switzerland",
  "published_at": "2024-10-01",
  "source_url": "https://...",
  "tags": ["salary", "tech", "switzerland"]
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


class MarketReportsLoader(BaseLoader):
    """Loads job-market and salary report documents."""

    def __init__(self, *, source: Path | bytes | None = None) -> None:
        self._source = source

    async def load(self) -> AsyncGenerator[Document, None]:
        if self._source is None:
            logger.warning("rag.market_reports_loader.no_source")
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
                doc_id=f"market-report::{doc_id}",
                doc_type=DocumentType.MARKET_REPORT,
                title=str(item.get("title", "Market Report")),
                content=content,
                source_url=item.get("source_url"),
                metadata={
                    "region": item.get("region", ""),
                    "published_at": item.get("published_at", ""),
                    "tags": item.get("tags", []),
                },
            )

        logger.info("rag.market_reports_loader.done", count=count)
