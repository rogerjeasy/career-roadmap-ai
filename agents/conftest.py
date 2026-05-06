"""Root conftest — sets required env vars before any agents module is imported.

AgentSettings validates at module-load time. Without these stubs, pytest
collection fails because ANTHROPIC_API_KEY, REDIS_URL, etc. are missing.
"""
import os

os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")
os.environ.setdefault("CELERY_BROKER_URL", "redis://localhost:6379/0")
os.environ.setdefault("CELERY_RESULT_BACKEND", "redis://localhost:6379/1")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/2")
