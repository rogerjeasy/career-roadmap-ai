"""Loader for ESCO / O*NET occupation taxonomy data.

ESCO (European Skills, Competences, Qualifications and Occupations):
  Download CSV from https://esco.ec.europa.eu/en/use-esco/download
  Expected columns: conceptUri, preferredLabel, altLabels, description

O*NET (US occupational taxonomy):
  Download from https://www.onetcenter.org/database.html
  Expected columns: O*NET-SOC Code, Title, Description

Set ``source_type="esco"`` (default) or ``source_type="onet"`` to control
which column mapping is used.
"""
from __future__ import annotations

import csv
import io
import uuid
from collections.abc import AsyncGenerator
from pathlib import Path

from agents.core.logging import get_logger
from agents.rag.ingestion.loaders.base_loader import BaseLoader
from agents.rag.models import Document, DocumentType

logger = get_logger(__name__)


class ESCOLoader(BaseLoader):
    """Loads ESCO / O*NET occupation entries from a CSV file."""

    def __init__(
        self,
        *,
        source: Path | bytes | None = None,
        source_type: str = "esco",
    ) -> None:
        self._source = source
        self._source_type = source_type

    async def load(self) -> AsyncGenerator[Document, None]:
        if self._source is None:
            logger.warning("rag.esco_loader.no_source")
            return

        text = (
            self._source.read_text(encoding="utf-8-sig")
            if isinstance(self._source, Path)
            else self._source.decode("utf-8-sig")
        )
        reader = csv.DictReader(io.StringIO(text))
        count = 0
        for row in reader:
            doc = _parse_row(row, self._source_type)
            if doc is None:
                continue
            count += 1
            yield doc

        logger.info(
            "rag.esco_loader.done", count=count, source_type=self._source_type
        )


def _parse_row(row: dict[str, str], source_type: str) -> Document | None:
    if source_type == "esco":
        label = row.get("preferredLabel", "").strip()
        description = row.get("description", "").strip()
        alt_labels = row.get("altLabels", "").strip()
        uri = row.get("conceptUri", "").strip()
        if not label or not description:
            return None
        content = f"{label}\n\nAlternative names: {alt_labels}\n\n{description}"
        return Document(
            doc_id=f"esco::{uuid.uuid4().hex[:12]}",
            doc_type=DocumentType.ESCO_ONET,
            title=label,
            content=content,
            source_url=uri or None,
            metadata={"alt_labels": alt_labels, "taxonomy": "esco"},
        )

    # O*NET column mapping
    title = (row.get("Title") or row.get("Occupation", "")).strip()
    description = row.get("Description", "").strip()
    code = row.get("O*NET-SOC Code", "").strip()
    if not title or not description:
        return None
    return Document(
        doc_id=f"onet::{code or uuid.uuid4().hex[:12]}",
        doc_type=DocumentType.ESCO_ONET,
        title=title,
        content=f"{title}\n\n{description}",
        metadata={"code": code, "taxonomy": "onet"},
    )
