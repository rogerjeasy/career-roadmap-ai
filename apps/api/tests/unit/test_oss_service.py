"""Unit tests for OssService (GitHub search + bookmarks)."""
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from src.core.exceptions import ExternalServiceError, NotFoundError
from src.domains.oss.schemas import OssBookmarkCreate, OssIssue
from src.domains.oss.service import OssService

pytestmark = pytest.mark.unit


class _Resp:
    def __init__(self, status_code: int, payload: dict | None = None) -> None:
        self.status_code = status_code
        self._payload = payload or {}

    def json(self) -> dict:
        return self._payload


def _make_service(http: MagicMock, repo: MagicMock | None = None, skills=None) -> OssService:
    repo = repo or MagicMock()
    sessions = MagicMock()
    profile = MagicMock()
    profile.skills = skills or []
    session = MagicMock()
    session.user_profile_context = profile
    sessions.get = AsyncMock(return_value=session)
    return OssService(repo, http, sessions)


async def test_search_parses_and_filters_pull_requests() -> None:
    items = {
        "items": [
            {"id": 1, "title": "Fix bug", "html_url": "u", "repository_url": "https://api.github.com/repos/o/r", "comments": 5, "labels": [{"name": "good first issue"}]},
            {"id": 2, "title": "A PR", "pull_request": {}},  # must be filtered out
        ]
    }
    http = MagicMock()
    http.get = AsyncMock(return_value=_Resp(200, items))
    result = await _make_service(http).search("u1", "python", None)
    assert len(result.issues) == 1
    assert result.issues[0].issue_id == 1
    assert "python" in result.languages_used


async def test_search_rate_limited_returns_note_not_error() -> None:
    http = MagicMock()
    http.get = AsyncMock(return_value=_Resp(403))
    result = await _make_service(http).search("u1", "python", None)
    assert result.issues == []
    assert "rate limit" in result.note.lower()


async def test_search_server_error_raises_external() -> None:
    http = MagicMock()
    http.get = AsyncMock(return_value=_Resp(500))
    with pytest.raises(ExternalServiceError):
        await _make_service(http).search("u1", "python", None)


async def test_search_network_error_raises_external() -> None:
    http = MagicMock()
    http.get = AsyncMock(side_effect=httpx.ConnectError("boom"))
    with pytest.raises(ExternalServiceError):
        await _make_service(http).search("u1", "python", None)


def test_to_issue_skips_pull_requests() -> None:
    assert OssService._to_issue({"pull_request": {}}, [], []) is None


def test_to_issue_scores_skill_overlap_and_caps_at_100() -> None:
    issue = OssService._to_issue(
        {"id": 9, "title": "Improve python sql docs", "labels": []},
        skills=["python", "sql"], languages=["python"],
    )
    assert isinstance(issue, OssIssue)
    assert 0 < issue.match_score <= 100
    assert "python" in issue.match_reason.lower()


async def test_update_bookmark_missing_raises() -> None:
    repo = MagicMock()
    repo.update = AsyncMock(return_value=None)
    svc = _make_service(MagicMock(), repo)
    with pytest.raises(NotFoundError):
        await svc.update_bookmark_status("u1", "missing", "applied")


async def test_remove_bookmark_missing_raises() -> None:
    repo = MagicMock()
    repo.soft_delete = AsyncMock(return_value=False)
    svc = _make_service(MagicMock(), repo)
    with pytest.raises(NotFoundError):
        await svc.remove_bookmark("u1", "missing")


async def test_add_bookmark_returns_out() -> None:
    repo = MagicMock()
    repo.create = AsyncMock(side_effect=lambda uid, doc: {"id": "b1", **doc})
    svc = _make_service(MagicMock(), repo)
    out = await svc.add_bookmark("u1", OssBookmarkCreate(issue_id=1, title="t", url="u"))
    assert out.id == "b1"
    assert out.issue_id == 1
