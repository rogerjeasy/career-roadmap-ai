"""Job Applications domain — Pydantic schemas."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

ApplicationStatus = Literal[
    "saved", "applied", "interviewing", "offer", "rejected", "accepted", "withdrawn"
]

_VALID_STATUS = (
    "saved", "applied", "interviewing", "offer", "rejected", "accepted", "withdrawn"
)


class ApplicationCreate(BaseModel):
    company: str = Field(min_length=1, max_length=200)
    role: str = Field(min_length=1, max_length=200)
    job_url: str = Field(default="", max_length=1000)
    job_description: str = Field(default="", max_length=20000)
    location: str = Field(default="", max_length=160)
    salary: str = Field(default="", max_length=120)
    status: ApplicationStatus = "saved"
    notes: str = Field(default="", max_length=4000)


class ApplicationUpdate(BaseModel):
    company: str | None = Field(default=None, min_length=1, max_length=200)
    role: str | None = Field(default=None, min_length=1, max_length=200)
    job_url: str | None = Field(default=None, max_length=1000)
    job_description: str | None = Field(default=None, max_length=20000)
    location: str | None = Field(default=None, max_length=160)
    salary: str | None = Field(default=None, max_length=120)
    status: ApplicationStatus | None = None
    notes: str | None = Field(default=None, max_length=4000)

    def to_patch(self) -> dict[str, Any]:
        return self.model_dump(exclude_none=True)


class TailoredCv(BaseModel):
    summary: str = ""
    bullets: list[str] = Field(default_factory=list)
    matched_keywords: list[str] = Field(default_factory=list)
    missing_keywords: list[str] = Field(default_factory=list)
    fit_score: int = 0
    advice: str = ""
    generated_at: datetime | None = None

    @classmethod
    def from_doc(cls, doc: dict[str, Any] | None) -> "TailoredCv | None":
        if not doc:
            return None
        return cls(
            summary=doc.get("summary", ""),
            bullets=list(doc.get("bullets", []) or []),
            matched_keywords=list(doc.get("matched_keywords", []) or []),
            missing_keywords=list(doc.get("missing_keywords", []) or []),
            fit_score=int(doc.get("fit_score", 0) or 0),
            advice=doc.get("advice", ""),
            generated_at=doc.get("generated_at"),
        )


class CoverLetter(BaseModel):
    content: str = ""
    generated_at: datetime | None = None

    @classmethod
    def from_doc(cls, doc: dict[str, Any] | None) -> "CoverLetter | None":
        if not doc:
            return None
        return cls(content=doc.get("content", ""), generated_at=doc.get("generated_at"))


class ApplicationOut(BaseModel):
    id: str
    company: str
    role: str
    job_url: str
    job_description: str
    location: str
    salary: str
    status: ApplicationStatus
    notes: str
    tailored_cv: TailoredCv | None = None
    cover_letter: CoverLetter | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @classmethod
    def from_doc(cls, doc: dict[str, Any]) -> "ApplicationOut":
        status = doc.get("status", "saved")
        return cls(
            id=doc.get("id", ""),
            company=doc.get("company", ""),
            role=doc.get("role", ""),
            job_url=doc.get("job_url", ""),
            job_description=doc.get("job_description", ""),
            location=doc.get("location", ""),
            salary=doc.get("salary", ""),
            status=status if status in _VALID_STATUS else "saved",
            notes=doc.get("notes", ""),
            tailored_cv=TailoredCv.from_doc(doc.get("tailored_cv")),
            cover_letter=CoverLetter.from_doc(doc.get("cover_letter")),
            created_at=doc.get("created_at"),
            updated_at=doc.get("updated_at"),
        )


class ApplicationSummary(BaseModel):
    total: int
    by_status: dict[str, int]
    active: int  # not in a terminal state
