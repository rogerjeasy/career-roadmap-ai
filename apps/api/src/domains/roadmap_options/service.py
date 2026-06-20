"""Roadmap Strategy Options — service layer.

Generates three comparable strategies from the user's real profile via the LLM,
caches them as a single per-user document, and records the selected strategy on
the session profile so the agent pipeline can pace generation accordingly.
"""
from __future__ import annotations

from uuid import uuid4

from fastapi import Depends
from google.cloud.firestore_v1.async_client import AsyncClient

from src.core.exceptions import NotFoundError, ValidationError
from src.core.llm import LlmJsonClient, get_llm_client
from src.core.logging import get_logger
from src.db.firestore import get_firestore_client
from src.db.firestore_crud import utcnow
from src.domains.roadmap_options.firestore_repository import (
    FirestoreRoadmapOptionsRepository,
)
from src.domains.roadmap_options.schemas import RoadmapOptionsSet
from src.session.manager import SessionManager, get_session_manager
from src.session.models import UserProfileContext

logger = get_logger(__name__)

_SYSTEM = """You are a career strategist. From a person's background and goal, \
produce THREE distinct strategic roadmaps to the same destination, differing in \
pace and intensity. Be honest about trade-offs; never infer protected attributes.

Return ONLY a valid JSON object — no markdown — with this schema:
{
  "based_on": "one sentence on what these strategies were derived from",
  "options": [
    {
      "strategy": "aggressive" | "balanced" | "long_term",
      "title": "short name for this strategy",
      "timeline_months": integer,
      "weekly_hours": integer realistic weekly time commitment,
      "intensity": "one phrase, e.g. 'sprint' / 'steady' / 'marathon'",
      "summary": "2-3 sentences describing the approach",
      "phases": [{"title": "phase name", "duration_weeks": integer, "focus": "what it covers"}],
      "tradeoffs": ["honest trade-off of this pace", "..."],
      "risks": ["a real risk", "..."],
      "best_for": "who this strategy suits"
    }
  ]
}
Rules:
- EXACTLY three options, one of each strategy: aggressive, balanced, long_term.
- aggressive = shortest timeline / highest weekly hours; long_term = gentlest pace.
- 3-5 phases each; 2-4 tradeoffs and 1-3 risks each. Ground everything in the profile.
"""


class RoadmapOptionsService:
    def __init__(
        self,
        repo: FirestoreRoadmapOptionsRepository,
        llm: LlmJsonClient,
        sessions: SessionManager,
    ) -> None:
        self._repo = repo
        self._llm = llm
        self._sessions = sessions

    async def get(self, user_id: str) -> RoadmapOptionsSet:
        doc = await self._repo.get(user_id, user_id)
        return RoadmapOptionsSet.from_doc(doc) if doc else RoadmapOptionsSet.empty()

    async def generate(self, user_id: str) -> RoadmapOptionsSet:
        context = await self._build_context(user_id)
        if not context.strip():
            raise ValidationError(
                "Add your goal and background (via onboarding or CV import) first."
            )
        try:
            raw = await self._llm.complete_json(system=_SYSTEM, user=context, max_tokens=3072)
        except ValueError:
            raw = {}
        if not isinstance(raw, dict):
            raw = {}

        options = []
        for o in raw.get("options", []) or []:
            if isinstance(o, dict):
                options.append({**o, "id": str(uuid4())})

        existing = await self._repo.get(user_id, user_id)
        data = {
            "based_on": raw.get("based_on", ""),
            "options": options,
            "selected_strategy": (existing or {}).get("selected_strategy"),
            "generated_at": utcnow(),
        }
        if existing is not None:
            await self._repo.update(user_id, user_id, data)
        else:
            await self._repo.create(user_id, data, doc_id=user_id)
        logger.info("roadmap_options.generated", user_id=user_id, count=len(options))
        return RoadmapOptionsSet.from_doc({"id": user_id, **data})

    async def select(self, user_id: str, strategy: str) -> RoadmapOptionsSet:
        doc = await self._repo.get(user_id, user_id)
        if doc is None or not doc.get("options"):
            raise NotFoundError("Generate strategy options first.")
        await self._repo.update(user_id, user_id, {"selected_strategy": strategy})

        # Record the preference on the session profile for the agent pipeline.
        session = await self._sessions.get_or_create(user_id, None)
        profile = session.user_profile_context or UserProfileContext()
        profile.additional["preferred_strategy"] = strategy
        await self._sessions.set_user_profile_context(user_id, profile, session.email)

        logger.info("roadmap_options.selected", user_id=user_id, strategy=strategy)
        updated = await self._repo.get(user_id, user_id)
        return RoadmapOptionsSet.from_doc(updated or {"id": user_id})

    # ── Internals ─────────────────────────────────────────────────────────────

    async def _build_context(self, user_id: str) -> str:
        session = await self._sessions.get(user_id)
        profile = session.user_profile_context if session else None
        if profile is None:
            return ""
        parts: list[str] = []
        if profile.target_role:
            parts.append(f"Goal / target role: {profile.target_role}")
        if profile.current_role:
            parts.append(f"Current role: {profile.current_role}")
        if profile.skills:
            parts.append("Skills: " + ", ".join(profile.skills[:30]))
        if profile.timeline_months:
            parts.append(f"Preferred timeline (months): {profile.timeline_months}")
        if profile.weekly_hours_available:
            parts.append(f"Weekly hours available: {profile.weekly_hours_available}")
        if profile.constraints:
            parts.append("Constraints: " + "; ".join(profile.constraints[:8]))
        if profile.goals:
            parts.append("Goals: " + "; ".join(profile.goals[:8]))
        if not parts:
            return ""
        return (
            "Career background and goal:\n"
            + "\n".join(parts)
            + "\n\nProduce the three strategic roadmap options as specified."
        )


async def get_roadmap_options_service(
    db: AsyncClient = Depends(get_firestore_client),
    llm: LlmJsonClient = Depends(get_llm_client),
    sessions: SessionManager = Depends(get_session_manager),
) -> RoadmapOptionsService:
    return RoadmapOptionsService(
        FirestoreRoadmapOptionsRepository(db), llm, sessions
    )
