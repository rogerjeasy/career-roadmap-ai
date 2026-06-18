"""Shared Anthropic JSON-completion helper for LLM-backed domain services.

Several domains (localisation, discovery, newsletter digests) ask Claude for a
structured JSON object and parse it. This module centralises the client setup
and the markdown-fence-tolerant JSON extraction so each service stays small and
they all behave identically. Inject a fake with an async ``complete_json`` in
tests to avoid network calls.
"""
from __future__ import annotations

import json
from typing import Any

import anthropic

from src.config import settings
from src.core.logging import get_logger

logger = get_logger(__name__)


def strip_json_fences(raw: str) -> str:
    """Strip markdown code fences / leading prose from a JSON LLM response."""
    raw = (raw or "").strip()
    if raw.startswith("```"):
        parts = raw.split("```", 2)
        body = parts[1] if len(parts) > 1 else ""
        if body.startswith("json"):
            body = body[4:]
        raw = body.rsplit("```", 1)[0].strip()
    return raw


class LlmJsonClient:
    """Thin async wrapper: ask Claude for JSON and return the parsed value."""

    def __init__(self, api_key: str | None = None, model: str | None = None) -> None:
        self._client = anthropic.AsyncAnthropic(
            api_key=api_key or settings.anthropic_api_key.get_secret_value()
        )
        self._model = model or settings.default_llm_model

    async def complete_json(
        self, *, system: str, user: str, max_tokens: int = 2048
    ) -> Any:
        """Return the parsed JSON value. Raises ``ValueError`` on unparseable output."""
        response = await self._client.messages.create(
            model=self._model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        raw = response.content[0].text if response.content else ""
        cleaned = strip_json_fences(raw)
        try:
            return json.loads(cleaned)
        except Exception as exc:  # noqa: BLE001 — normalise to ValueError for callers
            logger.warning("llm.json_parse_failed", error=str(exc), preview=cleaned[:200])
            raise ValueError("LLM did not return valid JSON") from exc


def get_llm_client() -> LlmJsonClient:
    """FastAPI-friendly factory for the shared JSON LLM client."""
    return LlmJsonClient()
