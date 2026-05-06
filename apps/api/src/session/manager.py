"""Redis-backed Session & Context Manager.

Single source of truth for per-user ephemeral state:
  - Conversation history (multi-turn dialogue)
  - Follow-up clarification queue (≤3 questions)
  - Clarification flags (completeness score, missing slots, round counter)
  - User profile context cache (consumed by specialist agents)
  - Plan/roadmap context cache (persisted across agentic steps)

All state is stored under `session:{user_id}` as a single JSON document with a
sliding 24-hour TTL — every write resets the expiry.
"""
from datetime import UTC, datetime
from typing import Any

import redis.asyncio as aioredis
from fastapi import Depends

from src.config import settings
from src.core.auth import AuthenticatedUser, get_current_user
from src.db.redis import get_redis
from src.session.models import (
    ClarificationFlags,
    ClarificationQuestion,
    ConversationRole,
    ConversationTurn,
    MAX_CONVERSATION_TURNS,
    PlanContext,
    SessionData,
    UserProfileContext,
)


class SessionManager:
    """All session operations against Redis. One instance per request via DI."""

    def __init__(self, redis: aioredis.Redis, ttl: int = settings.redis_session_ttl_seconds) -> None:
        self._redis = redis
        self._ttl = ttl

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _key(self, user_id: str) -> str:
        return f"session:{user_id}"

    async def _load(self, user_id: str) -> SessionData | None:
        raw = await self._redis.get(self._key(user_id))
        return SessionData.model_validate_json(raw) if raw else None

    async def _save(self, session: SessionData) -> SessionData:
        session.last_active_at = datetime.now(UTC)
        await self._redis.setex(
            self._key(session.user_id),
            self._ttl,
            session.model_dump_json(),
        )
        return session

    # ── Core CRUD ─────────────────────────────────────────────────────────────

    async def get(self, user_id: str) -> SessionData | None:
        """Return the session or None if it does not exist / has expired."""
        return await self._load(user_id)

    async def create(self, user_id: str, email: str | None) -> SessionData:
        """Create a fresh session, overwriting any existing one."""
        now = datetime.now(UTC)
        session = SessionData(
            user_id=user_id,
            email=email,
            created_at=now,
            last_active_at=now,
        )
        return await self._save(session)

    async def get_or_create(self, user_id: str, email: str | None) -> SessionData:
        """Load an existing session or create a new one; always refreshes last_active_at."""
        session = await self._load(user_id)
        if session is None:
            return await self.create(user_id, email)
        return await self._save(session)

    async def delete(self, user_id: str) -> None:
        """Delete the session from Redis immediately."""
        await self._redis.delete(self._key(user_id))

    # ── Conversation state ────────────────────────────────────────────────────

    async def add_turn(
        self,
        user_id: str,
        role: ConversationRole,
        content: str,
        email: str | None = None,
    ) -> SessionData:
        """Append a conversation turn. Trims oldest turns beyond MAX_CONVERSATION_TURNS."""
        session = await self.get_or_create(user_id, email)
        session.conversation_state.append(ConversationTurn(role=role, content=content))
        if len(session.conversation_state) > MAX_CONVERSATION_TURNS:
            session.conversation_state = session.conversation_state[-MAX_CONVERSATION_TURNS:]
        return await self._save(session)

    # ── Follow-up queue ───────────────────────────────────────────────────────

    async def set_follow_up_queue(
        self,
        user_id: str,
        questions: list[ClarificationQuestion],
        email: str | None = None,
    ) -> SessionData:
        """Replace the follow-up queue (Clarification Engine output, ≤3 questions)."""
        session = await self.get_or_create(user_id, email)
        session.follow_up_queue = questions[:3]  # architecture cap: ≤3 at a time
        session.clarification_flags.round_number += 1
        return await self._save(session)

    async def clear_follow_up_queue(self, user_id: str, email: str | None = None) -> SessionData:
        """Clear the follow-up queue after the user has answered all questions."""
        session = await self.get_or_create(user_id, email)
        session.follow_up_queue = []
        return await self._save(session)

    # ── Clarification answers ─────────────────────────────────────────────────

    async def apply_clarification_answers(
        self,
        user_id: str,
        answers: dict[str, Any],
        email: str | None = None,
    ) -> SessionData:
        """Merge field_name → value answers into user_profile_context.

        Known profile fields are applied directly; any unknown fields land in
        `additional` so no answer is ever silently dropped.
        """
        session = await self.get_or_create(user_id, email)
        profile = session.user_profile_context or UserProfileContext()

        _KNOWN_LIST_FIELDS = {"skills", "goals", "constraints"}
        _KNOWN_SCALAR_FIELDS = {
            "target_role",
            "current_role",
            "location",
            "timeline_months",
            "weekly_hours_available",
            "salary_goal",
        }

        for field, value in answers.items():
            if field in _KNOWN_LIST_FIELDS:
                current: list = getattr(profile, field)
                if isinstance(value, list):
                    current.extend(value)
                else:
                    current.append(str(value))
            elif field in _KNOWN_SCALAR_FIELDS:
                setattr(profile, field, value)
            else:
                profile.additional[field] = value

        session.user_profile_context = profile
        session.follow_up_queue = []  # answered — clear the queue
        return await self._save(session)

    # ── Context caches ────────────────────────────────────────────────────────

    async def update_clarification_flags(
        self,
        user_id: str,
        flags: ClarificationFlags,
        email: str | None = None,
    ) -> SessionData:
        session = await self.get_or_create(user_id, email)
        session.clarification_flags = flags
        return await self._save(session)

    async def set_user_profile_context(
        self,
        user_id: str,
        profile: UserProfileContext,
        email: str | None = None,
    ) -> SessionData:
        session = await self.get_or_create(user_id, email)
        session.user_profile_context = profile
        return await self._save(session)

    async def set_plan_context(
        self,
        user_id: str,
        plan: PlanContext,
        email: str | None = None,
    ) -> SessionData:
        session = await self.get_or_create(user_id, email)
        session.plan_context = plan
        return await self._save(session)


# ── FastAPI dependencies ───────────────────────────────────────────────────────


def get_session_manager(redis: aioredis.Redis = Depends(get_redis)) -> SessionManager:
    """Injectable SessionManager for controllers."""
    return SessionManager(redis)


async def get_or_create_session(
    user: AuthenticatedUser = Depends(get_current_user),
    redis: aioredis.Redis = Depends(get_redis),
) -> SessionData:
    """Backward-compatible dependency — load or create session, refresh last_active_at."""
    return await SessionManager(redis).get_or_create(user.uid, user.email)
