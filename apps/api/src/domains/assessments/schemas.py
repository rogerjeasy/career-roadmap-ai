"""Skill Assessment domain — Pydantic schemas.

The stored document keeps an ``answer_key`` (correct options + grading rubric)
that is **never** serialised back to the client — only :class:`QuizQuestion`
(prompt + options) is exposed while an assessment is in progress.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

AssessmentStatus = Literal["in_progress", "graded"]
QuestionKind = Literal["mcq", "short"]
SkillLevel = Literal["beginner", "intermediate", "advanced", "expert"]

_LEVELS = ("beginner", "intermediate", "advanced", "expert")

# Score (0–100) at or above which the assessment is considered passed and a
# verifiable credential is minted.
PASS_THRESHOLD = 70


def level_for_score(score: int) -> SkillLevel:
    if score >= 85:
        return "expert"
    if score >= 70:
        return "advanced"
    if score >= 45:
        return "intermediate"
    return "beginner"


class AssessmentStartInput(BaseModel):
    skill: str = Field(min_length=1, max_length=120)
    num_questions: int = Field(default=6, ge=3, le=12)


class QuizQuestion(BaseModel):
    """Client-facing question — deliberately carries no answer/rubric."""

    id: str
    kind: QuestionKind
    prompt: str
    options: list[str] = Field(default_factory=list)  # populated for mcq only

    @classmethod
    def from_doc(cls, doc: dict[str, Any]) -> "QuizQuestion":
        kind = doc.get("kind", "short")
        return cls(
            id=str(doc.get("id", "")),
            kind=kind if kind in ("mcq", "short") else "short",
            prompt=str(doc.get("prompt", "")),
            options=list(doc.get("options", []) or []),
        )


class AssessmentAnswer(BaseModel):
    question_id: str
    answer: str = Field(default="", max_length=4000)


class AssessmentSubmit(BaseModel):
    answers: list[AssessmentAnswer] = Field(default_factory=list, max_length=12)


class MeasuredGap(BaseModel):
    topic: str
    note: str = ""

    @classmethod
    def from_doc(cls, doc: dict[str, Any]) -> "MeasuredGap | None":
        if not isinstance(doc, dict) or not doc.get("topic"):
            return None
        return cls(topic=str(doc["topic"]), note=str(doc.get("note", "")))


class AssessmentOut(BaseModel):
    id: str
    skill: str
    status: AssessmentStatus
    num_questions: int
    questions: list[QuizQuestion] = Field(default_factory=list)
    score: int | None = None
    level: SkillLevel | None = None
    passed: bool = False
    summary: str = ""
    strengths: list[str] = Field(default_factory=list)
    gaps: list[MeasuredGap] = Field(default_factory=list)
    credential_id: str | None = None
    evidence_id: str | None = None
    created_at: datetime | None = None
    graded_at: datetime | None = None

    @classmethod
    def from_doc(cls, doc: dict[str, Any]) -> "AssessmentOut":
        status = doc.get("status", "in_progress")
        level = doc.get("level")
        questions = [QuizQuestion.from_doc(q) for q in (doc.get("questions") or []) if isinstance(q, dict)]
        gaps = [g for g in (MeasuredGap.from_doc(x) for x in (doc.get("gaps") or [])) if g]
        score = doc.get("score")
        return cls(
            id=doc.get("id", ""),
            skill=doc.get("skill", ""),
            status="graded" if status == "graded" else "in_progress",
            num_questions=int(doc.get("num_questions", len(questions)) or len(questions)),
            questions=questions,
            score=int(score) if isinstance(score, (int, float)) else None,
            level=level if level in _LEVELS else None,
            passed=bool(doc.get("passed", False)),
            summary=doc.get("summary", ""),
            strengths=list(doc.get("strengths", []) or []),
            gaps=gaps,
            credential_id=doc.get("credential_id"),
            evidence_id=doc.get("evidence_id"),
            created_at=doc.get("created_at"),
            graded_at=doc.get("graded_at"),
        )


class AssessmentSummary(BaseModel):
    id: str
    skill: str
    status: AssessmentStatus
    score: int | None = None
    level: SkillLevel | None = None
    passed: bool = False
    created_at: datetime | None = None

    @classmethod
    def from_doc(cls, doc: dict[str, Any]) -> "AssessmentSummary":
        out = AssessmentOut.from_doc(doc)
        return cls(
            id=out.id,
            skill=out.skill,
            status=out.status,
            score=out.score,
            level=out.level,
            passed=out.passed,
            created_at=out.created_at,
        )
