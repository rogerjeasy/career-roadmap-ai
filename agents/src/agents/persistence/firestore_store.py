"""Firestore implementation of IRoadmapStore.

Uses ``google-cloud-firestore`` directly (not firebase_admin) so the agents
package stays free of Firebase Admin SDK imports.  The same Firestore project
is accessed; only the initialisation path differs from the API layer.

Firestore layout (mirrors apps/api/src/domains/roadmap/firestore_repository.py):
  roadmaps/{roadmap_id}                     ← core metadata
  roadmaps/{roadmap_id}/phases/{id}         ← career phases (ordered)
  roadmaps/{roadmap_id}/weekly_habits/{id}  ← recurring habits (ordered)
  roadmaps/{roadmap_id}/next_steps/{id}     ← immediate action items (ordered)

All four writes are committed in a single Firestore batch for atomicity.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import TYPE_CHECKING
from uuid import uuid4

from agents.contracts.results import OrchestratorResult
from agents.core.logging import get_logger

if TYPE_CHECKING:
    from agents.config import AgentSettings
    from google.cloud.firestore_v1.async_client import AsyncClient

logger = get_logger(__name__)

_COL_ROADMAPS = "roadmaps"
_COL_PHASES = "phases"
_COL_WEEKLY_HABITS = "weekly_habits"
_COL_NEXT_STEPS = "next_steps"


class FirestoreRoadmapStore:
    """Persists completed OrchestratorResult objects to Firestore.

    Inject an instance via the constructor; use ``from_settings()`` as the
    production factory.  In tests, inject a spy/stub without any Firebase setup.
    """

    def __init__(self, client: "AsyncClient") -> None:
        self._db = client

    # ── Factory ───────────────────────────────────────────────────────────────

    @classmethod
    async def from_settings(cls, settings: "AgentSettings") -> "FirestoreRoadmapStore":
        """Build a client from agent settings — raises if credentials are missing."""
        from agents.persistence._client import make_async_client  # noqa: PLC0415

        project = settings.firebase_project_id
        if not project:
            raise ValueError("FIREBASE_PROJECT_ID is not configured in agent settings")

        client = await make_async_client(
            project=project,
            credentials_json=getattr(settings, "firebase_credentials_json", None),
            credentials_path=getattr(settings, "firebase_credentials_path", None),
        )
        return cls(client)

    # ── IRoadmapStore ─────────────────────────────────────────────────────────

    async def save(self, result: OrchestratorResult) -> str:
        """Write the roadmap + subcollections in one atomic batch."""
        roadmap_data = result.roadmap or {}
        roadmap_id = str(uuid4())
        now = datetime.now(timezone.utc)

        phases: list[dict] = roadmap_data.get("phases", [])
        weekly_habits: list = roadmap_data.get("weekly_habits", [])
        next_steps: list = roadmap_data.get("next_steps", [])

        roadmap_ref = self._db.collection(_COL_ROADMAPS).document(roadmap_id)
        batch = self._db.batch()

        batch.set(roadmap_ref, {
            "user_id": result.user_id,
            "session_id": result.session_id,
            "request_id": result.request_id,
            "summary": roadmap_data.get("summary", ""),
            "confidence": roadmap_data.get("confidence", result.confidence),
            "status": result.status.value,
            "validation_passed": result.validation_passed,
            "unverified_claims": roadmap_data.get("unverified_claims", []),
            "duration_ms": result.duration_ms,
            "phase_count": len(phases),
            "created_at": now,
            "deleted_at": None,
        })

        for i, phase in enumerate(phases):
            phase_ref = roadmap_ref.collection(_COL_PHASES).document(str(uuid4()))
            batch.set(phase_ref, {
                "order": i,
                "title": phase.get("title", ""),
                "duration_weeks": int(phase.get("duration_weeks", 0)),
                "milestones": list(phase.get("milestones", [])),
                "skills_to_gain": list(phase.get("skills_to_gain", [])),
                "confidence": float(phase.get("confidence", 1.0)),
            })

        for i, habit in enumerate(weekly_habits):
            habit_ref = roadmap_ref.collection(_COL_WEEKLY_HABITS).document(str(uuid4()))
            batch.set(habit_ref, {"order": i, "text": str(habit)})

        for i, step in enumerate(next_steps):
            step_ref = roadmap_ref.collection(_COL_NEXT_STEPS).document(str(uuid4()))
            batch.set(step_ref, {"order": i, "action": str(step)})

        await batch.commit()

        logger.info(
            "roadmap.persisted",
            roadmap_id=roadmap_id,
            user_id=result.user_id,
            session_id=result.session_id,
            phase_count=len(phases),
            habit_count=len(weekly_habits),
            step_count=len(next_steps),
        )
        return roadmap_id
