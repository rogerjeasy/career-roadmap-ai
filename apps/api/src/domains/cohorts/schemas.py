"""Accountability Cohorts domain — Pydantic schemas."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

CohortStatus = Literal["open", "full", "archived"]
CadenceType = Literal["weekly", "biweekly"]


class CohortMember(BaseModel):
    uid: str
    name: str
    joined_at: datetime | None = None


class CohortCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    focus: str = Field(min_length=1, max_length=160)
    description: str = Field(default="", max_length=1500)
    capacity: int = Field(default=6, ge=2, le=20)
    cadence: CadenceType = "weekly"


class CheckinCreate(BaseModel):
    done: str = Field(min_length=1, max_length=1500)
    next: str = Field(default="", max_length=1500)
    blockers: str = Field(default="", max_length=1500)


class CheckinOut(BaseModel):
    id: str
    cohort_id: str
    user_id: str
    user_name: str
    done: str
    next: str
    blockers: str
    created_at: datetime | None = None

    @classmethod
    def from_doc(cls, doc: dict[str, Any]) -> "CheckinOut":
        return cls(
            id=doc.get("id", ""),
            cohort_id=doc.get("cohort_id", ""),
            user_id=doc.get("user_id", ""),
            user_name=doc.get("user_name", "A member"),
            done=doc.get("done", ""),
            next=doc.get("next", ""),
            blockers=doc.get("blockers", ""),
            created_at=doc.get("created_at"),
        )


class CohortOut(BaseModel):
    id: str
    name: str
    focus: str
    description: str
    capacity: int
    cadence: CadenceType
    status: CohortStatus
    created_by: str
    members: list[CohortMember]
    member_count: int
    is_member: bool = False
    is_owner: bool = False
    # Only populated for the discover feed.
    match_score: int = 0
    match_reason: str = ""
    created_at: datetime | None = None

    @classmethod
    def from_doc(
        cls, doc: dict[str, Any], *, viewer_id: str | None = None
    ) -> "CohortOut":
        raw_members = doc.get("members") or []
        members = [
            CohortMember(
                uid=str(m.get("uid", "")),
                name=str(m.get("name", "A member")),
                joined_at=m.get("joined_at"),
            )
            for m in raw_members
            if isinstance(m, dict)
        ]
        member_ids = doc.get("member_ids") or [m.uid for m in members]
        status = doc.get("status", "open")
        return cls(
            id=doc.get("id", ""),
            name=doc.get("name", ""),
            focus=doc.get("focus", ""),
            description=doc.get("description", ""),
            capacity=int(doc.get("capacity", 6) or 6),
            cadence=doc.get("cadence", "weekly") if doc.get("cadence") in ("weekly", "biweekly") else "weekly",
            status=status if status in ("open", "full", "archived") else "open",
            created_by=doc.get("created_by", ""),
            members=members,
            member_count=len(member_ids),
            is_member=viewer_id in member_ids if viewer_id else False,
            is_owner=viewer_id == doc.get("created_by") if viewer_id else False,
            created_at=doc.get("created_at"),
        )


class CohortDashboard(BaseModel):
    """A member's view of one cohort: the cohort plus its recent check-ins."""

    cohort: CohortOut
    checkins: list[CheckinOut]
