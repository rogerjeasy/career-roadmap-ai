"""Integration tests for the Books controller.

Exercises the real router (routing, request validation, ``response_model``
serialisation, status codes) with the BookService dependency replaced by an
in-memory fake and the auth dependency overridden to a fixed user. Combined with
case conversion so the camelCase wire contract is verified too.
"""
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from src.domains.books.schemas import BookCreate, BookOut, BookUpdate
from src.domains.books.service import get_book_service
from src.endpoints.v1.books_controller import router as books_router
from src.core.exceptions import NotFoundError

pytestmark = pytest.mark.integration

NOW = datetime(2026, 6, 23, tzinfo=timezone.utc)


class FakeBookService:
    """Minimal in-memory stand-in matching the BookService surface used by the controller."""

    def __init__(self) -> None:
        self._store: dict[str, dict] = {}
        self._seq = 0

    async def list(self, uid: str, *, limit: int = 100) -> list[BookOut]:
        items = [BookOut.from_doc(d) for d in self._store.values() if d["user_id"] == uid]
        return items[:limit]

    async def create(self, uid: str, body: BookCreate) -> BookOut:
        self._seq += 1
        bid = f"b{self._seq}"
        doc = {"id": bid, "user_id": uid, "created_at": NOW, **body.model_dump()}
        self._store[bid] = doc
        return BookOut.from_doc(doc)

    async def get(self, uid: str, book_id: str) -> BookOut:
        doc = self._store.get(book_id)
        if not doc or doc["user_id"] != uid:
            raise NotFoundError("book not found")
        return BookOut.from_doc(doc)

    async def update(self, uid: str, book_id: str, body: BookUpdate) -> BookOut:
        doc = self._store.get(book_id)
        if not doc or doc["user_id"] != uid:
            raise NotFoundError("book not found")
        doc.update(body.to_patch())
        return BookOut.from_doc(doc)

    async def delete(self, uid: str, book_id: str) -> None:
        self._store.pop(book_id, None)


@pytest.fixture
def client(make_app, user) -> TestClient:
    service = FakeBookService()
    app = make_app(
        router=books_router,
        overrides={get_book_service: lambda: service},
        case_conversion=True,
        current_user=user,
    )
    return TestClient(app, raise_server_exceptions=False)


def test_create_then_get_roundtrip(client: TestClient) -> None:
    resp = client.post("/books", json={"title": "Deep Work", "author": "Cal Newport"})
    assert resp.status_code == 201
    body = resp.json()
    assert body["title"] == "Deep Work"
    assert body["status"] == "queued"  # default
    assert "createdAt" in body  # camelCased by middleware
    book_id = body["id"]

    got = client.get(f"/books/{book_id}")
    assert got.status_code == 200
    assert got.json()["author"] == "Cal Newport"


def test_list_returns_created_books(client: TestClient) -> None:
    client.post("/books", json={"title": "A"})
    client.post("/books", json={"title": "B"})
    resp = client.get("/books")
    assert resp.status_code == 200
    assert {b["title"] for b in resp.json()} == {"A", "B"}


def test_update_changes_status(client: TestClient) -> None:
    created = client.post("/books", json={"title": "X"}).json()
    resp = client.patch(f"/books/{created['id']}", json={"status": "done"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "done"


def test_get_missing_book_returns_404(client: TestClient) -> None:
    resp = client.get("/books/does-not-exist")
    assert resp.status_code == 404
    assert resp.json()["errorCode"] == "not_found"


def test_delete_returns_204(client: TestClient) -> None:
    created = client.post("/books", json={"title": "Y"}).json()
    resp = client.delete(f"/books/{created['id']}")
    assert resp.status_code == 204


def test_create_rejects_blank_title(client: TestClient) -> None:
    resp = client.post("/books", json={"title": ""})
    assert resp.status_code == 422  # FastAPI request validation (min_length=1)


def test_list_limit_is_validated(client: TestClient) -> None:
    resp = client.get("/books", params={"limit": 999})  # le=200
    assert resp.status_code == 422
