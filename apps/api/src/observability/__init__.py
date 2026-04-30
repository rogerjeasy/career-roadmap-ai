"""Observability bootstrap — call once at app startup."""
from src.observability.metrics import setup_prometheus
from src.observability.sentry import setup_sentry
from src.observability.tracing import setup_tracing

__all__ = ["setup_sentry", "setup_prometheus", "setup_tracing"]