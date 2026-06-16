"""User domain — Firestore data access layer."""
from datetime import datetime, timezone

from google.cloud.firestore_v1.async_client import AsyncClient

from src.domains.user.model import User, default_notification_preferences

_COLLECTION = "users"

# Sentinel so partial updates can distinguish "leave unchanged" from "set to None".
_UNSET: object = object()


class FirestoreUserRepository:
    def __init__(self, db: AsyncClient) -> None:
        self._col = db.collection(_COLLECTION)

    async def get_by_firebase_uid(self, uid: str) -> User | None:
        doc = await self._col.document(uid).get()
        if not doc.exists:
            return None
        return _doc_to_user(doc.id, doc.to_dict())

    async def get_by_email(self, email: str) -> User | None:
        async for doc in self._col.where("email", "==", email).limit(1).stream():
            return _doc_to_user(doc.id, doc.to_dict())
        return None

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
        doc_ref = self._col.document(firebase_uid)
        doc = await doc_ref.get()
        now = datetime.now(timezone.utc)

        if not doc.exists:
            data: dict = {
                "firebase_uid": firebase_uid,
                "email": email,
                "display_name": display_name,
                "photo_url": photo_url,
                "provider": provider,
                "email_verified": email_verified,
                "is_active": True,
                "notification_preferences": default_notification_preferences(),
                "created_at": now,
                "updated_at": now,
            }
            await doc_ref.set(data)
            return _doc_to_user(firebase_uid, data)

        existing = doc.to_dict()
        updates: dict = {
            "email": email,
            "display_name": display_name,
            "photo_url": photo_url,
            "email_verified": email_verified,
            "updated_at": now,
        }
        await doc_ref.update(updates)
        return _doc_to_user(firebase_uid, {**existing, **updates})

    async def update(
        self,
        firebase_uid: str,
        *,
        display_name: str | None | object = _UNSET,
        notification_preferences: dict[str, bool] | object = _UNSET,
    ) -> User | None:
        """Apply a partial update to an existing user document.

        Only arguments that differ from the ``_UNSET`` sentinel are written.
        Returns ``None`` if the user document does not exist.
        """
        doc_ref = self._col.document(firebase_uid)
        doc = await doc_ref.get()
        if not doc.exists:
            return None

        updates: dict = {"updated_at": datetime.now(timezone.utc)}
        if display_name is not _UNSET:
            updates["display_name"] = display_name
        if notification_preferences is not _UNSET:
            updates["notification_preferences"] = notification_preferences

        await doc_ref.update(updates)
        return _doc_to_user(firebase_uid, {**doc.to_dict(), **updates})

    async def delete(self, firebase_uid: str) -> None:
        """Hard-delete the user document."""
        await self._col.document(firebase_uid).delete()


def _doc_to_user(doc_id: str, data: dict) -> User:
    return User(
        id=doc_id,
        firebase_uid=data.get("firebase_uid", doc_id),
        email=data["email"],
        display_name=data.get("display_name"),
        photo_url=data.get("photo_url"),
        provider=data["provider"],
        email_verified=data.get("email_verified", False),
        is_active=data.get("is_active", True),
        notification_preferences=(
            data.get("notification_preferences")
            or default_notification_preferences()
        ),
        created_at=data["created_at"],
        updated_at=data["updated_at"],
    )
