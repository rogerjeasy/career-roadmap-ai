"""Negotiation & Offer Coach domain — Pydantic schemas."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

Competitiveness = Literal["below", "at", "above", "unknown"]


class OfferInput(BaseModel):
    role: str = Field(min_length=1, max_length=160)
    company: str = Field(default="", max_length=160)
    location: str = Field(default="", max_length=160)
    currency: str = Field(default="USD", max_length=8)
    base_salary: float = Field(default=0.0, ge=0)
    bonus: float = Field(default=0.0, ge=0)
    equity: str = Field(default="", max_length=300)
    other_benefits: str = Field(default="", max_length=1000)
    years_experience: int = Field(default=0, ge=0, le=70)
    competing_offer: str = Field(default="", max_length=500)
    notes: str = Field(default="", max_length=1500)


class OfferAnalysisOut(BaseModel):
    id: str
    offer: OfferInput
    assessment: str
    competitiveness: Competitiveness
    benchmark_low: float
    benchmark_high: float
    benchmark_currency: str
    counter_base: float
    counter_rationale: str
    talking_points: list[str]
    risks: list[str]
    assumptions: list[str]
    confidence: float
    created_at: datetime | None = None

    @classmethod
    def from_doc(cls, doc: dict[str, Any]) -> "OfferAnalysisOut":
        comp = doc.get("competitiveness", "unknown")
        offer_raw = doc.get("offer") or {}
        return cls(
            id=doc.get("id", ""),
            offer=OfferInput(**offer_raw) if isinstance(offer_raw, dict) else OfferInput(role=""),
            assessment=doc.get("assessment", ""),
            competitiveness=comp if comp in ("below", "at", "above", "unknown") else "unknown",
            benchmark_low=float(doc.get("benchmark_low", 0) or 0),
            benchmark_high=float(doc.get("benchmark_high", 0) or 0),
            benchmark_currency=doc.get("benchmark_currency", offer_raw.get("currency", "USD")),
            counter_base=float(doc.get("counter_base", 0) or 0),
            counter_rationale=doc.get("counter_rationale", ""),
            talking_points=list(doc.get("talking_points", []) or []),
            risks=list(doc.get("risks", []) or []),
            assumptions=list(doc.get("assumptions", []) or []),
            confidence=float(doc.get("confidence", 0) or 0),
            created_at=doc.get("created_at"),
        )


class RoleplayMessage(BaseModel):
    role: Literal["user", "recruiter"]
    content: str = Field(max_length=4000)


class RoleplayInput(BaseModel):
    offer: OfferInput
    history: list[RoleplayMessage] = Field(default_factory=list, max_length=40)
    message: str = Field(min_length=1, max_length=4000)


class RoleplayReply(BaseModel):
    reply: str       # the recruiter's in-character response
    coaching: str    # private feedback on the user's last move
    tip: str = ""    # one concrete suggestion for the next turn
