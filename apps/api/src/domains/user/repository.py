"""User domain — database access layer."""
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.user.model import User


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, user_id: UUID) -> User | None:
        result = await self.session.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()

    async def get_by_firebase_uid(self, uid: str) -> User | None:
        result = await self.session.execute(select(User).where(User.firebase_uid == uid))
        return result.scalar_one_or_none()

    async def get_by_email(self, email: str) -> User | None:
        result = await self.session.execute(select(User).where(User.email == email))
        return result.scalar_one_or_none()

    async def upsert(
        self,
        *,
        firebase_uid: str,
        email: str,
        provider: str,
        display_name: str | None = None,
        photo_url: str | None = None,
        email_verified: bool = False,
    ) -> User:
        """Create a new user or update mutable fields for an existing one."""
        user = await self.get_by_firebase_uid(firebase_uid)
        if user is None:
            user = User(
                firebase_uid=firebase_uid,
                email=email,
                provider=provider,
                display_name=display_name,
                photo_url=photo_url,
                email_verified=email_verified,
            )
            self.session.add(user)
        else:
            user.email = email
            user.display_name = display_name
            user.photo_url = photo_url
            user.email_verified = email_verified
        await self.session.flush()
        return user
