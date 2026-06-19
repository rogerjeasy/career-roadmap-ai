"""Wellness & Sustainability Monitor — service layer.

Stores wellness check-ins and derives the burnout-risk status from the most
recent ones via the pure engine. Status is computed on read so each new check-in
immediately updates the picture.
"""
from __future__ import annotations

from fastapi import Depends
from google.cloud.firestore_v1.async_client import AsyncClient

from src.core.exceptions import NotFoundError
from src.core.logging import get_logger
from src.db.firestore import get_firestore_client
from src.domains.wellness.engine import CheckinSignal, assess
from src.domains.wellness.firestore_repository import FirestoreWellnessRepository
from src.domains.wellness.schemas import (
    WellnessCheckinCreate,
    WellnessCheckinOut,
    WellnessStatus,
)

logger = get_logger(__name__)


class WellnessService:
    def __init__(self, repo: FirestoreWellnessRepository) -> None:
        self._repo = repo

    async def log_checkin(
        self, user_id: str, payload: WellnessCheckinCreate
    ) -> WellnessCheckinOut:
        doc = await self._repo.create(user_id, payload.model_dump())
        logger.info("wellness.checkin_logged", user_id=user_id, checkin_id=doc["id"])
        return WellnessCheckinOut.from_doc(doc)

    async def list_checkins(self, user_id: str, limit: int = 60) -> list[WellnessCheckinOut]:
        docs = await self._repo.list_for_user(user_id, limit=limit)
        return [WellnessCheckinOut.from_doc(d) for d in docs]

    async def delete_checkin(self, user_id: str, checkin_id: str) -> None:
        removed = await self._repo.soft_delete(checkin_id, user_id)
        if not removed:
            raise NotFoundError("Check-in not found.")

    async def status(self, user_id: str) -> WellnessStatus:
        docs = await self._repo.list_for_user(user_id, limit=12)  # newest-first
        signals = [
            CheckinSignal(
                energy=int(d.get("energy", 3) or 3),
                stress=int(d.get("stress", 3) or 3),
                motivation=int(d.get("motivation", 3) or 3),
                hours_worked=float(d.get("hours_worked", 40) or 40),
                sleep_hours=float(d.get("sleep_hours", 7) or 7),
            )
            for d in docs
        ]
        a = assess(signals)
        return WellnessStatus(
            risk_score=a.risk_score,
            risk_level=a.risk_level,
            trend=a.trend,
            drivers=a.drivers,
            recommendation=a.recommendation,
            recovery_suggested=a.recovery_suggested,
            sample_size=a.sample_size,
        )


async def get_wellness_service(
    db: AsyncClient = Depends(get_firestore_client),
) -> WellnessService:
    return WellnessService(FirestoreWellnessRepository(db))
