"""Scheduled application-reminder sweep.

A Celery-beat tick (registered in ``agents.bus.celery_app`` as
``applications.scan_due_reminders``) calls this every few minutes. The task
scans all applications and fires a web-push for each reminder that has come due,
marking it so it is never sent twice.

The task lives in the API layer (not the agents package) because it depends on
the API's Firestore client and ``PushService``. It registers on the shared
Celery app by being imported from ``src.tasks.worker`` at worker startup.
"""
from __future__ import annotations

import asyncio

import structlog

from agents.bus.celery_app import celery_app

logger = structlog.get_logger(__name__)


@celery_app.task(
    name="applications.scan_due_reminders",
    queue="agents.default",
    acks_late=True,
)
def scan_due_reminders() -> int:
    """Sync Celery entrypoint — runs the async sweep on its own event loop."""
    return asyncio.run(_scan())


async def _scan() -> int:
    # Late imports keep the agent-only worker cold-start cheap.
    from src.core.auth import init_firebase_app  # noqa: PLC0415
    from src.db.firestore import get_firestore_client  # noqa: PLC0415
    from src.domains.applications.firestore_repository import (  # noqa: PLC0415
        FirestoreApplicationRepository,
    )
    from src.domains.applications.service import fire_due_reminders  # noqa: PLC0415
    from src.domains.push.firestore_repository import (  # noqa: PLC0415
        FirestorePushRepository,
    )
    from src.domains.push.service import PushService  # noqa: PLC0415

    init_firebase_app()  # idempotent
    db = get_firestore_client()
    repo = FirestoreApplicationRepository(db)
    push = PushService(FirestorePushRepository(db))
    try:
        return await fire_due_reminders(repo, push)
    except Exception as exc:  # pragma: no cover - never let a tick crash the beat loop
        logger.error("application.reminder_sweep_failed", error=str(exc))
        return 0
