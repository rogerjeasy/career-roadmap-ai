"""Unit tests for SessionManager — all Redis calls are mocked."""
import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.session.manager import SessionManager
from src.session.models import (
    ClarificationFlags,
    ClarificationQuestion,
    ConversationRole,
    PlanContext,
    SessionData,
    UserProfileContext,
)

USER_ID = "firebase-uid-abc123"
EMAIL = "test@example.com"
TTL = 86400


def _make_redis(stored: SessionData | None = None) -> MagicMock:
    """Return a mock Redis client pre-configured with optional stored session."""
    redis = MagicMock()
    raw = stored.model_dump_json() if stored else None
    redis.get = AsyncMock(return_value=raw)
    redis.setex = AsyncMock(return_value=True)
    redis.delete = AsyncMock(return_value=1)
    return redis


def _make_session(**overrides) -> SessionData:
    now = datetime.now(UTC)
    defaults = dict(
        user_id=USER_ID,
        email=EMAIL,
        created_at=now,
        last_active_at=now,
    )
    return SessionData(**{**defaults, **overrides})


# ── get ───────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_returns_none_when_no_session():
    redis = _make_redis(stored=None)
    mgr = SessionManager(redis, ttl=TTL)
    result = await mgr.get(USER_ID)
    assert result is None
    redis.get.assert_awaited_once_with(f"session:{USER_ID}")


@pytest.mark.asyncio
async def test_get_returns_deserialized_session():
    stored = _make_session()
    redis = _make_redis(stored=stored)
    mgr = SessionManager(redis, ttl=TTL)
    result = await mgr.get(USER_ID)
    assert result is not None
    assert result.user_id == USER_ID
    assert result.email == EMAIL


# ── create ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_saves_new_session_and_returns_it():
    redis = _make_redis(stored=None)
    mgr = SessionManager(redis, ttl=TTL)
    result = await mgr.create(USER_ID, EMAIL)

    assert result.user_id == USER_ID
    assert result.email == EMAIL
    assert result.conversation_state == []
    assert result.follow_up_queue == []
    assert result.clarification_flags.is_complete is False
    redis.setex.assert_awaited_once()

    # verify TTL passed to Redis
    call_args = redis.setex.call_args
    assert call_args.args[1] == TTL


# ── get_or_create ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_or_create_creates_when_missing():
    redis = _make_redis(stored=None)
    mgr = SessionManager(redis, ttl=TTL)
    result = await mgr.get_or_create(USER_ID, EMAIL)
    assert result.user_id == USER_ID
    redis.setex.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_or_create_loads_and_refreshes_existing():
    stored = _make_session()
    redis = _make_redis(stored=stored)
    mgr = SessionManager(redis, ttl=TTL)
    result = await mgr.get_or_create(USER_ID, EMAIL)
    assert result.user_id == USER_ID
    # last_active_at is refreshed on _save
    redis.setex.assert_awaited_once()


# ── delete ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_delete_calls_redis_delete():
    redis = _make_redis()
    mgr = SessionManager(redis, ttl=TTL)
    await mgr.delete(USER_ID)
    redis.delete.assert_awaited_once_with(f"session:{USER_ID}")


# ── add_turn ──────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_add_turn_appends_to_conversation():
    stored = _make_session()
    redis = _make_redis(stored=stored)
    mgr = SessionManager(redis, ttl=TTL)

    result = await mgr.add_turn(USER_ID, ConversationRole.user, "Hello!", EMAIL)

    assert len(result.conversation_state) == 1
    assert result.conversation_state[0].role == ConversationRole.user
    assert result.conversation_state[0].content == "Hello!"


@pytest.mark.asyncio
async def test_add_turn_trims_oldest_beyond_max():
    from src.session.models import ConversationTurn, MAX_CONVERSATION_TURNS

    turns = [
        ConversationTurn(role=ConversationRole.user, content=f"msg {i}")
        for i in range(MAX_CONVERSATION_TURNS)
    ]
    stored = _make_session(conversation_state=turns)
    redis = _make_redis(stored=stored)
    mgr = SessionManager(redis, ttl=TTL)

    result = await mgr.add_turn(USER_ID, ConversationRole.assistant, "new", EMAIL)

    assert len(result.conversation_state) == MAX_CONVERSATION_TURNS
    assert result.conversation_state[-1].content == "new"
    assert result.conversation_state[0].content == "msg 1"  # oldest trimmed


