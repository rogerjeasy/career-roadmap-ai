"""Sentry initialization with AI-aware integrations.

Sentry auto-instruments:
- FastAPI (errors, HTTP request transactions)
- SQLAlchemy queries
- Redis calls
- Anthropic calls (gen_ai.* spans, token counts, latency)
- LangChain / LangGraph orchestration

This gives us out-of-the-box AI observability for the agent layer.
"""
import sentry_sdk
from sentry_sdk.integrations.anthropic import AnthropicIntegration
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.langchain import LangchainIntegration
from sentry_sdk.integrations.redis import RedisIntegration
from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration
from sentry_sdk.integrations.starlette import StarletteIntegration

from src.config import settings


def setup_sentry() -> None:
    """Initialize Sentry SDK. No-op if SENTRY_DSN is not set."""
    if not settings.sentry_dsn:
        return

    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.environment,
        release=f"career-roadmap-api@{settings.app_name}",
        # Performance & AI tracing
        traces_sample_rate=settings.sentry_traces_sample_rate,
        # PII: only enable after privacy review — captures prompts & responses
        send_default_pii=settings.sentry_send_default_pii,
        integrations=[
            StarletteIntegration(transaction_style="endpoint"),
            FastApiIntegration(transaction_style="endpoint"),
            SqlalchemyIntegration(),
            RedisIntegration(),
            AnthropicIntegration(
                include_prompts=settings.sentry_send_default_pii,
            ),
            LangchainIntegration(
                include_prompts=settings.sentry_send_default_pii,
            ),
        ],
    )