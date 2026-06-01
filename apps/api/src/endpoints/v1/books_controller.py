"""Books — CRUD for the user's curated reading list.

Routes:
  GET    /api/v1/books          — list reading list (newest-first)
  POST   /api/v1/books          — add a book
  GET    /api/v1/books/{id}     — get one
  PATCH  /api/v1/books/{id}     — update one
  DELETE /api/v1/books/{id}     — remove one
"""
from fastapi import APIRouter, Depends, Query, status

from src.core.auth import AuthenticatedUser, get_current_user
from src.domains.books.schemas import BookCreate, BookOut, BookUpdate
from src.domains.books.service import BookService, get_book_service

router = APIRouter(prefix="/books", tags=["books"])


@router.get("", response_model=list[BookOut], summary="List reading list")
async def list_books(
    limit: int = Query(default=100, ge=1, le=200),
    user: AuthenticatedUser = Depends(get_current_user),
    service: BookService = Depends(get_book_service),
) -> list[BookOut]:
    return await service.list(user.uid, limit=limit)


@router.post(
    "",
    response_model=BookOut,
    status_code=status.HTTP_201_CREATED,
    summary="Add a book",
)
async def create_book(
    body: BookCreate,
    user: AuthenticatedUser = Depends(get_current_user),
    service: BookService = Depends(get_book_service),
) -> BookOut:
    return await service.create(user.uid, body)


@router.get("/{book_id}", response_model=BookOut, summary="Get a book")
async def get_book(
    book_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
    service: BookService = Depends(get_book_service),
) -> BookOut:
    return await service.get(user.uid, book_id)


@router.patch("/{book_id}", response_model=BookOut, summary="Update a book")
async def update_book(
    book_id: str,
    body: BookUpdate,
    user: AuthenticatedUser = Depends(get_current_user),
    service: BookService = Depends(get_book_service),
) -> BookOut:
    return await service.update(user.uid, book_id, body)


@router.delete(
    "/{book_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove a book",
)
async def delete_book(
    book_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
    service: BookService = Depends(get_book_service),
) -> None:
    await service.delete(user.uid, book_id)
