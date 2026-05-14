"""Loader for Career Knowledge Base articles.

Reads a JSON file (array or single object) where each record has:
  id          — unique string identifier
  title       — article title
  content     — full article text (required)
  source_url  — canonical URL (optional)
  language    — ISO 639-1 code, default "en"
  tags        — list of keyword strings
  category    — e.g. "career_development", "interview_prep"

Example record:
{
  "id": "kb-001",
  "title": "How to negotiate a salary offer",
  "content": "Salary negotiation is a critical skill...",
  "source_url": "https://example.com/salary",
  "tags": ["negotiation", "salary"],
  "category": "career_development"
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


class CareerKBLoader(BaseLoader):
    """Loads career KB articles from a JSON file or raw bytes."""

    def __init__(self, *, source: Path | bytes | None = None) -> None:
        self._source = source

    async def load(self) -> AsyncGenerator[Document, None]:
        if self._source is None:
            logger.warning("rag.career_kb_loader.no_source")
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
                doc_id=f"career-kb::{doc_id}",
                doc_type=DocumentType.CAREER_KB,
                title=str(item.get("title", "Untitled")),
                content=content,
                source_url=item.get("source_url"),
                language=str(item.get("language", "en")),
                metadata={
                    "tags": item.get("tags", []),
                    "category": item.get("category", ""),
                },
            )

        logger.info("rag.career_kb_loader.done", count=count)
