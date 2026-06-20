"""Ask-My-Journey — service layer.

Assembles a compact, factual snapshot of the user's data across the main
collections and asks the LLM to answer the question grounded strictly in it. The
context is capped so the prompt stays bounded regardless of how much data exists.
"""
from __future__ import annotations

from fastapi import Depends
from google.cloud.firestore_v1.async_client import AsyncClient

from src.core.llm import LlmJsonClient, get_llm_client
from src.core.logging import get_logger
from src.db.firestore import get_firestore_client
from src.db.firestore_crud import FirestoreCrudRepository
from src.domains.journey_qa.schemas import AskInput, AskReply
from src.session.manager import SessionManager, get_session_manager

logger = get_logger(__name__)

_SYSTEM = """You are the user's career analyst. Answer their question using ONLY \
the data snapshot provided about them. If the data doesn't support an answer, say \
so plainly and suggest what they could log to get one — never invent facts or \
numbers. Be concise and specific. Do not infer protected attributes.

Return ONLY valid JSON — no markdown — with this schema:
{
  "answer": "your grounded answer",
  "sources": ["which data areas you used, e.g. 'applications', 'evidence'"],
  "suggestions": ["optional next-step the user could take", "..."]
}
"""


class JourneyQaService:
    def __init__(
        self,
        db: AsyncClient,
        llm: LlmJsonClient,
        sessions: SessionManager,
    ) -> None:
        self._db = db
        self._llm = llm
        self._sessions = sessions

    async def ask(self, user_id: str, payload: AskInput) -> AskReply:
        context = await self._snapshot(user_id)
        history = "\n".join(
            f"{'User' if m.role == 'user' else 'Analyst'}: {m.content}"
            for m in payload.history[-6:]
        )
        prompt = (
            f"USER DATA SNAPSHOT:\n{context}\n\n"
            + (f"EARLIER CONVERSATION:\n{history}\n\n" if history else "")
            + f"QUESTION: {payload.question}\n\nAnswer per the schema."
        )
        try:
            raw = await self._llm.complete_json(system=_SYSTEM, user=prompt, max_tokens=1024)
        except ValueError:
            raw = {}
        if not isinstance(raw, dict):
            raw = {}
        logger.info("journey_qa.answered", user_id=user_id)
        return AskReply(
            answer=str(raw.get("answer") or "I couldn't find enough data to answer that yet."),
            sources=list(raw.get("sources", []) or []),
            suggestions=list(raw.get("suggestions", []) or []),
        )

    # ── Context assembly ──────────────────────────────────────────────────────

    def _col(self, name: str) -> FirestoreCrudRepository:
        return FirestoreCrudRepository(self._db, name)

    async def _snapshot(self, user_id: str) -> str:
        parts: list[str] = []

        session = await self._sessions.get(user_id)
        profile = session.user_profile_context if session else None
        plan = session.plan_context if session else None
        if profile is not None:
            bits = []
            if profile.target_role:
                bits.append(f"target role {profile.target_role}")
            if profile.current_role:
                bits.append(f"currently {profile.current_role}")
            if profile.location:
                bits.append(f"in {profile.location}")
            if profile.skills:
                bits.append("skills: " + ", ".join(profile.skills[:20]))
            if bits:
                parts.append("PROFILE: " + "; ".join(bits))
        if plan is not None and isinstance(plan.snapshot, dict):
            summary = plan.snapshot.get("summary")
            if isinstance(summary, str) and summary:
                parts.append("ROADMAP: " + summary[:400])

        apps = await self._col("applications").list_for_user(user_id, limit=50)
        if apps:
            by_status: dict[str, int] = {}
            for a in apps:
                s = str(a.get("status", "saved"))
                by_status[s] = by_status.get(s, 0) + 1
            recent = "; ".join(
                f"{a.get('role', '')}@{a.get('company', '')} ({a.get('status', '')})"
                for a in apps[:8]
            )
            parts.append(f"APPLICATIONS ({len(apps)} total, {by_status}): {recent}")

        learning = await self._col("learning_items").list_for_user(user_id, limit=30)
        if learning:
            titles = ", ".join(str(x.get("title", "")) for x in learning[:8])
            parts.append(f"LEARNING ({len(learning)} items): {titles}")

        evidence = await self._col("evidence").list_for_user(user_id, limit=30)
        if evidence:
            titles = ", ".join(str(x.get("title", "")) for x in evidence[:8])
            parts.append(f"EVIDENCE ({len(evidence)} items): {titles}")

        reviews = await self._col("weekly_reviews").list_for_user(user_id, limit=5)
        if reviews:
            parts.append(f"WEEKLY REVIEWS: {len(reviews)} logged (most recent first)")

        wellness = await self._col("wellness_checkins").list_for_user(user_id, limit=5)
        if wellness:
            latest = wellness[0]
            parts.append(
                f"WELLNESS (latest): energy {latest.get('energy')}, stress {latest.get('stress')}, "
                f"motivation {latest.get('motivation')}"
            )

        return "\n".join(parts) if parts else "(no data logged yet)"


async def get_journey_qa_service(
    db: AsyncClient = Depends(get_firestore_client),
    llm: LlmJsonClient = Depends(get_llm_client),
    sessions: SessionManager = Depends(get_session_manager),
) -> JourneyQaService:
    return JourneyQaService(db, llm, sessions)
