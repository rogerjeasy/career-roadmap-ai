"""Regression tests for the Outreach domain."""
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.exceptions import ConflictError
from src.domains.outreach.schemas import OutreachDraftOut, OutreachEdit
from src.domains.outreach.service import OutreachService

pytestmark = pytest.mark.regression


def _service(repo) -> OutreachService:
    sessions = MagicMock()
    sessions.get = AsyncMock(return_value=None)
    return OutreachService(repo, MagicMock(), sessions)


async def test_editing_always_forces_re_review() -> None:
    # REGRESSION: any edit must reset status to "draft" so an approved/sent
    # message can never be silently altered and re-sent without re-approval.
    repo = MagicMock()
    repo.update = AsyncMock(side_effect=lambda did, uid, patch: {"id": did, "channel": "email", "tone": "warm", "goal": "g", **patch})
    out = await _service(repo).edit("u1", "d1", OutreachEdit(subject="new"))
    assert out.status == "draft"


async def test_sent_message_cannot_be_re_approved() -> None:
    # REGRESSION: the approval gate must reject re-approving an already-sent message.
    repo = MagicMock()
    repo.get = AsyncMock(return_value={"id": "d1", "status": "sent"})
    with pytest.raises(ConflictError):
        await _service(repo).approve("u1", "d1")


def test_from_doc_unknown_status_falls_back_to_draft() -> None:
    out = OutreachDraftOut.from_doc({"id": "d1", "status": "queued", "channel": "sms", "tone": "snarky"})
    assert out.status == "draft"
    assert out.channel == "email"
    assert out.tone == "warm"
