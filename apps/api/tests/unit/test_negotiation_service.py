"""Unit tests for NegotiationService."""
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.exceptions import NotFoundError
from src.domains.negotiation.schemas import (
    OfferAnalysisOut,
    OfferInput,
    RoleplayInput,
    RoleplayMessage,
    RoleplayReply,
)
from src.domains.negotiation.service import NegotiationService

pytestmark = pytest.mark.unit


def _offer(**over) -> OfferInput:
    base = {"role": "Senior PM", "base_salary": 150000}
    base.update(over)
    return OfferInput(**base)


@pytest.fixture
def llm() -> MagicMock:
    m = MagicMock()
    m.complete_json = AsyncMock(return_value={
        "assessment": "Solid offer.",
        "competitiveness": "at",
        "benchmark_low": 140000, "benchmark_high": 170000,
        "counter_base": 165000, "counter_rationale": "Market midpoint.",
        "talking_points": ["impact"], "risks": ["rescind"], "assumptions": ["US base"],
        "confidence": 0.6,
    })
    return m


@pytest.fixture
def repo() -> MagicMock:
    r = MagicMock()
    r.create = AsyncMock(side_effect=lambda uid, doc: {"id": "o1", **doc})
    r.list_for_user = AsyncMock(return_value=[])
    r.get = AsyncMock(return_value=None)
    r.soft_delete = AsyncMock(return_value=True)
    return r


@pytest.fixture
def service(repo, llm) -> NegotiationService:
    sessions = MagicMock()
    sessions.get = AsyncMock(return_value=None)
    return NegotiationService(repo, llm, sessions)


async def test_analyze_persists_and_returns_analysis(service, repo) -> None:
    out = await service.analyze("u1", _offer())
    assert isinstance(out, OfferAnalysisOut)
    assert out.competitiveness == "at"
    assert out.counter_base == 165000
    repo.create.assert_awaited_once()


async def test_analyze_falls_back_on_llm_value_error(service, repo, llm) -> None:
    llm.complete_json = AsyncMock(side_effect=ValueError("bad"))
    out = await service.analyze("u1", _offer())
    assert out.competitiveness == "unknown"
    assert out.confidence == 0.0


async def test_get_missing_raises(service, repo) -> None:
    with pytest.raises(NotFoundError):
        await service.get("u1", "missing")


async def test_delete_missing_raises(service, repo) -> None:
    repo.soft_delete = AsyncMock(return_value=False)
    with pytest.raises(NotFoundError):
        await service.delete("u1", "missing")


async def test_roleplay_returns_reply_and_coaching(service, llm) -> None:
    llm.complete_json = AsyncMock(return_value={"reply": "We can't move", "coaching": "Anchor higher", "tip": "Cite data"})
    out = await service.roleplay("u1", RoleplayInput(offer=_offer(), message="I'd like 180k", history=[RoleplayMessage(role="user", content="hi")]))
    assert isinstance(out, RoleplayReply)
    assert out.reply == "We can't move"
    assert out.tip == "Cite data"


async def test_roleplay_falls_back_on_bad_llm(service, llm) -> None:
    llm.complete_json = AsyncMock(return_value="not a dict")
    out = await service.roleplay("u1", RoleplayInput(offer=_offer(), message="x"))
    assert out.reply  # safe default
