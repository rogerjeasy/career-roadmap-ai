"""Localisation domain — Pydantic schemas.

A ``LocalisationReport`` is country-aware career intelligence for a (role,
country) pair: visa pathways, local salary norms in local currency, language
requirements, hiring-culture notes, networking channels, and relocation steps.

Per the platform's responsible-AI rules every report carries an explicit
``confidence`` score and an ``assumptions`` list so uncertain, model-derived
guidance is never presented as fact.
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

VisaDifficulty = Literal["easy", "moderate", "hard", "unknown"]


def report_slug(country: str, role: str) -> str:
    """Deterministic Firestore doc id for a (country, role) report, user-scoped."""
    base = f"{country.strip().lower()}|{role.strip().lower()}"
    slug = re.sub(r"[^a-z0-9]+", "-", base).strip("-")
    return slug[:200] or "report"


class VisaPathway(BaseModel):
    name: str
    summary: str
    difficulty: VisaDifficulty = "unknown"


class SalaryBand(BaseModel):
    currency: str = ""
    low: int = 0
    median: int = 0
    high: int = 0
    note: str = ""


class LocalisationReport(BaseModel):
    """Full country-aware intelligence for one (role, country)."""

    id: str = ""
    country: str
    role: str
    summary: str = ""
    salary: SalaryBand = Field(default_factory=SalaryBand)
    cost_of_living: str = ""
    visa_pathways: list[VisaPathway] = Field(default_factory=list)
    language_requirements: str = ""
    hiring_culture: list[str] = Field(default_factory=list)
    networking_channels: list[str] = Field(default_factory=list)
    relocation_steps: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    assumptions: list[str] = Field(default_factory=list)
    generated_at: datetime | None = None

    @classmethod
    def from_doc(cls, doc: dict[str, Any]) -> "LocalisationReport":
        payload = {k: v for k, v in doc.items() if k in cls.model_fields}
        payload["id"] = doc.get("id", "")
        payload["generated_at"] = doc.get("generated_at") or doc.get("created_at")
        return cls.model_validate(payload)


class LocalisationReportSummary(BaseModel):
    """Compact entry for the 'saved reports' list."""

    id: str
    country: str
    role: str
    confidence: float
    generated_at: datetime | None = None

    @classmethod
    def from_doc(cls, doc: dict[str, Any]) -> "LocalisationReportSummary":
        return cls(
            id=doc.get("id", ""),
            country=doc.get("country", ""),
            role=doc.get("role", ""),
            confidence=float(doc.get("confidence", 0.5) or 0.5),
            generated_at=doc.get("generated_at") or doc.get("created_at"),
        )
