"""Loader for role requirement templates.

Templates describe typical requirements for a specific job title:
skills, experience, certifications, and Swiss/EU-specific considerations.
Used by GapAgent and RoadmapAgent to ground their gap analysis in
verified role expectations rather than LLM priors.

Template schema:
{
  "id": "swe-senior",
  "role": "Senior Software Engineer",
  "level": "senior",
  "description": "...",
  "required_skills": ["Python", "System Design", "AWS"],
  "nice_to_have": ["Rust", "Kubernetes"],
  "experience_years": {"min": 5, "max": 10},
  "certifications": [],
  "region": "Switzerland",
  "industries": ["fintech", "insurtech", "startup"]
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


class RoleTemplatesLoader(BaseLoader):
    """Loads role requirement templates from a JSON file."""

    def __init__(self, *, source: Path | bytes | None = None) -> None:
        self._source = source

    async def load(self) -> AsyncGenerator[Document, None]:
        if self._source is None:
            logger.warning("rag.role_templates_loader.no_source")
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
            role = str(item.get("role", "")).strip()
            if not role:
                continue

            required = item.get("required_skills", [])
            nice_to_have = item.get("nice_to_have", [])
            exp = item.get("experience_years") or {}
            exp_str = (
                f"{exp.get('min', 0)}–{exp.get('max', 'N/A')} years"
                if exp
                else ""
            )
            content = (
                f"Role: {role}\n"
                f"Level: {item.get('level', '')}\n\n"
                f"{item.get('description', '')}\n\n"
                f"Required skills: {', '.join(required)}\n"
                f"Nice to have: {', '.join(nice_to_have)}\n"
                f"Experience: {exp_str}\n"
                f"Certifications: {', '.join(item.get('certifications', []))}\n"
                f"Region: {item.get('region', '')}\n"
                f"Industries: {', '.join(item.get('industries', []))}"
            ).strip()

            doc_id = str(item.get("id") or uuid.uuid4().hex)
            count += 1
            yield Document(
                doc_id=f"role-template::{doc_id}",
                doc_type=DocumentType.ROLE_TEMPLATE,
                title=f"{role} — Requirements",
                content=content,
                metadata={
                    "role": role,
                    "level": item.get("level", ""),
                    "region": item.get("region", ""),
                    "required_skills": required,
                },
            )

        logger.info("rag.role_templates_loader.done", count=count)
