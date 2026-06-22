"""Content Engine domain — service layer.

Generates personal-brand content grounded in the user's latest roadmap
milestones and profile, and enforces the consent gate on publishing: a draft can
only become ``published`` once LinkedIn is connected (checked against the
``user_integrations`` store).
"""
from __future__ import annotations

from fastapi import Depends
from google.cloud.firestore_v1.async_client import AsyncClient

from src.core.exceptions import NotFoundError, ValidationError
from src.core.llm import LlmJsonClient, get_llm_client
from src.core.logging import get_logger
from src.db.firestore import get_firestore_client
from src.db.firestore_crud import utcnow
from src.domains.content.firestore_repository import FirestoreContentRepository
from src.domains.content.schemas import (
    ContentDraftOut,
    ContentGenerateInput,
    ContentStatus,
)
from src.domains.integrations.firestore_repository import FirestoreIntegrationRepository
from src.domains.roadmap.service import RoadmapService, get_roadmap_service
from src.session.manager import SessionManager, get_session_manager

logger = get_logger(__name__)

_KIND_BRIEF = {
    "linkedin_post": (
        "a LinkedIn post (120-200 words) that shares an insight or update and "
        "invites engagement, written in first person"
    ),
    "build_in_public": (
        "a short 'build in public' update (80-140 words) that candidly shares "
        "progress, what was learned, and what's next"
    ),
    "milestone_announcement": (
        "a concise milestone announcement (60-120 words) celebrating a concrete "
        "achievement without exaggeration"
    ),
}

_SYSTEM = """You are a personal-brand writer. Draft authentic, specific content for \
a professional, grounded ONLY in the real milestones and context provided — never \
invent achievements, employers, or metrics. Avoid clichés and hype. Write in the \
first person. Do not reference or infer protected attributes.

Return ONLY a valid JSON object — no markdown — with this schema:
{
  "title": "a short internal label for this draft",
  "content": "the post text, ready to publish",
  "hashtags": ["Relevant", "Hashtags", "WithoutTheHashSymbol"],
  "based_on": "one phrase naming the milestone/context this drew on"
}
Rules: 3-6 hashtags; keep the content within the length implied by the format.
"""


