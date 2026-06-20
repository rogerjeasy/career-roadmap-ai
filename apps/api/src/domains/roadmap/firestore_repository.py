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
from uuid import uuid4

from google.cloud.firestore_v1 import Query as FSQuery
from google.cloud.firestore_v1.async_client import AsyncClient
from google.cloud.firestore_v1.async_document import AsyncDocumentReference

from src.core.logging import get_logger
from src.domains.roadmap.schemas import (
    ActionItem,
    LearningResource,
    NextStep,
    RoadmapDocument,
    RoadmapPhase,
    RoadmapSummary,
    SkillItem,
    WeeklyHabit,
    WeeklyTask,
)

logger = get_logger(__name__)

_COL_ROADMAPS = "roadmaps"
_COL_PHASES = "phases"
_COL_WEEKLY_HABITS = "weekly_habits"
_COL_NEXT_STEPS = "next_steps"
_COL_MARKET_DATA = "market_data"
# Per-user milestone completion, keyed `{user_id}_{roadmap_id}` so a user can
# only ever read or write their own progress document.
_COL_PROGRESS = "roadmap_progress"


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
            "market_grounding": doc.market_grounding,
            "created_at": doc.created_at,
            "deleted_at": None,
        })

        for phase in doc.phases:
            ref = roadmap_ref.collection(_COL_PHASES).document(phase.id)
            batch.set(ref, {
                "order": phase.order,
                "title": phase.title,
                "description": phase.description,
                "duration_weeks": phase.duration_weeks,
                "goals": phase.goals,
                "milestones": phase.milestones,
                "skills_to_gain": phase.skills_to_gain,
                "skills": [
                    {"text": s.text, "is_priority": s.is_priority, "display_order": s.display_order}
                    for s in phase.skills
                ],
                "actions": [
                    {"text": a.text, "sub_text": a.sub_text, "display_order": a.display_order}
                    for a in phase.actions
                ],
                "gaps_addressed": phase.gaps_addressed,
                "market_relevance": phase.market_relevance,
                "difficulty": phase.difficulty,
                "deliverables": phase.deliverables,
                "confidence": phase.confidence,
                "resources": [
                    {
                        "title": r.title,
                        "resource_type": r.resource_type,
                        "provider": r.provider,
                        "difficulty": r.difficulty,
                        "tags": r.tags,
                        "url": r.url,
                        "estimated_hours": r.estimated_hours,
                        "is_free": r.is_free,
                        "description": r.description,
                    }
                    for r in phase.resources
                ],
                "curated_resources": [
                    {
                        "title": r.title,
                        "resource_type": r.resource_type,
                        "provider": r.provider,
                        "difficulty": r.difficulty,
                        "tags": r.tags,
                        "url": r.url,
                        "estimated_hours": r.estimated_hours,
                        "is_free": r.is_free,
                        "description": r.description,
                    }
                    for r in phase.curated_resources
                ],
                "weekly_tasks": [
                    {
                        "week_number": t.week_number,
                        "focus_area": t.focus_area,
                        "tasks": t.tasks,
                        "estimated_hours": t.estimated_hours,
                        "deliverable": t.deliverable,
                    }
                    for t in phase.weekly_tasks
                ],
            })

        for habit in doc.weekly_habits:
            ref = roadmap_ref.collection(_COL_WEEKLY_HABITS).document(habit.id)
            batch.set(ref, {
                "order": habit.order,
                "text": habit.text,
                "frequency": habit.frequency,
                "duration_minutes": habit.duration_minutes,
                "rationale": habit.rationale,
            })

        for step in doc.next_steps:
            ref = roadmap_ref.collection(_COL_NEXT_STEPS).document(step.id)
            batch.set(ref, {"order": step.order, "action": step.action})

        await batch.commit()
        logger.info("roadmap.saved", roadmap_id=doc.id, user_id=doc.user_id)
        return doc.id

    async def restore_in_place(self, doc: RoadmapDocument) -> str:
        """Overwrite a roadmap with snapshot content, clearing stale subcollection docs.

        ``save`` writes subcollection docs by id but never removes ones absent from
        the incoming document, so restoring a snapshot with fewer phases/habits/steps
        would otherwise leave orphans. This deletes the existing subcollection docs
        first, then delegates to ``save`` for the (single-batch) rewrite.
        """
        roadmap_ref = self._col.document(doc.id)
        for col in (_COL_PHASES, _COL_WEEKLY_HABITS, _COL_NEXT_STEPS):
            async for snap in roadmap_ref.collection(col).stream():
                await snap.reference.delete()
        logger.info("roadmap.restore_cleared", roadmap_id=doc.id, user_id=doc.user_id)
        return await self.save(doc)

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
        market_grounding = await self._load_market_grounding(ref)

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
            market_grounding=data.get("market_grounding") or market_grounding,
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

    # ── Milestone progress ────────────────────────────────────────────────────

    def _progress_ref(self, roadmap_id: str, user_id: str) -> AsyncDocumentReference:
        return self._db.collection(_COL_PROGRESS).document(f"{user_id}_{roadmap_id}")

    async def get_progress(
        self, roadmap_id: str, user_id: str
    ) -> tuple[list[str], datetime | None]:
        snap = await self._progress_ref(roadmap_id, user_id).get()
        if not snap.exists:
            return [], None
        data: dict = snap.to_dict() or {}
        completed = [str(k) for k in data.get("completed_milestones", [])]
        return completed, data.get("updated_at")

    async def set_progress(
        self, roadmap_id: str, user_id: str, completed: list[str]
    ) -> datetime:
        now = datetime.now(timezone.utc)
        await self._progress_ref(roadmap_id, user_id).set({
            "user_id": user_id,
            "roadmap_id": roadmap_id,
            "completed_milestones": completed,
            "updated_at": now,
        })
        logger.info(
            "roadmap.progress_saved",
            roadmap_id=roadmap_id,
            user_id=user_id,
            completed_count=len(completed),
        )
        return now

    # ── Phase editing ─────────────────────────────────────────────────────────

    async def _owned_root(
        self, roadmap_id: str, user_id: str
    ) -> AsyncDocumentReference | None:
        """Return the root doc ref iff it exists, is owned by the user, and is live."""
        ref = self._col.document(roadmap_id)
        snap = await ref.get()
        if not snap.exists:
            return None
        data: dict = snap.to_dict() or {}
        if data.get("user_id") != user_id or data.get("deleted_at") is not None:
            return None
        return ref

    async def update_phase(
        self, roadmap_id: str, user_id: str, phase_id: str, updates: dict
    ) -> bool:
        """Patch allowed fields on a single phase. Returns False if not found."""
        root = await self._owned_root(roadmap_id, user_id)
        if root is None:
            return False
        phase_ref = root.collection(_COL_PHASES).document(phase_id)
        snap = await phase_ref.get()
        if not snap.exists:
            return False
        if updates:
            await phase_ref.update(updates)
        logger.info(
            "roadmap.phase_updated",
            roadmap_id=roadmap_id,
            user_id=user_id,
            phase_id=phase_id,
            fields=sorted(updates),
        )
        return True

    async def add_phase(
        self, roadmap_id: str, user_id: str, phase_data: dict
    ) -> str | None:
        """Append a new phase ordered after the current last. Returns its id."""
        root = await self._owned_root(roadmap_id, user_id)
        if root is None:
            return None

        phases_col = root.collection(_COL_PHASES)
        max_order = 0
        count = 0
        async for snap in phases_col.stream():
            count += 1
            order = (snap.to_dict() or {}).get("order", 0)
            if order > max_order:
                max_order = order

        phase_id = uuid4().hex
        doc = {
            "order": max_order + 1,
            "title": phase_data.get("title", ""),
            "description": phase_data.get("description", ""),
            "duration_weeks": phase_data.get("duration_weeks", 0),
            "goals": [],
            "milestones": phase_data.get("milestones", []),
            "skills_to_gain": phase_data.get("skills_to_gain", []),
            "skills": [],
            "actions": [],
            "gaps_addressed": [],
            "market_relevance": "",
            "difficulty": "intermediate",
            "deliverables": [],
            "confidence": 1.0,
            "resources": [],
            "curated_resources": [],
            "weekly_tasks": [],
        }
        await phases_col.document(phase_id).set(doc)
        await root.update({"phase_count": count + 1})
        logger.info("roadmap.phase_added", roadmap_id=roadmap_id, user_id=user_id, phase_id=phase_id)
        return phase_id

    async def delete_phase(self, roadmap_id: str, user_id: str, phase_id: str) -> bool:
        """Remove a phase. Returns False if the roadmap or phase is missing."""
        root = await self._owned_root(roadmap_id, user_id)
        if root is None:
            return False
        phase_ref = root.collection(_COL_PHASES).document(phase_id)
        snap = await phase_ref.get()
        if not snap.exists:
            return False
        await phase_ref.delete()

        remaining = 0
        async for _ in root.collection(_COL_PHASES).stream():
            remaining += 1
        await root.update({"phase_count": remaining})
        logger.info("roadmap.phase_deleted", roadmap_id=roadmap_id, user_id=user_id, phase_id=phase_id)
        return True

    async def reorder_phases(
        self, roadmap_id: str, user_id: str, ordered_ids: list[str]
    ) -> bool:
        """Reassign 1-based ``order`` to each phase in the given id sequence."""
        root = await self._owned_root(roadmap_id, user_id)
        if root is None:
            return False
        batch = self._db.batch()
        for index, phase_id in enumerate(ordered_ids):
            batch.update(root.collection(_COL_PHASES).document(phase_id), {"order": index + 1})
        await batch.commit()
        logger.info("roadmap.phases_reordered", roadmap_id=roadmap_id, user_id=user_id)
        return True

    # ── Private subcollection loaders ─────────────────────────────────────────

    async def _load_phases(self, roadmap_ref: AsyncDocumentReference) -> list[RoadmapPhase]:
        phases: list[RoadmapPhase] = []
        async for snap in roadmap_ref.collection(_COL_PHASES).order_by("order").stream():
            d: dict = snap.to_dict() or {}

            resources = [
                LearningResource(
                    title=r.get("title", ""),
                    resource_type=r.get("resource_type", "tutorial"),
                    provider=r.get("provider", ""),
                    difficulty=r.get("difficulty", "intermediate"),
                    tags=r.get("tags", []),
                    url=r.get("url"),
                    estimated_hours=r.get("estimated_hours"),
                    is_free=bool(r.get("is_free", True)),
                    description=r.get("description", ""),
                )
                for r in d.get("resources", [])
            ]
            curated_resources = [
                LearningResource(
                    title=r.get("title", ""),
                    resource_type=r.get("resource_type", "tutorial"),
                    provider=r.get("provider", ""),
                    difficulty=r.get("difficulty", "intermediate"),
                    tags=r.get("tags", []),
                    url=r.get("url"),
                    estimated_hours=r.get("estimated_hours"),
                    is_free=bool(r.get("is_free", True)),
                    description=r.get("description", ""),
                )
                for r in d.get("curated_resources", [])
            ]
            weekly_tasks = [
                WeeklyTask(
                    week_number=int(t.get("week_number", 0)),
                    focus_area=t.get("focus_area", ""),
                    tasks=t.get("tasks", []),
                    estimated_hours=float(t.get("estimated_hours", 0)),
                    deliverable=t.get("deliverable"),
                )
                for t in d.get("weekly_tasks", [])
            ]

            skills = [
                SkillItem(
                    text=s.get("text", ""),
                    is_priority=bool(s.get("is_priority", False)),
                    display_order=int(s.get("display_order", i)),
                )
                for i, s in enumerate(d.get("skills", []))
                if isinstance(s, dict)
            ]
            actions = [
                ActionItem(
                    text=a.get("text", ""),
                    sub_text=a.get("sub_text", ""),
                    display_order=int(a.get("display_order", i)),
                )
                for i, a in enumerate(d.get("actions", []))
                if isinstance(a, dict)
            ]

            phases.append(RoadmapPhase(
                id=snap.id,
                order=d["order"],
                title=d.get("title", ""),
                description=d.get("description", ""),
                duration_weeks=d.get("duration_weeks", 0),
                goals=d.get("goals", []),
                milestones=d.get("milestones", []),
                skills_to_gain=d.get("skills_to_gain", []),
                skills=skills,
                actions=actions,
                gaps_addressed=d.get("gaps_addressed", []),
                market_relevance=d.get("market_relevance", ""),
                difficulty=d.get("difficulty", "intermediate"),
                deliverables=d.get("deliverables", []),
                confidence=d.get("confidence", 1.0),
                resources=resources,
                curated_resources=curated_resources,
                weekly_tasks=weekly_tasks,
            ))
        return phases

    async def _load_habits(self, roadmap_ref: AsyncDocumentReference) -> list[WeeklyHabit]:
        habits: list[WeeklyHabit] = []
        async for snap in roadmap_ref.collection(_COL_WEEKLY_HABITS).order_by("order").stream():
            d: dict = snap.to_dict() or {}
            habits.append(WeeklyHabit(
                id=snap.id,
                order=d["order"],
                text=d.get("text", ""),
                frequency=d.get("frequency", "daily"),
                duration_minutes=int(d.get("duration_minutes", 0)),
                rationale=d.get("rationale", ""),
            ))
        return habits

    async def _load_next_steps(self, roadmap_ref: AsyncDocumentReference) -> list[NextStep]:
        steps: list[NextStep] = []
        async for snap in roadmap_ref.collection(_COL_NEXT_STEPS).order_by("order").stream():
            d: dict = snap.to_dict() or {}
            steps.append(NextStep(id=snap.id, order=d["order"], action=d["action"]))
        return steps

    async def _load_market_grounding(self, roadmap_ref: AsyncDocumentReference) -> dict:
        """Load market intelligence from its subcollection snapshot, if present."""
        try:
            snap = await roadmap_ref.collection(_COL_MARKET_DATA).document("snapshot").get()
            if snap.exists:
                return snap.to_dict() or {}
        except Exception:
            pass
        return {}
