"""Abstract base class for all knowledge-base document loaders."""
from __future__ import annotations

import abc
from collections.abc import AsyncGenerator

from agents.rag.models import Document


class BaseLoader(abc.ABC):
    """All loaders implement ``load()`` as an async generator of Documents."""

    @abc.abstractmethod
    async def load(self) -> AsyncGenerator[Document, None]:
        """Yield Document objects one at a time."""
        raise NotImplementedError
        yield  # type: ignore[misc]
