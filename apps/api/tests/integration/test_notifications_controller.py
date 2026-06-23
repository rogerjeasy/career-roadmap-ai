"""Integration tests for the Notifications controller."""
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from src.core.exceptions import NotFoundError
from src.domains.notifications.schemas import NotificationCreate, NotificationOut
from src.domains.notifications.service import get_notification_service
from src.endpoints.v1.notification_controller import router

pytestmark = pytest.mark.integration

NOW = datetime(2026, 6, 23, tzinfo=timezone.utc)


class FakeNotificationService:
    def __init__(self) -> None:
        self.store: dict[str, dict] = {}
        self._seq = 0

    async def list(self, uid, limit=30):
        return [NotificationOut.from_doc(d) for d in self.store.values()][:limit]

    async def unread_count(self, uid):
        return sum(1 for d in self.store.values() if not d["read"])

    async def create(self, uid, payload: NotificationCreate):
        self._seq += 1
        nid = f"n{self._seq}"
        self.store[nid] = {"id": nid, "created_at": NOW, "read": False, **payload.model_dump()}
        return NotificationOut.from_doc(self.store[nid])

    async def mark_read(self, uid, notification_id):
        if notification_id not in self.store:
            raise NotFoundError("not found")
        self.store[notification_id]["read"] = True
        return NotificationOut.from_doc(self.store[notification_id])

    async def mark_all_read(self, uid):
        n = 0
        for d in self.store.values():
            if not d["read"]:
                d["read"] = True
                n += 1
        return n

    async def delete(self, uid, notification_id):
        if notification_id not in self.store:
            raise NotFoundError("not found")
        del self.store[notification_id]


@pytest.fixture
def client(make_app, user) -> TestClient:
    service = FakeNotificationService()
    app = make_app(
        router=router,
        overrides={get_notification_service: lambda: service},
        case_conversion=True,
        current_user=user,
    )
    return TestClient(app, raise_server_exceptions=False)


def test_list_returns_items_and_unread_count(client: TestClient) -> None:
    client.post("/notifications", json={"title": "One"})
    resp = client.get("/notifications")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["items"]) == 1
    assert body["unreadCount"] == 1


def test_mark_read_and_read_all(client: TestClient) -> None:
    nid = client.post("/notifications", json={"title": "One"}).json()["id"]
    assert client.patch(f"/notifications/{nid}/read").json()["read"] is True
    client.post("/notifications", json={"title": "Two"})
    assert client.post("/notifications/read-all").json()["updated"] == 1


def test_mark_read_missing_returns_404(client: TestClient) -> None:
    assert client.patch("/notifications/nope/read").status_code == 404


def test_delete_returns_204(client: TestClient) -> None:
    nid = client.post("/notifications", json={"title": "One"}).json()["id"]
    assert client.delete(f"/notifications/{nid}").status_code == 204


def test_create_rejects_blank_title(client: TestClient) -> None:
    assert client.post("/notifications", json={"title": ""}).status_code == 422
