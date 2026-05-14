"""Roadmap domain — Firestore implementation of IRoadmapRepository.

Firestore layout:
  roadmaps/{roadmap_id}                     ← core metadata + scalar fields
  roadmaps/{roadmap_id}/phases/{phase_id}   ← career phases (ordered by ``order``)
  roadmaps/{roadmap_id}/weekly_habits/{id}  ← recurring habits (ordered)
  roadmaps/{roadmap_id}/next_steps/{id}     ← immediate action items (ordered)

Separating the subcollections avoids unbounded document growth, keeps list
queries cheap (they only touch the root collection), and lets each subcollection
grow independently without hitting the 1 MiB document size limit.

Writes use a single Firestore WriteBatch so the main document and all
subcollections are committed atomically.

Note: the query in ``list_for_user`` uses a composite index on
(user_id ASC, created_at DESC).  Create it in Firestore Console or via
Terraform ``google_firestore_index`` before deploying to production.
"""
from __future__ import annotations

from datetime import datetime, timezone

from google.cloud.firestore_v1 import Query as FSQuery
from google.cloud.firestore_v1.async_client import AsyncClient
from google.cloud.firestore_v1.async_document import AsyncDocumentReference

from src.core.logging import get_logger
from src.domains.roadmap.schemas import (
    NextStep,
    RoadmapDocument,
    RoadmapPhase,
    RoadmapSummary,
    WeeklyHabit,
)

logger = get_logger(__name__)

_COL_ROADMAPS = "roadmaps"
_COL_PHASES = "phases"
_COL_WEEKLY_HABITS = "weekly_habits"
_COL_NEXT_STEPS = "next_steps"


