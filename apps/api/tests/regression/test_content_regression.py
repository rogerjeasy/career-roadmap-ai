"""Regression tests for the Content domain."""
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.exceptions import ValidationError
from src.domains.content.schemas import ContentDraftOut, ContentGenerateInput
from src.domains.content.service import ContentService

pytestmark = pytest.mark.regression


def _service(integrations, repo, llm):
    sessions = MagicMock()
    sessions.get = AsyncMock(return_value=None)
    roadmaps = MagicMock()
    roadmaps.list_for_user = AsyncMock(return_value=[])
    return ContentService(repo, llm, sessions, roadmaps, integrations)


async def test_publish_consent_gate_requires_access_token() -> None:
    # REGRESSION: an integration row WITHOUT an access_token must not count as
    # connected — publishing must stay blocked until real consent exists.
    integrations = MagicMock()
    integrations.doc_id = MagicMock(return_value="u1:linkedin")
    integrations.get = AsyncMock(return_value={"connected_at": "x"})  # no access_token
    repo = MagicMock()
    repo.get = AsyncMock(return_value={"id": "d1", "status": "approved"})
    with pytest.raises(ValidationError):
        await _service(integrations, repo, MagicMock()).set_status("u1", "d1", "published")


async def test_generated_hashtags_strip_leading_hash_and_cap_at_six() -> None:
    # REGRESSION: hashtags must be normalised (no leading '#') and limited to 6.
    llm = MagicMock()
    llm.complete_json = AsyncMock(return_value={
        "content": "Body", "hashtags": [f"#tag{i}" for i in range(10)],
    })
    repo = MagicMock()
    repo.create = AsyncMock(side_effect=lambda uid, doc: {"id": "d1", **doc})
    out = await _service(MagicMock(get=AsyncMock(return_value=None), doc_id=MagicMock(return_value="x")), repo, llm).generate(
        "u1", ContentGenerateInput(milestone="m")
    )
    assert len(out.hashtags) == 6
    assert all(not h.startswith("#") for h in out.hashtags)


def test_from_doc_unknown_enums_fall_back() -> None:
    out = ContentDraftOut.from_doc({"id": "d1", "kind": "tweet", "tone": "snarky", "status": "live"})
    assert out.kind == "linkedin_post"
    assert out.tone == "professional"
    assert out.status == "draft"
