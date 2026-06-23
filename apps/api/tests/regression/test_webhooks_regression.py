"""Regression tests for the Webhooks domain."""
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.domains.webhooks.schemas import WebhookOut
from src.domains.webhooks.service import WebhookService

pytestmark = pytest.mark.regression


def test_list_out_model_never_exposes_full_secret() -> None:
    # REGRESSION: the signing secret is shown ONCE at creation; the list/read model
    # must expose only a prefix, never the full secret.
    assert "secret" not in WebhookOut.model_fields
    out = WebhookOut.from_doc({"id": "w1", "secret": "whsec_supersecretvalue"})
    assert out.secret_prefix == "whsec_supers"
    assert "supersecretvalue" not in out.secret_prefix


async def test_dispatch_never_raises_into_caller() -> None:
    # REGRESSION: dispatch is fired from request handlers (e.g. content.published).
    # A bad/unreachable webhook URL must not bubble an exception into that request.
    import httpx

    repo = MagicMock()
    repo.list_for_user = AsyncMock(return_value=[
        {"id": "a", "url": "https://dead", "secret": "s", "active": True, "events": ["*"]},
    ])
    repo.update = AsyncMock()
    http = MagicMock()
    http.post = AsyncMock(side_effect=httpx.ConnectError("down"))
    service = WebhookService(repo, http)
    # Should complete without raising.
    await service.dispatch("u1", "content.published", {"x": 1})
