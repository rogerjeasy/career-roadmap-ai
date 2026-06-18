"""Unit tests for the CV-by-GitHub importer (handle parsing + profile render)."""
from __future__ import annotations

import httpx
import pytest

from src.domains.cv.github_import import (
    GithubImportError,
    _render_profile,
    build_profile_document,
    parse_handle,
)


# ── Handle parsing ──────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("octocat", "octocat"),
        ("@octocat", "octocat"),
        ("github.com/octocat", "octocat"),
        ("https://github.com/octocat", "octocat"),
        ("https://github.com/octocat/", "octocat"),
        ("https://www.github.com/octocat/some-repo", "octocat"),
        ("torvalds-1", "torvalds-1"),
    ],
)
def test_parse_handle_accepts(raw: str, expected: str) -> None:
    assert parse_handle(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "   ",
        "-leadinghyphen",
        "double--hyphen",
        "bad name with spaces",
        "https://gitlab.com/octocat",
        "https://github.com/",
    ],
)
def test_parse_handle_rejects(raw: str) -> None:
    with pytest.raises(GithubImportError):
        parse_handle(raw)


# ── Profile rendering ───────────────────────────────────────────────────────


def test_render_profile_includes_key_sections() -> None:
    user = {
        "login": "octocat",
        "name": "The Octocat",
        "bio": "Building things.",
        "company": "GitHub",
        "location": "Internet",
        "blog": "https://octocat.example",
        "public_repos": 8,
        "followers": 1234,
    }
    repos = [
        {"name": "rocket", "language": "Python", "stargazers_count": 50,
         "description": "A rocket", "topics": ["space", "ml"]},
        {"name": "boat", "language": "Go", "stargazers_count": 5, "description": None},
    ]
    text = _render_profile(user, repos)
    assert "The Octocat" in text
    assert "github.com/octocat" in text
    assert "SUMMARY" in text and "Building things." in text
    assert "SKILLS (from repository languages)" in text
    assert "Go" in text and "Python" in text
    assert "NOTABLE PROJECTS" in text
    assert "rocket" in text and "50★" in text


# ── End-to-end build with a mocked GitHub API ───────────────────────────────


def _mock_client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


@pytest.mark.asyncio
async def test_build_profile_document_happy_path() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/users/octocat":
            return httpx.Response(
                200,
                json={"login": "octocat", "name": "Octo", "public_repos": 2,
                      "followers": 9, "bio": "Hi"},
            )
        if request.url.path == "/users/octocat/repos":
            return httpx.Response(
                200,
                json=[
                    {"name": "a", "language": "Python", "stargazers_count": 3, "fork": False},
                    {"name": "forked", "language": "C", "stargazers_count": 99, "fork": True},
                ],
            )
        return httpx.Response(404)

    async with _mock_client(handler) as client:
        data, filename = await build_profile_document("octocat", client)

    assert filename == "octocat-github.txt"
    text = data.decode("utf-8")
    assert "Octo" in text
    # Forked repo is excluded despite higher stars.
    assert "forked" not in text
    assert "Python" in text and "C" not in text.split("SKILLS")[1].split("\n")[1]


@pytest.mark.asyncio
async def test_build_profile_document_unknown_user() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404)

    async with _mock_client(handler) as client:
        with pytest.raises(GithubImportError):
            await build_profile_document("ghost", client)


@pytest.mark.asyncio
async def test_build_profile_document_rate_limited() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, headers={"x-ratelimit-remaining": "0"}, json={})

    async with _mock_client(handler) as client:
        with pytest.raises(GithubImportError):
            await build_profile_document("octocat", client)
