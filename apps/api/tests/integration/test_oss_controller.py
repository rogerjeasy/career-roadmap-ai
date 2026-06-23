"""Integration tests for the OSS controller."""
import pytest
from fastapi.testclient import TestClient

from src.core.exceptions import NotFoundError
from src.domains.oss.schemas import OssBookmarkCreate, OssBookmarkOut, OssSearchResult
from src.domains.oss.service import get_oss_service
from src.endpoints.v1.oss_controller import router

pytestmark = pytest.mark.integration


class FakeOssService:
    def __init__(self) -> None:
        self.store: dict[str, dict] = {}
        self._seq = 0

    async def search(self, uid, language, query):
        return OssSearchResult(issues=[], languages_used=[language] if language else [], query_used="q", note="")

    async def list_bookmarks(self, uid):
        return [OssBookmarkOut.from_doc(d) for d in self.store.values()]

    async def add_bookmark(self, uid, payload: OssBookmarkCreate):
        self._seq += 1
        bid = f"b{self._seq}"
        self.store[bid] = {"id": bid, **payload.model_dump()}
        return OssBookmarkOut.from_doc(self.store[bid])

    async def update_bookmark_status(self, uid, bookmark_id, status):
        if bookmark_id not in self.store:
            raise NotFoundError("Bookmark not found.")
        self.store[bookmark_id]["status"] = status
        return OssBookmarkOut.from_doc(self.store[bookmark_id])

    async def remove_bookmark(self, uid, bookmark_id):
        if bookmark_id not in self.store:
            raise NotFoundError("Bookmark not found.")
        del self.store[bookmark_id]


@pytest.fixture
def client(make_app, user) -> TestClient:
    service = FakeOssService()
    app = make_app(
        router=router,
        overrides={get_oss_service: lambda: service},
        case_conversion=True,
        current_user=user,
    )
    return TestClient(app, raise_server_exceptions=False)


def test_search_issues(client: TestClient) -> None:
    resp = client.get("/oss/issues", params={"language": "python"})
    assert resp.status_code == 200
    assert resp.json()["languagesUsed"] == ["python"]


def test_bookmark_crud_flow(client: TestClient) -> None:
    created = client.post("/oss/bookmarks", json={"issueId": 1, "title": "t", "url": "https://x/i"})
    assert created.status_code == 201
    bid = created.json()["id"]
    upd = client.patch(f"/oss/bookmarks/{bid}", json={"status": "applied"})
    assert upd.status_code == 200
    assert upd.json()["status"] == "applied"
    assert client.delete(f"/oss/bookmarks/{bid}").status_code == 204


def test_update_missing_returns_404(client: TestClient) -> None:
    assert client.patch("/oss/bookmarks/nope", json={"status": "applied"}).status_code == 404


def test_add_bookmark_rejects_blank_title(client: TestClient) -> None:
    assert client.post("/oss/bookmarks", json={"issueId": 1, "title": "", "url": "u"}).status_code == 422
