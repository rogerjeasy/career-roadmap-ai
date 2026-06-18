"""Newsletter domain — service layer.

Two responsibilities:
  1. Preferences — one document per user (doc id == ``user_id``); ``get`` returns
     sensible defaults, ``update`` upserts.
  2. Digest generation — an LLM composes a personalised weekly digest (industry
     summary, three articles, two people to follow, one action) grounded in the
     user's market snapshot and target role, cached as one document per user.
"""
from __future__ import annotations

from typing import Any

from fastapi import Depends
from google.cloud.firestore_v1.async_client import AsyncClient

from src.core.llm import LlmJsonClient, get_llm_client
from src.core.logging import get_logger
from src.db.firestore import get_firestore_client
from src.db.firestore_crud import utcnow
from src.domains.newsletter.firestore_repository import (
    FirestoreNewsletterDigestRepository,
    FirestoreNewsletterRepository,
)
from src.domains.newsletter.schemas import (
    NewsletterDigest,
    NewsletterPrefsOut,
    NewsletterPrefsUpdate,
)
from src.session.manager import SessionManager, get_session_manager

logger = get_logger(__name__)

_DIGEST_SYSTEM = """You are a career newsletter editor writing a short, personalised \
weekly digest for one professional, grounded in their plan and the market context provided.

Return ONLY a valid JSON object — no markdown, no prose — with this schema:
{
  "period_label": "e.g. 'Week of 16 Jun 2026' or 'This week'",
  "summary": "2-4 sentences: what changed in their industry/target field that matters to them",
  "articles": [{"title": "headline", "why": "why it matters to them", "url": "https://... or null"}],
  "people_to_follow": [{"name": "person", "reason": "why follow them", "handle": "@handle or null"}],
  "action_item": "one concrete action to take this week, tied to their plan",
  "confidence": 0.0
}

Rules:
- Exactly 3 articles and 2 people_to_follow.
- Only include a url/handle if you are confident it is real; otherwise use null. Never fabricate links.
- Ground the summary in the provided market signals when present; otherwise reason from the target role and lower confidence.
- The action_item must be specific and doable in a week.
- Do NOT infer or act on race, gender, age, nationality, disability, or any protected attribute.
"""


class NewsletterService:
    def __init__(
        self,
        repo: FirestoreNewsletterRepository,
        digests: FirestoreNewsletterDigestRepository,
        llm: LlmJsonClient,
        sessions: SessionManager,
    ) -> None:
        self._repo = repo
        self._digests = digests
        self._llm = llm
        self._sessions = sessions

    # ── Preferences ───────────────────────────────────────────────────────────

    async def get(self, user_id: str) -> NewsletterPrefsOut:
        doc = await self._repo.get(user_id, user_id)
        if doc is None:
            return NewsletterPrefsOut.defaults()
        return NewsletterPrefsOut.from_doc(doc)

    async def update(
        self, user_id: str, payload: NewsletterPrefsUpdate
    ) -> NewsletterPrefsOut:
        data = payload.model_dump()
        existing = await self._repo.get(user_id, user_id)
        if existing is None:
            doc = await self._repo.create(user_id, data, doc_id=user_id)
        else:
            doc = await self._repo.update(user_id, user_id, data)
        logger.info(
            "newsletter.prefs_updated",
            user_id=user_id,
            subscribed=payload.subscribed,
            frequency=payload.frequency,
        )
        return NewsletterPrefsOut.from_doc(doc or {"id": user_id, **data})

    # ── Digest ──────────────────────────────────────────────────────────────

    async def get_digest(self, user_id: str) -> NewsletterDigest:
        doc = await self._digests.get(user_id, user_id)
        return NewsletterDigest.from_doc(doc) if doc else NewsletterDigest.empty()

    async def generate_digest(self, user_id: str) -> NewsletterDigest:
        context = await self._build_context(user_id)
        if context is None:
            return NewsletterDigest.empty()

        try:
            raw = await self._llm.complete_json(
                system=_DIGEST_SYSTEM, user=context, max_tokens=2048
            )
        except ValueError:
            return NewsletterDigest.empty()

        digest = NewsletterDigest.from_doc(raw if isinstance(raw, dict) else {})
        data = digest.model_dump(exclude={"has_data", "generated_at"})
        data["generated_at"] = utcnow()

        existing = await self._digests.get(user_id, user_id)
        if existing is not None:
            await self._digests.update(user_id, user_id, data)
        else:
            await self._digests.create(user_id, data, doc_id=user_id)

        logger.info("newsletter.digest_generated", user_id=user_id, confidence=digest.confidence)
        return digest

    # ── Internal ────────────────────────────────────────────────────────────

    async def _build_context(self, user_id: str) -> str | None:
        """Assemble the prompt context. Returns None when there's nothing to write about."""
        session = await self._sessions.get(user_id)
        profile = session.user_profile_context if session else None
        snapshot: dict[str, Any] = {}
        if session and session.plan_context:
            snapshot = session.plan_context.snapshot or {}

        target_role = (profile.target_role if profile else None) or ""
        location = (profile.location if profile else None) or ""
        if not target_role and not snapshot:
            return None

        market = _extract_market(snapshot)
        parts: list[str] = []
        if target_role:
            parts.append(f"Target role: {target_role}")
        if location:
            parts.append(f"Location: {location}")
        if market.get("market_summary"):
            parts.append("Market summary: " + str(market["market_summary"]))
        signals = market.get("industry_signals") or []
        if isinstance(signals, list) and signals:
            topics = [str(s.get("topic", "")) for s in signals[:6] if isinstance(s, dict)]
            parts.append("Recent signals: " + "; ".join(t for t in topics if t))
        skills = market.get("trending_skills") or []
        if isinstance(skills, list) and skills:
            names = [str(s.get("name", "")) for s in skills[:8] if isinstance(s, dict)]
            parts.append("Trending skills: " + ", ".join(n for n in names if n))

        return (
            "Reader context:\n" + "\n".join(parts) + "\n\nWrite this week's digest as specified."
        )


def _extract_market(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Mirror MarketService's snapshot-shaping to find the market payload."""
    if not isinstance(snapshot, dict):
        return {}
    agent_outputs = snapshot.get("agent_outputs", {}) if isinstance(snapshot, dict) else {}
    return (
        snapshot.get("market")
        or snapshot.get("market_intelligence")
        or agent_outputs.get("market")
        or agent_outputs.get("market_intelligence")
        or {}
    )


async def get_newsletter_service(
    db: AsyncClient = Depends(get_firestore_client),
    llm: LlmJsonClient = Depends(get_llm_client),
    sessions: SessionManager = Depends(get_session_manager),
) -> NewsletterService:
    return NewsletterService(
        FirestoreNewsletterRepository(db),
        FirestoreNewsletterDigestRepository(db),
        llm,
        sessions,
    )
