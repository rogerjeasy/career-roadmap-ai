"""Redis-backed session management keyed by Firebase UID."""
from datetime import UTC, datetime

import redis.asyncio as aioredis
from fastapi import Depends
from pydantic import BaseModel

from src.config import settings
from src.core.auth import AuthenticatedUser, get_current_user
from src.db.redis import get_redis


class SessionData(BaseModel):
    user_id: str
    email: str | None
    created_at: datetime
    last_active_at: datetime


async def get_or_create_session(
    user: AuthenticatedUser = Depends(get_current_user),
    redis: aioredis.Redis = Depends(get_redis),
) -> SessionData:
    """Load an existing session or create a new one. Always refreshes last_active_at."""
    key = f"session:{user.uid}"
    raw = await redis.get(key)

    now = datetime.now(UTC)
    if raw:
        data = SessionData.model_validate_json(raw)
        data.last_active_at = now
    else:
        data = SessionData(
            user_id=user.uid,
            email=user.email,
            created_at=now,
            last_active_at=now,
        )

    await redis.setex(key, settings.redis_session_ttl_seconds, data.model_dump_json())
    return data