class ContentService:
    def __init__(
        self,
        repo: FirestoreContentRepository,
        llm: LlmJsonClient,
        sessions: SessionManager,
        roadmaps: RoadmapService,
        integrations: FirestoreIntegrationRepository,
    ) -> None:
        self._repo = repo
        self._llm = llm
        self._sessions = sessions
        self._roadmaps = roadmaps
        self._integrations = integrations

    # ── Reads ───────────────────────────────────────────────────────────────────

    async def list(self, user_id: str) -> list[ContentDraftOut]:
        docs = await self._repo.list_for_user(user_id, limit=100)
        return [ContentDraftOut.from_doc(d) for d in docs]

    async def get(self, user_id: str, draft_id: str) -> ContentDraftOut:
        doc = await self._repo.get(draft_id, user_id)
        if doc is None:
            raise NotFoundError("Draft not found.")
        return ContentDraftOut.from_doc(doc)

    # ── Generate ────────────────────────────────────────────────────────────────

    async def generate(self, user_id: str, payload: ContentGenerateInput) -> ContentDraftOut:
        context = await self._build_context(user_id, payload)
        brief = _KIND_BRIEF.get(payload.kind, _KIND_BRIEF["linkedin_post"])
        prompt = (
            f"FORMAT: Write {brief}.\n"
            f"TONE: {payload.tone}\n\n"
            f"CONTEXT:\n{context}\n\n"
            "Draft the content per the schema."
        )
        try:
            raw = await self._llm.complete_json(system=_SYSTEM, user=prompt, max_tokens=1280)
        except ValueError:
            raw = {}
        if not isinstance(raw, dict):
            raw = {}
        content = str(raw.get("content", "")).strip()
        if not content:
            raise ValidationError("Couldn't draft that content. Try again or add context.")

        doc = await self._repo.create(
            user_id,
            {
                "kind": payload.kind,
                "tone": payload.tone,
                "title": str(raw.get("title", "")) or f"{payload.kind.replace('_', ' ').title()}",
                "content": content,
                "hashtags": [str(h).lstrip("#") for h in (raw.get("hashtags") or [])][:6],
                "based_on": str(raw.get("based_on", "")),
                "status": "draft",
                "published_at": None,
            },
        )
        logger.info("content.generated", user_id=user_id, kind=payload.kind)
        return ContentDraftOut.from_doc(doc)

    # ── Status transitions (consent + approval gate) ─────────────────────────────

    async def set_status(
        self, user_id: str, draft_id: str, status: ContentStatus
    ) -> ContentDraftOut:
        doc = await self._repo.get(draft_id, user_id)
        if doc is None:
            raise NotFoundError("Draft not found.")
        patch: dict[str, object] = {"status": status}
        if status == "published":
            if not await self._linkedin_connected(user_id):
                raise ValidationError(
                    "Connect LinkedIn first — publishing requires your explicit "
                    "consent via Settings → Integrations."
                )
            patch["published_at"] = utcnow()
        updated = await self._repo.update(draft_id, user_id, patch)
        logger.info("content.status_changed", user_id=user_id, draft_id=draft_id, status=status)
        return ContentDraftOut.from_doc(updated or {**doc, **patch})

    async def delete(self, user_id: str, draft_id: str) -> None:
        removed = await self._repo.soft_delete(draft_id, user_id)
        if not removed:
            raise NotFoundError("Draft not found.")

    # ── Internals ─────────────────────────────────────────────────────────────────

    async def _linkedin_connected(self, user_id: str) -> bool:
        doc = await self._integrations.get(
            self._integrations.doc_id(user_id, "linkedin"), user_id
        )
        return bool(doc and doc.get("access_token"))

    async def _build_context(self, user_id: str, payload: ContentGenerateInput) -> str:
        parts: list[str] = []
        session = await self._sessions.get(user_id)
        profile = session.user_profile_context if session else None
        if profile is not None:
            if profile.current_role:
                parts.append(f"Current role: {profile.current_role}")
            if profile.target_role:
                parts.append(f"Target role: {profile.target_role}")

        if payload.milestone.strip():
            parts.append(f"Milestone to highlight: {payload.milestone.strip()}")
        elif payload.source == "roadmap_milestone":
            milestones = await self._roadmap_milestones(user_id)
            if milestones:
                parts.append("Recent roadmap milestones:\n" + "\n".join(f"- {m}" for m in milestones))

        if payload.extra_context.strip():
            parts.append(f"Extra context: {payload.extra_context.strip()}")

        if not parts:
            parts.append("(No roadmap or profile context yet — write a general update.)")
        return "\n".join(parts)

    async def _roadmap_milestones(self, user_id: str, limit: int = 8) -> list[str]:
        summaries = await self._roadmaps.list_for_user(user_id, limit=1)
        if not summaries:
            return []
        doc = await self._roadmaps.get(summaries[0].id, user_id)
        if doc is None:
            return []
        out: list[str] = []
        for phase in doc.phases:
            for milestone in phase.milestones:
                out.append(f"{phase.title}: {milestone}")
                if len(out) >= limit:
                    return out
        return out


async def get_content_service(
    db: AsyncClient = Depends(get_firestore_client),
    llm: LlmJsonClient = Depends(get_llm_client),
    sessions: SessionManager = Depends(get_session_manager),
    roadmaps: RoadmapService = Depends(get_roadmap_service),
) -> ContentService:
    return ContentService(
        FirestoreContentRepository(db),
        llm,
        sessions,
        roadmaps,
        FirestoreIntegrationRepository(db),
    )
