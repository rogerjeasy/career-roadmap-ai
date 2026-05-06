"""Structured logging for the agents package.

Style-identical to ``apps/api/src/core/logging.py`` but intentionally
separate — the agents package must not import from apps/api. Both sides
read the same environment variable (``LOG_LEVEL``) through their own
settings, producing consistent log formats across the whole system.
"""
import logging
import sys

import structlog

from agents.config import agent_settings


def configure_agent_logging() -> None:
    """Configure structlog for the agents worker process."""
    log_level = getattr(logging, agent_settings.log_level)

    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    renderers: list[structlog.types.Processor] = (
        [structlog.dev.ConsoleRenderer(colors=True)]
        if agent_settings.environment == "development"
        else [structlog.processors.JSONRenderer()]
    )

    structlog.configure(
        processors=[*shared_processors, *renderers],
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=True,
    )

    logging.getLogger("celery").setLevel(logging.WARNING)
    logging.getLogger("kombu").setLevel(logging.WARNING)


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)
