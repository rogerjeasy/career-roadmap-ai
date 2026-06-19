"""Career Storytelling Studio — service layer.

Gathers the user's selected evidence (ownership-checked) and profile, asks the
LLM to write the requested narrative grounded only in those facts, and persists
the draft. The format steers the prompt (résumé bullets vs. cover letter vs.
LinkedIn About vs. interview STAR story).
"""
from __future__ import annotations

import json

from fastapi import Depends
from google.cloud.firestore_v1.async_client import AsyncClient

from src.core.exceptions import NotFoundError, ValidationError
from src.core.llm import LlmJsonClient, get_llm_client
from src.core.logging import get_logger
from src.db.firestore import get_firestore_client
from src.db.firestore_crud import FirestoreCrudRepository
from src.domains.storytelling.firestore_repository import FirestoreStorytellingRepository
from src.domains.storytelling.schemas import StoryDraftOut, StoryGenerateInput
from src.session.manager import SessionManager, get_session_manager

logger = get_logger(__name__)

_FORMAT_BRIEF: dict[str, str] = {
    "resume_bullets": (
        "Write 4-6 résumé bullet points. Each starts with a strong action verb, "
        "quantifies impact where the evidence supports it, and is one line. "
        "Put them in `content` as a newline-separated list (no leading dashes)."
    ),
    "linkedin_about": (
        "Write a first-person LinkedIn 'About' section of 2-4 short paragraphs that "
        "tells a coherent career story and ends with what they're looking for next."
    ),
    "cover_letter": (
        "Write a tailored cover letter (greeting → 3 body paragraphs → close) for the "
        "target role/company, weaving in the evidence as proof points."
    ),
    "interview_story": (
        "Write a single interview answer in STAR format (Situation, Task, Action, "
        "Result) as flowing prose, anchored on the strongest evidence item."
    ),
}

_SYSTEM = """You are an expert career writer. Craft compelling, truthful career \
narratives from a person's REAL accomplishments. Never invent facts, employers, \
metrics, or titles beyond what the provided evidence and profile state — if a \
detail isn't given, omit it rather than fabricate. Do not reference or infer any \
protected attribute.

Return ONLY a valid JSON object — no markdown, no prose — with this schema:
{
  "title": "short label for this draft",
  "content": "the narrative, formatted per the brief",
  "highlights": ["the 2-4 strongest points this draft leans on"],
  "tips": ["1-3 concrete suggestions to make it even stronger"]
}
"""


class StorytellingService:
    def __init__(
        self,
        repo: FirestoreStorytellingRepository,
        evidence: FirestoreCrudRepository,
        llm: LlmJsonClient,
        sessions: SessionManager,
    ) -> None:
        self._repo = repo
        self._evidence = evidence
        self._llm = llm
        self._sessions = sessions

    async def generate(self, user_id: str, payload: StoryGenerateInput) -> StoryDraftOut:
        evidence = await self._gather_evidence(user_id, payload.evidence_ids)
        if not evidence:
            raise ValidationError(
                "Select at least one evidence item to ground the narrative in."
            )
        context = await self._build_prompt(user_id, payload, evidence)

        try:
            raw = await self._llm.complete_json(system=_SYSTEM, user=context, max_tokens=2048)
        except ValueError:
            raw = {}
        if not isinstance(raw, dict):
            raw = {}

        doc = await self._repo.create(
            user_id,
            {
                "format": payload.format,
                "tone": payload.tone,
                "target_role": payload.target_role,
                "target_company": payload.target_company,
                "title": raw.get("title", payload.format.replace("_", " ").title()),
                "content": raw.get("content", ""),
                "highlights": raw.get("highlights", []),
                "tips": raw.get("tips", []),
                "evidence_titles": [e["title"] for e in evidence],
            },
        )
        logger.info(
            "storytelling.generated",
            user_id=user_id,
            draft_id=doc["id"],
            format=payload.format,
        )
        return StoryDraftOut.from_doc(doc)

    async def list_drafts(self, user_id: str) -> list[StoryDraftOut]:
        docs = await self._repo.list_for_user(user_id, limit=100)
        return [StoryDraftOut.from_doc(d) for d in docs]

    async def get_draft(self, user_id: str, draft_id: str) -> StoryDraftOut:
        doc = await self._repo.get(draft_id, user_id)
        if doc is None:
            raise NotFoundError("Draft not found.")
        return StoryDraftOut.from_doc(doc)

    async def delete_draft(self, user_id: str, draft_id: str) -> None:
        removed = await self._repo.soft_delete(draft_id, user_id)
        if not removed:
            raise NotFoundError("Draft not found.")

    # ── Internals ─────────────────────────────────────────────────────────────

    async def _gather_evidence(self, user_id: str, evidence_ids: list[str]) -> list[dict]:
        out: list[dict] = []
        seen: set[str] = set()
        for eid in evidence_ids:
            if eid in seen:
                continue
            seen.add(eid)
            item = await self._evidence.get(eid, user_id)
            if item is None:
                continue
            out.append(
                {
                    "title": str(item.get("title", "")),
                    "type": str(item.get("type", "")),
                    "description": str(item.get("description", "")),
                    "skills": list(item.get("skills", []) or []),
                    "date_label": str(item.get("date_label", "")),
                }
            )
        return out

    async def _build_prompt(
        self, user_id: str, payload: StoryGenerateInput, evidence: list[dict]
    ) -> str:
        session = await self._sessions.get(user_id)
        profile = session.user_profile_context if session else None
        parts: list[str] = [f"FORMAT BRIEF: {_FORMAT_BRIEF[payload.format]}"]
        parts.append(f"TONE: {payload.tone}")
        if payload.target_role:
            parts.append(f"TARGET ROLE: {payload.target_role}")
        if payload.target_company:
            parts.append(f"TARGET COMPANY: {payload.target_company}")
        if profile is not None:
            bg: list[str] = []
            if profile.current_role:
                bg.append(f"Current role: {profile.current_role}")
            if profile.target_role and not payload.target_role:
                bg.append(f"Aspiration: {profile.target_role}")
            if profile.skills:
                bg.append("Skills: " + ", ".join(profile.skills[:25]))
            if bg:
                parts.append("CANDIDATE PROFILE:\n" + "\n".join(bg))
        parts.append("EVIDENCE (the only facts you may use):\n" + json.dumps(evidence, default=str))
        if payload.extra_context.strip():
            parts.append("EXTRA CONTEXT: " + payload.extra_context.strip())
        parts.append("Write the narrative now, per the schema.")
        return "\n\n".join(parts)


async def get_storytelling_service(
    db: AsyncClient = Depends(get_firestore_client),
    llm: LlmJsonClient = Depends(get_llm_client),
    sessions: SessionManager = Depends(get_session_manager),
) -> StorytellingService:
    return StorytellingService(
        FirestoreStorytellingRepository(db),
        FirestoreCrudRepository(db, "evidence"),
        llm,
        sessions,
    )