class FirestoreRoadmapRepository:
    """Firestore-backed implementation of ``IRoadmapRepository``.

    Accepts an ``AsyncClient`` via the constructor — inject a real client in
    production (via ``get_firestore_client`` FastAPI dependency) or pass any
    compatible async mock in tests.
    """

    def __init__(self, db: AsyncClient) -> None:
        self._db = db
        self._col = db.collection(_COL_ROADMAPS)

    # ── IRoadmapRepository ────────────────────────────────────────────────────

    async def save(self, doc: RoadmapDocument) -> str:
        """Write the roadmap root document + three subcollections in one batch."""
        roadmap_ref = self._col.document(doc.id)
        batch = self._db.batch()

        batch.set(roadmap_ref, {
            "user_id": doc.user_id,
            "session_id": doc.session_id,
            "request_id": doc.request_id,
            "summary": doc.summary,
            "confidence": doc.confidence,
            "status": doc.status,
            "validation_passed": doc.validation_passed,
            "unverified_claims": doc.unverified_claims,
            "duration_ms": doc.duration_ms,
            "phase_count": len(doc.phases),
            "created_at": doc.created_at,
            "deleted_at": None,
        })

        for phase in doc.phases:
            ref = roadmap_ref.collection(_COL_PHASES).document(phase.id)
            batch.set(ref, {
                "order": phase.order,
                "title": phase.title,
                "duration_weeks": phase.duration_weeks,
                "milestones": phase.milestones,
                "skills_to_gain": phase.skills_to_gain,
                "confidence": phase.confidence,
            })

        for habit in doc.weekly_habits:
            ref = roadmap_ref.collection(_COL_WEEKLY_HABITS).document(habit.id)
            batch.set(ref, {"order": habit.order, "text": habit.text})

        for step in doc.next_steps:
            ref = roadmap_ref.collection(_COL_NEXT_STEPS).document(step.id)
            batch.set(ref, {"order": step.order, "action": step.action})

        await batch.commit()
        logger.info("roadmap.saved", roadmap_id=doc.id, user_id=doc.user_id)
        return doc.id

    async def get(self, roadmap_id: str, user_id: str) -> RoadmapDocument | None:
        """Return the full roadmap with all subcollection data, or None."""
        ref = self._col.document(roadmap_id)
        snap = await ref.get()
        if not snap.exists:
            return None

        data: dict = snap.to_dict() or {}
        if data.get("user_id") != user_id:
            return None
        if data.get("deleted_at") is not None:
            return None

        phases = await self._load_phases(ref)
        habits = await self._load_habits(ref)
        steps = await self._load_next_steps(ref)

        return RoadmapDocument(
            id=snap.id,
            user_id=data["user_id"],
            session_id=data["session_id"],
            request_id=data["request_id"],
            summary=data["summary"],
            confidence=data["confidence"],
            status=data["status"],
            validation_passed=data.get("validation_passed", True),
            unverified_claims=data.get("unverified_claims", []),
            duration_ms=data.get("duration_ms", 0),
            phases=phases,
            weekly_habits=habits,
            next_steps=steps,
            created_at=data["created_at"],
            deleted_at=data.get("deleted_at"),
        )

    async def list_for_user(
        self,
        user_id: str,
        limit: int = 20,
        include_deleted: bool = False,
    ) -> list[RoadmapSummary]:
        """Return lightweight summaries newest-first.

        Sorting is done in Python to avoid a Firestore composite index on
        (user_id ASC, created_at DESC).  We fetch up to ``limit * 2`` docs
        to have enough headroom after filtering soft-deleted entries.
        """
        query = (
            self._col
            .where("user_id", "==", user_id)
            .limit(limit * 2)
        )
        summaries: list[RoadmapSummary] = []
        async for snap in query.stream():
            data: dict = snap.to_dict() or {}
            if not include_deleted and data.get("deleted_at") is not None:
                continue
            summaries.append(RoadmapSummary(
                id=snap.id,
                user_id=data["user_id"],
                session_id=data["session_id"],
                request_id=data["request_id"],
                summary=data["summary"],
                confidence=data["confidence"],
                status=data["status"],
                phase_count=data.get("phase_count", 0),
                created_at=data["created_at"],
                deleted_at=data.get("deleted_at"),
            ))
        summaries.sort(key=lambda s: s.created_at, reverse=True)
        return summaries[:limit]

    async def list_for_user_paginated(
        self,
        user_id: str,
        limit: int = 20,
        cursor: str | None = None,
    ) -> tuple[list[RoadmapSummary], str | None]:
        """Cursor-based keyset pagination ordered by created_at DESC.

        ``cursor`` is the ISO-8601 created_at timestamp of the last item
        returned by the previous page.  Returns (summaries, next_cursor)
        where next_cursor is None when no further pages exist.
        """
        query = (
            self._col
            .where("user_id", "==", user_id)
            .where("deleted_at", "==", None)
            .order_by("created_at", direction=FSQuery.DESCENDING)
            .limit(limit + 1)
        )

        if cursor:
            try:
                cursor_dt = datetime.fromisoformat(cursor)
                query = query.start_after({"created_at": cursor_dt})
            except ValueError:
                pass

        summaries: list[RoadmapSummary] = []
        async for snap in query.stream():
            data: dict = snap.to_dict() or {}
            summaries.append(RoadmapSummary(
                id=snap.id,
                user_id=data["user_id"],
                session_id=data["session_id"],
                request_id=data["request_id"],
                summary=data["summary"],
                confidence=data["confidence"],
                status=data["status"],
                phase_count=data.get("phase_count", 0),
                created_at=data["created_at"],
                deleted_at=data.get("deleted_at"),
            ))

        next_cursor: str | None = None
        has_more = len(summaries) > limit
        if has_more:
            summaries = summaries[:limit]
            next_cursor = summaries[-1].created_at.isoformat()

        return summaries, next_cursor

    async def soft_delete(self, roadmap_id: str, user_id: str) -> None:
        """Set ``deleted_at``; does nothing if the document does not exist."""
        ref = self._col.document(roadmap_id)
        snap = await ref.get()
        if not snap.exists:
            return
        owner = (snap.to_dict() or {}).get("user_id")
        if owner != user_id:
            raise PermissionError(
                f"roadmap {roadmap_id!r} is not owned by user {user_id!r}"
            )
        await ref.update({"deleted_at": datetime.now(timezone.utc)})
        logger.info("roadmap.soft_deleted", roadmap_id=roadmap_id, user_id=user_id)

    # ── Private subcollection loaders ─────────────────────────────────────────

    async def _load_phases(self, roadmap_ref: AsyncDocumentReference) -> list[RoadmapPhase]:
        phases: list[RoadmapPhase] = []
        async for snap in roadmap_ref.collection(_COL_PHASES).order_by("order").stream():
            d: dict = snap.to_dict() or {}
            phases.append(RoadmapPhase(
                id=snap.id,
                order=d["order"],
                title=d["title"],
                duration_weeks=d["duration_weeks"],
                milestones=d.get("milestones", []),
                skills_to_gain=d.get("skills_to_gain", []),
                confidence=d.get("confidence", 1.0),
            ))
        return phases

    async def _load_habits(self, roadmap_ref: AsyncDocumentReference) -> list[WeeklyHabit]:
        habits: list[WeeklyHabit] = []
        async for snap in roadmap_ref.collection(_COL_WEEKLY_HABITS).order_by("order").stream():
            d: dict = snap.to_dict() or {}
            habits.append(WeeklyHabit(id=snap.id, order=d["order"], text=d["text"]))
        return habits

    async def _load_next_steps(self, roadmap_ref: AsyncDocumentReference) -> list[NextStep]:
        steps: list[NextStep] = []
        async for snap in roadmap_ref.collection(_COL_NEXT_STEPS).order_by("order").stream():
            d: dict = snap.to_dict() or {}
            steps.append(NextStep(id=snap.id, order=d["order"], action=d["action"]))
        return steps
