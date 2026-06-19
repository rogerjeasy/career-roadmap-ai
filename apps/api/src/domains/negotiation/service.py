"""Negotiation & Offer Coach — service layer.

Grounds an LLM benchmark/counter in the offer details plus the user's real
profile (location, target role, salary goal) from the session, persists each
analysis, and runs a stateless roleplay turn where the LLM plays the recruiter
and returns private coaching alongside the in-character reply.
"""
from __future__ import annotations

import json

from fastapi import Depends
from google.cloud.firestore_v1.async_client import AsyncClient

from src.core.exceptions import NotFoundError
from src.core.llm import LlmJsonClient, get_llm_client
from src.core.logging import get_logger
from src.db.firestore import get_firestore_client
from src.domains.negotiation.firestore_repository import FirestoreNegotiationRepository
from src.domains.negotiation.schemas import (
    OfferAnalysisOut,
    OfferInput,
    RoleplayInput,
    RoleplayReply,
)
from src.session.manager import SessionManager, get_session_manager

logger = get_logger(__name__)

_ANALYZE_SYSTEM = """You are an expert compensation and negotiation coach. Given a \
job offer and the candidate's background, benchmark the offer and prepare a \
negotiation. Be honest and surface uncertainty — never present a benchmark as a \
certainty, and never infer or use race, gender, age, nationality, disability or \
any protected attribute.

Return ONLY a valid JSON object — no markdown, no prose — with this schema:
{
  "assessment": "2-4 sentence plain-language read on the offer",
  "competitiveness": "below|at|above|unknown",
  "benchmark_low": integer annual base for this role/location/seniority,
  "benchmark_high": integer annual base,
  "benchmark_currency": "currency code",
  "counter_base": integer base salary to counter with,
  "counter_rationale": "why this counter is justified and defensible",
  "talking_points": ["concrete point the candidate can say", "..."],
  "risks": ["a real risk of this negotiation", "..."],
  "assumptions": ["assumption this analysis depends on", "..."],
  "confidence": 0.0
}

Rules:
- Ground numbers in the role, location and seniority provided. If you lack data, set competitiveness "unknown", confidence low, and say so in assumptions.
- 3-6 talking_points, 2-4 risks, 2-4 assumptions.
- counter_base should be realistic, not greedy — anchor slightly above midpoint when justified.
"""

_ROLEPLAY_SYSTEM = """You are running a salary-negotiation roleplay. You play the \
RECRUITER/hiring manager for the given offer — realistic, professional, with \
budget constraints but willing to move when the candidate makes a strong case. \
After responding in character, give the candidate private coaching on their last \
message. Do not infer or use any protected attribute.

Return ONLY a valid JSON object — no markdown — with this schema:
{
  "reply": "the recruiter's in-character response to the candidate's last message",
  "coaching": "private feedback on how the candidate handled that turn",
  "tip": "one concrete suggestion for what to say next"
}
"""


class NegotiationService:
    def __init__(
        self,
        repo: FirestoreNegotiationRepository,
        llm: LlmJsonClient,
        sessions: SessionManager,
    ) -> None:
        self._repo = repo
        self._llm = llm
        self._sessions = sessions

    # ── Analysis ──────────────────────────────────────────────────────────────

    async def analyze(self, user_id: str, offer: OfferInput) -> OfferAnalysisOut:
        context = await self._offer_context(user_id, offer)
        try:
            raw = await self._llm.complete_json(
                system=_ANALYZE_SYSTEM, user=context, max_tokens=2048
            )
        except ValueError:
            raw = {}
        if not isinstance(raw, dict):
            raw = {}

        payload = {
            "offer": offer.model_dump(),
            "assessment": raw.get("assessment", ""),
            "competitiveness": raw.get("competitiveness", "unknown"),
            "benchmark_low": raw.get("benchmark_low", 0),
            "benchmark_high": raw.get("benchmark_high", 0),
            "benchmark_currency": raw.get("benchmark_currency", offer.currency),
            "counter_base": raw.get("counter_base", 0),
            "counter_rationale": raw.get("counter_rationale", ""),
            "talking_points": raw.get("talking_points", []),
            "risks": raw.get("risks", []),
            "assumptions": raw.get("assumptions", []),
            "confidence": raw.get("confidence", 0.0),
        }
        doc = await self._repo.create(user_id, payload)
        logger.info("negotiation.analyzed", user_id=user_id, offer_id=doc["id"])
        return OfferAnalysisOut.from_doc(doc)

    async def list(self, user_id: str) -> list[OfferAnalysisOut]:
        docs = await self._repo.list_for_user(user_id, limit=50)
        return [OfferAnalysisOut.from_doc(d) for d in docs]

    async def get(self, user_id: str, offer_id: str) -> OfferAnalysisOut:
        doc = await self._repo.get(offer_id, user_id)
        if doc is None:
            raise NotFoundError("Offer analysis not found.")
        return OfferAnalysisOut.from_doc(doc)

    async def delete(self, user_id: str, offer_id: str) -> None:
        removed = await self._repo.soft_delete(offer_id, user_id)
        if not removed:
            raise NotFoundError("Offer analysis not found.")

    # ── Roleplay ──────────────────────────────────────────────────────────────

    async def roleplay(self, user_id: str, payload: RoleplayInput) -> RoleplayReply:
        transcript = "\n".join(
            f"{'Candidate' if m.role == 'user' else 'Recruiter'}: {m.content}"
            for m in payload.history
        )
        user_prompt = (
            "OFFER:\n"
            + json.dumps(payload.offer.model_dump(), default=str)
            + "\n\nCONVERSATION SO FAR:\n"
            + (transcript or "(none yet)")
            + f"\n\nCandidate's new message: {payload.message}\n\n"
            "Respond as the recruiter and coach the candidate."
        )
        try:
            raw = await self._llm.complete_json(
                system=_ROLEPLAY_SYSTEM, user=user_prompt, max_tokens=1024
            )
        except ValueError:
            raw = {}
        if not isinstance(raw, dict):
            raw = {}
        return RoleplayReply(
            reply=str(raw.get("reply", "Let me consider that and get back to you.")),
            coaching=str(raw.get("coaching", "")),
            tip=str(raw.get("tip", "")),
        )

    # ── Internals ─────────────────────────────────────────────────────────────

    async def _offer_context(self, user_id: str, offer: OfferInput) -> str:
        session = await self._sessions.get(user_id)
        profile = session.user_profile_context if session else None
        parts = ["OFFER:", json.dumps(offer.model_dump(), default=str)]
        if profile is not None:
            bg: list[str] = []
            if profile.target_role:
                bg.append(f"Target role: {profile.target_role}")
            if profile.current_role:
                bg.append(f"Current role: {profile.current_role}")
            if profile.location:
                bg.append(f"Based in: {profile.location}")
            if profile.salary_goal:
                bg.append(f"Salary goal: {profile.salary_goal}")
            if profile.skills:
                bg.append("Skills: " + ", ".join(profile.skills[:25]))
            if bg:
                parts.append("\nCANDIDATE BACKGROUND:\n" + "\n".join(bg))
        parts.append("\nBenchmark this offer and prepare the negotiation as specified.")
        return "\n".join(parts)


async def get_negotiation_service(
    db: AsyncClient = Depends(get_firestore_client),
    llm: LlmJsonClient = Depends(get_llm_client),
    sessions: SessionManager = Depends(get_session_manager),
) -> NegotiationService:
    return NegotiationService(FirestoreNegotiationRepository(db), llm, sessions)
