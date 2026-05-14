"""Roadmap domain — repository interface.

Defined as a ``typing.Protocol`` (structural subtyping) so any class that
exposes the right async methods satisfies the contract without inheriting from
it.  This makes test doubles trivial: a plain ``MagicMock`` with the right
``AsyncMock`` attributes is a valid repository — no patching of imports needed.
"""
from typing import Protocol

from src.domains.roadmap.schemas import RoadmapDocument, RoadmapSummary


class IRoadmapRepository(Protocol):
    """Storage contract for the roadmap domain.

    Concrete implementations: ``FirestoreRoadmapRepository`` (production),
    any ``AsyncMock``-backed object (tests).
    """

    async def save(self, doc: RoadmapDocument) -> str:
        """Persist a full roadmap including all subcollections; return the document id."""
        ...

    async def get(self, roadmap_id: str, user_id: str) -> RoadmapDocument | None:
        """Return the full roadmap with phases, habits, and next steps, or None."""
        ...

    async def list_for_user(
        self,
        user_id: str,
        limit: int = 20,
        include_deleted: bool = False,
    ) -> list[RoadmapSummary]:
        """Return lightweight summaries for a user, newest first."""
        ...

    async def soft_delete(self, roadmap_id: str, user_id: str) -> None:
        """Set ``deleted_at``; raises ``PermissionError`` if the caller is not the owner."""
        ...
