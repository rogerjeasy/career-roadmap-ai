"""Discovery domain — service layer.

Reads the user's cached profile + CV text from the session and asks the LLM for
a set of comparable career paths. The result is cached as a single per-user
document; ``generate`` recomputes it from the current profile.
"""
from __future__ import annotations

from fastapi import Depends
from google.cloud.firestore_v1.async_client import AsyncClient

from src.core.llm import LlmJsonClient, get_llm_client
from src.core.logging import get_logger
from src.db.firestore import get_firestore_client
from src.db.firestore_crud import utcnow
from src.domains.discovery.firestore_repository import FirestoreDiscoveryRepository
from src.domains.discovery.schemas import DiscoveryResult
from src.session.manager import SessionManager, get_session_manager

logger = get_logger(__name__)

_SYSTEM_PROMPT = """You are a career-discovery advisor. A professional has shared \
their background but has NOT fixed a target role. Propose realistic career paths \
they could pursue and make them directly comparable.

Return ONLY a valid JSON object — no markdown, no prose — with this schema:
{
  "based_on": "one short sentence on what these paths were derived from",
  "confidence": 0.0,
  "paths": [
    {
      "title": "role/path title",
      "summary": "1-2 sentence description of the path",
      "fit_score": integer 0-100 (how well their current profile fits),
      "effort_to_switch": "low|medium|high",
      "timeline_months": integer realistic months to become competitive,
      "salary_currency": "local currency code if a location is known, else USD",
      "salary_low": integer annual gross,
      "salary_high": integer annual gross,
      "growth_outlook": "one sentence on demand/growth for this path",
      "key_skills_to_gain": ["skill", "..."],
      "transferable_strengths": ["existing strength that carries over", "..."],
      "sample_phases": [{"title": "phase name", "duration_weeks": integer, "focus": "what it covers"}],
      "rationale": "why this path is plausible for THIS person"
    }
  ]
}

Rules:
- Propose 3-5 DISTINCT paths spanning different directions (a natural next step AND genuine pivots).
- Ground every field in the actual background provided; do not invent unrelated roles.
- fit_score and confidence must be honest; lower them when the background is thin.
- 2-4 sample_phases per path; 3-6 items in skill/strength lists.
- Do NOT infer or act on race, gender, age, nationality, disability, or any protected attribute.
"""


class DiscoveryService:
    def __init__(
        self,
        repo: FirestoreDiscoveryRepository,
        llm: LlmJsonClient,
        sessions: SessionManager,
    ) -> None:
        self._repo = repo
        self._llm = llm
        self._sessions = sessions

    async def get(self, user_id: str) -> DiscoveryResult:
        doc = await self._repo.get(user_id, user_id)
        return DiscoveryResult.from_doc(doc) if doc else DiscoveryResult.empty()

    async def generate(self, user_id: str) -> DiscoveryResult:
        context = await self._build_context(user_id)
        if not context.strip():
            return DiscoveryResult(
                based_on="",
                has_data=False,
                confidence=0.0,
            )

        try:
            raw = await self._llm.complete_json(
                system=_SYSTEM_PROMPT, user=context, max_tokens=3072
            )
        except ValueError:
            return DiscoveryResult.empty()

        if not isinstance(raw, dict):
            raw = {}
        result = DiscoveryResult.from_doc(raw)

        data = result.model_dump(exclude={"has_data", "generated_at"})
        data["generated_at"] = utcnow()
        existing = await self._repo.get(user_id, user_id)
        if existing is not None:
            await self._repo.update(user_id, user_id, data)
        else:
            await self._repo.create(user_id, data, doc_id=user_id)

        logger.info("discovery.generated", user_id=user_id, path_count=len(result.paths))
        return result

    # ── Internal ────────────────────────────────────────────────────────────

    async def _build_context(self, user_id: str) -> str:
        session = await self._sessions.get(user_id)
        profile = session.user_profile_context if session else None
        if profile is None:
            return ""

        parts: list[str] = []
        if profile.current_role:
            parts.append(f"Current role: {profile.current_role}")
        if profile.location:
            parts.append(f"Location: {profile.location}")
        if profile.skills:
            parts.append("Skills: " + ", ".join(profile.skills[:40]))
        suggestions = profile.additional.get("career_path_suggestions")
        if isinstance(suggestions, list) and suggestions:
            parts.append("Prior path ideas: " + "; ".join(str(s) for s in suggestions[:8]))
        cv_text = profile.additional.get("cv_text")
        if isinstance(cv_text, str) and cv_text.strip():
            parts.append("CV extract:\n" + cv_text[:8000])

        if not parts:
            return ""
        return (
            "Professional background (no fixed target role):\n"
            + "\n".join(parts)
            + "\n\nProduce the career-path comparison as specified."
        )


async def get_discovery_service(
    db: AsyncClient = Depends(get_firestore_client),
    llm: LlmJsonClient = Depends(get_llm_client),
    sessions: SessionManager = Depends(get_session_manager),
) -> DiscoveryService:
    return DiscoveryService(FirestoreDiscoveryRepository(db), llm, sessions)
