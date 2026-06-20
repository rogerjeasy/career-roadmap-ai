"""Interview Prep — service layer.

Generates tailored question banks and runs a stateless mock-interview turn (the
LLM plays the interviewer + scores the candidate's last answer), both grounded in
the user's real profile. Completed practices are persisted with an overall score.
"""
from __future__ import annotations

import json

from fastapi import Depends
from google.cloud.firestore_v1.async_client import AsyncClient

from src.core.exceptions import NotFoundError
from src.core.llm import LlmJsonClient, get_llm_client
from src.core.logging import get_logger
from src.db.firestore import get_firestore_client
from src.domains.interview_prep.firestore_repository import FirestoreInterviewRepository
from src.domains.interview_prep.schemas import (
    InterviewQuestion,
    QuestionRequest,
    QuestionSet,
    SessionCreate,
    SessionOut,
    TurnInput,
    TurnReply,
)
from src.session.manager import SessionManager, get_session_manager

logger = get_logger(__name__)

_QUESTIONS_SYSTEM = """You are an expert interviewer. Generate a tailored set of \
interview questions for the given role, company and interview type, grounded in \
the candidate's background. Do not infer protected attributes.

Return ONLY valid JSON — no markdown — with this schema:
{
  "questions": [
    {
      "question": "the interview question",
      "category": "behavioral|technical|system_design|role_specific",
      "assesses": "what this question evaluates",
      "answer_tips": ["concrete tip for a strong answer", "..."]
    }
  ]
}
Rules: produce exactly the requested count; 2-3 answer_tips each; realistic and specific to the role.
"""

_TURN_SYSTEM = """You are conducting a mock interview. You are the INTERVIEWER for \
the given role/company/type. Score the candidate's last answer fairly, give \
actionable feedback, then ask the next question (harder if they did well). Do not \
infer protected attributes.

Return ONLY valid JSON — no markdown — with this schema:
{
  "feedback": "honest critique of the candidate's last answer",
  "score": integer 0-100 for that answer,
  "strengths": ["what they did well", "..."],
  "improvements": ["what to improve", "..."],
  "next_question": "your next interview question",
  "done": boolean (true only if the interview has naturally concluded)
}
"""


class InterviewPrepService:
    def __init__(
        self,
        repo: FirestoreInterviewRepository,
        llm: LlmJsonClient,
        sessions: SessionManager,
    ) -> None:
        self._repo = repo
        self._llm = llm
        self._sessions = sessions

    async def generate_questions(self, user_id: str, req: QuestionRequest) -> QuestionSet:
        background = await self._background(user_id)
        prompt = (
            f"ROLE: {req.role}\nCOMPANY: {req.company or '(unspecified)'}\n"
            f"INTERVIEW TYPE: {req.interview_type}\nCOUNT: {req.count}\n\n"
            f"JOB DESCRIPTION:\n{(req.job_description or '(none)')[:8000]}\n\n"
            f"CANDIDATE BACKGROUND:\n{background}\n\nGenerate the questions."
        )
        try:
            raw = await self._llm.complete_json(system=_QUESTIONS_SYSTEM, user=prompt, max_tokens=2048)
        except ValueError:
            raw = {}
        if not isinstance(raw, dict):
            raw = {}
        questions = [
            InterviewQuestion(
                question=str(q.get("question", "")),
                category=str(q.get("category", "")),
                assesses=str(q.get("assesses", "")),
                answer_tips=list(q.get("answer_tips", []) or []),
            )
            for q in (raw.get("questions") or [])
            if isinstance(q, dict) and q.get("question")
        ]
        logger.info("interview.questions_generated", user_id=user_id, count=len(questions))
        return QuestionSet(role=req.role, interview_type=req.interview_type, questions=questions)

    async def turn(self, user_id: str, payload: TurnInput) -> TurnReply:
        background = await self._background(user_id)
        transcript = "\n".join(
            f"{'Interviewer' if m.role == 'interviewer' else 'Candidate'}: {m.content}"
            for m in payload.history
        )
        prompt = (
            f"ROLE: {payload.role}\nCOMPANY: {payload.company or '(unspecified)'}\n"
            f"INTERVIEW TYPE: {payload.interview_type}\n\n"
            f"CANDIDATE BACKGROUND:\n{background}\n\n"
            f"TRANSCRIPT SO FAR:\n{transcript or '(interview just starting)'}\n\n"
            f"Current question: {payload.current_question or '(opening question)'}\n"
            f"Candidate's answer: {payload.answer}\n\n"
            "Score the answer and ask the next question."
        )
        try:
            raw = await self._llm.complete_json(system=_TURN_SYSTEM, user=prompt, max_tokens=1024)
        except ValueError:
            raw = {}
        if not isinstance(raw, dict):
            raw = {}
        score = raw.get("score", 0)
        return TurnReply(
            feedback=str(raw.get("feedback", "")),
            score=int(score) if isinstance(score, (int, float)) else 0,
            strengths=list(raw.get("strengths", []) or []),
            improvements=list(raw.get("improvements", []) or []),
            next_question=str(raw.get("next_question", "")),
            done=bool(raw.get("done", False)),
        )

    # ── Saved sessions ────────────────────────────────────────────────────────

    async def save_session(self, user_id: str, payload: SessionCreate) -> SessionOut:
        doc = await self._repo.create(
            user_id,
            {
                "role": payload.role,
                "company": payload.company,
                "interview_type": payload.interview_type,
                "overall_score": payload.overall_score,
                "transcript": [m.model_dump() for m in payload.transcript],
                "notes": payload.notes,
            },
        )
        logger.info("interview.session_saved", user_id=user_id, session_id=doc["id"])
        return SessionOut.from_doc(doc)

    async def list_sessions(self, user_id: str) -> list[SessionOut]:
        docs = await self._repo.list_for_user(user_id, limit=100)
        return [SessionOut.from_doc(d) for d in docs]

    async def delete_session(self, user_id: str, session_id: str) -> None:
        removed = await self._repo.soft_delete(session_id, user_id)
        if not removed:
            raise NotFoundError("Interview session not found.")

    # ── Internals ─────────────────────────────────────────────────────────────

    async def _background(self, user_id: str) -> str:
        session = await self._sessions.get(user_id)
        profile = session.user_profile_context if session else None
        if profile is None:
            return "(no profile on file)"
        parts: list[str] = []
        if profile.current_role:
            parts.append(f"Current role: {profile.current_role}")
        if profile.target_role:
            parts.append(f"Target role: {profile.target_role}")
        if profile.skills:
            parts.append("Skills: " + ", ".join(profile.skills[:25]))
        cv = profile.additional.get("cv_text")
        if isinstance(cv, str) and cv.strip():
            parts.append("CV extract: " + cv[:3000])
        return "\n".join(parts) or "(sparse profile)"


async def get_interview_prep_service(
    db: AsyncClient = Depends(get_firestore_client),
    llm: LlmJsonClient = Depends(get_llm_client),
    sessions: SessionManager = Depends(get_session_manager),
) -> InterviewPrepService:
    return InterviewPrepService(FirestoreInterviewRepository(db), llm, sessions)
