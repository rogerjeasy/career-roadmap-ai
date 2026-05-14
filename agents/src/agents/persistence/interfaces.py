"""Write-only persistence contract for completed orchestration results.

Using ``typing.Protocol`` (structural subtyping) means any class that exposes
``async def save(...)`` satisfies the interface without inheriting from it.
This makes mock objects in tests trivial — no patching or wrapping needed.
"""
from typing import Protocol

from agents.contracts.results import OrchestratorResult


class IRoadmapStore(Protocol):
    """Persist a completed roadmap to durable storage and return its new ID."""

    async def save(self, result: OrchestratorResult) -> str:
        ...
