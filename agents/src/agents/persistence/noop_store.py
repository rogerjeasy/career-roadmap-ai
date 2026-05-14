"""No-op roadmap store — used when persistence is disabled or in unit tests."""
from agents.contracts.results import OrchestratorResult
from agents.core.logging import get_logger

logger = get_logger(__name__)


class NoOpRoadmapStore:
    """Satisfies IRoadmapStore but writes nothing.

    Drop this in as the injected store in tests or when
    ``FIRESTORE_PERSISTENCE_ENABLED=false`` in the environment.
    """

    async def save(self, result: OrchestratorResult) -> str:
        logger.debug(
            "roadmap.persist_skipped",
            user_id=result.user_id,
            session_id=result.session_id,
            reason="persistence disabled",
        )
        return ""
