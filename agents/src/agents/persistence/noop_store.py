"""No-op roadmap store — used when persistence is disabled or in unit tests."""
from typing import Any

from agents.contracts.results import OrchestratorResult
from agents.core.logging import get_logger

logger = get_logger(__name__)


class NoOpRoadmapStore:
    """Satisfies IRoadmapStore but writes nothing."""

    async def create_skeleton(self, user_id: str, session_id: str, request_id: str) -> str:
        logger.debug("roadmap.skeleton_skipped", user_id=user_id, reason="persistence disabled")
        return ""

    async def persist_agent_output(
        self,
        roadmap_id: str,
        agent_type: str,
        output: dict[str, Any],
    ) -> None:
        logger.debug("roadmap.agent_persist_skipped", agent_type=agent_type, reason="persistence disabled")

    async def finalize(self, roadmap_id: str, result: OrchestratorResult) -> None:
        logger.debug(
            "roadmap.finalize_skipped",
            user_id=result.user_id,
            session_id=result.session_id,
            reason="persistence disabled",
        )
