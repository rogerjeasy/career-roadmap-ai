"""Regression tests for the Career Twin domain."""
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.domains.career_twin.schemas import DailyCheckinOut, TwinPersonaOut
from src.domains.career_twin.service import CareerTwinService, _today

pytestmark = pytest.mark.regression


def test_persona_from_none_doc_uses_defaults() -> None:
    # REGRESSION: a user with no persona doc must get the default twin, not crash.
    p = TwinPersonaOut.from_doc(None)
    assert p.name == "Your Career Twin"
    assert p.voice == "supportive"


def test_persona_unknown_voice_falls_back() -> None:
    assert TwinPersonaOut.from_doc({"voice": "angry"}).voice == "supportive"


def test_checkin_unknown_status_falls_back_to_open() -> None:
    assert DailyCheckinOut.from_doc({"id": "ck1", "status": "??"}).status == "open"


async def test_today_is_idempotent_per_utc_date() -> None:
    # REGRESSION: today's check-in is created lazily ONCE per UTC date — a second
    # request the same day must return the existing one, never create a duplicate.
    persona_repo = MagicMock()
    persona_repo.get = AsyncMock(return_value={"name": "C", "voice": "direct"})
    checkin_repo = MagicMock()
    checkin_repo.list_for_user = AsyncMock(return_value=[{"id": "ck1", "date": _today(), "status": "open"}])
    checkin_repo.create = AsyncMock()
    sessions = MagicMock()
    sessions.get = AsyncMock(return_value=None)
    service = CareerTwinService(persona_repo, checkin_repo, MagicMock(), sessions)

    out = await service.today("u1")
    assert out.id == "ck1"
    checkin_repo.create.assert_not_called()
