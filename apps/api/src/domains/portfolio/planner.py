"""Portfolio Build Plan — AI-guided artefact sequencing (§14.7).

Sits alongside the CRUD ``PortfolioService`` without changing it. Given the
user's target role, the gaps their portfolio doesn't yet cover, and the items
they already have, the LLM proposes a *prioritised sequence* of artefacts to
build — each tied to the skills it proves and the gap it closes. The plan is
cached as one per-user document and regenerated on demand.
"""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from fastapi import Depends
from google.cloud.firestore_v1.async_client import AsyncClient

from src.core.exceptions import NotFoundError, ValidationError
from src.core.llm import LlmJsonClient, get_llm_client
from src.core.logging import get_logger
from src.db.firestore import get_firestore_client
from src.db.firestore_crud import FirestoreCrudRepository, utcnow
from src.domains.portfolio.plan_schemas import PlanTrackResult, PortfolioPlan
from src.session.manager import SessionManager, get_session_manager

logger = get_logger(__name__)

_SYSTEM = """You are a portfolio strategist. Propose a PRIORITISED sequence of \
portfolio artefacts a person should build to become a credible candidate for \
their target role, closing the gaps their current portfolio doesn't cover. Be \
concrete and realistic; never invent work they've already done. Do not infer \
protected attributes.

Return ONLY a valid JSON object — no markdown — with this schema:
{
  "based_on": "one sentence on what this plan was derived from",
  "suggestions": [
    {
      "title": "short artefact name",
      "artefact_type": "project" | "case_study" | "demo" | "writeup" | "contribution",
      "summary": "1-2 sentences on what to build",
      "skills_demonstrated": ["skill", "..."],
      "closes_gap": "the gap or weakness this addresses",
      "effort": "small" | "medium" | "large",
      "priority": integer (1 = build first),
      "why": "why this matters for the target role",
      "starter_steps": ["first concrete step", "..."]
    }
  ]
}
Rules: 3-6 suggestions ordered by priority (1..N); 2-4 starter_steps each. Ground everything in the provided context.
"""


class PortfolioPlannerService:
    def __init__(
        self,
        plans: FirestoreCrudRepository,
        items: FirestoreCrudRepository,
        blocks: FirestoreCrudRepository,
        llm: LlmJsonClient,
        sessions: SessionManager,
    ) -> None:
        self._plans = plans
        self._items = items
        self._blocks = blocks
        self._llm = llm
        self._sessions = sessions

    async def get(self, user_id: str) -> PortfolioPlan:
        doc = await self._plans.get(user_id, user_id)
        return PortfolioPlan.from_doc(doc) if doc else PortfolioPlan.empty()

    async def track(self, user_id: str, suggestion_id: str) -> PlanTrackResult:
        """Turn a suggested artefact into tracked work: a planned portfolio item
        plus a weekly ``build`` schedule block, in one step."""
        plan_doc = await self._plans.get(user_id, user_id)
        suggestion = next(
            (
                s
                for s in ((plan_doc or {}).get("suggestions") or [])
                if isinstance(s, dict) and s.get("id") == suggestion_id
            ),
            None,
        )
        if suggestion is None:
            raise NotFoundError("Suggestion not found in your current plan.")

        title = str(suggestion.get("title", "Portfolio project"))
        skills = list(suggestion.get("skills_demonstrated", []) or [])
        item = await self._items.create(
            user_id,
            {
                "title": title,
                "description": str(suggestion.get("summary", "")),
                "status": "in_progress",
                "tech": skills,
                "link": "",
                "source": "portfolio_plan",
            },
        )
        block = await self._blocks.create(
            user_id,
            {
                "day": datetime.now(timezone.utc).weekday(),  # 0 = Monday
                "label": f"Build: {title}",
                "category": "build",
            },
        )
        logger.info(
            "portfolio_plan.tracked",
            user_id=user_id,
            suggestion_id=suggestion_id,
            item_id=item["id"],
            block_id=block["id"],
        )
        return PlanTrackResult(
            suggestion_id=suggestion_id,
            portfolio_item_id=item["id"],
            schedule_block_id=block["id"],
            message=f"Added “{title}” to your portfolio and this week's build schedule.",
        )

    async def generate(self, user_id: str) -> PortfolioPlan:
        context = await self._build_context(user_id)
        if not context.strip():
            raise ValidationError(
                "Add a target role (via onboarding or CV import) to plan your portfolio."
            )
        try:
            raw = await self._llm.complete_json(system=_SYSTEM, user=context, max_tokens=2560)
        except ValueError:
            raw = {}
        if not isinstance(raw, dict):
            raw = {}

        suggestions = []
        for s in raw.get("suggestions", []) or []:
            if isinstance(s, dict):
                suggestions.append({**s, "id": str(uuid4())})

        data = {
            "based_on": raw.get("based_on", ""),
            "suggestions": suggestions,
            "generated_at": utcnow(),
        }
        existing = await self._plans.get(user_id, user_id)
        if existing is not None:
            await self._plans.update(user_id, user_id, data)
        else:
            await self._plans.create(user_id, data, doc_id=user_id)
        logger.info("portfolio_plan.generated", user_id=user_id, count=len(suggestions))
        return PortfolioPlan.from_doc({"id": user_id, **data})

    # ── Internals ─────────────────────────────────────────────────────────────

    async def _build_context(self, user_id: str) -> str:
        session = await self._sessions.get(user_id)
        profile = session.user_profile_context if session else None
        parts: list[str] = []
        if profile is not None:
            if profile.target_role:
                parts.append(f"Target role: {profile.target_role}")
            if profile.current_role:
                parts.append(f"Current role: {profile.current_role}")
            if profile.skills:
                parts.append("Skills held: " + ", ".join(profile.skills[:30]))

        items = await self._items.list_for_user(user_id, limit=50)
        if items:
            lines = [
                f"- {i.get('title', '')} ({', '.join(i.get('tech', []) or [])})"
                for i in items
                if i.get("title")
            ]
            parts.append("EXISTING PORTFOLIO:\n" + "\n".join(lines))
        else:
            parts.append("EXISTING PORTFOLIO: (empty)")

        if not any(p for p in parts if p.startswith("Target role")):
            return ""
        parts.append("Propose the prioritised portfolio build plan as specified.")
        return "\n".join(parts)


async def get_portfolio_planner_service(
    db: AsyncClient = Depends(get_firestore_client),
    llm: LlmJsonClient = Depends(get_llm_client),
    sessions: SessionManager = Depends(get_session_manager),
) -> PortfolioPlannerService:
    return PortfolioPlannerService(
        FirestoreCrudRepository(db, "portfolio_plans"),
        FirestoreCrudRepository(db, "portfolio"),
        FirestoreCrudRepository(db, "schedule_blocks"),
        llm,
        sessions,
    )
