"""Billing domain — Firestore repository (collection: ``billing_customers``).

One document per user (doc id == ``user_id``) holds the Stripe customer id and
the last-known subscription state synced from webhooks. Webhook events identify
the user by Stripe customer id, so a reverse lookup is provided.
"""
from __future__ import annotations

from typing import Any

from google.cloud.firestore_v1.async_client import AsyncClient

from src.db.firestore_crud import FirestoreCrudRepository


class FirestoreBillingRepository(FirestoreCrudRepository):
    def __init__(self, db: AsyncClient) -> None:
        super().__init__(db, "billing_customers")

    async def get_for_user(self, user_id: str) -> dict[str, Any] | None:
        return await self.get(user_id, user_id)

    async def upsert_for_user(
        self, user_id: str, data: dict[str, Any]
    ) -> dict[str, Any]:
        existing = await self.get(user_id, user_id)
        if existing is None:
            return await self.create(user_id, data, doc_id=user_id)
        merged = await self.update(user_id, user_id, data)
        return merged or {"id": user_id, **data}

    async def find_by_customer_id(self, customer_id: str) -> dict[str, Any] | None:
        query = self._col.where("stripe_customer_id", "==", customer_id).limit(1)
        async for snap in query.stream():
            return {"id": snap.id, **(snap.to_dict() or {})}
        return None
