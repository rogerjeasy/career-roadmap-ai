"""AI Outreach Drafting — service layer.

Drafts messages with the LLM grounded in the user's profile, persists them as
``draft``, and enforces the approval gate: a draft must be ``approved`` before it
can be ``sent`` (the platform records the send; it does not transmit on the
user's behalf). Editing a sent/approved draft reverts it to ``draft`` so changes
are re-reviewed.
"""
from __future__ import annotations

from fastapi import Depends
from google.cloud.firestore_v1.async_client import AsyncClient

from src.core.exceptions import ConflictError, NotFoundError
from src.core.llm import LlmJsonClient, get_llm_client
from src.core.logging import get_logger
from src.db.firestore import get_firestore_client
from src.domains.outreach.firestore_repository import FirestoreOutreachRepository
from src.domains.outreach.schemas import (
    OutreachDraftOut,
    OutreachDraftRequest,
    OutreachEdit,
)
from src.session.manager import SessionManager, get_session_manager

logger = get_logger(__name__)

_SYSTEM = """You are an expert at warm, effective professional outreach. Draft a \
short message for the user to send. Be specific and human — no clichés or filler. \
Ground it in the user's real background; never invent achievements. Do not infer \
protected attributes.

Return ONLY valid JSON — no markdown — with this schema:
{ "subject": "concise subject line (empty string for LinkedIn/DM channels)", "body": "the message" }
"""


class OutreachService:
    def __init__(
        self,
        repo: FirestoreOutreachRepository,
        llm: LlmJsonClient,
        sessions: SessionManager,
    ) -> None:
        self._repo = repo
        self._llm = llm
        self._sessions = sessions

    async def draft(self, user_id: str, req: OutreachDraftRequest) -> OutreachDraftOut:
        background = await self._background(user_id)
        prompt = (
            f"CHANNEL: {req.channel}\nTONE: {req.tone}\n"
            f"RECIPIENT: {req.recipient_name or '(unknown)'} — {req.recipient_role or '(role unknown)'}\n"
            f"GOAL: {req.goal}\n"
            f"EXTRA CONTEXT: {req.context or '(none)'}\n\n"
            f"SENDER BACKGROUND:\n{background}\n\nDraft the message."
        )
        try:
            raw = await self._llm.complete_json(system=_SYSTEM, user=prompt, max_tokens=1024)
        except ValueError:
            raw = {}
        if not isinstance(raw, dict):
            raw = {}
        doc = await self._repo.create(
            user_id,
            {
                "recipient_name": req.recipient_name,
                "recipient_role": req.recipient_role,
                "channel": req.channel,
                "tone": req.tone,
                "goal": req.goal,
                "subject": str(raw.get("subject", "")),
                "body": str(raw.get("body", "")),
                "status": "draft",
            },
        )
        logger.info("outreach.drafted", user_id=user_id, draft_id=doc["id"])
        return OutreachDraftOut.from_doc(doc)

    async def list(self, user_id: str) -> list[OutreachDraftOut]:
        docs = await self._repo.list_for_user(user_id, limit=100)
        return [OutreachDraftOut.from_doc(d) for d in docs]

    async def edit(self, user_id: str, draft_id: str, payload: OutreachEdit) -> OutreachDraftOut:
        patch = payload.to_patch()
        if patch:
            patch["status"] = "draft"  # edits require re-approval
        doc = await self._repo.update(draft_id, user_id, patch) if patch else \
            await self._repo.get(draft_id, user_id)
        if doc is None:
            raise NotFoundError("Draft not found.")
        return OutreachDraftOut.from_doc(doc)

    async def approve(self, user_id: str, draft_id: str) -> OutreachDraftOut:
        doc = await self._require(user_id, draft_id)
        if doc.get("status") == "sent":
            raise ConflictError("This message has already been sent.")
        updated = await self._repo.update(draft_id, user_id, {"status": "approved"})
        logger.info("outreach.approved", user_id=user_id, draft_id=draft_id)
        return OutreachDraftOut.from_doc(updated or doc)

    async def mark_sent(self, user_id: str, draft_id: str) -> OutreachDraftOut:
        doc = await self._require(user_id, draft_id)
        if doc.get("status") != "approved":
            raise ConflictError("Approve the message before marking it sent.")
        updated = await self._repo.update(draft_id, user_id, {"status": "sent"})
        logger.info("outreach.marked_sent", user_id=user_id, draft_id=draft_id)
        return OutreachDraftOut.from_doc(updated or doc)

    async def delete(self, user_id: str, draft_id: str) -> None:
        removed = await self._repo.soft_delete(draft_id, user_id)
        if not removed:
            raise NotFoundError("Draft not found.")

    # ── Internals ─────────────────────────────────────────────────────────────

    async def _require(self, user_id: str, draft_id: str) -> dict:
        doc = await self._repo.get(draft_id, user_id)
        if doc is None:
            raise NotFoundError("Draft not found.")
        return doc

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
            parts.append("Skills: " + ", ".join(profile.skills[:20]))
        return "\n".join(parts) or "(sparse profile)"


async def get_outreach_service(
    db: AsyncClient = Depends(get_firestore_client),
    llm: LlmJsonClient = Depends(get_llm_client),
    sessions: SessionManager = Depends(get_session_manager),
) -> OutreachService:
    return OutreachService(FirestoreOutreachRepository(db), llm, sessions)
