"""Portfolio Build Plan — schemas for AI-guided artefact sequencing (§14.7)."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ArtefactSuggestion(BaseModel):
    id: str
    title: str
    artefact_type: str  # project | case_study | demo | writeup | contribution
    summary: str
    skills_demonstrated: list[str] = Field(default_factory=list)
    closes_gap: str = ""
    effort: str = "medium"  # small | medium | large
    priority: int = 0
    why: str = ""
    starter_steps: list[str] = Field(default_factory=list)

    @classmethod
    def from_doc(cls, doc: dict[str, Any]) -> "ArtefactSuggestion":
        return cls(
            id=str(doc.get("id", "")),
            title=str(doc.get("title", "")),
            artefact_type=str(doc.get("artefact_type", "project")),
            summary=str(doc.get("summary", "")),
            skills_demonstrated=list(doc.get("skills_demonstrated", []) or []),
            closes_gap=str(doc.get("closes_gap", "")),
            effort=str(doc.get("effort", "medium")),
            priority=int(doc.get("priority", 0) or 0),
            why=str(doc.get("why", "")),
            starter_steps=list(doc.get("starter_steps", []) or []),
        )


class PlanTrackResult(BaseModel):
    """Outcome of turning a suggestion into tracked work."""

    suggestion_id: str
    portfolio_item_id: str
    schedule_block_id: str
    message: str


class PortfolioPlan(BaseModel):
    has_data: bool = True
    based_on: str = ""
    suggestions: list[ArtefactSuggestion] = Field(default_factory=list)
    generated_at: datetime | None = None

    @classmethod
    def empty(cls) -> "PortfolioPlan":
        return cls(has_data=False, based_on="", suggestions=[])

    @classmethod
    def from_doc(cls, doc: dict[str, Any]) -> "PortfolioPlan":
        suggestions = [
            ArtefactSuggestion.from_doc(s)
            for s in (doc.get("suggestions") or [])
            if isinstance(s, dict)
        ]
        return cls(
            has_data=bool(suggestions),
            based_on=doc.get("based_on", ""),
            suggestions=sorted(suggestions, key=lambda s: s.priority),
            generated_at=doc.get("generated_at"),
        )
