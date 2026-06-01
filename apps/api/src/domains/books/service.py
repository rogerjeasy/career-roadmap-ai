"""Books domain — service layer."""
from __future__ import annotations

from fastapi import Depends
from google.cloud.firestore_v1.async_client import AsyncClient

from src.core.exceptions import NotFoundError
from src.core.logging import get_logger
from src.db.firestore import get_firestore_client
from src.domains.books.firestore_repository import FirestoreBookRepository
from src.domains.books.schemas import BookCreate, BookOut, BookUpdate

logger = get_logger(__name__)


class BookService:
    def __init__(self, repo: FirestoreBookRepository) -> None:
        self._repo = repo

    async def list(self, user_id: str, limit: int = 100) -> list[BookOut]:
        docs = await self._repo.list_for_user(user_id, limit=limit)
        return [BookOut.from_doc(d) for d in docs]

    async def get(self, user_id: str, book_id: str) -> BookOut:
        doc = await self._repo.get(book_id, user_id)
        if doc is None:
            raise NotFoundError(f"Book '{book_id}' not found")
        return BookOut.from_doc(doc)

    async def create(self, user_id: str, payload: BookCreate) -> BookOut:
        doc = await self._repo.create(user_id, payload.model_dump())
        return BookOut.from_doc(doc)

    async def update(self, user_id: str, book_id: str, payload: BookUpdate) -> BookOut:
        doc = await self._repo.update(book_id, user_id, payload.to_patch())
        if doc is None:
            raise NotFoundError(f"Book '{book_id}' not found")
        return BookOut.from_doc(doc)

    async def delete(self, user_id: str, book_id: str) -> None:
        deleted = await self._repo.hard_delete(book_id, user_id)
        if not deleted:
            raise NotFoundError(f"Book '{book_id}' not found")


async def get_book_service(
    db: AsyncClient = Depends(get_firestore_client),
) -> BookService:
    return BookService(FirestoreBookRepository(db))