# ── follow-up queue ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_set_follow_up_queue_caps_at_three():
    stored = _make_session()
    redis = _make_redis(stored=stored)
    mgr = SessionManager(redis, ttl=TTL)

    questions = [
        ClarificationQuestion(question=f"Q{i}", field_name=f"field_{i}", priority=i)
        for i in range(5)
    ]
    result = await mgr.set_follow_up_queue(USER_ID, questions, EMAIL)

    assert len(result.follow_up_queue) == 3
    assert result.clarification_flags.round_number == 1


@pytest.mark.asyncio
async def test_clear_follow_up_queue():
    q = ClarificationQuestion(question="Where?", field_name="location", priority=1)
    stored = _make_session(follow_up_queue=[q])
    redis = _make_redis(stored=stored)
    mgr = SessionManager(redis, ttl=TTL)

    result = await mgr.clear_follow_up_queue(USER_ID, EMAIL)
    assert result.follow_up_queue == []


# ── apply_clarification_answers ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_apply_clarification_answers_merges_known_scalar_fields():
    stored = _make_session()
    redis = _make_redis(stored=stored)
    mgr = SessionManager(redis, ttl=TTL)

    result = await mgr.apply_clarification_answers(
        USER_ID, {"target_role": "ML Engineer", "location": "Berlin"}, EMAIL
    )

    assert result.user_profile_context is not None
    assert result.user_profile_context.target_role == "ML Engineer"
    assert result.user_profile_context.location == "Berlin"


@pytest.mark.asyncio
async def test_apply_clarification_answers_extends_list_fields():
    stored = _make_session()
    redis = _make_redis(stored=stored)
    mgr = SessionManager(redis, ttl=TTL)

    result = await mgr.apply_clarification_answers(
        USER_ID, {"skills": ["Python", "SQL"]}, EMAIL
    )

    assert "Python" in result.user_profile_context.skills  # type: ignore[union-attr]
    assert "SQL" in result.user_profile_context.skills  # type: ignore[union-attr]


@pytest.mark.asyncio
async def test_apply_clarification_answers_puts_unknown_in_additional():
    stored = _make_session()
    redis = _make_redis(stored=stored)
    mgr = SessionManager(redis, ttl=TTL)

    result = await mgr.apply_clarification_answers(
        USER_ID, {"preferred_language": "English"}, EMAIL
    )

    assert result.user_profile_context is not None
    assert result.user_profile_context.additional["preferred_language"] == "English"


@pytest.mark.asyncio
async def test_apply_clarification_answers_clears_follow_up_queue():
    q = ClarificationQuestion(question="Where?", field_name="location", priority=1)
    stored = _make_session(follow_up_queue=[q])
    redis = _make_redis(stored=stored)
    mgr = SessionManager(redis, ttl=TTL)

    result = await mgr.apply_clarification_answers(USER_ID, {"location": "Paris"}, EMAIL)
    assert result.follow_up_queue == []


# ── context caches ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_set_user_profile_context():
    stored = _make_session()
    redis = _make_redis(stored=stored)
    mgr = SessionManager(redis, ttl=TTL)

    profile = UserProfileContext(target_role="Data Scientist", location="NYC")
    result = await mgr.set_user_profile_context(USER_ID, profile, EMAIL)

    assert result.user_profile_context is not None
    assert result.user_profile_context.target_role == "Data Scientist"


@pytest.mark.asyncio
async def test_set_plan_context():
    stored = _make_session()
    redis = _make_redis(stored=stored)
    mgr = SessionManager(redis, ttl=TTL)

    plan = PlanContext(roadmap_id="roadmap-001", snapshot={"weeks": 12})
    result = await mgr.set_plan_context(USER_ID, plan, EMAIL)

    assert result.plan_context is not None
    assert result.plan_context.roadmap_id == "roadmap-001"
    assert result.plan_context.snapshot["weeks"] == 12


# ── TTL refresh on every write ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_every_write_resets_ttl():
    stored = _make_session()
    redis = _make_redis(stored=stored)
    mgr = SessionManager(redis, ttl=TTL)

    await mgr.add_turn(USER_ID, ConversationRole.user, "hi", EMAIL)

    call_args = redis.setex.call_args
    assert call_args.args[1] == TTL
