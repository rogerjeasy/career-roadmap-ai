"""Structured JSON logging via structlog.

In production, logs are emitted as JSON on stdout — Promtail picks them up
and ships them to Loki. In dev, logs are pretty-printed for human reading.
"""
import logging
import sys

import structlog

from src.config import settings


def configure_logging() -> None:
    """Configure structlog with environment-aware processors."""
    log_level = getattr(logging, settings.log_level)

    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    if settings.environment == "development":
        renderers: list[structlog.types.Processor] = [
            structlog.dev.ConsoleRenderer(colors=True),
        ]
    else:
        renderers = [structlog.processors.JSONRenderer()]

    structlog.configure(
        processors=[*shared_processors, *renderers],
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=True,
    )

    # Quiet noisy third-party loggers
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Return a structlog logger bound to the given name."""
    return structlog.get_logger(name)