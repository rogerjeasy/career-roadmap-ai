"""Integration tests for the Outreach controller (approval gate)."""
import pytest
from fastapi.testclient import TestClient

from src.core.exceptions import ConflictError, NotFoundError
from src.domains.outreach.schemas import OutreachDraftOut, OutreachDraftRequest, OutreachEdit
from src.domains.outreach.service import get_outreach_service
from src.endpoints.v1.outreach_controller import router

pytestmark = pytest.mark.integration


class FakeOutreachService:
    def __init__(self) -> None:
        self.store: dict[str, dict] = {}
        self._seq = 0

    def _out(self, d) -> OutreachDraftOut:
        return OutreachDraftOut(
            id=d["id"], recipient_name="", recipient_role="", channel="email", tone="warm",
            goal=d.get("goal", ""), subject=d.get("subject", ""), body=d.get("body", ""),
            status=d["status"],
        )

    async def list(self, uid):
        return [self._out(d) for d in self.store.values()]

    async def draft(self, uid, req: OutreachDraftRequest):
        self._seq += 1
        did = f"d{self._seq}"
        self.store[did] = {"id": did, "goal": req.goal, "subject": "S", "body": "B", "status": "draft"}
        return self._out(self.store[did])

    async def edit(self, uid, draft_id, payload: OutreachEdit):
        if draft_id not in self.store:
            raise NotFoundError("Draft not found.")
        self.store[draft_id].update(payload.to_patch())
        self.store[draft_id]["status"] = "draft"
        return self._out(self.store[draft_id])

    async def approve(self, uid, draft_id):
        d = self.store.get(draft_id)
        if d is None:
            raise NotFoundError("Draft not found.")
        if d["status"] == "sent":
            raise ConflictError("Already sent.")
        d["status"] = "approved"
        return self._out(d)

    async def mark_sent(self, uid, draft_id):
        d = self.store.get(draft_id)
        if d is None:
            raise NotFoundError("Draft not found.")
        if d["status"] != "approved":
            raise ConflictError("Approve first.")
        d["status"] = "sent"
        return self._out(d)

    async def delete(self, uid, draft_id):
        if draft_id not in self.store:
            raise NotFoundError("Draft not found.")
        del self.store[draft_id]


@pytest.fixture
def client(make_app, user) -> TestClient:
    service = FakeOutreachService()
    app = make_app(
        router=router,
        overrides={get_outreach_service: lambda: service},
        case_conversion=True,
        current_user=user,
    )
    return TestClient(app, raise_server_exceptions=False)


def test_full_approval_gate_flow(client: TestClient) -> None:
    did = client.post("/outreach/draft", json={"goal": "reconnect"}).json()["id"]
    # Cannot send before approval.
    assert client.post(f"/outreach/{did}/sent").status_code == 409
    assert client.post(f"/outreach/{did}/approve").json()["status"] == "approved"
    assert client.post(f"/outreach/{did}/sent").json()["status"] == "sent"


def test_edit_reverts_approved_to_draft(client: TestClient) -> None:
    did = client.post("/outreach/draft", json={"goal": "g"}).json()["id"]
    client.post(f"/outreach/{did}/approve")
    edited = client.patch(f"/outreach/{did}", json={"body": "changed"})
    assert edited.json()["status"] == "draft"  # re-review required


def test_draft_requires_goal(client: TestClient) -> None:
    assert client.post("/outreach/draft", json={"goal": ""}).status_code == 422


def test_delete_missing_returns_404(client: TestClient) -> None:
    assert client.delete("/outreach/nope").status_code == 404
