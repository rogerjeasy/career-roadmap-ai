"""Firestore implementation of IRoadmapStore — incremental, per-agent persistence.

Each specialist agent writes its part of the roadmap as soon as it finishes:

  RoadmapGenerationAgent  → phases/{phase_N}  (rich: resources, weekly_tasks, goals)
                          → weekly_habits/{id}
  MarketIntelligenceAgent → market_data/snapshot
  GapAnalysisAgent        → gap_analysis/snapshot
  LearningResourcesAgent  → updates phases/{phase_N}.resources with curated links

SynthesizerNode (via ``finalize``) writes:
  → root document: summary, confidence, validation_passed, unverified_claims,
                   duration_ms, status="completed"
  → next_steps/{id}

Firestore layout:
  roadmaps/{id}
    user_id, session_id, request_id, status, phase_count, market_grounding
    summary, confidence, validation_passed, unverified_claims, duration_ms
    created_at, deleted_at

  roadmaps/{id}/phases/{phase_N}
    order, title, description, duration_weeks
    goals, milestones, skills_to_gain, gaps_addressed
    market_relevance, difficulty, deliverables, confidence
    resources: [{title, resource_type, provider, difficulty, tags,
                 url, estimated_hours, is_free, description}]
    weekly_tasks: [{week_number, focus_area, tasks, estimated_hours, deliverable}]

  roadmaps/{id}/weekly_habits/{id}         order, text, frequency, duration_minutes, rationale
  roadmaps/{id}/next_steps/{id}            order, action
  roadmaps/{id}/market_data/snapshot       market_summary, trending_skills, job_postings, ...
  roadmaps/{id}/gap_analysis/snapshot      prioritised_gaps, dimension_scores, overall_readiness
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any
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
_COL_MARKET_DATA = "market_data"
_COL_GAP_ANALYSIS = "gap_analysis"

# Agents whose outputs have dedicated persistence handlers.
_AGENT_HANDLERS: frozenset[str] = frozenset({
    "roadmap_generation",
    "market_intelligence",
    "gap_analysis",
    "learning_resources",
})


class FirestoreRoadmapStore:
    """Persists roadmap data incrementally as each agent completes."""

    def __init__(self, client: "AsyncClient") -> None:
        self._db = client

    # ── Factory ───────────────────────────────────────────────────────────────

    @classmethod
    async def from_settings(cls, settings: "AgentSettings") -> "FirestoreRoadmapStore":
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

    async def create_skeleton(
        self,
        user_id: str,
        session_id: str,
        request_id: str,
    ) -> str:
        """Create a placeholder roadmap document (status=processing) and return its ID."""
        roadmap_id = str(uuid4())
        now = datetime.now(timezone.utc)
        ref = self._db.collection(_COL_ROADMAPS).document(roadmap_id)
        await ref.set({
            "user_id": user_id,
            "session_id": session_id,
            "request_id": request_id,
            "status": "processing",
            "summary": "",
            "confidence": 0.0,
            "validation_passed": False,
            "unverified_claims": [],
            "duration_ms": 0,
            "phase_count": 0,
            "market_grounding": {},
            "created_at": now,
            "deleted_at": None,
        })
        logger.info("roadmap.skeleton_created", roadmap_id=roadmap_id, user_id=user_id)
        return roadmap_id

    async def persist_agent_output(
        self,
        roadmap_id: str,
        agent_type: str,
        output: dict[str, Any],
    ) -> None:
        """Route agent output to the appropriate writer. Unknown agents are skipped."""
        if not roadmap_id or agent_type not in _AGENT_HANDLERS:
            return
        try:
            if agent_type == "roadmap_generation":
                await self._persist_roadmap_generation(roadmap_id, output)
            elif agent_type == "market_intelligence":
                await self._persist_market_intelligence(roadmap_id, output)
            elif agent_type == "gap_analysis":
                await self._persist_gap_analysis(roadmap_id, output)
            elif agent_type == "learning_resources":
                await self._persist_learning_resources(roadmap_id, output)
        except Exception as exc:
            logger.error(
                "roadmap.agent_persist_failed",
                roadmap_id=roadmap_id,
                agent_type=agent_type,
                error=str(exc),
                exc_info=True,
            )

    async def finalize(self, roadmap_id: str, result: OrchestratorResult) -> None:
        """Update root document and write next_steps; set status=completed."""
        if not roadmap_id:
            return

        roadmap_data = result.roadmap or {}
        ref = self._db.collection(_COL_ROADMAPS).document(roadmap_id)
        batch = self._db.batch()

        batch.update(ref, {
            "status": result.status.value,
            "summary": roadmap_data.get("summary", ""),
            "confidence": float(roadmap_data.get("confidence", result.confidence)),
            "validation_passed": result.validation_passed,
            "unverified_claims": roadmap_data.get("unverified_claims", []),
            "duration_ms": result.duration_ms,
        })

        next_steps: list = roadmap_data.get("next_steps", [])
        for i, step in enumerate(next_steps):
            step_ref = ref.collection(_COL_NEXT_STEPS).document(str(uuid4()))
            batch.set(step_ref, {"order": i, "action": str(step)})

        # Persist weekly_habits from synthesizer only when roadmap_generation did
        # not run (e.g. it was stubbed or failed) — checked by looking at phase_count.
        snap = await ref.get()
        snap_data: dict = snap.to_dict() or {}
        if snap_data.get("phase_count", 0) == 0:
            weekly_habits: list = roadmap_data.get("weekly_habits", [])
            for i, habit in enumerate(weekly_habits):
                habit_ref = ref.collection(_COL_WEEKLY_HABITS).document(str(uuid4()))
                batch.set(habit_ref, {"order": i, "text": str(habit), "frequency": "", "duration_minutes": 0, "rationale": ""})

        await batch.commit()
        logger.info(
            "roadmap.finalized",
            roadmap_id=roadmap_id,
            user_id=result.user_id,
            status=result.status.value,
            next_step_count=len(next_steps),
        )

    # ── Agent-specific writers ─────────────────────────────────────────────────

    async def _persist_roadmap_generation(self, roadmap_id: str, output: dict[str, Any]) -> None:
        """Persist rich phase data, habits, and market grounding from RoadmapAgent."""
        phases: list[dict] = output.get("phases", [])
        milestones: list[dict] = output.get("milestones", [])
        weekly_schedule: list[dict] = output.get("weekly_schedule", [])
        habits: list[dict] = output.get("habits", [])
        resources: list[dict] = output.get("resources", [])
        market_grounding: dict = output.get("market_grounding", {})

        # Build lookup maps keyed by phase index
        milestones_by_phase: dict[int, list[str]] = {}
        for m in milestones:
            idx = int(m.get("phase_index", 0))
            milestones_by_phase.setdefault(idx, []).append(
                m.get("name") or m.get("description", "")
            )

        tasks_by_phase: dict[int, list[dict]] = {}
        for t in weekly_schedule:
            idx = int(t.get("phase_index", 0))
            tasks_by_phase.setdefault(idx, []).append(t)

        resources_by_phase: dict[int, list[dict]] = {}
        for r in resources:
            idx = int(r.get("phase_index", 0))
            resources_by_phase.setdefault(idx, []).append(r)

        roadmap_ref = self._db.collection(_COL_ROADMAPS).document(roadmap_id)
        batch = self._db.batch()

        # Write each phase as a sub-document with a stable ID (phase_N)
        for phase in phases:
            phase_idx = int(phase.get("index", 0))
            phase_ref = roadmap_ref.collection(_COL_PHASES).document(f"phase_{phase_idx}")

            phase_milestones = milestones_by_phase.get(phase_idx, [])
            phase_resources = [
                {
                    "title": r.get("title", ""),
                    "resource_type": r.get("resource_type", "tutorial"),
                    "provider": r.get("provider", ""),
                    "difficulty": r.get("difficulty", "intermediate"),
                    "tags": r.get("tags", []),
                    "url": r.get("url"),
                    "estimated_hours": r.get("estimated_hours"),
                    "is_free": bool(r.get("is_free", True)),
                    "description": r.get("description", ""),
                }
                for r in resources_by_phase.get(phase_idx, [])
            ]
            phase_weekly_tasks = [
                {
                    "week_number": int(t.get("week_number", 0)),
                    "focus_area": t.get("focus_area", ""),
                    "tasks": list(t.get("tasks", [])),
                    "estimated_hours": float(t.get("estimated_hours", 0)),
                    "deliverable": t.get("deliverable"),
                }
                for t in tasks_by_phase.get(phase_idx, [])
            ]

            raw_skills = phase.get("skills", [])
            serialised_skills = [
                {
                    "text": str(s.get("text", "")),
                    "is_priority": bool(s.get("is_priority", False)),
                    "display_order": int(s.get("display_order", i)),
                }
                for i, s in enumerate(raw_skills)
                if isinstance(s, dict)
            ]

            raw_actions = phase.get("actions", [])
            serialised_actions = [
                {
                    "text": str(a.get("text", "")),
                    "sub_text": str(a.get("sub_text", "")),
                    "display_order": int(a.get("display_order", i)),
                }
                for i, a in enumerate(raw_actions)
                if isinstance(a, dict)
            ]

            batch.set(phase_ref, {
                "order": phase_idx,
                "title": phase.get("title", ""),
                "description": phase.get("description", ""),
                "duration_weeks": int(phase.get("duration_weeks", 0)),
                "goals": list(phase.get("goals", [])),
                "milestones": phase_milestones,
                "skills_to_gain": list(phase.get("skills_to_acquire", [])),
                "skills": serialised_skills,
                "actions": serialised_actions,
                "gaps_addressed": list(phase.get("gaps_addressed", [])),
                "market_relevance": phase.get("market_relevance", ""),
                "difficulty": phase.get("difficulty", "intermediate"),
                "deliverables": [
                    m.get("deliverable", "")
                    for m in milestones
                    if m.get("phase_index") == phase_idx and m.get("deliverable")
                ],
                "confidence": float(phase.get("confidence", 1.0)) if "confidence" in phase else 1.0,
                "resources": phase_resources,
                "weekly_tasks": phase_weekly_tasks,
            })

        # Write habits
        for i, habit in enumerate(habits):
            habit_ref = roadmap_ref.collection(_COL_WEEKLY_HABITS).document(str(uuid4()))
            batch.set(habit_ref, {
                "order": i,
                "text": habit.get("name", ""),
                "frequency": habit.get("frequency", "daily"),
                "duration_minutes": int(habit.get("duration_minutes", 0)),
                "rationale": habit.get("rationale", ""),
            })

        # Update root doc
        batch.update(roadmap_ref, {
            "phase_count": len(phases),
            "market_grounding": market_grounding,
        })

        await batch.commit()
        logger.info(
            "roadmap.roadmap_generation_persisted",
            roadmap_id=roadmap_id,
            phase_count=len(phases),
            habit_count=len(habits),
            resource_count=len(resources),
        )

    async def _persist_market_intelligence(self, roadmap_id: str, output: dict[str, Any]) -> None:
        """Save market intelligence snapshot to its own subcollection."""
        ref = (
            self._db.collection(_COL_ROADMAPS)
            .document(roadmap_id)
            .collection(_COL_MARKET_DATA)
            .document("snapshot")
        )
        trending_skills: list[dict] = output.get("trending_skills", [])
        job_postings: list[dict] = output.get("job_postings", [])
        await ref.set({
            "market_summary": output.get("market_summary", ""),
            "trending_skills": trending_skills[:20],
            "job_posting_count": len(job_postings),
            "job_postings": job_postings[:50],
            "salary_benchmark": output.get("salary_benchmark"),
            "country": output.get("country", ""),
            "role": output.get("role", ""),
            "fetched_at": output.get("fetched_at", ""),
        })
        logger.info("roadmap.market_intelligence_persisted", roadmap_id=roadmap_id)

    async def _persist_gap_analysis(self, roadmap_id: str, output: dict[str, Any]) -> None:
        """Save gap analysis snapshot."""
        ref = (
            self._db.collection(_COL_ROADMAPS)
            .document(roadmap_id)
            .collection(_COL_GAP_ANALYSIS)
            .document("snapshot")
        )
        await ref.set({
            "prioritised_gaps": output.get("prioritised_gaps", []),
            "dimension_scores": output.get("dimension_scores", {}),
            "overall_readiness": float(output.get("overall_readiness", 0.0)),
            "role": output.get("role", ""),
            "analysed_at": output.get("analysed_at", ""),
        })
        logger.info("roadmap.gap_analysis_persisted", roadmap_id=roadmap_id)

    async def _persist_learning_resources(self, roadmap_id: str, output: dict[str, Any]) -> None:
        """Enrich phase documents with curated resources from LearningAgent."""
        roadmap_ref = self._db.collection(_COL_ROADMAPS).document(roadmap_id)
        roadmap_embeddings: list[dict] = output.get("roadmap_embeddings", [])
        if not roadmap_embeddings:
            return

        batch = self._db.batch()
        for embedding in roadmap_embeddings:
            phase_idx = int(embedding.get("phase_index", 0))
            resources: list[dict] = embedding.get("resources", [])
            if not resources:
                continue
            phase_ref = roadmap_ref.collection(_COL_PHASES).document(f"phase_{phase_idx}")
            serialised = [
                {
                    "title": r.get("title", ""),
                    "resource_type": r.get("resource_type", "course"),
                    "provider": r.get("provider", ""),
                    "difficulty": r.get("difficulty", "intermediate"),
                    "tags": r.get("tags", []),
                    "url": r.get("url"),
                    "estimated_hours": r.get("estimated_hours"),
                    "is_free": bool(r.get("is_free", True)),
                    "description": r.get("description", ""),
                }
                for r in resources
            ]
            # Merge: append curated resources from the learning agent (avoid full overwrite)
            batch.update(phase_ref, {"curated_resources": serialised})

        await batch.commit()
        logger.info(
            "roadmap.learning_resources_persisted",
            roadmap_id=roadmap_id,
            phase_count=len(roadmap_embeddings),
        )
