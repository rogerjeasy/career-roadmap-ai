"""Roadmap domain — repository interface.

Defined as a ``typing.Protocol`` (structural subtyping) so any class that
exposes the right async methods satisfies the contract without inheriting from
it.  This makes test doubles trivial: a plain ``MagicMock`` with the right
``AsyncMock`` attributes is a valid repository — no patching of imports needed.
"""
from datetime import datetime
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

    async def get_progress(
        self, roadmap_id: str, user_id: str
    ) -> tuple[list[str], datetime | None]:
        """Return (completed milestone keys, last-updated timestamp) for a user."""
        ...

    async def set_progress(
        self, roadmap_id: str, user_id: str, completed: list[str]
    ) -> datetime:
        """Persist the completed milestone keys; return the write timestamp."""
        ...

    async def update_phase(
        self, roadmap_id: str, user_id: str, phase_id: str, updates: dict
    ) -> bool:
        """Patch allowed fields on one phase; False if roadmap/phase not found."""
        ...

    async def add_phase(
        self, roadmap_id: str, user_id: str, phase_data: dict
    ) -> str | None:
        """Append a new phase; return its id, or None if the roadmap is not found."""
        ...

    async def delete_phase(self, roadmap_id: str, user_id: str, phase_id: str) -> bool:
        """Remove a phase; False if roadmap/phase not found."""
        ...

    async def reorder_phases(
        self, roadmap_id: str, user_id: str, ordered_ids: list[str]
    ) -> bool:
        """Reassign phase order from the given id sequence; False if not found."""
        ...
