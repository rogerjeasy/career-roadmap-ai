"""Integration tests for the Newsletter controller."""
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from src.domains.newsletter.schemas import NewsletterDigest, NewsletterPrefsOut, NewsletterPrefsUpdate
from src.domains.newsletter.service import get_newsletter_service
from src.domains.push.service import get_push_service
from src.domains.webhooks.service import get_webhook_service
from src.endpoints.v1.newsletter_controller import router

pytestmark = pytest.mark.integration


class FakeNewsletterService:
    def __init__(self) -> None:
        self.prefs = NewsletterPrefsOut.defaults()
        self.digest = NewsletterDigest.empty()

    async def get(self, uid):
        return self.prefs

    async def update(self, uid, payload: NewsletterPrefsUpdate):
        self.prefs = NewsletterPrefsOut(subscribed=payload.subscribed, frequency=payload.frequency, topics=payload.topics)
        return self.prefs

    async def get_digest(self, uid):
        return self.digest

    async def generate_digest(self, uid):
        self.digest = NewsletterDigest(period_label="This week", summary="News", action_item="Do it", has_data=True)
        return self.digest


@pytest.fixture
def client(make_app, user) -> TestClient:
    service = FakeNewsletterService()
    webhooks = MagicMock(); webhooks.dispatch = AsyncMock()
    push = MagicMock(); push.send_to_user = AsyncMock()
    app = make_app(
        router=router,
        overrides={
            get_newsletter_service: lambda: service,
            get_webhook_service: lambda: webhooks,
            get_push_service: lambda: push,
        },
        case_conversion=True,
        current_user=user,
    )
    return TestClient(app, raise_server_exceptions=False)


def test_get_and_update_prefs(client: TestClient) -> None:
    assert client.get("/newsletter").json()["subscribed"] is False
    up = client.put("/newsletter", json={"subscribed": True, "frequency": "monthly"})
    assert up.status_code == 200
    assert up.json()["frequency"] == "monthly"


def test_digest_generate_get_and_deliver(client: TestClient) -> None:
    assert client.get("/newsletter/digest").json()["hasData"] is False
    gen = client.post("/newsletter/digest/generate")
    assert gen.json()["hasData"] is True
    # deliver reuses webhooks + push (runs in background); just verify it returns the digest
    delivered = client.post("/newsletter/digest/deliver")
    assert delivered.status_code == 200
    assert delivered.json()["summary"] == "News"


def test_update_rejects_bad_frequency(client: TestClient) -> None:
    assert client.put("/newsletter", json={"subscribed": True, "frequency": "yearly"}).status_code == 422
