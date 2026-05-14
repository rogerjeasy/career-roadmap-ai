"""Celery application instance — single source of truth for Celery config.

Both the agents package (task definitions) and apps/api (task dispatch)
share this instance by importing from here. Workers are started by pointing
Celery at ``agents.bus.celery_app:celery_app``.

Beat schedules (run with: celery -A agents.bus.celery_app beat):
  - Nightly at 02:00 UTC: refresh market reports and swiss/EU market docs
  - Weekly on Sunday at 03:00 UTC: full KB refresh (all document types)
"""
from celery import Celery
from celery.schedules import crontab

from agents.config import agent_settings

celery_app = Celery(
    "career_agents",
    broker=str(agent_settings.celery_broker_url),
    backend=str(agent_settings.celery_result_backend),
    # Tasks discovered at worker startup — not imported here to avoid
    # pulling the entire agent graph into every process that imports this module.
    include=[
        "agents.bus.tasks",
        "agents.bus.upload_tasks",
        "agents.rag.tasks.ingestion_tasks",
    ],
)

# Absolute paths to the seed data files used by Beat-scheduled ingestion.
# Override by setting KB_DATA_DIR env var before starting the beat process.
import os as _os  # noqa: E402
_KB_DIR = agent_settings.kb_data_dir or _os.path.join(
    _os.path.dirname(__file__), "..", "..", "..", "..", "data", "knowledge-base"
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
        "agents.ingestion": {
            "exchange": "agents",
            "routing_key": "agents.ingestion",
        },
        "agents.dead_letter": {
            "exchange": "agents",
            "routing_key": "agents.dead_letter",
        },
    },

    # ── Worker ───────────────────────────────────────────────
    # Prefetch=1 ensures fair dispatch for long-running agent tasks
    worker_prefetch_multiplier=1,
    # Recycle workers after N tasks to prevent memory leaks from large LLM payloads
    worker_max_tasks_per_child=50,

    # ── Beat schedule ─────────────────────────────────────────
    # Nightly: refresh the two most time-sensitive data sources (market data).
    # Weekly: full KB refresh covering all document types.
    beat_schedule={
        "nightly-market-reports-refresh": {
            "task": "rag.ingest_market_reports",
            "schedule": crontab(hour=2, minute=0),  # 02:00 UTC daily
            "args": [_os.path.join(_KB_DIR, "market_reports.json")],
            "options": {"queue": "agents.ingestion"},
        },
        "nightly-swiss-eu-market-refresh": {
            "task": "rag.ingest_swiss_eu_market",
            "schedule": crontab(hour=2, minute=15),  # 02:15 UTC daily
            "args": [_os.path.join(_KB_DIR, "swiss_eu_market.json")],
            "options": {"queue": "agents.ingestion"},
        },
        # Global market (Asia, LATAM, Africa, MENA, Oceania) — all industries.
        # Runs weekly on Sunday at 02:30 UTC alongside the nightly refreshes
        # so fresh fetch-script output is indexed before the weekly KB cycle.
        "weekly-global-market-refresh": {
            "task": "rag.ingest_global_market",
            "schedule": crontab(hour=2, minute=30, day_of_week=0),  # Sunday 02:30 UTC
            "args": [_os.path.join(_KB_DIR, "global_market.json")],
            "options": {"queue": "agents.ingestion"},
        },
        "weekly-career-kb-refresh": {
            "task": "rag.ingest_career_kb",
            "schedule": crontab(hour=3, minute=0, day_of_week=0),  # Sunday 03:00 UTC
            "args": [_os.path.join(_KB_DIR, "career_kb.json")],
            "options": {"queue": "agents.ingestion"},
        },
        "weekly-role-templates-refresh": {
            "task": "rag.ingest_role_templates",
            "schedule": crontab(hour=3, minute=20, day_of_week=0),  # Sunday 03:20 UTC
            "args": [_os.path.join(_KB_DIR, "role_templates.json")],
            "options": {"queue": "agents.ingestion"},
        },
        "weekly-esco-refresh": {
            "task": "rag.ingest_esco",
            "schedule": crontab(hour=3, minute=40, day_of_week=0),  # Sunday 03:40 UTC
            "args": [_os.path.join(_KB_DIR, "esco_sample.csv")],
            "options": {"queue": "agents.ingestion"},
        },
        # Re-fit BM25 encoder weekly after all KB data is refreshed.
        # Only meaningful when HYBRID_SEARCH_ENABLED=true.
        "weekly-bm25-encoder-fit": {
            "task": "rag.fit_bm25_encoder",
            "schedule": crontab(hour=4, minute=0, day_of_week=0),  # Sunday 04:00 UTC
            "args": [[
                _os.path.join(_KB_DIR, "career_kb.json"),
                _os.path.join(_KB_DIR, "market_reports.json"),
                _os.path.join(_KB_DIR, "role_templates.json"),
                _os.path.join(_KB_DIR, "swiss_eu_market.json"),
                _os.path.join(_KB_DIR, "global_market.json"),
                _os.path.join(_KB_DIR, "esco_sample.csv"),
            ]],
            "options": {"queue": "agents.ingestion"},
        },
        # Offline RAG quality eval — runs after BM25 refit so scores reflect
        # the freshest encoder.  Saturday 00:00 UTC gives a weekly snapshot
        # before Sunday's ingestion cycle begins.
        "weekly-rag-eval": {
            "task": "rag.run_eval",
            "schedule": crontab(hour=0, minute=0, day_of_week=6),  # Saturday 00:00 UTC
            "options": {"queue": "agents.ingestion"},
        },
        # Nightly cleanup: purge dead-letter queue items older than 7 days
        # and surface error summary to logs for ops review.
        "nightly-dead-letter-cleanup": {
            "task": "agents.bus.tasks.cleanup_dead_letter",
            "schedule": crontab(hour=1, minute=0),  # 01:00 UTC daily
            "options": {"queue": "agents.default"},
        },
    },
    beat_scheduler="celery.beat:PersistentScheduler",
    beat_schedule_filename="celerybeat-schedule",
)
