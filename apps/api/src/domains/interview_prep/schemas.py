"""Interview Prep domain — Pydantic schemas."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

InterviewType = Literal[
    "behavioral", "technical", "system_design", "role_specific", "mixed"
]

_VALID_TYPES = ("behavioral", "technical", "system_design", "role_specific", "mixed")


class QuestionRequest(BaseModel):
    role: str = Field(min_length=1, max_length=160)
    company: str = Field(default="", max_length=160)
    interview_type: InterviewType = "mixed"
    job_description: str = Field(default="", max_length=12000)
    count: int = Field(default=6, ge=1, le=15)


class InterviewQuestion(BaseModel):
    question: str
    category: str = ""
    assesses: str = ""
    answer_tips: list[str] = Field(default_factory=list)


class QuestionSet(BaseModel):
    role: str
    interview_type: InterviewType
    questions: list[InterviewQuestion]


class TurnMessage(BaseModel):
    role: Literal["candidate", "interviewer"]
    content: str = Field(max_length=4000)


class TurnInput(BaseModel):
    role: str = Field(min_length=1, max_length=160)
    company: str = Field(default="", max_length=160)
    interview_type: InterviewType = "mixed"
    current_question: str = Field(default="", max_length=2000)
    history: list[TurnMessage] = Field(default_factory=list, max_length=40)
    answer: str = Field(min_length=1, max_length=6000)


class TurnReply(BaseModel):
    feedback: str          # critique of the candidate's last answer
    score: int             # 0-100 for that answer
    strengths: list[str] = Field(default_factory=list)
    improvements: list[str] = Field(default_factory=list)
    next_question: str     # interviewer's next question
    done: bool = False


class SessionCreate(BaseModel):
    role: str = Field(min_length=1, max_length=160)
    company: str = Field(default="", max_length=160)
    interview_type: InterviewType = "mixed"
    overall_score: int = Field(default=0, ge=0, le=100)
    transcript: list[TurnMessage] = Field(default_factory=list, max_length=80)
    notes: str = Field(default="", max_length=2000)


class SessionOut(BaseModel):
    id: str
    role: str
    company: str
    interview_type: InterviewType
    overall_score: int
    transcript: list[TurnMessage]
    notes: str
    created_at: datetime | None = None

    @classmethod
    def from_doc(cls, doc: dict[str, Any]) -> "SessionOut":
        itype = doc.get("interview_type", "mixed")
        raw = doc.get("transcript") or []
        transcript = [
            TurnMessage(
                role="interviewer" if m.get("role") == "interviewer" else "candidate",
                content=str(m.get("content", "")),
            )
            for m in raw
            if isinstance(m, dict)
        ]
        return cls(
            id=doc.get("id", ""),
            role=doc.get("role", ""),
            company=doc.get("company", ""),
            interview_type=itype if itype in _VALID_TYPES else "mixed",
            overall_score=int(doc.get("overall_score", 0) or 0),
            transcript=transcript,
            notes=doc.get("notes", ""),
            created_at=doc.get("created_at"),
        )
