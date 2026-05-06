"""Celery application instance — single source of truth for Celery config.

Both the agents package (task definitions) and apps/api (task dispatch)
share this instance by importing from here. Workers are started by pointing
Celery at ``agents.bus.celery_app:celery_app``.
"""
from celery import Celery

from agents.config import agent_settings

celery_app = Celery(
    "career_agents",
    broker=str(agent_settings.celery_broker_url),
    backend=str(agent_settings.celery_result_backend),
    # Tasks discovered at worker startup — not imported here to avoid
    # pulling the entire agent graph into every process that imports this module.
    include=["agents.bus.tasks"],
)

celery_app.conf.update(
    # ── Serialization ────────────────────────────────────────
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],

    # ── Reliability ──────────────────────────────────────────
    task_acks_late=True,           # acknowledge only after task completes
    task_reject_on_worker_lost=True,  # re-queue on unexpected worker death
    task_track_started=True,

    # ── Timeouts ─────────────────────────────────────────────
    task_soft_time_limit=agent_settings.agent_task_timeout_seconds,
    task_time_limit=agent_settings.agent_task_timeout_seconds + 30,

    # ── Results ──────────────────────────────────────────────
    result_expires=3600,

    # ── Routing ──────────────────────────────────────────────
    task_default_queue="agents.default",
    task_queues={
        "agents.default": {
            "exchange": "agents",
            "routing_key": "agents.default",
        },
        "agents.priority": {
            "exchange": "agents",
            "routing_key": "agents.priority",
        },
    },

    # ── Worker ───────────────────────────────────────────────
    # Prefetch=1 ensures fair dispatch for long-running agent tasks
    worker_prefetch_multiplier=1,
    # Recycle workers after N tasks to prevent memory leaks from large LLM payloads
    worker_max_tasks_per_child=50,
)
