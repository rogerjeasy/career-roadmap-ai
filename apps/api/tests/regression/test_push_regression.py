"""Regression tests for the Push domain."""
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.domains.push.service import PushService

pytestmark = pytest.mark.regression


async def test_send_never_raises_when_push_unconfigured() -> None:
    # REGRESSION: nudges from other domains call send_to_user opportunistically.
    # With push unconfigured it must degrade to a no-op result, never raise — or
    # it would break the calling flow (e.g. an application reminder sweep).
    repo = MagicMock()
    repo.list_for_user = AsyncMock(return_value=[])
    service = PushService(repo)
    result = await service.send_to_user("u1", title="t", body="b", url="/x")
    assert result.enabled is False
    assert result.sent == 0 and result.failed == 0
    # Must not even attempt to read subscriptions when disabled.
    repo.list_for_user.assert_not_called()
