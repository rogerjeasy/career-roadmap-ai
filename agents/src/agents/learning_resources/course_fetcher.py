"""CourseFetcher — concurrent MCP course catalog queries for skill gaps.

Calls ``course_catalog`` / ``course.search`` for every gap in the input list
concurrently via asyncio.gather. Failures for individual gaps are silently
degraded to an empty list so the pipeline can proceed with partial data.
"""
from __future__ import annotations

import asyncio
import time
from typing import Any

from agents.core.logging import get_logger
from agents.core.observability import LR_COURSE_FETCH_DURATION, LR_COURSE_FETCH_TOTAL
from agents.learning_resources.mcp_client import MCPClientProtocol

logger = get_logger(__name__)

_DEFAULT_LIMIT = 5   # courses returned per skill gap from MCP
_SKILL_DIMENSIONS = frozenset({"tech_skill", "certification"})


class CourseFetcher:
    """Fetch courses from the MCP course catalog for multiple skill gaps concurrently.

    Parameters
    ----------
    mcp_client:
        MCP client implementing MCPClientProtocol.
    limit_per_skill:
        Maximum courses to fetch per skill gap.
    """

    def __init__(
        self,
        mcp_client: MCPClientProtocol,
        *,
        limit_per_skill: int = _DEFAULT_LIMIT,
    ) -> None:
        self._client = mcp_client
        self._limit = limit_per_skill

    async def fetch(
        self,
        gaps: list[dict[str, Any]],
        *,
        max_cost_usd: float | None = None,
        correlation_id: str = "",
    ) -> dict[str, list[dict[str, Any]]]:
        """Fetch courses for all gaps concurrently.

        Only gaps with ``dimension`` in ``tech_skill`` or ``certification`` are
        searched — soft skills and portfolio gaps have no direct course match.

        Parameters
        ----------
        gaps:
            Serialised gap dicts from GapAgent (prioritised_gaps).
        max_cost_usd:
            Optional cost ceiling forwarded to the course catalog.
        correlation_id:
            Tracing token forwarded to all MCP calls.

        Returns
        -------
        dict mapping requirement_name → list[raw course dict]
        """
        searchable = [
            g for g in gaps if g.get("dimension", "tech_skill") in _SKILL_DIMENSIONS
        ]

        if not searchable:
            logger.info(
                "course_fetcher.no_searchable_gaps",
                total_gaps=len(gaps),
                correlation_id=correlation_id,
            )
            # Return empty buckets for all gaps so downstream sees every gap name
            return {g["requirement_name"]: [] for g in gaps}

        tasks = {
            gap["requirement_name"]: self._fetch_one(gap, max_cost_usd, correlation_id)
            for gap in searchable
        }
        settled = await asyncio.gather(*tasks.values(), return_exceptions=True)

        output: dict[str, list[dict[str, Any]]] = {g["requirement_name"]: [] for g in gaps}
        for skill, result in zip(tasks.keys(), settled):
            if isinstance(result, Exception):
                logger.warning(
                    "course_fetcher.single_fetch_failed",
                    skill=skill,
                    error=str(result),
                    correlation_id=correlation_id,
                )
            else:
                output[skill] = result  # type: ignore[assignment]

        return output

    # ── Private helpers ────────────────────────────────────────────────────

    async def _fetch_one(
        self,
        gap: dict[str, Any],
        max_cost_usd: float | None,
        correlation_id: str,
    ) -> list[dict[str, Any]]:
        skill = gap["requirement_name"]
        level = _infer_search_level(gap)
        params: dict[str, Any] = {
            "skill": skill,
            "level": level,
            "limit": self._limit,
        }

        t0 = time.monotonic()
        try:
            result = await self._client.call(
                "course_catalog",
                "search_courses",
                params,
                correlation_id=correlation_id,
            )
            LR_COURSE_FETCH_TOTAL.labels(status="success").inc()
        except Exception:
            LR_COURSE_FETCH_TOTAL.labels(status="error").inc()
            raise
        finally:
            LR_COURSE_FETCH_DURATION.observe(time.monotonic() - t0)

        return result.get("courses", [])


# ── Helpers ───────────────────────────────────────────────────────────────────


def _infer_search_level(gap: dict[str, Any]) -> str:
    """Derive an appropriate course level from the gap's current level + severity."""
    current = (gap.get("current_level") or "").lower()
    severity = gap.get("severity", "high")

    if current in ("advanced", "expert"):
        return "advanced"
    if current == "intermediate":
        return "advanced" if severity in ("medium", "low") else "intermediate"
    if current == "beginner":
        return "intermediate"

    # No current level — infer from severity
    return "beginner" if severity == "critical" else "intermediate"
