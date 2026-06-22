"""Job Applications domain — Pydantic schemas.

The pipeline is modelled as six ordered stages:

    saved → applied → screening → interview → offer → closed

A *closed* application keeps its terminal ``outcome`` (accepted / rejected /
withdrawn) so funnel analytics stay meaningful even though the board collapses
them into a single column. Documents written under the legacy taxonomy
(``interviewing`` / ``accepted`` / ``rejected`` / ``withdrawn`` as a status) are
normalised at read-time via :func:`normalize_status` — Firestore has no
migrations, so old records are mapped on the fly.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

ApplicationStatus = Literal[
    "saved", "applied", "screening", "interview", "offer", "closed"
]
ApplicationOutcome = Literal["accepted", "rejected", "withdrawn"]

STAGES: tuple[ApplicationStatus, ...] = (
    "saved", "applied", "screening", "interview", "offer", "closed"
)
OUTCOMES: tuple[ApplicationOutcome, ...] = ("accepted", "rejected", "withdrawn")

# Stages that mean the search for this role is over.
TERMINAL: frozenset[str] = frozenset({"closed"})

# Legacy status value → (new status, derived outcome or None).
_LEGACY: dict[str, tuple[ApplicationStatus, ApplicationOutcome | None]] = {
    "interviewing": ("interview", None),
    "accepted": ("closed", "accepted"),
    "rejected": ("closed", "rejected"),
    "withdrawn": ("closed", "withdrawn"),
}


def normalize_status(
    raw_status: Any, raw_outcome: Any = None
) -> tuple[ApplicationStatus, ApplicationOutcome | None]:
    """Map any stored status (current or legacy) to the canonical (status, outcome)."""
    status = str(raw_status or "saved")
    outcome: ApplicationOutcome | None = (
        raw_outcome if raw_outcome in OUTCOMES else None
    )
    if status in _LEGACY:
        mapped, legacy_outcome = _LEGACY[status]
        return mapped, outcome or legacy_outcome
    if status not in STAGES:
        return "saved", outcome
    return status, outcome  # type: ignore[return-value]


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
    outcome: ApplicationOutcome | None = None
    notes: str | None = Field(default=None, max_length=4000)

    def to_patch(self) -> dict[str, Any]:
        return self.model_dump(exclude_none=True)


class BulletChange(BaseModel):
    """A single before/after rewrite produced by the tailoring pass (diff view)."""

    before: str = ""
    after: str = ""

    @classmethod
    def from_doc(cls, doc: dict[str, Any] | None) -> "BulletChange | None":
        if not isinstance(doc, dict):
            return None
        return cls(before=doc.get("before", ""), after=doc.get("after", ""))


class TailoredCv(BaseModel):
    summary: str = ""
    bullets: list[str] = Field(default_factory=list)
    changes: list[BulletChange] = Field(default_factory=list)
    matched_keywords: list[str] = Field(default_factory=list)
    missing_keywords: list[str] = Field(default_factory=list)
    fit_score: int = 0
    advice: str = ""
    generated_at: datetime | None = None

    @classmethod
    def from_doc(cls, doc: dict[str, Any] | None) -> "TailoredCv | None":
        if not doc:
            return None
        changes = [
            c for c in (BulletChange.from_doc(x) for x in (doc.get("changes") or [])) if c
        ]
        return cls(
            summary=doc.get("summary", ""),
            bullets=list(doc.get("bullets", []) or []),
            changes=changes,
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


class StatusEvent(BaseModel):
    """One entry in an application's status history (newest appended last)."""

    status: ApplicationStatus
    outcome: ApplicationOutcome | None = None
    note: str = ""
    at: datetime | None = None

    @classmethod
    def from_doc(cls, doc: dict[str, Any]) -> "StatusEvent":
        status, outcome = normalize_status(doc.get("status"), doc.get("outcome"))
        return cls(status=status, outcome=outcome, note=doc.get("note", ""), at=doc.get("at"))


class Reminder(BaseModel):
    id: str
    title: str
    due_at: datetime
    done: bool = False
    created_at: datetime | None = None

    @classmethod
    def from_doc(cls, doc: dict[str, Any]) -> "Reminder | None":
        if not isinstance(doc, dict) or not doc.get("id") or not doc.get("due_at"):
            return None
        return cls(
            id=str(doc["id"]),
            title=doc.get("title", ""),
            due_at=doc["due_at"],
            done=bool(doc.get("done", False)),
            created_at=doc.get("created_at"),
        )


class ReminderCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    due_at: datetime


class StageNoteUpdate(BaseModel):
    note: str = Field(default="", max_length=4000)


class ApplicationOut(BaseModel):
    id: str
    company: str
    role: str
    job_url: str
    job_description: str
    location: str
    salary: str
    status: ApplicationStatus
    outcome: ApplicationOutcome | None = None
    notes: str
    stage_notes: dict[str, str] = Field(default_factory=dict)
    timeline: list[StatusEvent] = Field(default_factory=list)
    reminders: list[Reminder] = Field(default_factory=list)
    tailored_cv: TailoredCv | None = None
    cover_letter: CoverLetter | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @classmethod
    def from_doc(cls, doc: dict[str, Any]) -> "ApplicationOut":
        status, outcome = normalize_status(doc.get("status"), doc.get("outcome"))
        stage_notes_raw = doc.get("stage_notes") or {}
        stage_notes = {
            str(k): str(v)
            for k, v in stage_notes_raw.items()
            if isinstance(stage_notes_raw, dict)
        }
        timeline = [StatusEvent.from_doc(e) for e in (doc.get("timeline") or []) if isinstance(e, dict)]
        reminders = [
            r for r in (Reminder.from_doc(x) for x in (doc.get("reminders") or [])) if r
        ]
        reminders.sort(key=lambda r: r.due_at)
        return cls(
            id=doc.get("id", ""),
            company=doc.get("company", ""),
            role=doc.get("role", ""),
            job_url=doc.get("job_url", ""),
            job_description=doc.get("job_description", ""),
            location=doc.get("location", ""),
            salary=doc.get("salary", ""),
            status=status,
            outcome=outcome,
            notes=doc.get("notes", ""),
            stage_notes=stage_notes,
            timeline=timeline,
            reminders=reminders,
            tailored_cv=TailoredCv.from_doc(doc.get("tailored_cv")),
            cover_letter=CoverLetter.from_doc(doc.get("cover_letter")),
            created_at=doc.get("created_at"),
            updated_at=doc.get("updated_at"),
        )


class ApplicationSummary(BaseModel):
    total: int
    by_status: dict[str, int]
    active: int  # not in a terminal state
    due_reminders: int = 0  # open reminders due now or overdue
