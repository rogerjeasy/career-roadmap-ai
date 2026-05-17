"""Write-only persistence contract for incremental roadmap persistence.

The three-method protocol replaces the old single ``save()`` call so that
each specialist agent can persist its contribution as soon as it finishes,
rather than waiting for the entire pipeline to complete.

Flow:
  1. ``create_skeleton``   — called by the orchestrator before dispatching agents;
                             creates a placeholder document (status="processing").
  2. ``persist_agent_output`` — called after each agent completes; routes to the
                             agent-specific writer (phases, market data, etc.).
  3. ``finalize``          — called once after validation; writes summary,
                             confidence, next_steps and flips status to "completed".
"""
from typing import Any, Protocol

from agents.contracts.results import OrchestratorResult


class IRoadmapStore(Protocol):
    """Incremental persistence contract for roadmap documents."""

    async def create_skeleton(
        self,
        user_id: str,
        session_id: str,
        request_id: str,
    ) -> str:
        """Create a placeholder roadmap document and return its ID."""
        ...

    async def persist_agent_output(
        self,
        roadmap_id: str,
        agent_type: str,
        output: dict[str, Any],
    ) -> None:
        """Persist one agent's contribution to the roadmap document."""
        ...

    async def finalize(
        self,
        roadmap_id: str,
        result: OrchestratorResult,
    ) -> None:
        """Write synthesized summary, next_steps, and mark status=completed."""
        ...
