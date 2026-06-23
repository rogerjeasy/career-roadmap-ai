"""Integration tests for the Credentials controller."""
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from src.core.exceptions import NotFoundError
from src.domains.credentials.schemas import CredentialIssue, CredentialOut, CredentialVerification
from src.domains.credentials.service import get_credential_service
from src.domains.webhooks.service import get_webhook_service
from src.endpoints.v1.credentials_controller import router

pytestmark = pytest.mark.integration


def _cred(cid: str, skill: str, status: str = "active") -> CredentialOut:
    return CredentialOut(
        id=cid, skill=skill, level="intermediate", summary="", holder_name="Ada",
        evidence=[], status=status, signature="sig", share_token=f"tok-{cid}",
        verify_url=f"https://x/verify/tok-{cid}",
    )


class FakeCredentialService:
    def __init__(self) -> None:
        self.store: dict[str, CredentialOut] = {}
        self._seq = 0

    async def list(self, uid):
        return list(self.store.values())

    async def issue(self, uid, holder_name, payload: CredentialIssue):
        self._seq += 1
        cid = f"c{self._seq}"
        c = _cred(cid, payload.skill)
        self.store[cid] = c
        return c

    async def get(self, uid, credential_id):
        if credential_id not in self.store:
            raise NotFoundError("Credential not found.")
        return self.store[credential_id]

    async def revoke(self, uid, credential_id):
        if credential_id not in self.store:
            raise NotFoundError("Credential not found.")
        c = _cred(credential_id, self.store[credential_id].skill, status="revoked")
        self.store[credential_id] = c
        return c

    async def delete(self, uid, credential_id):
        if credential_id not in self.store:
            raise NotFoundError("Credential not found.")
        del self.store[credential_id]

    async def verify(self, share_token):
        return CredentialVerification(valid=True, status="active", reason="ok", skill="SQL")


@pytest.fixture
def client(make_app, user) -> TestClient:
    service = FakeCredentialService()
    webhooks = MagicMock()
    webhooks.dispatch = AsyncMock()
    app = make_app(
        router=router,
        overrides={get_credential_service: lambda: service, get_webhook_service: lambda: webhooks},
        case_conversion=True,
        current_user=user,
    )
    return TestClient(app, raise_server_exceptions=False)


def test_issue_then_get(client: TestClient) -> None:
    cid = client.post("/credentials", json={"skill": "SQL", "evidenceIds": ["e1"]}).json()["id"]
    got = client.get(f"/credentials/{cid}")
    assert got.status_code == 200
    assert got.json()["skill"] == "SQL"


def test_revoke_flips_status(client: TestClient) -> None:
    cid = client.post("/credentials", json={"skill": "SQL"}).json()["id"]
    resp = client.post(f"/credentials/{cid}/revoke")
    assert resp.json()["status"] == "revoked"


def test_public_verify_route_needs_no_auth(client: TestClient) -> None:
    # The literal "verify" segment must route to the public verifier, not /{id}.
    resp = client.get("/credentials/verify/sometoken")
    assert resp.status_code == 200
    assert resp.json()["valid"] is True


def test_delete_returns_204(client: TestClient) -> None:
    cid = client.post("/credentials", json={"skill": "SQL"}).json()["id"]
    assert client.delete(f"/credentials/{cid}").status_code == 204


def test_issue_rejects_blank_skill(client: TestClient) -> None:
    assert client.post("/credentials", json={"skill": ""}).status_code == 422
