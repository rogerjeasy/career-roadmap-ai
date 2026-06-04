"""Unit tests for IntegrationsService status + authorize logic.

Settings, repository, Redis, and HTTP client are all mocked — no network, no
real OAuth credentials.
"""
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.exceptions import NotFoundError, ValidationError
from src.domains.integrations.service import IntegrationsService


def _settings(**creds: str | None) -> SimpleNamespace:
    """A minimal settings stub exposing only the fields providers read."""
    base = {
        "github_client_id": None,
        "github_client_secret": None,
        "linkedin_client_id": None,
        "linkedin_client_secret": None,
        "google_client_id": None,
        "google_client_secret": None,
        "oauth_callback_base_url": "http://localhost:8000",
    }
    base.update(creds)

    # ProviderSpec.client_secret expects a SecretStr-like object with get_secret_value.
    for key, value in list(base.items()):
        if key.endswith("_client_secret") and value is not None:
            base[key] = SimpleNamespace(get_secret_value=lambda v=value: v)
    return SimpleNamespace(**base)


@pytest.fixture
def repo() -> MagicMock:
    m = MagicMock()
    m.get = AsyncMock(return_value=None)
    m.doc_id = lambda user_id, provider: f"{user_id}:{provider}"
    return m


def _service(settings: SimpleNamespace, repo: MagicMock) -> IntegrationsService:
    return IntegrationsService(settings, repo, MagicMock(), MagicMock())  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_status_reports_availability_and_connection(repo: MagicMock) -> None:
    # GitHub configured + connected; LinkedIn/Calendar not configured.
    settings = _settings(github_client_id="id", github_client_secret="secret")
    repo.get = AsyncMock(
        side_effect=lambda doc_id, uid: (
            {
                "access_token": "enc",
                "account_label": "octocat",
                "connected_at": datetime.now(timezone.utc),
                "scopes": ["read:user"],
            }
            if doc_id == "u1:github"
            else None
        )
    )
    service = _service(settings, repo)

    statuses = {s.provider: s for s in await service.list_status("u1")}

    assert statuses["github"].available is True
    assert statuses["github"].connected is True
    assert statuses["github"].account_label == "octocat"
    assert statuses["linkedin"].available is False
    assert statuses["linkedin"].connected is False


@pytest.mark.asyncio
async def test_authorize_rejects_unconfigured_provider(repo: MagicMock) -> None:
    service = _service(_settings(), repo)
    with pytest.raises(ValidationError):
        await service.build_authorize_url("u1", "github")


@pytest.mark.asyncio
async def test_authorize_rejects_unknown_provider(repo: MagicMock) -> None:
    service = _service(_settings(), repo)
    with pytest.raises(NotFoundError):
        await service.build_authorize_url("u1", "nope")


@pytest.mark.asyncio
async def test_authorize_builds_url_and_stores_state(repo: MagicMock) -> None:
    settings = _settings(github_client_id="cid", github_client_secret="csecret")
    redis = MagicMock()
    redis.set = AsyncMock()
    service = IntegrationsService(settings, repo, redis, MagicMock())  # type: ignore[arg-type]

    url = await service.build_authorize_url("u1", "github")

    assert url.startswith("https://github.com/login/oauth/authorize")
    assert "client_id=cid" in url
    assert "redirect_uri=" in url
    redis.set.assert_awaited_once()  # CSRF state persisted
